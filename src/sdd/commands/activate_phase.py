"""ActivatePhaseCommand + ActivatePhaseHandler — Spec_v15 §2 BC-4, Phase_v15.5 §3–§7.

Invariants: I-ACT-1, I-HANDLER-BATCH-PURE-1, I-PHASE-EMIT-1, I-PHASE-EVENT-PAIR-1
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from sdd.commands._base import CommandHandlerBase
from sdd.core.errors import InvalidActor, SDDError
from sdd.core.events import DomainEvent, PhaseInitializedEvent, PhaseStartedEvent, classify_event_level
from sdd.infra.paths import event_store_file


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ActivatePhaseCommand:
    command_id: str
    command_type: str
    payload: Mapping[str, Any]
    phase_id: int
    actor: str
    tasks_total: int  # passed from CLI --tasks N; handler is pure (I-HANDLER-BATCH-PURE-1)

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
        )
        return [phase_started, phase_init]


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2) — routes through execute_and_project (Bug-A fix)
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="activate-phase")
    parser.add_argument("phase_id", type=int)
    parser.add_argument("--actor", default="human")
    parser.add_argument("--tasks", type=int, default=0, help="Total tasks in phase TaskSet")
    parser.add_argument("--db", default=None)
    parsed = parser.parse_args(args)
    db = parsed.db or str(event_store_file())
    try:
        from sdd.commands.registry import REGISTRY, execute_and_project
        cmd = ActivatePhaseCommand(
            command_id=str(uuid.uuid4()),
            command_type="ActivatePhaseCommand",
            payload={},
            phase_id=parsed.phase_id,
            actor=parsed.actor,
            tasks_total=parsed.tasks,
        )
        execute_and_project(REGISTRY["activate-phase"], cmd, db_path=db)
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
