"""Tests for CompleteTaskHandler — Spec_v4 §9 Verification row 4.

Invariants: I-CMD-1, I-CMD-4, I-ES-1, I-ES-2, I-ES-4, I-SYNC-1
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.update_state import CompleteTaskCommand, CompleteTaskHandler, main
from sdd.core.errors import MissingContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _command(task_id: str = "T-401", phase_id: int = 4) -> CompleteTaskCommand:
    return CompleteTaskCommand(
        command_id=str(uuid.uuid4()),
        command_type="CompleteTask",
        payload={},
        task_id=task_id,
        phase_id=phase_id,
        taskset_path="fake/TaskSet_v4.md",
        state_path="fake/State_index.yaml",
    )


def _task(task_id: str = "T-401", status: str = "TODO") -> MagicMock:
    t = MagicMock()
    t.task_id = task_id
    t.status = status
    return t


@pytest.fixture
def handler(tmp_path):
    return CompleteTaskHandler(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# Emit-first ordering (I-ES-1, I-CMD-4)
# ---------------------------------------------------------------------------

class TestEmitFirst:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_appends_event_before_file_write(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """EventStore.append is called before sync_projections (I-ES-1, I-CMD-4, I-SYNC-1)."""
        call_order: list[str] = []

        mock_parse.return_value = [_task("T-401")]
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store
        mock_store.append.side_effect = lambda *a, **kw: call_order.append("append")
        mock_sync.side_effect = lambda *a, **kw: call_order.append("sync")

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(_command("T-401"))

        assert call_order == ["append", "sync"]

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_syncs_both_projections_after_append(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """sync_projections called with db_path, taskset_path, state_path (I-ES-4, I-SYNC-1)."""
        mock_parse.return_value = [_task("T-401")]
        mock_event_store_cls.return_value = MagicMock()
        cmd = _command("T-401")

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(cmd)

        mock_sync.assert_called_once_with(handler._db_path, cmd.taskset_path, cmd.state_path)


# ---------------------------------------------------------------------------
# Batch emission (I-ES-2)
# ---------------------------------------------------------------------------

class TestBatchEmission:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_emits_batch(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """Handler returns [TaskImplemented, MetricRecorded] and passes both to append (I-ES-2)."""
        mock_parse.return_value = [_task("T-401")]
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command("T-401"))

        assert len(events) == 2
        event_types = {e.event_type for e in events}
        assert event_types == {"TaskImplemented", "MetricRecorded"}

        appended_batch = mock_store.append.call_args[0][0]
        assert len(appended_batch) == 2


# ---------------------------------------------------------------------------
# Idempotency (I-CMD-1, I-CMD-2b)
# ---------------------------------------------------------------------------

class TestIdempotency:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_idempotent(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """Duplicate command_id returns [] without emitting or syncing (I-CMD-1)."""
        mock_parse.return_value = [_task("T-401")]
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store

        with patch.object(handler, "_check_idempotent", return_value=True):
            result = handler.handle(_command("T-401"))

        assert result == []
        mock_store.append.assert_not_called()
        mock_sync.assert_not_called()

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_semantic_idempotent(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """Semantic duplicate (same task_id+phase_id) is detected and returns [] (I-CMD-2b)."""
        mock_parse.return_value = [_task("T-401")]
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store

        with patch.object(handler, "_check_idempotent", return_value=True):
            result = handler.handle(_command("T-401"))

        assert result == []
        mock_store.append.assert_not_called()
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_missing_task_raises(
        self, mock_parse, mock_event_store_cls, handler
    ):
        """MissingContext raised when task_id is absent from TaskSet."""
        mock_parse.return_value = [_task("T-999")]
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(MissingContext):
                handler.handle(_command("T-401"))

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_already_done_is_noop(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """Already-DONE task: returns [], no events, sync_projections called once (§R.11, I-CMD-2b, I-SYNC-1)."""
        mock_parse.return_value = [_task("T-401", status="DONE")]
        mock_event_store_cls.return_value = MagicMock()
        cmd = _command("T-401")

        with patch.object(handler, "_check_idempotent", return_value=False):
            result = handler.handle(cmd)

        assert result == []
        mock_event_store_cls.return_value.append.assert_not_called()
        mock_sync.assert_called_once_with(handler._db_path, cmd.taskset_path, cmd.state_path)


# ---------------------------------------------------------------------------
# Atomicity (I-ES-1)
# ---------------------------------------------------------------------------

class TestAtomicity:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_batch_is_atomic_on_failure(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """sync_projections never called when EventStore.append raises (I-ES-1 atomicity, I-SYNC-1)."""
        mock_parse.return_value = [_task("T-401")]
        mock_store = MagicMock()
        mock_event_store_cls.return_value = mock_store
        mock_store.append.side_effect = RuntimeError("DuckDB write failed")

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(RuntimeError, match="DuckDB write failed"):
                handler.handle(_command("T-401"))

        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# No direct file writes (I-CMD-4)
# ---------------------------------------------------------------------------

class TestNoDirectFileWrite:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.EventStore")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_no_direct_file_write_in_handler(
        self, mock_parse, mock_event_store_cls, mock_sync, handler
    ):
        """Handler never calls open() directly; all file mutations go through sync_projections (I-SYNC-1)."""
        mock_parse.return_value = [_task("T-401")]
        mock_event_store_cls.return_value = MagicMock()

        with patch.object(handler, "_check_idempotent", return_value=False):
            with patch("builtins.open") as mock_open:
                handler.handle(_command("T-401"))
                mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Status signal (stdout JSON)  — I-SYNC-1, §R.11
# ---------------------------------------------------------------------------

class TestStatusSignal:
    def test_complete_new_task_emits_done_signal(self, tmp_path, capsys):
        """main() prints {"status": "done", "task_id": ...} when task transitions TODO → DONE."""
        import yaml
        from sdd.infra.projections import rebuild_state, rebuild_taskset

        taskset = tmp_path / "TaskSet_v4.md"
        taskset.write_text("T-401: My task\n\nStatus:               TODO\n")

        state_file = tmp_path / "State_index.yaml"
        state_file.write_text(yaml.dump({
            "phase": {"current": 4, "status": "ACTIVE"},
            "plan": {"version": 4, "status": "ACTIVE"},
            "tasks": {"version": 4, "total": 1, "completed": 0, "done_ids": []},
            "invariants": {"status": "UNKNOWN"},
            "tests": {"status": "UNKNOWN"},
            "meta": {"last_updated": "2026-01-01T00:00:00Z", "schema_version": 1,
                     "snapshot_event_id": None},
        }))

        db = str(tmp_path / "events.duckdb")
        rc = main([
            "complete", "T-401",
            "--phase", "4",
            "--taskset", str(taskset),
            "--state", str(state_file),
            "--db", db,
        ])

        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["status"] == "done"
        assert out["task_id"] == "T-401"

    def test_complete_already_done_emits_noop_signal(self, tmp_path, capsys):
        """main() prints {"status": "noop", "task_id": ...} when task is already DONE."""
        import yaml

        taskset = tmp_path / "TaskSet_v4.md"
        taskset.write_text("T-401: My task\n\nStatus:               DONE\n")

        state_file = tmp_path / "State_index.yaml"
        state_file.write_text(yaml.dump({
            "phase": {"current": 4, "status": "ACTIVE"},
            "plan": {"version": 4, "status": "ACTIVE"},
            "tasks": {"version": 4, "total": 1, "completed": 1,
                      "done_ids": ["T-401"]},
            "invariants": {"status": "UNKNOWN"},
            "tests": {"status": "UNKNOWN"},
            "meta": {"last_updated": "2026-01-01T00:00:00Z", "schema_version": 1,
                     "snapshot_event_id": None},
        }))

        db = str(tmp_path / "events.duckdb")
        rc = main([
            "complete", "T-401",
            "--phase", "4",
            "--taskset", str(taskset),
            "--state", str(state_file),
            "--db", db,
        ])

        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["status"] == "noop"
        assert out["task_id"] == "T-401"

    def test_complete_exits_zero_for_done(self, tmp_path, capsys):
        """exit code 0 for new task (done path)."""
        import yaml

        taskset = tmp_path / "TaskSet_v4.md"
        taskset.write_text("T-401: My task\n\nStatus:               TODO\n")
        state_file = tmp_path / "State_index.yaml"
        state_file.write_text(yaml.dump({
            "phase": {"current": 4, "status": "ACTIVE"},
            "plan": {"version": 4, "status": "ACTIVE"},
            "tasks": {"version": 4, "total": 1, "completed": 0, "done_ids": []},
            "invariants": {"status": "UNKNOWN"},
            "tests": {"status": "UNKNOWN"},
            "meta": {"last_updated": "2026-01-01T00:00:00Z", "schema_version": 1,
                     "snapshot_event_id": None},
        }))
        db = str(tmp_path / "events.duckdb")
        rc = main([
            "complete", "T-401",
            "--phase", "4", "--taskset", str(taskset),
            "--state", str(state_file), "--db", db,
        ])
        assert rc == 0

    def test_complete_exits_zero_for_noop(self, tmp_path, capsys):
        """exit code 0 for already-done task (noop path, idempotent)."""
        import yaml

        taskset = tmp_path / "TaskSet_v4.md"
        taskset.write_text("T-401: My task\n\nStatus:               DONE\n")
        state_file = tmp_path / "State_index.yaml"
        state_file.write_text(yaml.dump({
            "phase": {"current": 4, "status": "ACTIVE"},
            "plan": {"version": 4, "status": "ACTIVE"},
            "tasks": {"version": 4, "total": 1, "completed": 1,
                      "done_ids": ["T-401"]},
            "invariants": {"status": "UNKNOWN"},
            "tests": {"status": "UNKNOWN"},
            "meta": {"last_updated": "2026-01-01T00:00:00Z", "schema_version": 1,
                     "snapshot_event_id": None},
        }))
        db = str(tmp_path / "events.duckdb")
        rc = main([
            "complete", "T-401",
            "--phase", "4", "--taskset", str(taskset),
            "--state", str(state_file), "--db", db,
        ])
        assert rc == 0
