"""Tests for SyncStateHandler — Spec_v4 §9 Verification row 6.

Invariants: I-CMD-1, I-CMD-8, I-PK-5, I-SYNC-1
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.update_state import SyncStateCommand, SyncStateHandler
from sdd.infra.db import open_sdd_connection


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def handler(tmp_path):
    return SyncStateHandler(db_path=str(tmp_path / "test.duckdb"))


def _command(
    phase_id: int = 4,
    taskset_path: str = "fake/TaskSet_v4.md",
    state_path: str = "fake/State_index.yaml",
    command_id: str | None = None,
) -> SyncStateCommand:
    return SyncStateCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="SyncStateCommand",
        payload={},
        phase_id=phase_id,
        taskset_path=taskset_path,
        state_path=state_path,
    )


# ---------------------------------------------------------------------------
# test_sync_state_writes_atomically  (I-ES-1, I-CMD-8)
# StateSyncedEvent is appended BEFORE rebuild_state is called.
# ---------------------------------------------------------------------------

class TestEmitFirst:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    def test_sync_state_writes_atomically(
        self, mock_event_store_cls, mock_sync, handler
    ):
        """EventStore.append is called before sync_projections (emit-first, I-ES-1, I-CMD-8, I-SYNC-1)."""
        call_order: list[str] = []

        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store
        mock_store.append.side_effect = lambda *a, **kw: call_order.append("append")
        mock_sync.side_effect = lambda *a, **kw: call_order.append("sync")

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(_command())

        assert call_order == ["append", "sync"]


# ---------------------------------------------------------------------------
# test_sync_state_emits_synced_event  (I-CMD-8, I-ES-2)
# Handler returns a list containing exactly one StateSynced event.
# ---------------------------------------------------------------------------

class TestEventEmission:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    def test_sync_state_emits_synced_event(
        self, mock_event_store_cls, mock_sync, handler
    ):
        """Returned events contain exactly one StateSynced event with correct fields."""
        mock_event_store_cls.return_value = MagicMock()
        cmd = _command(phase_id=4)

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(cmd)

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "StateSynced"
        assert ev.phase_id == 4       # type: ignore[attr-defined]
        assert ev.level == "L2"
        assert ev.event_source == "runtime"


# ---------------------------------------------------------------------------
# test_sync_state_idempotent  (I-CMD-1)
# Duplicate command_id returns [] without emitting or rebuilding.
# ---------------------------------------------------------------------------

class TestIdempotency:
    @patch("sdd.commands.update_state.rebuild_state")
    @patch("sdd.commands.update_state.EventStore")
    def test_sync_state_idempotent(
        self, mock_event_store_cls, mock_rebuild, handler
    ):
        """Duplicate command_id returns [] with no append or rebuild calls (I-CMD-1)."""
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store

        with patch.object(handler, "_check_idempotent", return_value=True):
            result = handler.handle(_command())

        assert result == []
        mock_store.append.assert_not_called()
        mock_rebuild.assert_not_called()


# ---------------------------------------------------------------------------
# test_sync_uses_atomic_write  (I-PK-5)
# rebuild_state → write_state → atomic_write; verified by patching atomic_write.
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    def test_sync_uses_atomic_write(
        self, mock_event_store_cls, mock_sync, handler
    ):
        """sync_projections is called with db_path, taskset_path, state_path (I-PK-5, I-CMD-8, I-SYNC-1).

        sync_projections → rebuild_taskset + rebuild_state → atomic_write;
        we verify the correct arguments reach sync_projections.
        """
        mock_event_store_cls.return_value = MagicMock()
        cmd = _command(taskset_path="fake/TaskSet_v4.md", state_path="fake/State_index.yaml")

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(cmd)

        mock_sync.assert_called_once_with(handler._db_path, cmd.taskset_path, cmd.state_path)

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    def test_rebuild_not_called_when_append_fails(
        self, mock_event_store_cls, mock_sync, handler
    ):
        """sync_projections never called when EventStore.append raises (atomicity guard, I-SYNC-1)."""
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store
        mock_store.append.side_effect = RuntimeError("DuckDB write failed")

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(RuntimeError, match="DuckDB write failed"):
                handler.handle(_command())

        mock_sync.assert_not_called()
