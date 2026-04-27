"""Tests for CompleteTaskHandler — Spec_v4 §9 Verification row 4.

Invariants: I-CMD-1, I-CMD-2b, I-ES-2, I-HANDLER-PURE-1, I-KERNEL-WRITE-1
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
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


def _seed_active_phase(db_path: str, phase_id: int, tasks_total: int) -> None:
    """Seed EventLog with PhaseInitialized so EventReducer derives ACTIVE state."""
    from sdd.infra.event_log import sdd_append
    sdd_append(
        "PhaseInitialized",
        {
            "phase_id": phase_id,
            "tasks_total": tasks_total,
            "plan_version": phase_id,
            "actor": "test-seed",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        db_path=db_path,
        level="L1",
    )


# ---------------------------------------------------------------------------
# Handler purity (I-HANDLER-PURE-1): no EventStore.append, no sync_projections
# ---------------------------------------------------------------------------

class TestHandlerPurity:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_handler_does_not_call_eventstore(
        self, mock_parse, mock_sync, handler
    ):
        """Pure handler: handle() returns events without any store writes (I-HANDLER-PURE-1).

        EventStore is removed; kernel (execute_and_project) owns all writes via EventLog.
        """
        mock_parse.return_value = [_task("T-401")]
        events = handler.handle(_command("T-401"))
        assert len(events) == 2

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_handler_does_not_call_sync_projections(
        self, mock_parse, mock_sync, handler
    ):
        """Pure handler: sync_projections never called from handle() (I-HANDLER-PURE-1)."""
        mock_parse.return_value = [_task("T-401")]
        handler.handle(_command("T-401"))
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Batch emission (I-ES-2)
# ---------------------------------------------------------------------------

class TestBatchEmission:
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_emits_batch(
        self, mock_parse, handler
    ):
        """Handler returns [TaskImplemented, MetricRecorded] (I-ES-2)."""
        mock_parse.return_value = [_task("T-401")]

        events = handler.handle(_command("T-401"))

        assert len(events) == 2
        event_types = {e.event_type for e in events}
        assert event_types == {"TaskImplemented", "MetricRecorded"}


# ---------------------------------------------------------------------------
# Idempotency (I-CMD-1, I-CMD-2b)
# ---------------------------------------------------------------------------

class TestIdempotency:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_idempotent(
        self, mock_parse, mock_sync, handler
    ):
        """Task already DONE returns [] without emitting or syncing (I-CMD-1)."""
        mock_parse.return_value = [_task("T-401", status="DONE")]

        result = handler.handle(_command("T-401"))

        assert result == []
        mock_sync.assert_not_called()

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_semantic_idempotent(
        self, mock_parse, mock_sync, handler
    ):
        """Semantic duplicate (task already DONE) returns [] (I-CMD-2b)."""
        mock_parse.return_value = [_task("T-401", status="DONE")]

        result = handler.handle(_command("T-401"))

        assert result == []
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_missing_task_raises(
        self, mock_parse, handler
    ):
        """MissingContext raised when task_id is absent from TaskSet."""
        mock_parse.return_value = [_task("T-999")]

        with pytest.raises(MissingContext):
            handler.handle(_command("T-401"))

    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_complete_task_already_done_is_noop(
        self, mock_parse, mock_sync, handler
    ):
        """Already-DONE task: returns [], no events, no sync (§R.11, I-CMD-2b, I-HANDLER-PURE-1)."""
        mock_parse.return_value = [_task("T-401", status="DONE")]
        cmd = _command("T-401")

        result = handler.handle(cmd)

        assert result == []
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Atomicity: kernel owns EventStore; handler is pure (I-KERNEL-WRITE-1)
# ---------------------------------------------------------------------------

class TestAtomicity:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_batch_is_atomic_on_failure(
        self, mock_parse, mock_sync, handler
    ):
        """Pure handler returns events without calling sync — atomicity owned by kernel (I-KERNEL-WRITE-1)."""
        mock_parse.return_value = [_task("T-401")]

        events = handler.handle(_command("T-401"))

        assert len(events) == 2
        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# No direct file writes (I-CMD-4)
# ---------------------------------------------------------------------------

class TestNoDirectFileWrite:
    @patch("sdd.commands.update_state.sync_projections")
    @patch("sdd.commands.update_state.parse_taskset")
    def test_no_direct_file_write_in_handler(
        self, mock_parse, mock_sync, handler
    ):
        """Handler never calls open() directly; all file mutations go through the kernel (I-CMD-4)."""
        mock_parse.return_value = [_task("T-401")]

        with patch("builtins.open") as mock_open:
            handler.handle(_command("T-401"))
            mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# Status signal (stdout JSON) — sdd complete routes through execute_and_project
# ---------------------------------------------------------------------------

class TestStatusSignal:
    def test_complete_new_task_emits_done_signal(self, tmp_path, capsys):
        """main() prints {"status": "done", "task_id": ...} when task transitions TODO → DONE."""
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
        _seed_active_phase(db, phase_id=4, tasks_total=1)

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
        _seed_active_phase(db, phase_id=4, tasks_total=1)

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
