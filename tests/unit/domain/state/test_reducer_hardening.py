"""Tests for reducer pre-filter hardening — Spec_v7 §5 I-REDUCER-1 / I-REDUCER-WARN."""
from __future__ import annotations

import logging

import pytest

from sdd.domain.state.reducer import (
    EMPTY_STATE,
    EventReducer,
    ReducerDiagnostics,
    _REDUCER_REQUIRES_LEVEL,
    _REDUCER_REQUIRES_SOURCE,
    reduce_with_diagnostics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_source": "runtime", "level": "L1", "event_type": event_type, **payload}


def _task_implemented(task_id: str = "T-101") -> dict[str, object]:
    return _runtime_l1("TaskImplemented", task_id=task_id, phase_id=1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_meta_events_filtered() -> None:
    """Events with event_source != 'runtime' are silently dropped (I-REDUCER-1)."""
    meta_event = {"event_source": "meta", "level": "L1", "event_type": "TaskImplemented",
                  "task_id": "T-999", "phase_id": 1}
    _, diag = reduce_with_diagnostics([meta_event])
    assert diag.events_filtered_source == 1
    assert diag.events_filtered_level == 0
    assert diag.events_processed == 0


def test_l2_events_filtered() -> None:
    """Runtime events with level == 'L2' are silently dropped (I-REDUCER-1)."""
    l2_event = {"event_source": "runtime", "level": "L2", "event_type": "MetricRecorded"}
    _, diag = reduce_with_diagnostics([l2_event])
    assert diag.events_filtered_level == 1
    assert diag.events_filtered_source == 0
    assert diag.events_processed == 0


def test_l3_events_filtered() -> None:
    """Runtime events with level == 'L3' are silently dropped (I-REDUCER-1)."""
    l3_event = {"event_source": "runtime", "level": "L3", "event_type": "BashCommandStarted"}
    _, diag = reduce_with_diagnostics([l3_event])
    assert diag.events_filtered_level == 1
    assert diag.events_filtered_source == 0
    assert diag.events_processed == 0


def test_only_runtime_l1_dispatched() -> None:
    """Only runtime+L1 events reach the handler; mixed batch isolates them correctly."""
    events = [
        {"event_source": "meta",    "level": "L1", "event_type": "TaskImplemented", "task_id": "T-1", "phase_id": 1},
        {"event_source": "runtime", "level": "L2", "event_type": "MetricRecorded"},
        {"event_source": "runtime", "level": "L3", "event_type": "BashCommandStarted"},
        _task_implemented("T-2"),
    ]
    state, diag = reduce_with_diagnostics(events)
    assert diag.events_total == 4
    assert diag.events_filtered_source == 1
    assert diag.events_filtered_level == 2
    assert diag.events_processed == 1
    assert "T-2" in state.tasks_done_ids
    assert "T-1" not in state.tasks_done_ids


def test_pre_filter_constants_named() -> None:
    """Module-level constants _REDUCER_REQUIRES_SOURCE and _REDUCER_REQUIRES_LEVEL exist with correct values."""
    assert _REDUCER_REQUIRES_SOURCE == "runtime"
    assert _REDUCER_REQUIRES_LEVEL == "L1"


def test_state_identical_with_without_meta() -> None:
    """SDDState is identical whether or not meta / L2 / L3 events are in the batch."""
    l1_events = [_task_implemented("T-3")]
    mixed_events = [
        {"event_source": "meta",    "level": "L1", "event_type": "TaskImplemented", "task_id": "T-99", "phase_id": 1},
        {"event_source": "runtime", "level": "L2", "event_type": "MetricRecorded"},
        _task_implemented("T-3"),
    ]
    state_clean = EventReducer().reduce(l1_events)
    state_mixed = EventReducer().reduce(mixed_events)
    assert state_clean == state_mixed


def test_misclassified_l1_event_type_warns(caplog: pytest.LogCaptureFixture) -> None:
    """An event that passes the pre-filter but has an unregistered event_type emits a warning."""
    unknown_event = _runtime_l1("UnknownFutureEvent")
    with caplog.at_level(logging.DEBUG, logger="root"):
        state, diag = reduce_with_diagnostics([unknown_event])
    assert diag.events_unknown_type == 1
    assert diag.events_processed == 0
    assert any("UnknownFutureEvent" in r.message for r in caplog.records)
    assert state == EMPTY_STATE
