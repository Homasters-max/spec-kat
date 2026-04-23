"""Tests for ReportErrorHandler — Spec_v4 §9 Verification row 10.

Invariants: I-CMD-1, I-ERR-1
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.report_error import ReportErrorCommand, ReportErrorHandler


def _cmd(command_id: str | None = None) -> ReportErrorCommand:
    return ReportErrorCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ReportErrorCommand",
        payload={},
        error_type="SomeError",
        message="something went wrong",
        source="test.source",
        recoverable=False,
    )


@pytest.fixture
def handler(tmp_db_path: str) -> ReportErrorHandler:
    return ReportErrorHandler(db_path=tmp_db_path)


# ---------------------------------------------------------------------------
# test_report_error_emits_error_event
# ---------------------------------------------------------------------------

def test_report_error_emits_error_event(handler: ReportErrorHandler) -> None:
    """handle() returns exactly one ErrorEvent (I-ERR-1)."""
    events = handler.handle(_cmd())
    assert len(events) == 1
    assert events[0].event_type == "ErrorEvent"


# ---------------------------------------------------------------------------
# test_report_error_retry_count_zero
# ---------------------------------------------------------------------------

def test_report_error_retry_count_zero(handler: ReportErrorHandler) -> None:
    """retry_count is always 0 — manual reports are not retries (Spec_v4 §4.9)."""
    events = handler.handle(_cmd())
    assert len(events) == 1
    assert events[0].retry_count == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# test_report_error_idempotent
# ---------------------------------------------------------------------------

def test_report_error_idempotent(handler: ReportErrorHandler) -> None:
    """Second call with the same command_id returns [] (I-CMD-1)."""
    cmd = _cmd("cmd-report-idem")
    events_first = handler.handle(cmd)
    events_second = handler.handle(cmd)

    assert len(events_first) == 1
    assert events_second == []
