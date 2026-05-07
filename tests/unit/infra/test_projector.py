"""Unit tests for Projector dispatch — I-PROJ-NOOP-1, I-TABLE-SEP-1, I-EVENT-PURE-1.

Tests run without a real database; open_db_connection is patched.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from sdd.core.events import DomainEvent
from sdd.infra.projector import Projector


def _make_mock_conn() -> MagicMock:
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = MagicMock()
    return mock_conn


def _make_projector(mock_conn: MagicMock) -> Projector:
    """Create a Projector backed by a mock connection."""
    with patch("sdd.infra.projector.open_db_connection", return_value=mock_conn):
        return Projector("postgresql://localhost/test_db")


def _unknown_event() -> DomainEvent:
    return DomainEvent(
        event_type="SomeCompletelyUnknownEventType42",
        event_id="test-noop-id",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
    )


def test_projector_noop_for_unknown_event(caplog: pytest.LogCaptureFixture) -> None:
    """I-PROJ-NOOP-1: unknown event_type → NO-OP; no DB cursor calls after __init__."""
    mock_conn = _make_mock_conn()
    projector = _make_projector(mock_conn)

    # Reset mock state accumulated during __init__ / _ensure_schema
    mock_conn.reset_mock()

    with caplog.at_level(logging.DEBUG, logger="sdd.infra.projector"):
        projector.apply(_unknown_event())

    # No DB interaction for unknown event type (I-PROJ-NOOP-1)
    mock_conn.cursor.assert_not_called()
    assert "NO-OP" in caplog.text


def test_projector_noop_does_not_raise() -> None:
    """I-PROJ-NOOP-1: apply() must not raise for any unknown event_type."""
    mock_conn = _make_mock_conn()
    projector = _make_projector(mock_conn)

    for unknown_type in ("FutureEvent", "DeprecatedEvent", "", "UnregisteredType"):
        event = DomainEvent(
            event_type=unknown_type,
            event_id=f"test-{unknown_type}",
            appended_at=0,
            level="L1",
            event_source="runtime",
            caused_by_meta_seq=None,
        )
        projector.apply(event)  # must not raise


def test_projector_context_manager_closes_connection() -> None:
    """Projector.__exit__ calls close(); connection is released after context."""
    mock_conn = _make_mock_conn()
    with _make_projector(mock_conn) as projector:
        projector.apply(_unknown_event())

    mock_conn.close.assert_called_once()


def test_apply_projector_safe_swallows_exception() -> None:
    """I-PROJ-SAFE-1: _apply_projector_safe swallows Projector.apply() exceptions (I-FAIL-1)."""
    from unittest.mock import patch as _patch

    from sdd.commands.registry import _apply_projector_safe

    mock_conn = _make_mock_conn()
    projector = _make_projector(mock_conn)

    event = DomainEvent(
        event_type="TaskImplemented",
        event_id="test-safe-id",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
    )

    with _patch.object(projector, "apply", side_effect=RuntimeError("DB failure")):
        # Must not raise — exception is swallowed (I-PROJ-SAFE-1)
        _apply_projector_safe(projector, [event])


def test_apply_projector_safe_noop_for_none_projector() -> None:
    """_apply_projector_safe is a no-op when projector is None."""
    from sdd.commands.registry import _apply_projector_safe

    _apply_projector_safe(None, [_unknown_event()])  # must not raise


def test_apply_projector_safe_noop_for_empty_events() -> None:
    """_apply_projector_safe is a no-op when events list is empty."""
    from sdd.commands.registry import _apply_projector_safe

    mock_conn = _make_mock_conn()
    projector = _make_projector(mock_conn)
    mock_conn.reset_mock()

    _apply_projector_safe(projector, [])  # must not raise; no DB calls
    mock_conn.cursor.assert_not_called()
