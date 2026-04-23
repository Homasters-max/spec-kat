"""Tests for CheckDoDHandler — Spec_v4 §9 Verification row 7.

Invariants: I-CMD-1, I-CMD-5
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.update_state import CheckDoDCommand, CheckDoDHandler
from sdd.core.errors import DoDNotMet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _command(
    phase_id: int = 4,
    state_path: str = "fake/State_index.yaml",
    command_id: str | None = None,
) -> CheckDoDCommand:
    return CheckDoDCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="CheckDoDCommand",
        payload={},
        phase_id=phase_id,
        state_path=state_path,
    )


def _state(
    tasks_completed: int = 5,
    tasks_total: int = 5,
    invariants_status: str = "PASS",
    tests_status: str = "PASS",
) -> MagicMock:
    s = MagicMock()
    s.tasks_completed = tasks_completed
    s.tasks_total = tasks_total
    s.invariants_status = invariants_status
    s.tests_status = tests_status
    return s


@pytest.fixture
def handler(tmp_path):
    return CheckDoDHandler(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# Happy path (I-CMD-5)
# ---------------------------------------------------------------------------

class TestHappyPath:
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_check_dod_emits_phase_completed_when_all_pass(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """PhaseCompleted + MetricRecorded returned when all DoD conditions met (I-CMD-5)."""
        mock_read_state.return_value = _state()
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command(phase_id=4))

        assert len(events) == 2
        event_types = {e.event_type for e in events}
        assert event_types == {"PhaseCompleted", "MetricRecorded"}

        phase_ev = next(e for e in events if e.event_type == "PhaseCompleted")
        assert phase_ev.phase_id == 4  # type: ignore[attr-defined]
        assert phase_ev.total_tasks == 5  # type: ignore[attr-defined]
        assert phase_ev.level == "L1"
        assert phase_ev.event_source == "runtime"

        metric_ev = next(e for e in events if e.event_type == "MetricRecorded")
        assert metric_ev.metric_id == "phase.completion_time"  # type: ignore[attr-defined]
        assert metric_ev.phase_id == 4  # type: ignore[attr-defined]
        assert metric_ev.task_id is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# DoD guard conditions (I-CMD-5)
# ---------------------------------------------------------------------------

class TestDoDConditions:
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_check_dod_raises_if_tasks_incomplete(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """DoDNotMet raised when tasks.completed < tasks.total (I-CMD-5)."""
        mock_read_state.return_value = _state(tasks_completed=3, tasks_total=5)
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(DoDNotMet, match="not all tasks DONE"):
                handler.handle(_command())

    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_check_dod_raises_if_invariants_fail(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """DoDNotMet raised when invariants.status != PASS (I-CMD-5)."""
        mock_read_state.return_value = _state(invariants_status="FAIL")
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(DoDNotMet, match="invariants not PASS"):
                handler.handle(_command())

    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_check_dod_raises_if_tests_fail(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """DoDNotMet raised when tests.status != PASS (I-CMD-5)."""
        mock_read_state.return_value = _state(tests_status="FAIL")
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(DoDNotMet, match="tests not PASS"):
                handler.handle(_command())


# ---------------------------------------------------------------------------
# Idempotency (I-CMD-1)
# ---------------------------------------------------------------------------

class TestIdempotency:
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_check_dod_idempotent(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """Duplicate command_id returns [] without reading state or emitting (I-CMD-1)."""
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=True):
            result = handler.handle(_command())

        assert result == []
        mock_read_state.assert_not_called()
        mock_event_store_cls.return_value.append.assert_not_called()


# ---------------------------------------------------------------------------
# Batch atomicity (I-ES-1)
# ---------------------------------------------------------------------------

class TestBatchAtomicity:
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.read_state")
    def test_phase_completed_batch_atomic(
        self, mock_read_state, mock_event_store_cls, handler
    ):
        """PhaseCompletedEvent + MetricRecorded appended in a single batch call (I-ES-1)."""
        mock_read_state.return_value = _state()
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(_command())

        mock_store.append.assert_called_once()
        appended = mock_store.append.call_args[0][0]
        assert len(appended) == 2
        event_types = {e.event_type for e in appended}
        assert event_types == {"PhaseCompleted", "MetricRecorded"}
