"""ActivatePhaseCommand + ActivatePhaseHandler — Spec_v5 §4.1, §4.2.

Invariants: I-ACT-1, I-CMD-1, I-DOMAIN-1
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

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import AlreadyActivated, InvalidActor, SDDError
from sdd.core.events import DomainEvent, PhaseActivatedEvent, classify_event_level
from sdd.domain.state.reducer import reduce
from sdd.infra.event_log import sdd_replay
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class ActivatePhaseHandler(CommandHandlerBase):
    """Transition phase_status PLANNED → ACTIVE by emitting PhaseActivatedEvent.

    Actor constraint: command.actor MUST be "human" (I-ACT-1).
    Guard: NormGuard must ALLOW actor="human", action="activate_phase".
    Idempotency:
      - command-level: based on command_id (I-CMD-1) — duplicate command_id → return []
      - domain rule: if phase_status already "ACTIVE" → raise AlreadyActivated (I-DOMAIN-1)
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ActivatePhaseCommand) -> list[DomainEvent]:
        if self._check_idempotent(command):
            return []

        if command.actor != "human":
            raise InvalidActor(
                f"ActivatePhaseCommand requires actor='human', got {command.actor!r}"
            )

        state = reduce(sdd_replay(db_path=self._db_path))
        if state.phase_status == "ACTIVE":
            raise AlreadyActivated(command.phase_id)

        event = PhaseActivatedEvent(
            event_type="PhaseActivated",
            event_id=str(uuid.uuid4()),
            appended_at=int(time.time() * 1000),
            level=classify_event_level("PhaseActivated"),
            event_source="runtime",
            caused_by_meta_seq=None,
            phase_id=command.phase_id,
            actor=command.actor,
            timestamp=_utc_now_iso(),
        )
        return [event]


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="activate-phase")
    parser.add_argument("phase_id", type=int)
    parser.add_argument("--actor", default="human")
    parser.add_argument("--db", default=None)
    parsed = parser.parse_args(args)
    db = parsed.db or str(event_store_file())
    try:
        from sdd.infra.event_store import EventStore
        cmd = ActivatePhaseCommand(
            command_id=str(uuid.uuid4()),
            command_type="ActivatePhaseCommand",
            payload={},
            phase_id=parsed.phase_id,
            actor=parsed.actor,
        )
        events = ActivatePhaseHandler(db).handle(cmd)
        if events:
            EventStore(db).append(events, source=__name__)
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
