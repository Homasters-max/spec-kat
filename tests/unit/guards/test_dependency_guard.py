"""Tests for DependencyGuard — I-CMD-11."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sdd.domain.guards.context import DAG, EventLogView, GuardContext, GuardOutcome, PhaseState, load_dag
from sdd.domain.guards.dependency_guard import DependencyGuard


def _make_ctx(done_ids: list[str], task_deps: list[str], task_id: str = "T-001") -> GuardContext:
    state = MagicMock()
    state.tasks_done_ids = list(done_ids)
    dag = DAG(deps={task_id: frozenset(task_deps)})
    return GuardContext(
        state=state,
        phase=PhaseState(phase_id=4, status="ACTIVE"),
        task=None,
        norms=MagicMock(),
        event_log=EventLogView(db_path=":memory:"),
        task_graph=dag,
        now="2026-01-01T00:00:00Z",
    )


def test_dependency_guard_deny_if_dependency_not_done():
    ctx = _make_ctx(done_ids=["T-099"], task_deps=["T-099", "T-100"])
    result, events = DependencyGuard.check(ctx, "T-001")

    assert result.outcome == GuardOutcome.DENY
    assert result.guard_name == "DependencyGuard"
    assert "T-100" in result.message
    assert result.norm_id == "I-CMD-11"
    assert len(events) == 1
    assert events[0].event_type == "SDDEventRejected"


def test_dependency_guard_allow_if_all_dependencies_done():
    ctx = _make_ctx(done_ids=["T-099", "T-100"], task_deps=["T-099", "T-100"])
    result, events = DependencyGuard.check(ctx, "T-001")

    assert result.outcome == GuardOutcome.ALLOW
    assert result.guard_name == "DependencyGuard"
    assert events == []


def test_dependency_guard_allow_when_no_dependencies():
    ctx = _make_ctx(done_ids=[], task_deps=[])
    result, events = DependencyGuard.check(ctx, "T-001")

    assert result.outcome == GuardOutcome.ALLOW
    assert events == []


def test_dependency_guard_is_pure_no_io():
    ctx = _make_ctx(done_ids=["T-099"], task_deps=["T-099", "T-100"])

    r1, e1 = DependencyGuard.check(ctx, "T-001")
    r2, e2 = DependencyGuard.check(ctx, "T-001")

    assert r1 == r2
    assert len(e1) == len(e2)
    assert e1[0].event_type == e2[0].event_type
    assert e1[0].rejection_reason == e2[0].rejection_reason


def test_dependency_guard_deny_lists_all_blocking():
    ctx = _make_ctx(done_ids=[], task_deps=["T-010", "T-020", "T-030"])
    result, _ = DependencyGuard.check(ctx, "T-001")

    assert result.outcome == GuardOutcome.DENY
    for dep in ["T-010", "T-020", "T-030"]:
        assert dep in result.message


def test_dependency_guard_unknown_task_has_no_deps():
    ctx = _make_ctx(done_ids=[], task_deps=[])
    result, events = DependencyGuard.check(ctx, "T-UNKNOWN")

    assert result.outcome == GuardOutcome.ALLOW
    assert events == []


def test_load_dag_filters_sentinel_depends_on(tmp_path):
    """load_dag must filter sentinel values ('—', '-', '') from depends_on (I-CMD-11)."""
    taskset = tmp_path / "TaskSet_v1.md"
    taskset.write_text(
        "## T-001: Sentinel task\n"
        "Status: TODO\n"
        "Depends on: —\n"
        "\n"
        "## T-002: Dash task\n"
        "Status: TODO\n"
        "Depends on: -\n",
        encoding="utf-8",
    )
    dag = load_dag(str(taskset))
    assert dag.dependencies("T-001") == frozenset()
    assert dag.dependencies("T-002") == frozenset()


def test_dependency_guard_deny_populates_reason():
    """DependencyGuard must set GuardResult.reason on DENY (I-GUARD-REASON-1)."""
    ctx = _make_ctx(done_ids=[], task_deps=["T-100"])
    result, _ = DependencyGuard.check(ctx, "T-001")

    assert result.outcome == GuardOutcome.DENY
    assert result.reason is not None
    assert result.reason != ""
