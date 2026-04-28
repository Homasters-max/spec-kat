"""InvalidateEventHandler — BC-WG-5 (Spec_v28 §2).

Invariants: I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from typing import ClassVar

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import InvariantViolationError
from sdd.core.events import DomainEvent, EventLevel
from sdd.core.types import Command
from sdd.infra.db import open_sdd_connection

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventInvalidatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "EventInvalidated"
    target_seq:           int   # seq of the neutralized event
    reason:               str   # ≤200 chars
    invalidated_by_phase: int   # phase_current at emission time (audit)


@dataclass(frozen=True)
class InvalidateEventCommand:
    command_id:   str
    command_type: str
    payload:      dict
    target_seq:   int
    reason:       str
    phase_id:     int


class InvalidateEventHandler(CommandHandlerBase):
    """Emits EventInvalidated to neutralize an invalid EventLog entry (BC-WG-5)."""

    @error_event_boundary(source=__name__)
    def handle(self, cmd: Command) -> list[DomainEvent]:  # type: ignore[override]
        _cmd = cmd  # type: ignore[assignment]
        conn = open_sdd_connection(self._db_path)
        try:
            row = conn.execute(
                "SELECT event_type FROM events WHERE seq = ?", [_cmd.target_seq]
            ).fetchone()
            existing = conn.execute(
                "SELECT 1 FROM events WHERE event_type = 'EventInvalidated' "
                "AND CAST(payload->>'target_seq' AS INTEGER) = ?",
                [_cmd.target_seq],
            ).fetchone()
        finally:
            conn.close()

        # I-INVALID-1: target_seq must exist in EventLog
        if row is None:
            raise InvariantViolationError(
                f"I-INVALID-1: seq={_cmd.target_seq} not found in EventLog"
            )
        target_type: str = row[0]

        # I-INVALID-3: cannot invalidate EventInvalidated (no recursion)
        if target_type == "EventInvalidated":
            raise InvariantViolationError(
                "I-INVALID-3: cannot invalidate an EventInvalidated event"
            )

        # I-INVALID-4: cannot invalidate state-mutating events
        from sdd.domain.state.reducer import EventReducer
        if target_type in EventReducer._EVENT_SCHEMA:
            raise InvariantViolationError(
                f"I-INVALID-4: cannot invalidate state-mutating event "
                f"(type={target_type!r} is in EventReducer._EVENT_SCHEMA)"
            )

        # I-INVALID-IDEM-1: already-invalidated target → noop
        if existing:
            _log.info("invalidate-event: seq=%d already invalidated, noop", _cmd.target_seq)
            return []

        return [EventInvalidatedEvent(
            event_type="EventInvalidated",
            event_id=str(uuid.uuid4()),
            appended_at=int(time.time() * 1000),
            level=EventLevel.L1,
            event_source="runtime",
            caused_by_meta_seq=None,
            target_seq=_cmd.target_seq,
            reason=_cmd.reason[:200],
            invalidated_by_phase=_cmd.phase_id,
        )]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdd invalidate-event")
    parser.add_argument("--seq", type=int, required=True, help="Target event seq to invalidate")
    parser.add_argument("--reason", required=True, help="Reason for invalidation (≤200 chars)")
    parser.add_argument("--db", default=None, help="Override DB path")
    args = parser.parse_args(argv)

    import json

    from sdd.commands.registry import REGISTRY, execute_and_project
    from sdd.infra.paths import event_store_url
    from sdd.infra.projections import get_current_state

    _db = args.db or event_store_url()
    state = get_current_state(_db)

    cmd = InvalidateEventCommand(
        command_id=str(uuid.uuid4()),
        command_type="InvalidateEvent",
        payload={"target_seq": args.seq},
        target_seq=args.seq,
        reason=args.reason,
        phase_id=state.phase_current,
    )
    try:
        execute_and_project(REGISTRY["invalidate-event"], cmd, db_path=_db)
        print(json.dumps({"status": "ok", "invalidated_seq": args.seq}))
        return 0
    except Exception as exc:
        json.dump({"error_type": type(exc).__name__, "message": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
