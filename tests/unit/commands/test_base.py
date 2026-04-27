"""Tests for CommandHandlerBase and error_event_boundary.

Invariants covered: I-ES-1 (final form), I-CMD-3
Spec ref: Spec_v5 §4.4, §9 Verification row 3

T-502 changed error_event_boundary to attach ErrorEvent to the raised exception
via exc._sdd_error_events instead of calling sdd_append directly.
CommandRunner now owns the sole write path (I-ES-1 final form).
"""
from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from sdd.commands._base import (
    CommandHandlerBase,
    RecoverableError,
    command_payload_hash,
    error_event_boundary,
)
from sdd.core.events import DomainEvent, ErrorEvent
from sdd.core.types import Command
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import sdd_append


# ── Test helpers ──────────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class _FakeCommand(Command):
    task_id: str | None = None
    phase_id: int | None = None


def _cmd(
    command_id: str = "cmd-test",
    task_id: str = "T-001",
    phase_id: int = 4,
) -> _FakeCommand:
    return _FakeCommand(
        command_id=command_id,
        command_type="_FakeCommand",
        payload={},
        task_id=task_id,
        phase_id=phase_id,
    )


class _ErrorHandler(CommandHandlerBase):
    """Handler that always raises RuntimeError("boom")."""

    @error_event_boundary(source="test._error_handler")
    def handle(self, command: Command) -> list[DomainEvent]:
        raise RuntimeError("boom")


class _SuccessHandler(CommandHandlerBase):
    """Handler that always returns []."""

    @error_event_boundary(source="test._success_handler")
    def handle(self, command: Command) -> list[DomainEvent]:
        return []


class _NoIdempotencyErrorHandler(CommandHandlerBase):
    """Bypasses idempotency check; raises RuntimeError. For retry-count tests."""

    def _check_idempotent(self, command: Command) -> bool:
        return False

    @error_event_boundary(source="test._no_idem")
    def handle(self, command: Command) -> list[DomainEvent]:
        raise RuntimeError("boom")


def _event_count(db_path: str) -> int:
    conn = open_sdd_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ── Phase 5 named tests (Spec_v5 §9 row 3) ────────────────────────────────────


def test_error_boundary_no_direct_sdd_append(tmp_db_path: str) -> None:
    """error_event_boundary must NOT call sdd_append — I-ES-1 final form (T-502).

    The boundary attaches ErrorEvent to exc._sdd_error_events and re-raises.
    CommandRunner is the sole entity that calls EventStore.append.
    """
    with pytest.raises(RuntimeError, match="boom"):
        _ErrorHandler(tmp_db_path).handle(_cmd("cmd-no-append"))
    # No event written to DB by the boundary
    assert _event_count(tmp_db_path) == 0


def test_error_boundary_attaches_to_exception(tmp_db_path: str) -> None:
    """error_event_boundary attaches ErrorEvent to exc._sdd_error_events — I-ES-1 (T-502)."""
    with pytest.raises(RuntimeError) as exc_info:
        _ErrorHandler(tmp_db_path).handle(_cmd("cmd-attach"))
    exc = exc_info.value
    assert hasattr(exc, "_sdd_error_events"), "boundary must set _sdd_error_events on exception"
    error_events = exc._sdd_error_events
    assert len(error_events) == 1
    assert isinstance(error_events[0], ErrorEvent)
    assert error_events[0].error_type == "RuntimeError"
    assert error_events[0].source == "test._error_handler"


def test_error_boundary_reraises_always(tmp_db_path: str) -> None:
    """The original exception is always re-raised — boundary never swallows it (I-CMD-3)."""
    original = RuntimeError("boom")

    class _ExactRaiser(CommandHandlerBase):
        @error_event_boundary(source="test")
        def handle(self, command: Command) -> list[DomainEvent]:
            raise original

    with pytest.raises(RuntimeError) as exc_info:
        _ExactRaiser(tmp_db_path).handle(_cmd("cmd-reraise"))
    assert exc_info.value is original


def test_retry_count_is_best_effort_note(tmp_db_path: str) -> None:
    """If get_error_count raises, retry_count defaults to 0 — I-CMD-3 best-effort (T-502)."""
    with patch("sdd.infra.event_log.EventLog.get_error_count", side_effect=OSError("DB gone")):
        with pytest.raises(RuntimeError) as exc_info:
            _NoIdempotencyErrorHandler(tmp_db_path).handle(_cmd("cmd-best-effort"))
    error_events = exc_info.value._sdd_error_events
    assert error_events[0].retry_count == 0


# ── Idempotency tests (I-CMD-2, I-CMD-2b) ─────────────────────────────────────


def test_idempotent_check_skips_boundary(tmp_db_path: str) -> None:
    """Structural idempotency (exists_command=True) returns [] without triggering boundary."""
    cmd = _cmd("cmd-idem-struct")
    sdd_append(
        "TaskImplemented",
        {"command_id": "cmd-idem-struct", "task_id": "T-001", "phase_id": 4},
        db_path=tmp_db_path,
        level="L1",
    )
    result = _ErrorHandler(tmp_db_path).handle(cmd)
    assert result == []
    # No additional events written beyond the pre-populated one
    assert _event_count(tmp_db_path) == 1


def test_semantic_idempotent_skips_boundary(tmp_db_path: str) -> None:
    """Semantic idempotency (exists_semantic=True) returns [] without triggering boundary."""
    cmd = _cmd("cmd-idem-semantic")
    payload_hash = command_payload_hash(cmd)
    sdd_append(
        "_FakeCommand",
        {
            "command_id": "cmd-prior-different-id",
            "task_id": "T-001",
            "phase_id": 4,
            "payload_hash": payload_hash,
        },
        db_path=tmp_db_path,
        level="L2",
    )
    result = _ErrorHandler(tmp_db_path).handle(cmd)
    assert result == []
    assert _event_count(tmp_db_path) == 1
