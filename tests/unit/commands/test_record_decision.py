"""Tests for RecordDecisionHandler — Spec_v4 §9 Verification row 11.

Invariants: I-CMD-1, I-CMD-9
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.record_decision import RecordDecisionCommand, RecordDecisionHandler
from sdd.core.errors import InvalidState


def _cmd(
    decision_id: str = "D-16",
    title: str = "command idempotency by command_id",
    summary: str = "Commands are idempotent by command_id in the EventLog.",
    phase_id: int = 4,
    command_id: str | None = None,
) -> RecordDecisionCommand:
    return RecordDecisionCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="RecordDecisionCommand",
        payload={},
        decision_id=decision_id,
        title=title,
        summary=summary,
        phase_id=phase_id,
    )


@pytest.fixture
def handler(tmp_db_path: str) -> RecordDecisionHandler:
    return RecordDecisionHandler(db_path=tmp_db_path)


# ---------------------------------------------------------------------------
# test_record_decision_emits_event
# ---------------------------------------------------------------------------

def test_record_decision_emits_event(handler: RecordDecisionHandler) -> None:
    """handle() returns exactly one DecisionRecordedEvent (I-CMD-9)."""
    events = handler.handle(_cmd())
    assert len(events) == 1
    assert events[0].event_type == "DecisionRecorded"


# ---------------------------------------------------------------------------
# test_record_decision_idempotent
# ---------------------------------------------------------------------------

def test_record_decision_idempotent(handler: RecordDecisionHandler) -> None:
    """Second call with the same command_id returns [] (I-CMD-1)."""
    cmd = _cmd(command_id="cmd-record-idem")
    events_first = handler.handle(cmd)
    events_second = handler.handle(cmd)

    assert len(events_first) == 1
    assert events_second == []


# ---------------------------------------------------------------------------
# test_decision_recorded_event_fields
# ---------------------------------------------------------------------------

def test_decision_recorded_event_fields(handler: RecordDecisionHandler) -> None:
    """Emitted DecisionRecordedEvent carries all required fields (I-CMD-9)."""
    cmd = _cmd(
        decision_id="D-16",
        title="command idempotency by command_id",
        summary="Commands are idempotent by command_id in the EventLog.",
        phase_id=4,
    )
    events = handler.handle(cmd)
    assert len(events) == 1
    ev = events[0]

    assert ev.decision_id == "D-16"          # type: ignore[attr-defined]
    assert ev.title == "command idempotency by command_id"  # type: ignore[attr-defined]
    assert ev.summary == "Commands are idempotent by command_id in the EventLog."  # type: ignore[attr-defined]
    assert ev.phase_id == 4                   # type: ignore[attr-defined]
    assert ev.level == "L1"
    assert ev.event_source == "meta"


# ---------------------------------------------------------------------------
# Validation guard tests
# ---------------------------------------------------------------------------

def test_invalid_decision_id_raises(handler: RecordDecisionHandler) -> None:
    """decision_id not matching D-<number> raises InvalidState."""
    with pytest.raises(InvalidState, match="D-"):
        handler.handle(_cmd(decision_id="decision-16"))


def test_summary_too_long_raises(handler: RecordDecisionHandler) -> None:
    """summary exceeding 500 chars raises InvalidState."""
    long_summary = "x" * 501
    with pytest.raises(InvalidState, match="500"):
        handler.handle(_cmd(summary=long_summary))


def test_summary_exactly_500_chars_is_valid(handler: RecordDecisionHandler) -> None:
    """summary of exactly 500 chars is accepted."""
    events = handler.handle(_cmd(summary="x" * 500))
    assert len(events) == 1
