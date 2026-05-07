"""Tests for T-4601: invalidate_event.py PG migration (BC-46-H).

Invariants: I-INVALIDATE-PG-1, I-DB-ENTRY-1
"""
from __future__ import annotations

import json
import pathlib
import time
import uuid

import pytest

from sdd.commands.invalidate_event import (
    EVENT_LOG_TABLE,
    InvalidateEventCommand,
    InvalidateEventHandler,
)


def _make_cmd(
    target_seq: int = 1,
    reason: str = "test",
    phase_id: int = 46,
    force: bool = False,
) -> InvalidateEventCommand:
    return InvalidateEventCommand(
        command_id=str(uuid.uuid4()),
        command_type="InvalidateEvent",
        payload={"target_seq": target_seq},
        target_seq=target_seq,
        reason=reason,
        phase_id=phase_id,
        force=force,
    )


# ---------------------------------------------------------------------------
# test_invalidate_event_uses_pg_syntax
# ---------------------------------------------------------------------------

def test_invalidate_event_uses_pg_syntax() -> None:
    """I-INVALIDATE-PG-1: source file must use PG syntax — no DuckDB artefacts."""
    src = pathlib.Path(__file__).parent.parent.parent / "src/sdd/commands/invalidate_event.py"
    code = src.read_text()

    # Must use PG table and column
    assert "EVENT_LOG_TABLE" in code
    assert '"event_log"' in code
    assert "sequence_id" in code
    # Must use %s placeholders (psycopg3)
    assert "%s" in code
    # Must NOT use DuckDB artefacts
    assert "events WHERE seq" not in code
    assert "= ?" not in code
    assert "event_store_file" not in code
    assert "psycopg.connect" not in code


# ---------------------------------------------------------------------------
# test_invalidate_event_rejects_production_without_force
# ---------------------------------------------------------------------------

def test_invalidate_event_rejects_production_without_force(
    monkeypatch: pytest.MonkeyPatch,
    pg_test_db: str,
) -> None:
    """I-INVALIDATE-PG-1: without --force, command MUST raise ValueError on production store."""
    # Simulate handler targeting production by making db_path == SDD_DATABASE_URL
    monkeypatch.setenv("SDD_DATABASE_URL", pg_test_db)
    handler = InvalidateEventHandler(db_path=pg_test_db)

    cmd = _make_cmd(target_seq=1, force=False)
    with pytest.raises(ValueError, match="--force"):
        handler.handle(cmd)


# ---------------------------------------------------------------------------
# test_invalidate_event_pg_roundtrip
# ---------------------------------------------------------------------------

def test_invalidate_event_pg_roundtrip(pg_url: str) -> None:
    """I-INVALIDATE-PG-1 + I-DB-ENTRY-1: handler queries PG event_log and returns EventInvalidatedEvent."""
    from sdd.db.connection import open_db_connection

    conn = open_db_connection(pg_url)
    try:
        # Ensure DDL (idempotent via PostgresEventLog.__init__ called in handler)
        from sdd.infra.event_log import PostgresEventLog
        PostgresEventLog(pg_url)

        # Seed a non-state L2 event directly into event_log
        event_id = str(uuid.uuid4())
        payload = json.dumps({"msg": "roundtrip-test"})
        conn.execute(
            f"INSERT INTO {EVENT_LOG_TABLE} "
            "(event_id, event_type, payload, level, event_source) "
            "VALUES (%s::uuid, %s, %s::jsonb, 'L2', 'runtime')",
            [event_id, "ErrorOccurred", payload],
        )
        conn.commit()

        row = conn.execute(
            f"SELECT sequence_id FROM {EVENT_LOG_TABLE} WHERE event_id = %s::uuid",
            [event_id],
        ).fetchone()
        assert row is not None, "seeded event not found"
        seq_id = int(row[0])
    finally:
        conn.close()

    handler = InvalidateEventHandler(db_path=pg_url)
    cmd = _make_cmd(target_seq=seq_id, force=True)

    events = handler.handle(cmd)

    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "EventInvalidated"
    assert ev.target_seq == seq_id  # type: ignore[attr-defined]
    assert ev.reason == "test"       # type: ignore[attr-defined]
    assert ev.invalidated_by_phase == 46  # type: ignore[attr-defined]
    assert ev.level == "L1"
    assert ev.event_source == "runtime"
