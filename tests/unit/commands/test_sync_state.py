"""Tests for SyncStateHandler — Spec_v4 §9 Verification row 6.

Invariants: I-CMD-1, I-CMD-8, I-PK-5, I-SYNC-1
"""
from __future__ import annotations

import json
import time
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
    def test_sync_state_writes_atomically(
        self, mock_sync, handler
    ):
        """handle() is pure: sync_projections is not called (I-KERNEL-WRITE-1, I-CI-PURITY-3).

        Emit-first ordering is enforced by execute_and_project in the Write Kernel,
        not by SyncStateHandler.handle() itself.
        """
        handler.handle(_command())

        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# test_sync_state_emits_synced_event  (I-CMD-8, I-ES-2)
# Handler returns a list containing exactly one StateSynced event.
# ---------------------------------------------------------------------------

class TestEventEmission:
    @patch("sdd.commands.update_state.sync_projections")
    def test_sync_state_emits_synced_event(
        self, mock_sync, handler
    ):
        """Returned events contain exactly one StateSynced event with correct fields."""
        cmd = _command(phase_id=4)

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
    @patch("sdd.commands.update_state.sync_projections")
    def test_sync_state_idempotent(
        self, mock_sync, handler
    ):
        """Duplicate command_id returns [] with no sync calls (I-CMD-1)."""
        cmd = _command()

        conn = open_sdd_connection(handler._db_path)
        try:
            conn.execute(
                "INSERT INTO events (seq, event_id, event_type, payload, appended_at) "
                "VALUES (nextval('sdd_event_seq'), ?, 'StateSynced', ?, ?)",
                [
                    str(uuid.uuid4()),
                    json.dumps({"command_id": cmd.command_id, "_source": "test"}),
                    int(time.time() * 1000),
                ],
            )
        finally:
            conn.close()

        result = handler.handle(cmd)

        assert result == []
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# test_sync_uses_atomic_write  (I-PK-5)
# rebuild_state → write_state → atomic_write; verified by patching atomic_write.
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    @patch("sdd.commands.update_state.sync_projections")
    def test_sync_uses_atomic_write(
        self, mock_sync, handler
    ):
        """handle() does not call sync_projections — projection is the caller's responsibility (I-KERNEL-PROJECT-1).

        Projection rebuild (sync_projections → rebuild_taskset + rebuild_state → atomic_write)
        is now orchestrated by execute_and_project in the Write Kernel.
        """
        cmd = _command(taskset_path="fake/TaskSet_v4.md", state_path="fake/State_index.yaml")

        handler.handle(cmd)

        mock_sync.assert_not_called()

    @patch("sdd.commands.update_state.sync_projections")
    def test_rebuild_not_called_when_append_fails(
        self, mock_sync, handler
    ):
        """handle() never calls sync_projections — the handler is purely functional (I-KERNEL-WRITE-1)."""
        events = handler.handle(_command())

        mock_sync.assert_not_called()
        assert len(events) == 1
