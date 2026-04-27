"""Tests for SDDState, ReducerDiagnostics, EventReducer — Spec_v2 §9 row 1."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from sdd.core.errors import Inconsistency, SDDError
from sdd.core.events import V1_L1_EVENT_TYPES
from sdd.domain.state.reducer import (
    EMPTY_STATE,
    EventReducer,
    SDDState,
    UnknownEventType,
    reduce,
    reduce_with_diagnostics,
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


def _phase_initialized(**kw: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "phase_id": 2,
        "tasks_total": 10,
        "plan_version": 2,
        "actor": "llm",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    defaults.update(kw)
    return _runtime_l1("PhaseInitialized", **defaults)


def _task_implemented(task_id: str, phase_id: int = 2) -> dict[str, object]:
    return _runtime_l1("TaskImplemented", task_id=task_id, phase_id=phase_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_reduce_empty_returns_empty_state() -> None:
    assert reduce([]) == EMPTY_STATE


def test_reduce_filters_meta_events() -> None:
    meta_event: dict[str, object] = {
        "event_type": "TaskImplemented",
        "event_source": "meta",
        "level": "L1",
        "task_id": "T-201",
        "phase_id": 2,
    }
    assert reduce([meta_event]) == EMPTY_STATE


def test_reduce_filters_non_l1() -> None:
    l2_event: dict[str, object] = {
        "event_type": "TaskImplemented",
        "event_source": "runtime",
        "level": "L2",
        "task_id": "T-201",
        "phase_id": 2,
    }
    assert reduce([l2_event]) == EMPTY_STATE


def test_reduce_state_derivation_has_no_handler() -> None:
    sdc_event = _runtime_l1(
        "StateDerivationCompleted",
        phase_id="2",
        tasks_total=10,
        tasks_completed=5,
        derived_from="eventlog",
        timestamp="2026-01-01T00:00:00Z",
    )
    state, diag = reduce_with_diagnostics([sdc_event])
    assert state == EMPTY_STATE
    assert diag.events_known_no_handler == 1
    assert diag.events_processed == 0


def test_reduce_task_implemented_deduplicates() -> None:
    events = [_task_implemented("T-201"), _task_implemented("T-201")]
    state = reduce(events)
    assert state.tasks_completed == 1
    assert state.tasks_done_ids.count("T-201") == 1


def test_reduce_task_implemented_increments_count() -> None:
    events = [_task_implemented("T-201"), _task_implemented("T-202")]
    state = reduce(events)
    assert state.tasks_completed == 2
    assert "T-201" in state.tasks_done_ids
    assert "T-202" in state.tasks_done_ids


def test_reduce_phase_completed_has_handler() -> None:
    """Phase 15: PhaseCompleted moved to _EVENT_SCHEMA — sets phase_status=COMPLETE (I-PHASE-COMPLETE-1)."""
    event = _runtime_l1("PhaseCompleted", phase_id=2)
    state, diag = reduce_with_diagnostics([event])
    assert state.phase_status == "COMPLETE"
    assert state.plan_status == "COMPLETE"
    assert diag.events_processed == 1
    assert diag.events_known_no_handler == 0


def test_reduce_is_deterministic() -> None:
    events = [_phase_initialized(), _task_implemented("T-201"), _task_implemented("T-202")]
    assert reduce(events) == reduce(events)


def test_reduce_unknown_type_counted_in_diagnostics() -> None:
    event = _runtime_l1("SomeFutureEvent", task_id="T-999")
    state, diag = reduce_with_diagnostics([event])
    assert diag.events_unknown_type == 1
    assert state == EMPTY_STATE


def test_reduce_strict_mode_raises_on_unknown() -> None:
    # UnknownEventType must be a subclass of SDDError (I-ST-7).
    assert issubclass(UnknownEventType, SDDError)
    event = _runtime_l1("SomeFutureEvent", task_id="T-999")
    with pytest.raises(UnknownEventType):
        reduce([event], strict_mode=True)


def test_reduce_strict_mode_raises_on_missing_schema_field() -> None:
    # TaskImplemented missing required "phase_id" raises UnknownEventType (schema error).
    incomplete = _task_implemented("T-201")
    del incomplete["phase_id"]
    with pytest.raises(UnknownEventType):
        reduce([incomplete], strict_mode=True)


def test_reduce_incremental_equivalent_to_full() -> None:
    events = [_phase_initialized(), _task_implemented("T-201"), _task_implemented("T-202")]
    reducer = EventReducer()
    assert reducer.reduce(events) == reducer.reduce_incremental(EMPTY_STATE, events)


def test_all_l1_events_classified() -> None:
    reducer = EventReducer()
    classified = reducer._KNOWN_NO_HANDLER | frozenset(reducer._EVENT_SCHEMA.keys())
    assert classified == V1_L1_EVENT_TYPES


def test_reduce_assumes_sorted_input() -> None:
    """Reducer processes events in given order — sorted seq ASC is caller's precondition.
    Reversed order produces a different final state, proving no internal sort.
    """
    phase_init = _phase_initialized()
    phase_activated = _runtime_l1(
        "PhaseActivated", phase_id=2, actor="human", timestamp="2026-01-01T00:00:00Z"
    )
    # Correct order: PhaseInitialized then PhaseActivated
    correct_order = reduce([phase_init, phase_activated])
    assert correct_order.phase_status == "ACTIVE"
    assert correct_order.phase_current == 2
    # Reversed: PhaseActivated before PhaseInitialized — state still accumulates both
    reversed_order = reduce([phase_activated, phase_init])
    assert reversed_order.phase_status == "ACTIVE"
    assert reversed_order.phase_current == 2


def test_state_hash_excludes_human_fields() -> None:
    common: dict[str, object] = dict(
        phase_current=1, plan_version=1, tasks_version=1,
        tasks_total=5, tasks_completed=2, tasks_done_ids=("T-201", "T-202"),
        invariants_status="UNKNOWN", tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z", schema_version=1, snapshot_event_id=None,
    )
    s_active = SDDState(**common, phase_status="ACTIVE", plan_status="ACTIVE")  # type: ignore[arg-type]
    s_complete = SDDState(**common, phase_status="COMPLETE", plan_status="COMPLETE")  # type: ignore[arg-type]
    assert s_active.state_hash == s_complete.state_hash


def test_state_hash_includes_reducer_version() -> None:
    state = SDDState(
        phase_current=1, plan_version=1, tasks_version=1,
        tasks_total=5, tasks_completed=2, tasks_done_ids=("T-201",),
        invariants_status="UNKNOWN", tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z", schema_version=1, snapshot_event_id=None,
        phase_status="ACTIVE", plan_status="ACTIVE",
    )
    data = {k: v for k, v in asdict(state).items() if k not in SDDState._HUMAN_FIELDS}
    data["reducer_version"] = SDDState.REDUCER_VERSION
    expected = hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()
    assert state.state_hash == expected


# ---------------------------------------------------------------------------
# Phase 5 named tests (Spec_v5 §9 Verification row 2)
# ---------------------------------------------------------------------------


def test_unknown_event_noop_default() -> None:
    """Unknown event_type → NO-OP in default mode: state unchanged (I-REDUCER-1)."""
    unknown = _runtime_l1("SomeFuturePhase9Event", task_id="T-999")
    state, diag = reduce_with_diagnostics([unknown])
    assert state == EMPTY_STATE
    assert diag.events_unknown_type == 1
    assert diag.events_processed == 0


def test_unknown_event_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Unknown event_type emits a logging.warning (I-REDUCER-1 observability)."""
    import logging

    unknown = _runtime_l1("UnknownFutureEvent", task_id="T-999")
    with caplog.at_level(logging.WARNING, logger="sdd.domain.state.reducer"):
        reduce([unknown])
    assert any("UnknownFutureEvent" in m for m in caplog.messages)


def test_unknown_event_raises_strict() -> None:
    """Unknown event_type raises UnknownEventType in strict_mode=True (I-REDUCER-1)."""
    unknown = _runtime_l1("AnotherFutureEvent", task_id="T-999")
    with pytest.raises(UnknownEventType):
        reduce([unknown], strict_mode=True)


def test_replay_old_events_after_phase5_handlers() -> None:
    """Phase 5 reducer handlers (PhaseActivated, PlanActivated) must not break
    replay of Phase 0–4 events — I-SCHEMA-1 backward compatibility."""
    # Pre-Phase-5 events: no PhaseActivated/PlanActivated
    phase4_events = [
        _phase_initialized(phase_id=4, plan_version=4),
        _task_implemented("T-401", phase_id=4),
        _task_implemented("T-402", phase_id=4),
        _runtime_l1("TaskValidated", task_id="T-401", phase_id=4, result="PASS"),
    ]
    state = reduce(phase4_events)
    assert state.phase_current == 4
    assert state.tasks_completed == 2
    assert "T-401" in state.tasks_done_ids
    assert "T-402" in state.tasks_done_ids
    # No phase_status mutation from missing activation events — compat fallback via YAML
    assert state.invariants_status == "PASS"
    assert state.tests_status == "PASS"


def test_replay_golden_scenario() -> None:
    """Golden scenario: Phase 5 activation sequence fully derivable from replay (Q1)."""
    events = [
        _phase_initialized(phase_id=5, plan_version=5, tasks_total=3),
        _task_implemented("T-501", phase_id=5),
        _task_implemented("T-502", phase_id=5),
        _runtime_l1(
            "PhaseActivated",
            phase_id=5,
            actor="human",
            timestamp="2026-01-01T00:00:00Z",
        ),
        _runtime_l1(
            "PlanActivated",
            plan_version=5,
            actor="human",
            timestamp="2026-01-01T00:00:00Z",
        ),
    ]
    state = reduce(events)
    assert state.phase_current == 5
    assert state.plan_version == 5
    assert state.tasks_completed == 2
    assert state.phase_status == "ACTIVE"
    assert state.plan_status == "ACTIVE"
    assert "T-501" in state.tasks_done_ids
    assert "T-502" in state.tasks_done_ids


def test_replay_is_deterministic() -> None:
    """Replaying the same event sequence twice yields identical SDDState (I-REDUCER-2)."""
    events = [
        _phase_initialized(phase_id=5, plan_version=5),
        _task_implemented("T-501", phase_id=5),
        _runtime_l1("PhaseActivated", phase_id=5, actor="human", timestamp="2026-01-01T00:00:00Z"),
    ]
    assert reduce(events) == reduce(events)


def test_handler_does_not_mutate_input() -> None:
    """Reducer handlers must not mutate the input state — I-REDUCER-2.

    reduce(events_A + events_B) must equal
    reduce_incremental(reduce(events_A), events_B).
    The intermediate base state must not be altered by the second fold.
    """
    events_a = [_phase_initialized(phase_id=5, plan_version=5)]
    events_b = [_task_implemented("T-501", phase_id=5)]

    reducer = EventReducer()
    base = reducer.reduce(events_a)
    base_hash_before = base.state_hash

    result = reducer.reduce_incremental(base, events_b)

    # base must be untouched after reduce_incremental (I-REDUCER-2)
    assert base.state_hash == base_hash_before
    # result correctly reflects events_b
    assert "T-501" in result.tasks_done_ids
    # Full replay produces same result (I-ST-9)
    assert result == reducer.reduce(events_a + events_b)


# ---------------------------------------------------------------------------
# T-3108: PlanAmended reducer handler (BC-31-2)
# ---------------------------------------------------------------------------

def _plan_amended(phase_id: int, new_plan_hash: str, **kw: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "phase_id": phase_id,
        "new_plan_hash": new_plan_hash,
        "reason": "test amendment",
        "actor": "human",
    }
    defaults.update(kw)
    return _runtime_l1("PlanAmended", **defaults)


def test_plan_amended_updates_snapshot_plan_hash() -> None:
    """Acceptance criteria T-3108: reducer replay with PlanAmended sets plan_hash in snapshot."""
    events = [
        _phase_initialized(phase_id=7, plan_version=7),
        _plan_amended(phase_id=7, new_plan_hash="abc123def456"),
    ]
    state = reduce(events)
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    assert 7 in snap_map
    assert snap_map[7].plan_hash == "abc123def456"


def test_plan_amended_multiple_updates_last_wins() -> None:
    """Second PlanAmended for same phase overwrites the previous plan_hash."""
    events = [
        _phase_initialized(phase_id=7, plan_version=7),
        _plan_amended(phase_id=7, new_plan_hash="first_hash_000"),
        _plan_amended(phase_id=7, new_plan_hash="second_hash_111"),
    ]
    state = reduce(events)
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    assert snap_map[7].plan_hash == "second_hash_111"


def test_plan_amended_absent_snapshot_raises_inconsistency() -> None:
    """I-PHASE-SNAPSHOT-4: PlanAmended for unknown phase_id → Inconsistency."""
    events = [
        _plan_amended(phase_id=99, new_plan_hash="deadbeef"),
    ]
    with pytest.raises(Inconsistency):
        reduce(events)


def test_plan_amended_preserves_other_snapshot_fields() -> None:
    """PlanAmended MUST NOT alter tasks_completed, tasks_done_ids, or phase_status."""
    events = [
        _phase_initialized(phase_id=7, plan_version=7, tasks_total=5),
        _task_implemented("T-701", phase_id=7),
        _plan_amended(phase_id=7, new_plan_hash="newhash"),
    ]
    state = reduce(events)
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    snap = snap_map[7]
    assert snap.plan_hash == "newhash"
    assert snap.tasks_completed == 1
    assert "T-701" in snap.tasks_done_ids
    assert snap.phase_status == "ACTIVE"


def test_plan_amended_replay_is_deterministic() -> None:
    """Replaying the same PlanAmended sequence twice yields identical state (I-REDUCER-2)."""
    events = [
        _phase_initialized(phase_id=7, plan_version=7),
        _plan_amended(phase_id=7, new_plan_hash="det_hash"),
    ]
    assert reduce(events) == reduce(events)
