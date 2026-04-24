"""Tests for Phase 4 event dataclasses + reducer C-1 compliance — Spec_v4 §9 row 1."""
from __future__ import annotations

import pytest

from sdd.core.events import (
    DecisionRecordedEvent,
    PhaseCompletedEvent,
    TaskImplementedEvent,
    TaskValidatedEvent,
    V1_L1_EVENT_TYPES,
)
from sdd.domain.state.reducer import (
    EMPTY_STATE,
    EventReducer,
    reduce,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {
        "event_type": event_type,
        "event_source": "runtime",
        "level": "L1",
        **payload,
    }


def _base_kwargs() -> dict[str, object]:
    return {
        "event_id": "abc123",
        "appended_at": 1_700_000_000_000,
        "level": "L1",
        "event_source": "runtime",
        "caused_by_meta_seq": None,
    }


# ---------------------------------------------------------------------------
# Frozen dataclass tests
# ---------------------------------------------------------------------------

def test_task_implemented_event_is_frozen() -> None:
    ev = TaskImplementedEvent(
        **_base_kwargs(),
        event_type="TaskImplemented",
        task_id="T-401",
        phase_id=4,
        timestamp="2026-04-22T00:00:00Z",
    )
    with pytest.raises(AttributeError):
        ev.task_id = "T-999"  # type: ignore[misc]


def test_task_validated_event_is_frozen() -> None:
    ev = TaskValidatedEvent(
        **_base_kwargs(),
        event_type="TaskValidated",
        task_id="T-401",
        phase_id=4,
        result="PASS",
        timestamp="2026-04-22T00:00:00Z",
    )
    with pytest.raises(AttributeError):
        ev.result = "FAIL"  # type: ignore[misc]


def test_phase_completed_event_is_frozen() -> None:
    ev = PhaseCompletedEvent(
        **_base_kwargs(),
        event_type="PhaseCompleted",
        phase_id=4,
        total_tasks=27,
        timestamp="2026-04-22T00:00:00Z",
    )
    with pytest.raises(AttributeError):
        ev.phase_id = 99  # type: ignore[misc]


def test_decision_recorded_event_is_frozen() -> None:
    ev = DecisionRecordedEvent(
        **_base_kwargs(),
        event_type="DecisionRecorded",
        decision_id="D-16",
        title="command idempotency",
        summary="Commands are idempotent by command_id.",
        phase_id=4,
        timestamp="2026-04-22T00:00:00Z",
    )
    with pytest.raises(AttributeError):
        ev.decision_id = "D-99"  # type: ignore[misc]


def test_event_dataclasses_are_hashable() -> None:
    ev = TaskImplementedEvent(
        **_base_kwargs(),
        event_type="TaskImplemented",
        task_id="T-401",
        phase_id=4,
        timestamp="2026-04-22T00:00:00Z",
    )
    assert hash(ev) is not None
    assert ev in {ev}


# ---------------------------------------------------------------------------
# C-1 compliance
# ---------------------------------------------------------------------------

def test_c1_assert_passes_after_import() -> None:
    # The import-time assert in EventReducer verifies C-1.
    # If the assert fires, this module would fail to import above.
    assert EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES


def test_decision_recorded_in_v1_l1_types() -> None:
    assert "DecisionRecorded" in V1_L1_EVENT_TYPES


def test_phase_completed_in_event_schema() -> None:
    # Phase 15: PhaseCompleted moved from _KNOWN_NO_HANDLER to _EVENT_SCHEMA (I-PHASE-COMPLETE-1)
    assert "PhaseCompleted" in EventReducer._EVENT_SCHEMA


def test_phase_completed_not_in_known_no_handler() -> None:
    assert "PhaseCompleted" not in EventReducer._KNOWN_NO_HANDLER


def test_decision_recorded_in_known_no_handler() -> None:
    assert "DecisionRecorded" in EventReducer._KNOWN_NO_HANDLER


# ---------------------------------------------------------------------------
# Reducer handlers — TaskImplemented
# ---------------------------------------------------------------------------

def test_reducer_handles_task_implemented() -> None:
    events = [
        _runtime_l1("TaskImplemented", task_id="T-401", phase_id=4),
    ]
    state = reduce(events)
    assert "T-401" in state.tasks_done_ids
    assert state.tasks_completed == 1


def test_reducer_task_implemented_increments_completed() -> None:
    events = [
        _runtime_l1("TaskImplemented", task_id="T-401", phase_id=4),
        _runtime_l1("TaskImplemented", task_id="T-402", phase_id=4),
    ]
    state = reduce(events)
    assert state.tasks_completed == 2
    assert set(state.tasks_done_ids) == {"T-401", "T-402"}


def test_reducer_task_implemented_deduplicates() -> None:
    events = [
        _runtime_l1("TaskImplemented", task_id="T-401", phase_id=4),
        _runtime_l1("TaskImplemented", task_id="T-401", phase_id=4),
    ]
    state = reduce(events)
    assert state.tasks_completed == 1
    assert state.tasks_done_ids.count("T-401") == 1


# ---------------------------------------------------------------------------
# Reducer handlers — TaskValidated
# ---------------------------------------------------------------------------

def test_reducer_handles_task_validated() -> None:
    events = [
        _runtime_l1("TaskValidated", task_id="T-401", phase_id=4, result="PASS"),
    ]
    state = reduce(events)
    assert state.tests_status == "PASS"
    assert state.invariants_status == "PASS"


def test_reducer_task_validated_fail() -> None:
    events = [
        _runtime_l1("TaskValidated", task_id="T-401", phase_id=4, result="FAIL"),
    ]
    state = reduce(events)
    assert state.tests_status == "FAIL"
    assert state.invariants_status == "FAIL"


def test_reducer_task_validated_ignores_unknown_result() -> None:
    events = [
        _runtime_l1("TaskValidated", task_id="T-401", phase_id=4, result="UNKNOWN"),
    ]
    state = reduce(events)
    assert state.tests_status == EMPTY_STATE.tests_status
    assert state.invariants_status == EMPTY_STATE.invariants_status


# ---------------------------------------------------------------------------
# PhaseCompleted — Phase 15: now in _EVENT_SCHEMA (I-PHASE-COMPLETE-1)
# ---------------------------------------------------------------------------

def test_reducer_phase_completed_sets_complete() -> None:
    # Phase 15: PhaseCompleted handler sets phase_status=COMPLETE, plan_status=COMPLETE
    events = [
        _runtime_l1("PhaseCompleted", phase_id=4),
    ]
    state = reduce(events)
    assert state.phase_status == "COMPLETE"
    assert state.plan_status == "COMPLETE"
