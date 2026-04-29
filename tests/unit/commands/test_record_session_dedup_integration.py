"""Integration tests for record-session dedup against live PostgreSQL.

Invariants: I-SESSION-DEDUP-2, I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1,
            I-SESSION-DEDUP-SCOPE-1, I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1
Skipped when SDD_DATABASE_URL is not set.
"""
from __future__ import annotations

import json
import uuid

import psycopg
import pytest

from sdd.commands.record_session import RecordSessionCommand, stable_session_command_id
from sdd.commands.registry import REGISTRY, execute_command
from sdd.db.connection import open_db_connection
from sdd.infra.projector import Projector, _sync_p_sessions, build_sessions_view


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cmd(session_type: str, phase_id: int) -> RecordSessionCommand:
    return RecordSessionCommand(
        command_id=stable_session_command_id(session_type, phase_id),
        command_type="RecordSession",
        payload={"session_type": session_type, "phase_id": phase_id},
        session_type=session_type,
        task_id=None,
        phase_id=phase_id,
        plan_hash="test-hash",
    )


def _setup_tables(pg_url: str) -> None:
    """Ensure p_sessions exists and is clean for the current test."""
    with Projector(pg_url):
        pass
    with psycopg.connect(pg_url) as conn:
        conn.execute("TRUNCATE p_sessions RESTART IDENTITY")
        conn.commit()


def _count_session_declared(pg_url: str, session_type: str, phase_id: int) -> int:
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM event_log"
            " WHERE event_type = 'SessionDeclared'"
            " AND payload->>'session_type' = %s"
            " AND (payload->>'phase_id')::INTEGER = %s",
            (session_type, phase_id),
        ).fetchone()
    return row[0] if row else 0


def _insert_session_declared_raw(
    pg_url: str, session_type: str, phase_id: int, timestamp_str: str
) -> int:
    """Insert SessionDeclared directly into event_log; return its sequence_id."""
    payload = json.dumps({
        "session_type": session_type,
        "phase_id": phase_id,
        "task_id": None,
        "timestamp": timestamp_str,
    })
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "INSERT INTO event_log"
            " (event_id, event_type, payload, level, event_source)"
            " VALUES (%s, 'SessionDeclared', %s::jsonb, 'L1', 'test')"
            " RETURNING sequence_id",
            (str(uuid.uuid4()), payload),
        ).fetchone()
        conn.commit()
    assert row is not None
    return row[0]


def _insert_event_invalidated_raw(pg_url: str, target_seq: int) -> None:
    """Insert EventInvalidated pointing to target_seq directly into event_log."""
    payload = json.dumps({"target_seq": target_seq, "reason": "test-invalidation"})
    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "INSERT INTO event_log"
            " (event_id, event_type, payload, level, event_source)"
            " VALUES (%s, 'EventInvalidated', %s::jsonb, 'L1', 'test')",
            (str(uuid.uuid4()), payload),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.pg
def test_double_record_session_emits_one_event(
    pg_test_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-SESSION-DEDUP-2: double record-session for same (type, phase) emits exactly one event."""
    _setup_tables(pg_test_db)
    monkeypatch.setenv("SDD_DATABASE_URL", pg_test_db)
    spec = REGISTRY["record-session"]
    cmd = _make_cmd("IMPLEMENT", 48)

    events1 = execute_command(spec, cmd, db_path=pg_test_db)
    assert len(events1) == 1, f"First call: expected 1 event, got {len(events1)}"

    events2 = execute_command(spec, cmd, db_path=pg_test_db)
    assert len(events2) == 0, f"Second call (dedup): expected 0 events, got {len(events2)}"

    count = _count_session_declared(pg_test_db, "IMPLEMENT", 48)
    assert count == 1, f"Expected 1 SessionDeclared in event_log, got {count}"


@pytest.mark.pg
def test_after_invalidate_record_session_emits_new(
    pg_test_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1:
    after EventInvalidated removes session from sessions_view, record-session emits a new event.
    """
    _setup_tables(pg_test_db)
    monkeypatch.setenv("SDD_DATABASE_URL", pg_test_db)

    # Insert a SessionDeclared with a past-day timestamp to bypass handler's today-check
    past_ts = "2020-01-01T00:00:00Z"
    seq = _insert_session_declared_raw(pg_test_db, "PLAN", 48, past_ts)

    # Sync and verify session is visible before invalidation
    conn = open_db_connection(pg_test_db)
    try:
        _sync_p_sessions(conn)
        view_before = build_sessions_view(conn)
    finally:
        conn.close()
    assert view_before.get_last("PLAN", 48) is not None, (
        "Session should be visible in sessions_view before invalidation"
    )

    # Invalidate the session
    _insert_event_invalidated_raw(pg_test_db, seq)

    # After invalidation, sessions_view must not return the session (I-INVALIDATION-FINAL-1)
    conn = open_db_connection(pg_test_db)
    try:
        _sync_p_sessions(conn)
        view_after = build_sessions_view(conn)
    finally:
        conn.close()
    assert view_after.get_last("PLAN", 48) is None, (
        "Session must be absent from sessions_view after invalidation (I-INVALIDATION-FINAL-1)"
    )

    # Dedup passes (sessions_view empty) → handler emits new event
    spec = REGISTRY["record-session"]
    cmd = _make_cmd("PLAN", 48)
    events = execute_command(spec, cmd, db_path=pg_test_db)
    assert len(events) == 1, f"Expected 1 new event after invalidation, got {len(events)}"

    count = _count_session_declared(pg_test_db, "PLAN", 48)
    assert count == 2, f"Expected 2 SessionDeclared total (past + new), got {count}"


@pytest.mark.pg
def test_different_types_both_emitted(
    pg_test_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-SESSION-DEDUP-SCOPE-1: dedup is scoped to (session_type, phase_id); different types both emit."""
    _setup_tables(pg_test_db)
    monkeypatch.setenv("SDD_DATABASE_URL", pg_test_db)
    spec = REGISTRY["record-session"]

    cmd_impl = _make_cmd("IMPLEMENT", 48)
    cmd_plan = _make_cmd("PLAN", 48)

    events_impl = execute_command(spec, cmd_impl, db_path=pg_test_db)
    assert len(events_impl) == 1, f"IMPLEMENT call: expected 1 event, got {len(events_impl)}"

    events_plan = execute_command(spec, cmd_plan, db_path=pg_test_db)
    assert len(events_plan) == 1, f"PLAN call: expected 1 event, got {len(events_plan)}"

    count_impl = _count_session_declared(pg_test_db, "IMPLEMENT", 48)
    count_plan = _count_session_declared(pg_test_db, "PLAN", 48)
    assert count_impl == 1, f"Expected 1 IMPLEMENT/48 event, got {count_impl}"
    assert count_plan == 1, f"Expected 1 PLAN/48 event, got {count_plan}"


@pytest.mark.pg
def test_sync_before_sessions_view(pg_test_db: str) -> None:
    """I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1:
    _sync_p_sessions must be called before build_sessions_view to reflect new events.
    """
    _setup_tables(pg_test_db)

    # Insert SessionDeclared directly into event_log, bypassing the projector
    session_type, phase_id = "DECOMPOSE", 48
    _insert_session_declared_raw(
        pg_test_db, session_type, phase_id, "2026-04-29T10:00:00Z"
    )

    conn = open_db_connection(pg_test_db)
    try:
        # Before _sync: p_sessions is empty → sessions_view reflects no session
        view_stale = build_sessions_view(conn)
        assert view_stale.get_last(session_type, phase_id) is None, (
            "Without _sync_p_sessions, sessions_view must not see unprojected event "
            "(I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1)"
        )

        # After _sync: session is reflected in sessions_view
        _sync_p_sessions(conn)
        view_fresh = build_sessions_view(conn)
        assert view_fresh.get_last(session_type, phase_id) is not None, (
            "After _sync_p_sessions, sessions_view must see the event (I-PROJECTION-FRESH-1)"
        )
    finally:
        conn.close()
