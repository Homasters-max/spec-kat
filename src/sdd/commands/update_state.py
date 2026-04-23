"""CompleteTaskHandler, ValidateTaskHandler, SyncStateHandler, CheckDoDHandler — Spec_v9 §2.

Invariants: I-CMD-ENV-1, I-CMD-1, I-CMD-4, I-CMD-8, I-ES-2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import DoDNotMet, InvalidState, MissingContext, SDDError
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
from sdd.infra.event_store import EventStore
from sdd.infra.projections import rebuild_state, rebuild_taskset, sync_projections

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
    """Mark a task DONE in TaskSet_vN.md and emit TaskImplementedEvent + MetricRecorded.

    Emit-first protocol: EventStore.append is called atomically BEFORE
    rebuild_taskset so the EventLog is always the source of truth (I-ES-1,
    I-ES-2, I-CMD-4).  A crash between append and rebuild leaves the EventLog
    correct; the projection is rebuilt on the next run (I-ES-5).

    Idempotent on command_id and semantic key (I-CMD-1, I-CMD-2b).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: Any) -> list[DomainEvent]:
        p = _unpack_payload("CompleteTask", command.payload)

        tasks = parse_taskset(p.taskset_path)
        task = next((t for t in tasks if t.task_id == p.task_id), None)

        if task is None:
            raise MissingContext(
                f"Task {p.task_id!r} not found in {p.taskset_path!r}"
            )

        if task.status == "DONE":
            # Idempotent: task already DONE — re-sync projections and return empty (I-CMD-2b, §R.11, I-SYNC-1)
            sync_projections(self._db_path, p.taskset_path, p.state_path)
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

        events: list[DomainEvent] = [task_event, metric_event]

        # Emit-first: persist events atomically BEFORE any file mutation (I-ES-1, I-CMD-4)
        EventStore(self._db_path).append(events, source=__name__)

        # Rebuild both projections atomically AFTER the event is in EventLog (I-ES-4, I-SYNC-1)
        sync_projections(self._db_path, p.taskset_path, p.state_path)

        return events


# ---------------------------------------------------------------------------
# ValidateTaskHandler  (Spec_v4 §4.4, §6)
# Invariants: I-CMD-1, I-ES-2
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TaskValidatedWithCmd(TaskValidatedEvent):
    command_id: str


class ValidateTaskHandler(CommandHandlerBase):
    """Emit TaskValidatedEvent + MetricRecorded, then rebuild State_index.yaml.

    Emit-first: EventStore.append is called atomically BEFORE rebuild_state so
    the EventLog is always the source of truth (I-ES-1, I-ES-4).  A crash
    between append and rebuild leaves the EventLog correct; the projection is
    rebuilt on the next run (I-ES-5).

    Idempotent on command_id and semantic key (I-CMD-1, I-CMD-2b).
    """

    @error_event_boundary(source=__name__)
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

        events: list[DomainEvent] = [validated_event, metric_event]

        # Emit-first: persist events atomically BEFORE any file mutation (I-ES-1)
        EventStore(self._db_path).append(events, source=__name__)

        # Rebuild State_index.yaml as projection AFTER events are in EventLog (I-ES-4)
        rebuild_state(self._db_path, p.state_path)

        return events


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
    """Rebuild State_index.yaml from EventLog replay (Spec_v4 §4.5).

    Emit-first: StateSyncedEvent appended before rebuild_state so the EventLog
    is always the source of truth (I-ES-1, I-ES-4).  rebuild_state uses
    atomic_write internally (I-PK-5).  Idempotent on command_id and semantic
    key (I-CMD-1, I-CMD-8).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: Any) -> list[DomainEvent]:
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

        events: list[DomainEvent] = [synced_event]

        # Emit-first: persist event atomically BEFORE any file mutation (I-ES-1)
        EventStore(self._db_path).append(events, source=__name__)

        # Rebuild both projections atomically AFTER event is in EventLog (I-ES-4, I-CMD-8, I-SYNC-1)
        sync_projections(self._db_path, p.taskset_path, p.state_path)

        return events


# ---------------------------------------------------------------------------
# CheckDoDHandler  (Spec_v4 §4.6)
# Invariants: I-CMD-1, I-CMD-5, I-ES-2
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _PhaseCompletedWithCmd(PhaseCompletedEvent):
    command_id: str


class CheckDoDHandler(CommandHandlerBase):
    """Check Definition of Done: ALL tasks DONE + invariants PASS + tests PASS.

    Emits PhaseCompletedEvent + MetricRecorded(phase.completion_time) atomically.
    Raises DoDNotMet if any condition fails (I-CMD-5).
    No projection rebuild — PhaseCompleted is in _KNOWN_NO_HANDLER.
    Idempotent on command_id (I-CMD-1).
    """

    @error_event_boundary(source=__name__)
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

        events: list[DomainEvent] = [phase_event, metric_event]

        # Emit-first: persist events atomically BEFORE returning (I-ES-1, I-CMD-5)
        EventStore(self._db_path).append(events, source=__name__)

        return events


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = os.environ.get("SDD_DB_PATH", ".sdd/state/sdd_events.duckdb")
_DEFAULT_STATE_PATH = os.environ.get("SDD_STATE_PATH", ".sdd/runtime/State_index.yaml")


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
    p_comp.add_argument("--state", default=_DEFAULT_STATE_PATH)
    p_comp.add_argument("--db", default=_DEFAULT_DB_PATH)

    p_val = sub.add_parser("validate")
    p_val.add_argument("task_id", nargs="?")
    p_val.add_argument("--phase", type=int, default=None)
    p_val.add_argument("--result", choices=["PASS", "FAIL"], default=None)
    p_val.add_argument("--check-dod", action="store_true")
    p_val.add_argument("--taskset", default=None)
    p_val.add_argument("--state", default=_DEFAULT_STATE_PATH)
    p_val.add_argument("--db", default=_DEFAULT_DB_PATH)

    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--phase", type=int, default=None)
    p_sync.add_argument("--taskset", default=None)
    p_sync.add_argument("--state", default=_DEFAULT_STATE_PATH)
    p_sync.add_argument("--db", default=_DEFAULT_DB_PATH)

    parsed = parser.parse_args(args)
    try:
        phase_id = parsed.phase if parsed.phase is not None else _read_phase(parsed.state)
        taskset = parsed.taskset or f".sdd/tasks/TaskSet_v{phase_id}.md"

        if parsed.cmd == "complete":
            events = CompleteTaskHandler(parsed.db).handle(build_command(
                "CompleteTask",
                task_id=parsed.task_id,
                phase_id=phase_id,
                taskset_path=taskset,
                state_path=parsed.state,
            ))
            status = "noop" if not events else "done"
            print(json.dumps({"status": status, "task_id": parsed.task_id}))
        elif parsed.cmd == "validate":
            if parsed.check_dod:
                CheckDoDHandler(parsed.db).handle(build_command(
                    "CheckDoD",
                    phase_id=phase_id,
                    state_path=parsed.state,
                ))
            else:
                ValidateTaskHandler(parsed.db).handle(build_command(
                    "ValidateTask",
                    task_id=parsed.task_id,
                    phase_id=phase_id,
                    result=parsed.result,
                    check_dod=False,
                    taskset_path=taskset,
                    state_path=parsed.state,
                ))
        elif parsed.cmd == "sync":
            SyncStateHandler(parsed.db).handle(build_command(
                "SyncState",
                phase_id=phase_id,
                taskset_path=taskset,
                state_path=parsed.state,
            ))
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
