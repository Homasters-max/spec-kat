"""ActivatePhaseCommand + ActivatePhaseHandler — Spec_v15 §2 BC-4, Phase_v15.5 §3–§7.

Invariants: I-ACT-1, I-HANDLER-BATCH-PURE-1, I-PHASE-EMIT-1, I-PHASE-EVENT-PAIR-1,
            I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from sdd.commands._base import CommandHandlerBase
from sdd.core.errors import Inconsistency, InvalidActor, MissingContext, SDDError
from sdd.core.events import DomainEvent, PhaseInitializedEvent, PhaseStartedEvent, classify_event_level
from sdd.domain.tasks.parser import parse_taskset
from sdd.infra.paths import event_store_file, plan_file, taskset_file


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_plan_hash(phase_id: int) -> str:
    """Read Plan_vN.md and return sha256[:16] — I-SESSION-PLAN-HASH-1.

    Raises MissingContext if the plan file is absent.
    Called at CLI level to keep handler pure (I-HANDLER-BATCH-PURE-1).
    """
    path = plan_file(phase_id)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MissingContext(
            f"Plan_v{phase_id}.md not found at {path} (I-SESSION-PLAN-HASH-1)"
        ) from exc
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _resolve_tasks_total(phase_id: int, tasks_arg: int | None) -> int:
    """Single validation point for tasks_total before PhaseInitialized is emitted.

    I-PHASE-INIT-2: tasks_total MUST be consistent with TaskSet at activation time.
    I-PHASE-INIT-3: tasks_total MUST be > 0.

    Raises:
        MissingContext: TaskSet absent or contains no tasks.
        Inconsistency: tasks_arg provided but doesn't match actual TaskSet size.
    Returns:
        int > 0
    """
    path = taskset_file(phase_id)
    tasks = parse_taskset(str(path))
    actual = len(tasks)
    if actual <= 0:
        raise MissingContext(f"TaskSet_v{phase_id}.md exists but contains no tasks (I-PHASE-INIT-3)")
    if tasks_arg is None:
        return actual
    if tasks_arg != actual:
        raise Inconsistency(
            f"--tasks {tasks_arg} does not match TaskSet_v{phase_id}.md count={actual} (I-PHASE-INIT-2)"
        )
    return actual


@dataclass(frozen=True)
class ActivatePhaseCommand:
    command_id: str
    command_type: str
    payload: Mapping[str, Any]
    phase_id: int
    actor: str
    tasks_total: int  # passed from CLI --tasks N; handler is pure (I-HANDLER-BATCH-PURE-1)
    plan_hash: str = ""       # sha256(Plan_vN.md)[:16]; "" when --executed-by absent
    executed_by: str = ""     # I-SESSION-ACTOR-1: caller identity; "" when absent

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class ActivatePhaseHandler(CommandHandlerBase):
    """Emit [PhaseStarted, PhaseInitialized] atomic pair for phase activation.

    Pure handler (I-HANDLER-BATCH-PURE-1, A-14): no I/O, no EventStore calls, no replay.
    Actor constraint: command.actor MUST be "human" (I-ACT-1).
    Idempotency enforced at kernel level via command_id UNIQUE constraint — NOT via
    _check_idempotent() (Amendment A-14, I-HANDLER-BATCH-PURE-1).
    AlreadyActivated guard: handled by guard pipeline before handle() is called.
    """

    def handle(self, command: ActivatePhaseCommand) -> list[DomainEvent]:
        if command.actor != "human":
            raise InvalidActor(
                f"ActivatePhaseCommand requires actor='human', got {command.actor!r}"
            )

        now_iso = _utc_now_iso()
        now_ms = int(time.time() * 1000)

        phase_started = PhaseStartedEvent(
            event_type="PhaseStarted",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("PhaseStarted"),
            event_source="runtime",
            caused_by_meta_seq=None,
            phase_id=command.phase_id,
            actor=command.actor,
        )
        phase_init = PhaseInitializedEvent(
            event_type="PhaseInitialized",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("PhaseInitialized"),
            event_source="runtime",
            caused_by_meta_seq=None,
            phase_id=command.phase_id,
            tasks_total=command.tasks_total,
            plan_version=command.phase_id,
            actor=command.actor,
            timestamp=now_iso,
            plan_hash=command.plan_hash,
            executed_by=command.executed_by,
        )
        return [phase_started, phase_init]


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2) — routes through execute_and_project (Bug-A fix)
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None) -> int:
    import warnings

    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="activate-phase")
    parser.add_argument("phase_id", type=int)
    parser.add_argument("--actor", default="human")
    parser.add_argument("--tasks", type=int, default=None, help="[DEPRECATED] Total tasks; auto-detected from TaskSet")
    parser.add_argument("--executed-by", default=None, dest="executed_by",
                        help="Record caller identity in PhaseInitialized payload (I-SESSION-ACTOR-1)")
    parser.add_argument("--db", default=None)
    parsed = parser.parse_args(args)
    db = parsed.db or str(event_store_file())
    if parsed.tasks is not None:
        warnings.warn(
            "--tasks is deprecated; tasks_total is now auto-detected from TaskSet",
            DeprecationWarning,
            stacklevel=2,
        )
    try:
        from sdd.commands.registry import REGISTRY, execute_and_project
        tasks_total = _resolve_tasks_total(parsed.phase_id, parsed.tasks)
        plan_hash = _compute_plan_hash(parsed.phase_id) if parsed.executed_by else ""
        executed_by = parsed.executed_by or ""
        cmd = ActivatePhaseCommand(
            command_id=str(uuid.uuid4()),
            command_type="ActivatePhaseCommand",
            payload={"phase_id": parsed.phase_id, "tasks_total": tasks_total,
                     "executed_by": executed_by, "plan_hash": plan_hash},
            phase_id=parsed.phase_id,
            actor=parsed.actor,
            tasks_total=tasks_total,
            plan_hash=plan_hash,
            executed_by=executed_by,
        )
        execute_and_project(REGISTRY["activate-phase"], cmd, db_path=db)
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
