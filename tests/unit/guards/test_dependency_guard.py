"""Tests for DependencyGuard — I-CMD-11."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sdd.domain.guards.context import DAG, EventLogView, GuardContext, GuardOutcome, PhaseState
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
