"""C-1 classifier completeness + PhaseStarted zero-mutation invariants.

Row 9 (C-1): V1_L1_EVENT_TYPES == _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys())
             after adding PhaseContextSwitched.
Row 1 (I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1):
             PhaseStarted MUST NOT mutate any state field in any branch.
"""
from __future__ import annotations

import inspect
import logging

import pytest

import sdd.domain.state.reducer as reducer_mod
from sdd.core.events import V1_L1_EVENT_TYPES
from sdd.domain.state.reducer import EMPTY_STATE, EventReducer, reduce, reduce_with_diagnostics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_source": "runtime", "level": "L1", "event_type": event_type, **payload}


def _phase_initialized(phase_id: int = 23, tasks_total: int = 5, plan_version: int = 23) -> dict[str, object]:
    return _runtime_l1(
        "PhaseInitialized",
        phase_id=phase_id,
        tasks_total=tasks_total,
        plan_version=plan_version,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
    )


def _phase_started(phase_id: int) -> dict[str, object]:
    return _runtime_l1("PhaseStarted", phase_id=phase_id, actor="human")


def _state_with_phase(phase_id: int) -> object:
    return reduce([_phase_initialized(phase_id=phase_id)])


# ---------------------------------------------------------------------------
# C-1: classifier completeness (row 9)
# ---------------------------------------------------------------------------

def test_phase_context_switched_in_v1_l1_event_types() -> None:
    """PhaseContextSwitched MUST be in V1_L1_EVENT_TYPES (BC-PC-1)."""
    assert "PhaseContextSwitched" in V1_L1_EVENT_TYPES


def test_phase_context_switched_in_event_schema() -> None:
    """PhaseContextSwitched MUST be registered in EventReducer._EVENT_SCHEMA."""
    reducer = EventReducer()
    assert "PhaseContextSwitched" in reducer._EVENT_SCHEMA


def test_c1_completeness_union_equals_v1_l1_event_types() -> None:
    """C-1: every V1_L1_EVENT_TYPE classified in either _KNOWN_NO_HANDLER or _EVENT_SCHEMA."""
    reducer = EventReducer()
    classified = reducer._KNOWN_NO_HANDLER | frozenset(reducer._EVENT_SCHEMA.keys())
    assert classified == V1_L1_EVENT_TYPES


def test_c1_no_unclassified_events() -> None:
    """No event type falls through both sets (complement is empty)."""
    reducer = EventReducer()
    classified = reducer._KNOWN_NO_HANDLER | frozenset(reducer._EVENT_SCHEMA.keys())
    unclassified = V1_L1_EVENT_TYPES - classified
    assert not unclassified, f"Unclassified event types: {unclassified}"


# ---------------------------------------------------------------------------
# I-PHASE-AUTH-1: PhaseStarted must NOT mutate phase_current (row 1)
# ---------------------------------------------------------------------------

def test_phase_started_less_than_current_zero_mutations() -> None:
    """PhaseStarted(phase_id < phase_current) → ZERO state mutations (I-PHASE-AUTH-1)."""
    base_events = [_phase_initialized(phase_id=23)]
    state_before = reduce(base_events)

    state_after = reduce(base_events + [_phase_started(phase_id=18)])

    assert state_after.phase_current == state_before.phase_current
    assert state_after.tasks_total == state_before.tasks_total
    assert state_after.tasks_completed == state_before.tasks_completed
    assert state_after.phase_status == state_before.phase_status
    assert state_after.plan_status == state_before.plan_status
    assert state_after.tasks_done_ids == state_before.tasks_done_ids
    assert state_after.invariants_status == state_before.invariants_status
    assert state_after.tests_status == state_before.tests_status
    assert state_after.phases_known == state_before.phases_known


def test_phase_started_equal_current_zero_mutations() -> None:
    """PhaseStarted(phase_id == phase_current) → ZERO state mutations (I-PHASE-AUTH-1)."""
    base_events = [_phase_initialized(phase_id=23)]
    state_before = reduce(base_events)

    state_after = reduce(base_events + [_phase_started(phase_id=23)])

    assert state_after.phase_current == state_before.phase_current
    assert state_after.tasks_total == state_before.tasks_total
    assert state_after.tasks_completed == state_before.tasks_completed
    assert state_after.phase_status == state_before.phase_status
    assert state_after.plan_status == state_before.plan_status
    assert state_after.tasks_done_ids == state_before.tasks_done_ids


def test_phase_started_greater_than_current_zero_mutations() -> None:
    """PhaseStarted(phase_id > phase_current) → ZERO state mutations (I-PHASE-AUTH-1).

    PhaseInitialized is the sole authoritative source; PhaseStarted is a pure signal.
    """
    base_events = [_phase_initialized(phase_id=23)]
    state_before = reduce(base_events)

    state_after = reduce(base_events + [_phase_started(phase_id=24)])

    assert state_after.phase_current == state_before.phase_current
    assert state_after.tasks_total == state_before.tasks_total
    assert state_after.tasks_completed == state_before.tasks_completed
    assert state_after.phase_status == state_before.phase_status
    assert state_after.plan_status == state_before.plan_status


# ---------------------------------------------------------------------------
# I-PHASE-REDUCER-1: PhaseStarted emits DEBUG, no state change (row 1)
# ---------------------------------------------------------------------------

def test_phase_started_regression_emits_debug_log(caplog: pytest.LogCaptureFixture) -> None:
    """PhaseStarted(phase_id < current) emits DEBUG log, not ERROR/WARNING (I-PHASE-REDUCER-1)."""
    base_events = [_phase_initialized(phase_id=23)]

    with caplog.at_level(logging.DEBUG):
        reduce(base_events + [_phase_started(phase_id=18)])

    debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("18" in r.getMessage() for r in debug_msgs), (
        "Expected DEBUG log mentioning phase_id=18"
    )
    error_msgs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_msgs, f"Unexpected ERROR/WARNING logs: {[r.getMessage() for r in error_msgs]}"


def test_phase_started_counted_as_processed(caplog: pytest.LogCaptureFixture) -> None:
    """PhaseStarted is processed (handler called) but produces zero net mutations."""
    base_events = [_phase_initialized(phase_id=23)]
    phase_started = _phase_started(phase_id=24)

    state_after, diag = reduce_with_diagnostics(base_events + [phase_started])
    # PhaseStarted has a registered handler → counted as processed
    assert diag.events_processed >= 1
    # But phase_current is NOT advanced (PhaseInitialized is authoritative)
    assert state_after.phase_current == 23


# ---------------------------------------------------------------------------
# I-PHASE-STARTED-1: code comment guard (row 1)
# ---------------------------------------------------------------------------

def test_phase_started_handler_has_no_logic_comment() -> None:
    """I-PHASE-STARTED-1: handler MUST contain '# DO NOT ADD LOGIC HERE' comment."""
    source = inspect.getsource(reducer_mod)
    assert "# DO NOT ADD LOGIC HERE" in source, (
        "I-PHASE-STARTED-1 violated: PhaseStarted handler missing '# DO NOT ADD LOGIC HERE' comment"
    )


def test_phase_started_handler_references_invariants_in_comment() -> None:
    """I-PHASE-STARTED-1: comment MUST reference I-PHASE-AUTH-1 and I-PHASE-STARTED-1."""
    source = inspect.getsource(reducer_mod)
    assert "I-PHASE-AUTH-1" in source
    assert "I-PHASE-STARTED-1" in source
