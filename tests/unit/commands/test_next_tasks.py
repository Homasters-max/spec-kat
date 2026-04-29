"""Tests for next_tasks — returns TODO tasks with fulfilled dependencies.

Invariants: I-CMD-IDEM-1, I-CMD-IDEM-2, I-READ-ONLY-EXCEPTION-1
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.next_tasks import EVENT_TASK_DONE, NextTasksCommand, next_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(task_id: str) -> MagicMock:
    t = MagicMock()
    t.task_id = task_id
    return t


def _state(done_ids: list[str]) -> MagicMock:
    s = MagicMock()
    s.tasks_done_ids = done_ids
    return s


def _dag(deps: dict[str, list[str]]) -> MagicMock:
    d = MagicMock()
    d.deps = deps
    return d


# ---------------------------------------------------------------------------
# EVENT_TASK_DONE — single source of truth (I-CMD-IDEM-1, I-CMD-IDEM-2)
# ---------------------------------------------------------------------------

def test_event_task_done_constant_defined():
    """EVENT_TASK_DONE is defined in next_tasks module (single source of truth)."""
    assert EVENT_TASK_DONE == "DONE"


def test_event_task_done_importable_from_module():
    """Ensures EVENT_TASK_DONE is exported at module level, not buried in a class."""
    import sdd.commands.next_tasks as m
    assert hasattr(m, "EVENT_TASK_DONE")
    assert m.EVENT_TASK_DONE == "DONE"


# ---------------------------------------------------------------------------
# next_tasks — filtering logic
# ---------------------------------------------------------------------------

class TestNextTasks:
    """sdd next-tasks --phase N returns tasks without unfinished deps."""

    @patch("sdd.commands.next_tasks.load_dag")
    @patch("sdd.commands.next_tasks.parse_taskset")
    @patch("sdd.commands.next_tasks.get_current_state")
    @patch("sdd.commands.next_tasks.taskset_file")
    @patch("sdd.commands.next_tasks.event_store_url")
    def _call(
        self,
        mock_store,
        mock_ts_file,
        mock_state_fn,
        mock_parse,
        mock_dag_fn,
        tasks,
        done_ids,
        deps,
    ):
        mock_store.return_value = ":memory:"
        mock_ts_file.return_value = "TaskSet_v32.md"
        mock_state_fn.return_value = _state(done_ids)
        mock_parse.return_value = tasks
        mock_dag_fn.return_value = _dag(deps)
        cmd = NextTasksCommand(phase_id=32, db_path=":memory:")
        return next_tasks(cmd)

    def test_no_deps_all_returned(self):
        tasks = [_task("T-01"), _task("T-02")]
        result = self._call(tasks=tasks, done_ids=[], deps={})
        assert [t.task_id for t in result] == ["T-01", "T-02"]

    def test_done_tasks_excluded(self):
        tasks = [_task("T-01"), _task("T-02")]
        result = self._call(tasks=tasks, done_ids=["T-01"], deps={})
        assert [t.task_id for t in result] == ["T-02"]

    def test_blocked_task_excluded(self):
        """T-02 depends on T-01 which is not done → T-02 must not appear."""
        tasks = [_task("T-01"), _task("T-02")]
        result = self._call(
            tasks=tasks,
            done_ids=[],
            deps={"T-02": ["T-01"]},
        )
        assert [t.task_id for t in result] == ["T-01"]

    def test_unblocked_after_dep_done(self):
        """T-02 depends on T-01; T-01 is done → T-02 appears."""
        tasks = [_task("T-01"), _task("T-02")]
        result = self._call(
            tasks=tasks,
            done_ids=["T-01"],
            deps={"T-02": ["T-01"]},
        )
        assert [t.task_id for t in result] == ["T-02"]

    def test_partial_deps_blocked(self):
        """T-03 depends on T-01 and T-02; only T-01 done → T-03 blocked."""
        tasks = [_task("T-01"), _task("T-02"), _task("T-03")]
        result = self._call(
            tasks=tasks,
            done_ids=["T-01"],
            deps={"T-03": ["T-01", "T-02"]},
        )
        ids = [t.task_id for t in result]
        assert "T-03" not in ids
        assert "T-02" in ids

    def test_all_done_returns_empty(self):
        tasks = [_task("T-01"), _task("T-02")]
        result = self._call(
            tasks=tasks,
            done_ids=["T-01", "T-02"],
            deps={},
        )
        assert result == []


# ---------------------------------------------------------------------------
# I-CMD-IDEM-1 / I-CMD-IDEM-2: next-tasks is read-only — NOT in REGISTRY
# ---------------------------------------------------------------------------

def test_next_tasks_not_in_registry():
    """next-tasks is read-only and bypasses REGISTRY (I-READ-ONLY-EXCEPTION-1).

    I-CMD-IDEM-1/I-CMD-IDEM-2 apply only to commands in the Write Kernel.
    A read-only command that is absent from REGISTRY cannot violate idempotency rules.
    """
    from sdd.commands.registry import REGISTRY
    assert "next-tasks" not in REGISTRY, (
        "next-tasks is read-only — must bypass REGISTRY (I-READ-ONLY-EXCEPTION-1)"
    )
