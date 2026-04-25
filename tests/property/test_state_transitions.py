"""I-STATE-TRANSITION-1: each DomainEvent has a deterministic and verifiable effect on SDDState.

Relational Properties (Appendix B, Spec_v17):
  RP-1: TaskImplemented → tasks_completed +1, task_id ∈ tasks_done_ids
  RP-2: PhaseStarted (new phase) → tasks_completed == 0, tasks_done_ids == (), phase_current updated
  RP-3: DecisionRecorded → no side-effect on tasks_completed or phase_current
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sdd.core.events import (
    DecisionRecordedEvent,
    EventLevel,
    PhaseStartedEvent,
    TaskImplementedEvent,
)
from tests.harness.fixtures import (
    db_factory,  # noqa: F401 — pytest fixture
    state_builder,  # noqa: F401 — pytest fixture (depends on db_factory)
)


# ---------------------------------------------------------------------------
# Event factories — L1 runtime events eligible for reducer dispatch
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task_implemented(task_id: str, phase_id: int = 1) -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L1,
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id=task_id,
        phase_id=phase_id,
        timestamp=_utc_now(),
    )


def _phase_started(phase_id: int, actor: str = "human") -> PhaseStartedEvent:
    return PhaseStartedEvent(
        event_type="PhaseStarted",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L1,
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=phase_id,
        actor=actor,
    )


def _decision_recorded(decision_id: str, phase_id: int = 1) -> DecisionRecordedEvent:
    return DecisionRecordedEvent(
        event_type="DecisionRecorded",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L1,
        event_source="runtime",
        caused_by_meta_seq=None,
        decision_id=decision_id,
        title=f"Decision {decision_id}",
        summary=f"Summary for {decision_id}",
        phase_id=phase_id,
        timestamp=_utc_now(),
    )


# ---------------------------------------------------------------------------
# RP-1: TaskImplemented delta (I-STATE-TRANSITION-1)
# ---------------------------------------------------------------------------

class TestRP1TaskImplementedDelta:
    """RP-1: TaskImplemented → tasks_completed +1, task_id ∈ tasks_done_ids."""

    def test_tasks_completed_increments_by_one(self, state_builder):
        task_id = "T-RP1-001"
        state_before = state_builder([])
        state_after = state_builder([_task_implemented(task_id)])
        assert state_after.tasks_completed == state_before.tasks_completed + 1

    def test_task_id_appears_in_tasks_done_ids(self, state_builder):
        task_id = "T-RP1-002"
        state_after = state_builder([_task_implemented(task_id)])
        assert task_id in state_after.tasks_done_ids

    def test_duplicate_task_id_not_double_counted(self, state_builder):
        task_id = "T-RP1-003"
        ev = _task_implemented(task_id)
        state_once = state_builder([ev])
        ev_dup = _task_implemented(task_id)
        state_twice = state_builder([ev, ev_dup])
        assert state_twice.tasks_completed == state_once.tasks_completed

    def test_multiple_distinct_tasks_accumulate(self, state_builder):
        task_ids = [f"T-RP1-{i:03d}" for i in range(10, 15)]
        events = [_task_implemented(tid) for tid in task_ids]
        state = state_builder(events)
        assert state.tasks_completed == len(task_ids)
        for tid in task_ids:
            assert tid in state.tasks_done_ids

    def test_sequential_delta_correct_for_each_step(self, state_builder):
        tids = ["T-RP1-SEQ-A", "T-RP1-SEQ-B", "T-RP1-SEQ-C"]
        for n in range(len(tids)):
            state = state_builder([_task_implemented(t) for t in tids[:n + 1]])
            assert state.tasks_completed == n + 1

    def test_phase_current_unaffected_by_task_implemented(self, state_builder):
        ph = _phase_started(phase_id=3)
        state_before = state_builder([ph])
        state_after = state_builder([ph, _task_implemented("T-RP1-PH", phase_id=3)])
        assert state_after.phase_current == state_before.phase_current


# ---------------------------------------------------------------------------
# RP-2: PhaseStarted resets counters (I-STATE-TRANSITION-1)
# ---------------------------------------------------------------------------

class TestRP2PhaseStartedResetsCounters:
    """RP-2: PhaseStarted (new phase) → tasks_completed == 0, tasks_done_ids == (), phase_current updated."""

    def test_tasks_completed_resets_to_zero(self, state_builder):
        tasks = [_task_implemented(f"T-OLD-{i}") for i in range(4)]
        state = state_builder(tasks + [_phase_started(phase_id=2)])
        assert state.tasks_completed == 0

    def test_tasks_done_ids_resets_to_empty_tuple(self, state_builder):
        tasks = [_task_implemented(f"T-PREV-{i}") for i in range(3)]
        state = state_builder(tasks + [_phase_started(phase_id=2)])
        assert state.tasks_done_ids == ()

    def test_phase_current_advances_to_new_phase(self, state_builder):
        state = state_builder([_phase_started(phase_id=7)])
        assert state.phase_current == 7

    def test_tasks_added_after_phase_start_count_fresh(self, state_builder):
        old_tasks = [_task_implemented(f"T-BEFORE-{i}") for i in range(5)]
        new_task = _task_implemented("T-AFTER-PHASE", phase_id=2)
        state = state_builder(old_tasks + [_phase_started(phase_id=2), new_task])
        assert state.tasks_completed == 1
        assert "T-AFTER-PHASE" in state.tasks_done_ids

    def test_regression_phase_id_skipped(self, state_builder):
        # PhaseStarted with phase_id <= current is skipped (A-8, I-PHASE-SEQ-1)
        ph5 = _phase_started(phase_id=5)
        ph3 = _phase_started(phase_id=3)   # regression: 3 <= 5
        state = state_builder([ph5, ph3])
        assert state.phase_current == 5

    def test_sequential_phase_advances_correctly(self, state_builder):
        evs = [_phase_started(phase_id=n) for n in range(1, 6)]
        state = state_builder(evs)
        assert state.phase_current == 5
        assert state.tasks_completed == 0
        assert state.tasks_done_ids == ()


# ---------------------------------------------------------------------------
# RP-3: DecisionRecorded — no side-effect on tasks or phase (I-STATE-TRANSITION-1)
# ---------------------------------------------------------------------------

class TestRP3DecisionRecordedNoSideEffect:
    """RP-3: DecisionRecorded → tasks_completed and phase_current unchanged."""

    def test_tasks_completed_unchanged(self, state_builder):
        task_ev = _task_implemented("T-RP3-001")
        decision_ev = _decision_recorded("D-1")
        state_before = state_builder([task_ev])
        state_after = state_builder([task_ev, decision_ev])
        assert state_after.tasks_completed == state_before.tasks_completed

    def test_phase_current_unchanged(self, state_builder):
        ph = _phase_started(phase_id=4)
        decision_ev = _decision_recorded("D-2", phase_id=4)
        state_before = state_builder([ph])
        state_after = state_builder([ph, decision_ev])
        assert state_after.phase_current == state_before.phase_current

    def test_tasks_done_ids_unchanged(self, state_builder):
        task_ev = _task_implemented("T-RP3-002")
        decision_ev = _decision_recorded("D-3")
        state_before = state_builder([task_ev])
        state_after = state_builder([task_ev, decision_ev])
        assert state_after.tasks_done_ids == state_before.tasks_done_ids

    def test_many_decisions_no_accumulation_on_any_field(self, state_builder):
        task_ev = _task_implemented("T-RP3-003")
        ph_ev = _phase_started(phase_id=1)
        decisions = [_decision_recorded(f"D-{i}", phase_id=1) for i in range(6)]
        state_before = state_builder([ph_ev, task_ev])
        state_after = state_builder([ph_ev, task_ev] + decisions)
        assert state_after.tasks_completed == state_before.tasks_completed
        assert state_after.phase_current == state_before.phase_current
        assert state_after.tasks_done_ids == state_before.tasks_done_ids

    def test_decision_does_not_affect_invariants_status(self, state_builder):
        decision_ev = _decision_recorded("D-STATUS")
        state_before = state_builder([])
        state_after = state_builder([decision_ev])
        assert state_after.invariants_status == state_before.invariants_status
        assert state_after.tests_status == state_before.tests_status
