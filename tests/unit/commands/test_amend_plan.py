"""Tests for amend-plan command handler and PlanAmended reducer.

Covers:
- I-HANDLER-PURE-1: handle() returns events only, no side effects
- I-PLAN-IMMUTABLE-AFTER-ACTIVATE: guard rejects PLANNED phase (§9 #4)
- I-PHASE-SNAPSHOT-1: reducer updates plan_hash in snapshot after PlanAmended (§9 #3)
"""
from __future__ import annotations

import hashlib
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.amend_plan import AmendPlanHandler, _make_amend_plan_guard
from sdd.core.errors import Inconsistency, InvalidState, MissingContext
from sdd.core.events import PlanAmended
from sdd.domain.state.reducer import (
    EMPTY_STATE,
    EventReducer,
    FrozenPhaseSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state_with_status(phase_status: str) -> Any:
    from dataclasses import replace
    return replace(EMPTY_STATE, phase_status=phase_status)


def _guard_ctx(phase_status: str) -> Any:
    return types.SimpleNamespace(state=_make_state_with_status(phase_status))


def _mock_cmd(phase_id: int, reason: str = "test reason", actor: str = "human") -> Any:
    cmd = MagicMock()
    cmd.phase_id = phase_id
    cmd.reason = reason
    cmd.actor = actor
    return cmd


def _phase_init_event(phase_id: int, plan_hash: str = "") -> dict:
    return {
        "event_type": "PhaseInitialized",
        "event_source": "runtime",
        "level": "L1",
        "phase_id": phase_id,
        "tasks_total": 5,
        "plan_version": phase_id,
        "actor": "human",
        "timestamp": "2026-01-01T00:00:00Z",
        "plan_hash": plan_hash,
    }


def _plan_amended_event(phase_id: int, new_hash: str) -> dict:
    return {
        "event_type": "PlanAmended",
        "event_source": "runtime",
        "level": "L1",
        "phase_id": phase_id,
        "new_plan_hash": new_hash,
        "reason": "post-activation amendment",
        "actor": "human",
    }


# ---------------------------------------------------------------------------
# Guard: I-PLAN-IMMUTABLE-AFTER-ACTIVATE
# ---------------------------------------------------------------------------

class TestAmendPlanGuard:
    def test_rejects_planned_phase(self) -> None:
        """§9 #4: guard raises InvalidState when phase_status == PLANNED."""
        guard = _make_amend_plan_guard(phase_id=31)
        with pytest.raises(InvalidState, match="has not been activated"):
            guard(_guard_ctx("PLANNED"))

    def test_allows_active_phase(self) -> None:
        guard = _make_amend_plan_guard(phase_id=31)
        result, events = guard(_guard_ctx("ACTIVE"))
        assert result.outcome.name == "ALLOW"
        assert events == []

    def test_allows_complete_phase(self) -> None:
        guard = _make_amend_plan_guard(phase_id=31)
        result, events = guard(_guard_ctx("COMPLETE"))
        assert result.outcome.name == "ALLOW"
        assert events == []

    def test_error_message_contains_phase_id(self) -> None:
        guard = _make_amend_plan_guard(phase_id=99)
        with pytest.raises(InvalidState, match="99"):
            guard(_guard_ctx("PLANNED"))


# ---------------------------------------------------------------------------
# Handler: I-HANDLER-PURE-1
# ---------------------------------------------------------------------------

class TestAmendPlanHandler:
    """Unit-tests for the pure handle() logic.

    @error_event_boundary adds idempotency check via DuckDB; we patch _check_idempotent
    to False (not yet seen) so the pure handler body runs without a real DB.
    """

    def _handler(self, tmp_path: Path) -> AmendPlanHandler:
        return AmendPlanHandler(db_path=str(tmp_path / "sdd_test.duckdb"))

    def _run(self, handler: AmendPlanHandler, cmd: Any, plan_path: Path) -> list:
        with patch.object(handler, "_check_idempotent", return_value=False):
            with patch("sdd.commands.amend_plan.plan_file", return_value=plan_path):
                return handler.handle(cmd)

    def test_returns_plan_amended_event(self, tmp_path: Path) -> None:
        """§9 #3: handler returns [PlanAmended] — I-HANDLER-PURE-1."""
        plan_path = tmp_path / "Plan_v31.md"
        plan_path.write_text("# Plan v31\n")
        expected_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()[:16]

        handler = self._handler(tmp_path)
        events = self._run(handler, _mock_cmd(phase_id=31, reason="post-fix"), plan_path)

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, PlanAmended)
        assert evt.phase_id == 31
        assert evt.new_plan_hash == expected_hash
        assert evt.reason == "post-fix"
        assert evt.actor == "human"

    def test_handle_returns_list_only(self, tmp_path: Path) -> None:
        """I-HANDLER-PURE-1: handle() returns list[DomainEvent] with no side effects."""
        plan_path = tmp_path / "Plan_v5.md"
        plan_path.write_bytes(b"content")
        handler = self._handler(tmp_path)
        result = self._run(handler, _mock_cmd(phase_id=5), plan_path)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_raises_missing_context_when_plan_absent(self, tmp_path: Path) -> None:
        """Handler raises MissingContext when Plan_vN.md does not exist."""
        missing = tmp_path / "Plan_v99.md"
        handler = self._handler(tmp_path)
        with pytest.raises(MissingContext):
            self._run(handler, _mock_cmd(phase_id=99), missing)

    def test_hash_is_content_dependent(self, tmp_path: Path) -> None:
        """plan_hash is derived from file content — deterministic."""
        plan_path = tmp_path / "Plan_v10.md"
        content = b"# Specific content for hash test\n"
        plan_path.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest()[:16]

        handler = self._handler(tmp_path)
        events = self._run(handler, _mock_cmd(phase_id=10), plan_path)
        assert events[0].new_plan_hash == expected_hash

    def test_actor_passed_through(self, tmp_path: Path) -> None:
        """actor field from cmd is preserved in PlanAmended event."""
        plan_path = tmp_path / "Plan_v1.md"
        plan_path.write_text("x")
        handler = self._handler(tmp_path)
        events = self._run(handler, _mock_cmd(phase_id=1, actor="operator"), plan_path)
        assert events[0].actor == "operator"


# ---------------------------------------------------------------------------
# Reducer: PlanAmended → plan_hash update (BC-31-2, I-PHASE-SNAPSHOT-1)
# ---------------------------------------------------------------------------

class TestPlanAmendedReducer:
    def test_plan_hash_updated_in_snapshot(self) -> None:
        """BC-31-2: plan_hash in snapshot updated after PlanAmended replay."""
        reducer = EventReducer()
        state = reducer.reduce([
            _phase_init_event(31),
            _plan_amended_event(31, "abcdef1234567890"),
        ])
        snap = {s.phase_id: s for s in state.phases_snapshots}[31]
        assert snap.plan_hash == "abcdef1234567890"

    def test_plan_hash_initially_empty(self) -> None:
        """plan_hash is empty string after PhaseInitialized with no plan_hash."""
        reducer = EventReducer()
        state = reducer.reduce([_phase_init_event(31)])
        snap = {s.phase_id: s for s in state.phases_snapshots}[31]
        assert snap.plan_hash == ""

    def test_multiple_amendments_last_wins(self) -> None:
        """Successive PlanAmended events: last hash is authoritative."""
        reducer = EventReducer()
        state = reducer.reduce([
            _phase_init_event(10),
            _plan_amended_event(10, "first_hash_00000"),
            _plan_amended_event(10, "second_hash_1111"),
        ])
        snap = {s.phase_id: s for s in state.phases_snapshots}[10]
        assert snap.plan_hash == "second_hash_1111"

    def test_other_snapshot_fields_unchanged(self) -> None:
        """PlanAmended MUST NOT modify any snapshot field except plan_hash."""
        reducer = EventReducer()
        state = reducer.reduce([
            _phase_init_event(7),
            _plan_amended_event(7, "new_hash_12345678"),
        ])
        snap = {s.phase_id: s for s in state.phases_snapshots}[7]
        assert snap.phase_status == "ACTIVE"
        assert snap.plan_status == "ACTIVE"
        assert snap.tasks_total == 5
        assert snap.tasks_completed == 0
        assert snap.tasks_done_ids == ()
        assert snap.plan_version == 7
        assert snap.invariants_status == "UNKNOWN"
        assert snap.tests_status == "UNKNOWN"

    def test_raises_inconsistency_without_snapshot(self) -> None:
        """I-PHASE-SNAPSHOT-4: PlanAmended without prior PhaseInitialized raises Inconsistency."""
        reducer = EventReducer()
        with pytest.raises(Inconsistency, match="I-PHASE-SNAPSHOT-4"):
            reducer.reduce([_plan_amended_event(99, "orphan_hash")])

    def test_plan_hash_set_from_phase_initialized(self) -> None:
        """plan_hash in PhaseInitialized event is stored in snapshot."""
        reducer = EventReducer()
        state = reducer.reduce([_phase_init_event(5, plan_hash="init_hash_abc123")])
        snap = {s.phase_id: s for s in state.phases_snapshots}[5]
        assert snap.plan_hash == "init_hash_abc123"

    def test_incremental_reduce_consistent_with_full_reduce(self) -> None:
        """I-ST-9: reduce_incremental(base, new) == reduce(all)."""
        events_all = [
            _phase_init_event(3),
            _plan_amended_event(3, "consistency_hash"),
        ]
        reducer = EventReducer()
        full_state = reducer.reduce(events_all)

        base = reducer.reduce([_phase_init_event(3)])
        incremental_state = reducer.reduce_incremental(base, [_plan_amended_event(3, "consistency_hash")])

        snap_full = {s.phase_id: s for s in full_state.phases_snapshots}[3]
        snap_inc = {s.phase_id: s for s in incremental_state.phases_snapshots}[3]
        assert snap_full.plan_hash == snap_inc.plan_hash
