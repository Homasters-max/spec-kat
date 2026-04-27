"""Integration: incident backfill — 6 TestEvent entries → invalidate all → replay no WARNING.

Invariants: I-INVALID-2, I-INVALID-IDEM-1
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import pytest

from sdd.commands.invalidate_event import (
    EventInvalidatedEvent,
    InvalidateEventCommand,
    InvalidateEventHandler,
)
from sdd.domain.state.reducer import reduce
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventLog


def _sql_insert(db_path: str, event_type: str, payload: dict, level: str = "L1") -> int:
    """Insert one event via direct SQL and return its seq (bypasses batch_id column)."""
    conn = open_sdd_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO events
                (seq, event_id, event_type, payload, schema_version,
                 appended_at, level, event_source, caused_by_meta_seq, expired)
            VALUES (nextval('sdd_event_seq'), ?, ?, ?, 1, ?, ?, 'runtime', NULL, FALSE)""",
            [str(uuid.uuid4()), event_type, json.dumps(payload), int(time.time() * 1000), level],
        )
        conn.commit()
        row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
        return int(row[0])
    finally:
        conn.close()


def _persist_invalidated_event(db_path: str, ev: EventInvalidatedEvent) -> None:
    """Write an EventInvalidatedEvent to the DB via direct SQL."""
    _sql_insert(
        db_path,
        "EventInvalidated",
        {"target_seq": ev.target_seq, "reason": ev.reason, "invalidated_by_phase": ev.invalidated_by_phase},
        level=ev.level,
    )


def test_incident_backfill_no_warnings(
    tmp_db_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    """I-INVALID-2, I-INVALID-IDEM-1: 6 TestEvent → invalidate all → replay + reduce emit no WARNING."""
    # 1. Seed 6 L1 runtime TestEvent events (replicate production incident)
    seqs: list[int] = []
    for _ in range(6):
        seq = _sql_insert(tmp_db_path, "TestEvent", {"_source": "test_seed"}, level="L1")
        seqs.append(seq)
    assert len(seqs) == 6

    # 2. Pre-condition: without invalidation the reducer warns for each unknown type
    with caplog.at_level(logging.WARNING, logger="root"):
        reduce(EventLog(tmp_db_path).replay())
    pre_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "unknown event_type" in r.getMessage()
    ]
    assert len(pre_warnings) == 6, (
        f"Expected 6 'unknown event_type' WARNINGs before backfill, got {len(pre_warnings)}"
    )
    caplog.clear()

    # 3. Invalidate all 6 via handler; persist emitted EventInvalidated events
    handler = InvalidateEventHandler(db_path=tmp_db_path)
    for seq in seqs:
        cmd = InvalidateEventCommand(
            command_id=str(uuid.uuid4()),
            command_type="InvalidateEvent",
            payload={},
            target_seq=seq,
            reason="incident backfill: neutralize stray TestEvent",
            phase_id=28,
        )
        emitted = handler.handle(cmd)
        assert len(emitted) == 1, f"Expected one EventInvalidated for seq={seq}"
        _persist_invalidated_event(tmp_db_path, emitted[0])  # type: ignore[arg-type]

    # 4. I-INVALID-IDEM-1: second pass returns [] for all already-invalidated seqs
    for seq in seqs:
        cmd = InvalidateEventCommand(
            command_id=str(uuid.uuid4()),
            command_type="InvalidateEvent",
            payload={},
            target_seq=seq,
            reason="idempotency check",
            phase_id=28,
        )
        assert handler.handle(cmd) == [], (
            f"I-INVALID-IDEM-1: second invalidate of seq={seq} must be noop"
        )

    # 5. I-INVALID-2: after backfill, replay + reduce must produce no WARNING
    with caplog.at_level(logging.WARNING, logger="root"):
        replayed_after = EventLog(tmp_db_path).replay()
        reduce(replayed_after)

    post_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "unknown event_type" in r.getMessage()
    ]
    assert not post_warnings, (
        f"I-INVALID-2: no 'unknown event_type' WARNINGs expected after backfill, "
        f"got: {[r.getMessage() for r in post_warnings]}"
    )

    # 6. Confirm all 6 invalidated seqs absent from replayed events
    replayed_seqs = {e["seq"] for e in replayed_after}
    for seq in seqs:
        assert seq not in replayed_seqs, (
            f"I-INVALID-2: invalidated seq={seq} must not appear in replay"
        )
