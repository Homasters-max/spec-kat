"""Unit tests for SessionRecord, SessionsView, build_sessions_view.

Invariants: I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1,
            I-SESSION-INVALIDATION-1, I-PROJECTION-ORDER-1, I-PSESSIONS-SEQ-1
"""
from __future__ import annotations

import dataclasses
import types
from unittest.mock import MagicMock, patch

import pytest

from sdd.infra.projector import (
    Projector,
    SessionRecord,
    SessionsView,
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
