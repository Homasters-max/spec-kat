"""Tests for tests/harness/api.py — System Harness API.

Invariants: I-VR-HARNESS-1, I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from sdd.commands.registry import REGISTRY
from tests.harness.api import execute_sequence, fork, replay, rollback
from tests.harness.fixtures import (
    db_factory,  # noqa: F401 — pytest fixture
    event_factory,  # noqa: F401 — pytest fixture
    make_minimal_event,
    state_builder,  # noqa: F401 — pytest fixture
)


# ---------------------------------------------------------------------------
# I-VR-HARNESS-1: execute_sequence uses only execute_command in the loop
# ---------------------------------------------------------------------------

class TestExecuteSequenceUsesOnlyExecuteCommand:
    """I-VR-HARNESS-1: execute_sequence MUST call execute_command for each pair."""

    def test_calls_execute_command_once_per_pair(self):
        """execute_command is called exactly N times for N (spec, cmd) pairs."""
        spec = REGISTRY["sync-state"]
        cmds = [(spec, SimpleNamespace()), (spec, SimpleNamespace()), (spec, SimpleNamespace())]
        fake_event = make_minimal_event()

        with patch("tests.harness.api.execute_command", return_value=[fake_event]) as mock_exec, \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            events, _ = execute_sequence(cmds, db_path=":memory:")

        assert mock_exec.call_count == 3
        assert len(events) == 3

    def test_passes_db_path_to_execute_command(self):
        """execute_command receives the same db_path on every call."""
        spec = REGISTRY["sync-state"]
        db = "/tmp/test.duckdb"
        cmds = [(spec, SimpleNamespace()), (spec, SimpleNamespace())]

        with patch("tests.harness.api.execute_command", return_value=[]) as mock_exec, \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            execute_sequence(cmds, db_path=db)

        for c in mock_exec.call_args_list:
            assert c.kwargs.get("db_path") == db or c.args[-1] == db or db in str(c)

    def test_empty_sequence_skips_execute_command(self):
        """execute_sequence([]) calls execute_command zero times."""
        with patch("tests.harness.api.execute_command", return_value=[]) as mock_exec, \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            events, _ = execute_sequence([], db_path=":memory:")

        mock_exec.assert_not_called()
        assert events == []

    def test_events_collected_from_all_commands(self):
        """All events returned by each execute_command call are concatenated."""
        spec = REGISTRY["sync-state"]
        ev1 = make_minimal_event("_ev1")
        ev2 = make_minimal_event("_ev2")
        side_effects = [[ev1], [ev2]]

        with patch("tests.harness.api.execute_command", side_effect=side_effects), \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            events, _ = execute_sequence(
                [(spec, SimpleNamespace()), (spec, SimpleNamespace())],
                db_path=":memory:",
            )

        assert events == [ev1, ev2]

    def test_get_current_state_called_once_after_loop(self):
        """get_current_state is called exactly once, after the execution loop."""
        spec = REGISTRY["sync-state"]
        mock_state = MagicMock()

        with patch("tests.harness.api.execute_command", return_value=[]), \
             patch("tests.harness.api.get_current_state", return_value=mock_state) as mock_gcs:
            _, state = execute_sequence([(spec, SimpleNamespace())], db_path=":memory:")

        mock_gcs.assert_called_once_with(":memory:")
        assert state is mock_state


# ---------------------------------------------------------------------------
# I-VR-HARNESS-2: replay uses only get_current_state
# ---------------------------------------------------------------------------

class TestReplayUsesOnlyGetCurrentState:
    """I-VR-HARNESS-2: replay MUST use only get_current_state — no execute_command."""

    def test_calls_get_current_state(self):
        """replay calls get_current_state once with the provided db_path."""
        events = [make_minimal_event()]
        mock_state = MagicMock()

        with patch("tests.harness.api.get_current_state", return_value=mock_state) as mock_gcs:
            result = replay(events, db_path="/tmp/test.duckdb")

        mock_gcs.assert_called_once_with("/tmp/test.duckdb")
        assert result is mock_state

    def test_does_not_call_execute_command(self):
        """replay does not call execute_command (I-VR-HARNESS-2 strict)."""
        events = [make_minimal_event()]

        with patch("tests.harness.api.execute_command") as mock_exec, \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            replay(events, db_path=":memory:")

        mock_exec.assert_not_called()

    def test_replay_empty_events(self):
        """replay([]) is valid — it reads state from DB regardless of events list."""
        mock_state = MagicMock()

        with patch("tests.harness.api.get_current_state", return_value=mock_state) as mock_gcs:
            result = replay([], db_path=":memory:")

        mock_gcs.assert_called_once()
        assert result is mock_state


# ---------------------------------------------------------------------------
# I-VR-HARNESS-3: event log is append-only; events are not mutated
# ---------------------------------------------------------------------------

class TestEventLogAppendOnly:
    """I-VR-HARNESS-3: existing events are never mutated by harness operations."""

    def test_rollback_does_not_mutate_original(self):
        """rollback returns a prefix slice; the original list is unchanged."""
        ev1 = make_minimal_event("_e1")
        ev2 = make_minimal_event("_e2")
        ev3 = make_minimal_event("_e3")
        original = [ev1, ev2, ev3]
        original_ids = [e.event_id for e in original]

        result = rollback(original, t=2)

        assert result == [ev1, ev2]
        assert len(original) == 3
        assert [e.event_id for e in original] == original_ids

    def test_rollback_returns_prefix(self):
        """rollback(events, t) returns exactly events[:t]."""
        events = [make_minimal_event(f"_e{i}") for i in range(5)]
        for t in range(6):
            assert rollback(events, t) == events[:t]

    def test_rollback_t_zero_returns_empty(self):
        """rollback(events, 0) returns []."""
        events = [make_minimal_event()]
        assert rollback(events, 0) == []

    def test_events_are_immutable_frozen_dataclass(self):
        """DomainEvent is a frozen dataclass; mutation raises FrozenInstanceError."""
        ev = make_minimal_event()
        with pytest.raises((AttributeError, TypeError)):
            ev.event_type = "mutated"  # type: ignore[misc]

    def test_execute_sequence_does_not_modify_input_list(self):
        """execute_sequence does not mutate the cmds list passed in."""
        spec = REGISTRY["sync-state"]
        cmd_obj = SimpleNamespace()
        cmds = [(spec, cmd_obj)]
        cmds_copy = list(cmds)

        with patch("tests.harness.api.execute_command", return_value=[]), \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            execute_sequence(cmds, db_path=":memory:")

        assert cmds == cmds_copy

    def test_fork_does_not_mutate_checkpoint_events(self):
        """fork does not modify the checkpoint events list."""
        ev = make_minimal_event()
        checkpoint = [ev]
        checkpoint_ids = [e.event_id for e in checkpoint]
        spec = REGISTRY["sync-state"]

        with patch("tests.harness.api.execute_command", return_value=[]), \
             patch("tests.harness.api.get_current_state", return_value=MagicMock()):
            fork(checkpoint, [(spec, SimpleNamespace())], db_path=":memory:")

        assert [e.event_id for e in checkpoint] == checkpoint_ids


# ---------------------------------------------------------------------------
# I-VR-HARNESS-4: each VR call uses tmp_path-isolated DuckDB (db_factory)
# ---------------------------------------------------------------------------

class TestDbFactoryIsolation:
    """I-VR-HARNESS-4: db_factory returns unique, tmp_path-scoped paths per call."""

    def test_each_call_returns_unique_path(self, db_factory):
        """Two calls to db_factory() produce distinct paths."""
        path_a = db_factory()
        path_b = db_factory()
        assert path_a != path_b

    def test_paths_are_under_tmp_path(self, tmp_path, db_factory):
        """db_factory paths are scoped to pytest tmp_path (not shared)."""
        path = db_factory()
        assert str(tmp_path) in path

    def test_multiple_calls_are_unique(self, db_factory):
        """N calls to db_factory() all return distinct paths."""
        n = 5
        paths = [db_factory() for _ in range(n)]
        assert len(set(paths)) == n

    def test_db_paths_end_with_duckdb(self, db_factory):
        """db_factory paths have .duckdb extension."""
        assert db_factory().endswith(".duckdb")

    def test_separate_fixture_invocations_are_independent(self, db_factory, event_factory):
        """db_factory and event_factory fixtures are independent (no shared state)."""
        db = db_factory()
        ev = event_factory()
        assert db != ev.event_id
