"""Unit tests for SessionRecord, SessionsView, build_sessions_view.

Invariants: I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1,
            I-SESSION-INVALIDATION-1, I-PROJECTION-ORDER-1, I-PSESSIONS-SEQ-1,
            I-DEDUP-KERNEL-AUTHORITY-1
"""
from __future__ import annotations

import dataclasses
import json
import time
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.infra.projector import (
    Projector,
    SessionRecord,
    SessionsView,
    _sync_p_sessions,
    build_sessions_view,
)


def _make_record(
    session_type: str,
    phase_id: int | None,
    seq: int,
    task_id: str | None = None,
    timestamp: str = "2024-01-01T00:00:00",
) -> SessionRecord:
    return SessionRecord(
        session_type=session_type,
        phase_id=phase_id,
        task_id=task_id,
        seq=seq,
        timestamp=timestamp,
    )


def _conn_returning(rows: list[tuple]) -> MagicMock:
    """Mock connection whose cursor().fetchall() returns `rows`."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _make_projector_with_mock() -> tuple[Projector, MagicMock]:
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = MagicMock()
    with patch("sdd.infra.projector.open_db_connection", return_value=mock_conn):
        p = Projector("postgresql://localhost/test_db")
    mock_conn.reset_mock()
    return p, mock_conn


# ---------------------------------------------------------------------------
# I-SESSIONSVIEW-O1-1
# ---------------------------------------------------------------------------


def test_sessions_view_get_last_o1() -> None:
    """I-SESSIONSVIEW-O1-1: get_last returns correct record via O(1) dict lookup."""
    rec_implement = _make_record("IMPLEMENT", 42, seq=10)
    rec_validate = _make_record("VALIDATE", 42, seq=20)
    view = SessionsView(
        _index={
            ("IMPLEMENT", 42): rec_implement,
            ("VALIDATE", 42): rec_validate,
        }
    )

    assert view.get_last("IMPLEMENT", 42) is rec_implement
    assert view.get_last("VALIDATE", 42) is rec_validate
    # Missing keys → None
    assert view.get_last("IMPLEMENT", 99) is None
    assert view.get_last("PLAN", None) is None


# ---------------------------------------------------------------------------
# I-INVALIDATION-FINAL-1, I-SESSION-INVALIDATION-1
# ---------------------------------------------------------------------------


def test_sessions_view_respects_transitive_invalidation() -> None:
    """I-INVALIDATION-FINAL-1, I-SESSION-INVALIDATION-1: invalidated seqs excluded.

    The SQL WHERE clause filters out seq values that appear in EventInvalidated
    target_seq. We simulate this by controlling which rows the mock cursor returns.
    """
    # seq=5 was invalidated — DB returns only the non-invalidated row (seq=10)
    rows = [
        ("IMPLEMENT", 48, "T-4801", 10, "2024-01-02T00:00:00"),
    ]
    view = build_sessions_view(_conn_returning(rows))
    result = view.get_last("IMPLEMENT", 48)
    assert result is not None
    assert result.seq == 10

    # All rows invalidated → empty view → get_last returns None (I-SESSION-INVALIDATION-1)
    empty_view = build_sessions_view(_conn_returning([]))
    assert empty_view.get_last("IMPLEMENT", 48) is None


# ---------------------------------------------------------------------------
# I-PROJECTION-ORDER-1
# ---------------------------------------------------------------------------


def test_sessions_view_last_seq_wins() -> None:
    """I-PROJECTION-ORDER-1: rows processed ORDER BY seq ASC; last entry per key wins."""
    rows = [
        # Same (session_type, phase_id) key — ascending seq order as DB returns
        ("IMPLEMENT", 48, "T-4801", 5, "2024-01-01T00:00:00"),
        ("IMPLEMENT", 48, "T-4802", 15, "2024-01-02T00:00:00"),
        ("IMPLEMENT", 48, "T-4803", 25, "2024-01-03T00:00:00"),
        # Different key — must not interfere
        ("VALIDATE", 48, "T-4801", 7, "2024-01-01T12:00:00"),
    ]
    view = build_sessions_view(_conn_returning(rows))

    result = view.get_last("IMPLEMENT", 48)
    assert result is not None
    assert result.seq == 25
    assert result.task_id == "T-4803"

    validate_result = view.get_last("VALIDATE", 48)
    assert validate_result is not None
    assert validate_result.seq == 7


# ---------------------------------------------------------------------------
# I-GUARD-PURE-1 (frozen dataclasses)
# ---------------------------------------------------------------------------


def test_sessions_view_is_frozen() -> None:
    """SessionRecord and SessionsView are frozen dataclasses — immutable after construction."""
    rec = _make_record("IMPLEMENT", 1, seq=1)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        rec.seq = 999  # type: ignore[misc]

    view = SessionsView(_index={})
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        view._index = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# I-PSESSIONS-SEQ-1
# ---------------------------------------------------------------------------


def test_psessions_seq_column_populated() -> None:
    """I-PSESSIONS-SEQ-1: _handle_session_declared inserts seq into p_sessions."""
    p, mock_conn = _make_projector_with_mock()
    mock_cur = mock_conn.cursor.return_value

    event = types.SimpleNamespace(
        event_type="SessionDeclared",
        session_type="IMPLEMENT",
        phase_id=48,
        task_id="T-4810",
        seq=99,
        timestamp="2024-01-01T00:00:00",
    )
    p.apply(event)  # type: ignore[arg-type]

    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "seq" in sql.lower()
    assert 99 in params


# ---------------------------------------------------------------------------
# I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1 — PG integration
# ---------------------------------------------------------------------------


def _seed_event(conn: object, event_type: str, payload: dict, level: str = "L1") -> int:
    """Insert event directly into event_log; return assigned sequence_id."""
    import psycopg
    assert isinstance(conn, psycopg.Connection)
    conn.execute(
        "INSERT INTO event_log"
        " (event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired)"
        " VALUES (%s, %s, %s::jsonb, %s, 'runtime', NULL, FALSE)",
        [str(uuid.uuid4()), event_type, json.dumps(payload), level],
    )
    conn.commit()
    row = conn.execute("SELECT MAX(sequence_id) FROM event_log").fetchone()
    return int(row[0])  # type: ignore[index]


@pytest.mark.pg
def test_reemit_after_invalidation_creates_new_event(tmp_db_path: str) -> None:
    """I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1.

    Scenario: SessionDeclared emitted → invalidated → re-emitted.
    After invalidate+re-emit:
    - event_log contains 2 SessionDeclared for the same (session_type, phase_id)
    - sessions_view (kernel authority) transitions from blocking to allowing re-emission

    I-DEDUP-KERNEL-AUTHORITY-1: dedup policy consults sessions_view; invalidation
    removes the session from the live view → policy returns should_emit=True.
    I-SESSION-INVALIDATION-1: re-emit after invalidation produces a second
    SessionDeclared in event_log for the same (type, phase_id).
    """
    import psycopg

    from sdd.domain.session.policy import SessionDedupPolicy

    # Initialize p_* projection tables via Projector
    with Projector(tmp_db_path):
        pass

    sd_payload = {
        "session_type": "IMPLEMENT",
        "phase_id": 49,
        "task_id": "T-4909",
        "plan_hash": "abc123",
        "timestamp": "2026-04-29T00:00:00Z",
    }

    policy = SessionDedupPolicy()

    mock_cmd = MagicMock()
    mock_cmd.session_type = "IMPLEMENT"
    mock_cmd.phase_id = 49

    with psycopg.connect(tmp_db_path) as conn:
        # Step 1: emit first SessionDeclared
        first_seq = _seed_event(conn, "SessionDeclared", sd_payload)

        # Step 2: sync p_sessions and build view → dedup MUST block re-emission
        _sync_p_sessions(conn)
        view_live = build_sessions_view(conn)
        assert policy.should_emit(view_live, mock_cmd) is False, (
            "I-DEDUP-KERNEL-AUTHORITY-1: dedup MUST block re-emission when"
            " a live SessionDeclared exists for (IMPLEMENT, 49)"
        )

        # Step 3: invalidate the first SessionDeclared
        _seed_event(
            conn,
            "EventInvalidated",
            {"target_seq": first_seq, "reason": "duplicate session", "invalidated_by_phase": 49},
        )

        # Step 4: rebuild view — invalidated seq excluded → dedup MUST allow re-emission
        view_after_invalidation = build_sessions_view(conn)
        assert policy.should_emit(view_after_invalidation, mock_cmd) is True, (
            "I-DEDUP-KERNEL-AUTHORITY-1: dedup MUST allow re-emission after"
            " SessionDeclared for (IMPLEMENT, 49) was invalidated"
        )

        # Step 5: re-emit SessionDeclared (second event for same key)
        _seed_event(conn, "SessionDeclared", sd_payload)

        # Step 6: verify event_log has exactly 2 SessionDeclared for (IMPLEMENT, 49)
        row = conn.execute(
            "SELECT COUNT(*) FROM event_log"
            " WHERE event_type = 'SessionDeclared'"
            " AND (payload->>'session_type') = 'IMPLEMENT'"
            " AND (payload->>'phase_id')::INTEGER = 49",
        ).fetchone()
        count = int(row[0])  # type: ignore[index]
        assert count == 2, (
            f"I-SESSION-INVALIDATION-1: event_log MUST contain 2 SessionDeclared"
            f" for (IMPLEMENT, 49) after invalidate+re-emit, got {count}"
        )


@pytest.mark.pg
def test_rebuild_populates_seq_from_event_log(tmp_db_path: str) -> None:
    """I-PSESSIONS-SEQ-1: rebuild() MUST populate p_sessions.seq from event_log.sequence_id.

    Regression guard for the seq=0 bug: rebuild() proxy was created without
    sequence_id, causing _handle_session_declared to always insert seq=0.
    """
    import psycopg

    from sdd.infra.projector import Projector

    sd_payload = {
        "session_type": "IMPLEMENT",
        "phase_id": 49,
        "task_id": "T-4901",
        "plan_hash": "abc123",
        "timestamp": "2024-01-01T00:00:00",
    }

    # Initialize p_* tables
    with Projector(tmp_db_path):
        pass

    with psycopg.connect(tmp_db_path) as conn:
        # Seed SessionDeclared directly into event_log; get its sequence_id
        expected_seq = _seed_event(conn, "SessionDeclared", sd_payload)
        assert expected_seq > 0

        # Rebuild projections from event_log
        proj = Projector(tmp_db_path)
        proj.rebuild(conn)

        # p_sessions.seq MUST equal event_log.sequence_id, not 0
        row = conn.execute(
            "SELECT seq FROM p_sessions"
            " WHERE session_type = 'IMPLEMENT' AND phase_id = 49",
        ).fetchone()
        assert row is not None, "p_sessions MUST contain the rebuilt SessionDeclared row"
        actual_seq = int(row[0])  # type: ignore[index]
        assert actual_seq == expected_seq, (
            f"I-PSESSIONS-SEQ-1: p_sessions.seq MUST equal event_log.sequence_id"
            f" after rebuild; expected {expected_seq}, got {actual_seq} (seq=0 bug)"
        )
