"""Contract tests: GuardContext.state MUST be built from EventLog replay, not State_index.yaml.

Spec_v4 §4.13 construction rule (I-CMD-11 stale-state fix):
    state = sdd_reducer(replay_all_events(db_path))  # authoritative full replay
State_index.yaml is a derived projection and may lag; using it in DependencyGuard
could allow a task to run before its dependency is DONE per the EventLog truth.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sdd.domain.guards.context import DAG, EventLogView, GuardContext, GuardOutcome, PhaseState
from sdd.domain.guards.dependency_guard import DependencyGuard


def _make_state(done_ids: list[str]) -> MagicMock:
    state = MagicMock()
    state.tasks_done_ids = list(done_ids)
    return state


def _make_ctx(state, task_deps: dict[str, list[str]]) -> GuardContext:
    dag = DAG(deps={tid: frozenset(deps) for tid, deps in task_deps.items()})
    return GuardContext(
        state=state,
        phase=PhaseState(phase_id=4, status="ACTIVE"),
        task=None,
        norms=MagicMock(),
        event_log=EventLogView(db_path=":memory:"),
        task_graph=dag,
        now="2026-01-01T00:00:00Z",
    )


def test_guard_context_state_from_eventlog_replay():
    """GuardContext.state (from EventLog replay) drives guard decisions, not State_index.yaml.

    Scenario: T-100 is DONE in the EventLog (replay_state). A stale YAML projection
    omits T-100 from done_ids. DependencyGuard must use ctx.state (replay), not YAML.
    """
    # Replay projection: T-100 is confirmed DONE in EventLog
    replay_state = _make_state(done_ids=["T-100"])
    ctx_replay = _make_ctx(replay_state, task_deps={"T-101": ["T-100"]})

    result, events = DependencyGuard.check(ctx_replay, "T-101")

    # Guard uses replay state → T-100 is DONE → ALLOW
    assert result.outcome == GuardOutcome.ALLOW
    assert events == []


def test_stale_yaml_projection_would_incorrectly_deny():
    """Demonstrates why YAML projection must not be used as guard input (I-CMD-11).

    If the caller passed a stale YAML-derived state (T-100 not yet flushed),
    DependencyGuard would DENY a task that is legitimately ready per the EventLog.
    GuardContext construction MUST use replay, not YAML, to avoid this.
    """
    stale_yaml_state = _make_state(done_ids=[])  # YAML lag: T-100 not flushed yet
    ctx_stale = _make_ctx(stale_yaml_state, task_deps={"T-101": ["T-100"]})

    result, events = DependencyGuard.check(ctx_stale, "T-101")

    # Stale state → guard incorrectly returns DENY (showing why YAML must not be used)
    assert result.outcome == GuardOutcome.DENY
    assert len(events) == 1


def test_guard_context_is_immutable_snapshot():
    """GuardContext is a frozen dataclass — guards cannot mutate it (I-ES-3)."""
    state = _make_state(done_ids=["T-100"])
    ctx = _make_ctx(state, task_deps={"T-101": ["T-100"]})

    with pytest.raises((AttributeError, TypeError)):
        ctx.now = "2099-01-01T00:00:00Z"  # type: ignore[misc]


def test_guard_context_event_log_view_is_read_only():
    """EventLogView carries db_path only — no mutable state, no write methods."""
    ev = EventLogView(db_path="/some/path/sdd_events.duckdb")

    assert ev.db_path == "/some/path/sdd_events.duckdb"
    assert not hasattr(ev, "append")
    assert not hasattr(ev, "write")


def test_replay_state_fully_determines_allow_boundary():
    """Exact boundary: ALLOW only when ALL deps in ctx.state.tasks_done_ids."""
    replay_partial = _make_state(done_ids=["T-100"])  # T-101 not yet done
    ctx = _make_ctx(replay_partial, task_deps={"T-102": ["T-100", "T-101"]})

    result, events = DependencyGuard.check(ctx, "T-102")

    assert result.outcome == GuardOutcome.DENY
    assert "T-101" in result.message
    assert len(events) == 1
