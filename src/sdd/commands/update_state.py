"""CompleteTaskHandler, ValidateTaskHandler, SyncStateHandler, CheckDoDHandler — Spec_v9 §2.

Invariants: I-CMD-ENV-1, I-CMD-1, I-CMD-4, I-CMD-8, I-ES-2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import DependencyNotMet, DoDNotMet, InvalidState, MissingContext, SDDError
from sdd.core.events import (
    DomainEvent,
    PhaseCompletedEvent,
    TaskImplementedEvent,
    TaskValidatedEvent,
    classify_event_level,
)
from sdd.core.payloads import _unpack_payload, build_command
from sdd.domain.state.yaml_state import read_state
from sdd.domain.tasks.parser import parse_taskset
from sdd.infra.paths import event_store_file, state_file, taskset_file
from sdd.infra.projections import sync_projections

# ---------------------------------------------------------------------------
# Legacy command envelope shims (I-CMD-ENV-1)
# These are NOT Command subclasses — standalone dataclasses whose __post_init__
# auto-populates payload so handlers can use _unpack_payload uniformly.
# Names preserved for backward-compatible imports.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompleteTaskCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    task_id:      str
    phase_id:     int
    taskset_path: str
    state_path:   str

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "task_id":      self.task_id,
                "phase_id":     self.phase_id,
                "taskset_path": self.taskset_path,
                "state_path":   self.state_path,
            })


@dataclass(frozen=True)
class ValidateTaskCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    task_id:      str | None
    phase_id:     int
    result:       str | None
    taskset_path: str
    state_path:   str

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "task_id":      self.task_id,
                "phase_id":     self.phase_id,
                "result":       self.result,
                "check_dod":    False,
                "taskset_path": self.taskset_path,
                "state_path":   self.state_path,
            })


@dataclass(frozen=True)
class SyncStateCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    phase_id:     int
    taskset_path: str
    state_path:   str

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "phase_id":     self.phase_id,
                "taskset_path": self.taskset_path,
                "state_path":   self.state_path,
            })


@dataclass(frozen=True)
class CheckDoDCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    phase_id:     int
    state_path:   str

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "phase_id":   self.phase_id,
                "state_path": self.state_path,
            })


# ---------------------------------------------------------------------------
# Internal event payload types
# Extend canonical events with command_id so exists_command can detect
# duplicates (I-CMD-1).  These are internal to this module.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TaskImplementedWithCmd(TaskImplementedEvent):
    command_id: str


@dataclass(frozen=True)
class _MetricRecordedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "MetricRecorded"
    command_id: str
    metric_id:  str
    value:      float
    task_id:    str | None
    phase_id:   int | None


# ---------------------------------------------------------------------------
# CompleteTaskHandler
# ---------------------------------------------------------------------------

class CompleteTaskHandler(CommandHandlerBase):
    """Mark a task DONE: pure handler — returns [TaskImplemented, MetricRecorded] with no I/O.

    Caller (execute_and_project via REGISTRY["complete"]) is responsible for
    EventLog.append and projection rebuild (I-HANDLER-PURE-1, I-KERNEL-WRITE-1).
    Idempotent on task.status == "DONE" (I-CMD-2b, §R.11).
    """

    def __init__(self, db_path: str = "") -> None:
        super().__init__(db_path)

    def handle(self, command: Any) -> list[DomainEvent]:
        p = _unpack_payload("CompleteTask", command.payload)

        tasks = parse_taskset(p.taskset_path)
        task = next((t for t in tasks if t.task_id == p.task_id), None)

        if task is None:
            raise MissingContext(
                f"Task {p.task_id!r} not found in {p.taskset_path!r}"
            )

        if task.status == "DONE":
            return []

        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        task_event = _TaskImplementedWithCmd(
            event_type="TaskImplemented",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("TaskImplemented"),
            event_source="runtime",
            caused_by_meta_seq=None,
            task_id=p.task_id,
            phase_id=p.phase_id,
            timestamp=now_iso,
            command_id=command.command_id,
        )

        metric_event = _MetricRecordedEvent(
            event_type="MetricRecorded",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("MetricRecorded"),
            event_source="runtime",
            caused_by_meta_seq=None,
            command_id=command.command_id,
            metric_id="task.lead_time",
            value=0.0,
            task_id=p.task_id,
            phase_id=p.phase_id,
        )

        return [task_event, metric_event]


# ---------------------------------------------------------------------------
# ValidateTaskHandler  (Spec_v4 §4.4, §6)
# Invariants: I-CMD-1, I-ES-2
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TaskValidatedWithCmd(TaskValidatedEvent):
    command_id: str


class ValidateTaskHandler(CommandHandlerBase):
    """Pure handler: return [TaskValidated, MetricRecorded] with no I/O.

    Caller (execute_and_project via REGISTRY["validate"]) is responsible for
    EventLog.append and projection rebuild (I-HANDLER-PURE-1, I-KERNEL-WRITE-1).
    Idempotent on command_id and semantic key (I-CMD-1, I-CMD-2b).
    """

    def handle(self, command: Any) -> list[DomainEvent]:
        p = _unpack_payload("ValidateTask", command.payload)

        if p.result not in ("PASS", "FAIL"):
            raise InvalidState(
                f"Invalid result {p.result!r}: must be 'PASS' or 'FAIL'"
            )

        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        validated_event = _TaskValidatedWithCmd(
            event_type="TaskValidated",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("TaskValidated"),
            event_source="runtime",
            caused_by_meta_seq=None,
            task_id=p.task_id,
            phase_id=p.phase_id,
            result=p.result,
            timestamp=now_iso,
            command_id=command.command_id,
        )

        metric_event = _MetricRecordedEvent(
            event_type="MetricRecorded",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("MetricRecorded"),
            event_source="runtime",
            caused_by_meta_seq=None,
            command_id=command.command_id,
            metric_id="task.validation_attempts",
            value=1.0,
            task_id=p.task_id,
            phase_id=p.phase_id,
        )

        return [validated_event, metric_event]


# ---------------------------------------------------------------------------
# SyncStateHandler  (Spec_v4 §4.5)
# Invariants: I-CMD-1, I-CMD-8, I-ES-2
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _StateSyncedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "StateSynced"
    command_id: str
    phase_id:   int
    timestamp:  str


class SyncStateHandler(CommandHandlerBase):
    """Pure handler: returns [StateSynced] with no I/O (I-HANDLER-PURE-1, I-KERNEL-WRITE-1).

    Superseded by NoOpHandler in REGISTRY["sync-state"]; retained for backward compat.
    Caller (execute_and_project) is responsible for EventLog.append and projection rebuild.
    """

    def handle(self, command: Any) -> list[DomainEvent]:
        if self._check_idempotent(command):
            return []

        p = _unpack_payload("SyncState", command.payload)

        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        synced_event = _StateSyncedEvent(
            event_type="StateSynced",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("StateSynced"),
            event_source="runtime",
            caused_by_meta_seq=None,
            command_id=command.command_id,
            phase_id=p.phase_id,
            timestamp=now_iso,
        )

        return [synced_event]


# ---------------------------------------------------------------------------
# CheckDoDHandler  (Spec_v4 §4.6)
# Invariants: I-CMD-1, I-CMD-5, I-ES-2
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _PhaseCompletedWithCmd(PhaseCompletedEvent):
    command_id: str


class CheckDoDHandler(CommandHandlerBase):
    """Check Definition of Done: ALL tasks DONE + invariants PASS + tests PASS.

    Pure handler: returns [PhaseCompleted, MetricRecorded] with no I/O.
    Caller (execute_and_project via REGISTRY["check-dod"]) is responsible for
    EventLog.append and projection rebuild (I-HANDLER-PURE-1, I-KERNEL-WRITE-1).
    Raises DoDNotMet if any condition fails (I-CMD-5).
    Idempotent on command_id (I-CMD-1).
    """

    def handle(self, command: Any) -> list[DomainEvent]:
        p = _unpack_payload("CheckDoD", command.payload)

        state = read_state(p.state_path)

        if state.tasks_completed != state.tasks_total:
            raise DoDNotMet(
                f"not all tasks DONE: {state.tasks_completed}/{state.tasks_total}"
            )
        if state.invariants_status != "PASS":
            raise DoDNotMet("invariants not PASS")
        if state.tests_status != "PASS":
            raise DoDNotMet("tests not PASS")

        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        phase_event = _PhaseCompletedWithCmd(
            event_type="PhaseCompleted",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("PhaseCompleted"),
            event_source="runtime",
            caused_by_meta_seq=None,
            phase_id=p.phase_id,
            total_tasks=state.tasks_total,
            timestamp=now_iso,
            command_id=command.command_id,
        )

        metric_event = _MetricRecordedEvent(
            event_type="MetricRecorded",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("MetricRecorded"),
            event_source="runtime",
            caused_by_meta_seq=None,
            command_id=command.command_id,
            metric_id="phase.completion_time",
            value=0.0,
            task_id=None,
            phase_id=p.phase_id,
        )

        return [phase_event, metric_event]


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------



def _read_phase(state_path: str) -> int:
    from pathlib import Path

    import yaml
    return yaml.safe_load(Path(state_path).read_text(encoding="utf-8"))["phase"]["current"]


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="update-state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_comp = sub.add_parser("complete")
    p_comp.add_argument("task_id")
    p_comp.add_argument("--phase", type=int, default=None)
    p_comp.add_argument("--taskset", default=None)
    p_comp.add_argument("--state", default=str(state_file()))
    p_comp.add_argument("--db", default=str(event_store_file()))

    p_val = sub.add_parser("validate")
    p_val.add_argument("task_id", nargs="?")
    p_val.add_argument("--phase", type=int, default=None)
    p_val.add_argument("--result", choices=["PASS", "FAIL"], default=None)
    p_val.add_argument("--check-dod", action="store_true")
    p_val.add_argument("--taskset", default=None)
    p_val.add_argument("--state", default=str(state_file()))
    p_val.add_argument("--db", default=str(event_store_file()))

    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--phase", type=int, default=None)
    p_sync.add_argument("--taskset", default=None)
    p_sync.add_argument("--state", default=str(state_file()))
    p_sync.add_argument("--db", default=str(event_store_file()))

    parsed = parser.parse_args(args)
    try:
        phase_id = parsed.phase if parsed.phase is not None else _read_phase(parsed.state)
        taskset = parsed.taskset or str(taskset_file(phase_id))

        if parsed.cmd == "complete":
            # Noop fast-path: task already DONE — idempotent, bypass kernel guards (I-CMD-2b)
            _all_tasks = parse_taskset(taskset)
            _task_obj = next((t for t in _all_tasks if t.task_id == parsed.task_id), None)
            if _task_obj is not None and _task_obj.status == "DONE":
                print(json.dumps({"status": "noop", "task_id": parsed.task_id}))
                return 0
            # I-BOOTSTRAP-2: bootstrap tasks are PRE-RESOLVED — skip event emission permanently
            from sdd.infra.bootstrap_manifest import contains as _bootstrap_contains
            if _bootstrap_contains(parsed.task_id):
                print(json.dumps({"status": "noop", "task_id": parsed.task_id, "reason": "bootstrap_pre_resolved"}))
                return 0
            # Guard-lite: check dependencies before Write Kernel (BC-32-6, I-CMD-IDEM-2)
            from sdd.commands.complete import _check_deps
            from sdd.domain.guards.context import load_dag as _load_dag
            _done_ids = frozenset(t.task_id for t in _all_tasks if t.status == "DONE")
            _check_deps(parsed.task_id, _done_ids, _load_dag(taskset))
            # Route through Write Kernel (I-SPEC-EXEC-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1)
            from sdd.commands.registry import REGISTRY, execute_and_project
            events = execute_and_project(
                REGISTRY["complete"],
                build_command(
                    "CompleteTask",
                    task_id=parsed.task_id,
                    phase_id=phase_id,
                    taskset_path=taskset,
                    state_path=parsed.state,
                ),
                db_path=parsed.db,
                state_path=parsed.state,
                taskset_path=taskset,
            )
            status = "noop" if not events else "done"
            print(json.dumps({"status": status, "task_id": parsed.task_id}))
        elif parsed.cmd == "validate":
            if parsed.check_dod:
                from sdd.commands.registry import REGISTRY, execute_and_project
                execute_and_project(
                    REGISTRY["check-dod"],
                    build_command(
                        "CheckDoD",
                        phase_id=phase_id,
                        state_path=parsed.state,
                    ),
                    db_path=parsed.db,
                    state_path=parsed.state,
                )
            else:
                from sdd.commands.registry import REGISTRY, execute_and_project
                execute_and_project(
                    REGISTRY["validate"],
                    build_command(
                        "ValidateTask",
                        task_id=parsed.task_id,
                        phase_id=phase_id,
                        result=parsed.result,
                        check_dod=False,
                        taskset_path=taskset,
                        state_path=parsed.state,
                    ),
                    db_path=parsed.db,
                    state_path=parsed.state,
                    taskset_path=taskset,
                )
        elif parsed.cmd == "sync":
            from sdd.commands.registry import REGISTRY, execute_and_project
            execute_and_project(
                REGISTRY["sync-state"],
                build_command("SyncState", phase_id=phase_id, taskset_path=taskset, state_path=parsed.state),
                db_path=parsed.db,
                state_path=parsed.state,
                taskset_path=taskset,
            )
        return 0
    except DependencyNotMet:
        raise  # propagate to cli.py for JSON stderr output (BC-32-6)
    except SDDError:
        return 1
    except Exception:
        return 2
