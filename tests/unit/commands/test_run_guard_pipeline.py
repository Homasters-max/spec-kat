"""Unit tests for run_guard_pipeline — pure function contract.

Invariants covered: I-ES-3, I-GRD-4, I-CMD-7, I-CMD-11, I-CMD-12
Spec ref: Spec_v4 §4.11, §4.13
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sdd.commands.sdd_run import run_guard_pipeline
from sdd.core.errors import InvalidState, MissingContext
from sdd.domain.guards.context import DAG, EventLogView, GuardContext, GuardOutcome, PhaseState
from sdd.domain.norms.catalog import NormCatalog, NormEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allow_entry() -> NormEntry:
    return NormEntry(
        norm_id="TEST-ALLOW",
        actor="llm",
        action="implement_task",
        result="allowed",
        description="test allow",
        severity="soft",
    )


def _make_state(
    phase_current: int = 4,
    plan_version: int = 4,
    tasks_version: int = 4,
    tasks_done_ids: tuple[str, ...] = (),
) -> MagicMock:
    s = MagicMock()
    s.phase_current = phase_current
    s.plan_version = plan_version
    s.tasks_version = tasks_version
    s.tasks_done_ids = list(tasks_done_ids)
    return s


def _make_ctx(
    state: MagicMock | None = None,
    phase: PhaseState | None = None,
    task: MagicMock | None = None,
    norms: NormCatalog | None = None,
    task_graph: DAG | None = None,
) -> GuardContext:
    return GuardContext(
        state=state or _make_state(),
        phase=phase or PhaseState(phase_id=4, status="ACTIVE"),
        task=task,
        norms=norms or NormCatalog(entries=(_allow_entry(),), strict=True),
        event_log=EventLogView(db_path=":memory:"),
        task_graph=task_graph or DAG(deps={}),
        now="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_allow_when_all_guards_pass() -> None:
    """Pipeline returns ALLOW and empty audit when all guards are satisfied."""
    ctx = _make_ctx()
    result, audit = run_guard_pipeline(ctx, "Implement T-401", "llm", "implement_task", None, (), ())
    assert result.outcome is GuardOutcome.ALLOW
    assert audit == []


def test_allow_with_task_and_no_dependencies() -> None:
    """Pipeline returns ALLOW when task is TODO and has no dependencies."""
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    ctx = _make_ctx(task=task, task_graph=DAG(deps={}))
    result, _ = run_guard_pipeline(ctx, "Implement T-401", "llm", "implement_task", task_id, (), ())
    assert result.outcome is GuardOutcome.ALLOW


# ---------------------------------------------------------------------------
# Phase guard (step 1)
# ---------------------------------------------------------------------------

def test_phase_guard_deny_on_phase_current_mismatch() -> None:
    """Step 1: DENY when state.phase_current != phase.phase_id (PG-1)."""
    ctx = _make_ctx(state=_make_state(phase_current=99))
    result, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert result.outcome is GuardOutcome.DENY
    assert result.guard_name == "PhaseGuard"
    assert any(e.event_type == "SDDEventRejected" and e.failed_check == "PG-1" for e in audit)


def test_phase_guard_deny_on_version_mismatch() -> None:
    """Step 1: DENY when plan_version != phase_id (PG-2)."""
    ctx = _make_ctx(state=_make_state(plan_version=99))
    result, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert result.outcome is GuardOutcome.DENY
    assert any(e.event_type == "SDDEventRejected" and e.failed_check == "PG-2" for e in audit)


def test_phase_guard_deny_on_status_not_active() -> None:
    """Step 1: DENY when phase.status != 'ACTIVE' (PG-3)."""
    ctx = _make_ctx(phase=PhaseState(phase_id=4, status="PLANNED"))
    result, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert result.outcome is GuardOutcome.DENY
    assert any(e.event_type == "SDDEventRejected" and e.failed_check == "PG-3" for e in audit)


def test_phase_guard_emits_sdd_event_rejected() -> None:
    """Step 1 DENY produces an SDDEventRejected audit event."""
    ctx = _make_ctx(state=_make_state(phase_current=99))
    _, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert len(audit) == 1
    assert audit[0].event_type == "SDDEventRejected"


# ---------------------------------------------------------------------------
# Task guard (step 2)
# ---------------------------------------------------------------------------

def test_task_guard_raises_missing_context_when_task_not_found() -> None:
    """Step 2: MissingContext raised when task_id is provided but ctx.task is None."""
    ctx = _make_ctx(task=None)
    with pytest.raises(MissingContext):
        run_guard_pipeline(ctx, "cmd", "llm", "implement_task", "T-401", (), ())


def test_task_guard_raises_invalid_state_when_task_done() -> None:
    """Step 2: InvalidState raised when task.status == 'DONE' (duplicate execution blocked)."""
    task = MagicMock()
    task.task_id = "T-401"
    task.status = "DONE"
    ctx = _make_ctx(task=task)
    with pytest.raises(InvalidState):
        run_guard_pipeline(ctx, "cmd", "llm", "implement_task", "T-401", (), ())


# ---------------------------------------------------------------------------
# DependencyGuard (step 3)
# ---------------------------------------------------------------------------

def test_dependency_guard_deny_returns_sdd_event_rejected() -> None:
    """Step 3: DENY from DependencyGuard includes SDDEventRejected audit event."""
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    dag = DAG(deps={task_id: frozenset(["T-399"])})
    ctx = _make_ctx(task=task, task_graph=dag)

    _, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", task_id, (), ())

    assert len(audit) == 1
    assert audit[0].event_type == "SDDEventRejected"


def test_dependency_guard_allow_when_all_deps_done() -> None:
    """Step 3: ALLOW when all declared dependencies are in tasks_done_ids."""
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    state = _make_state(tasks_done_ids=("T-399",))
    dag = DAG(deps={task_id: frozenset(["T-399"])})
    ctx = _make_ctx(state=state, task=task, task_graph=dag)

    result, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", task_id, (), ())

    assert result.outcome is GuardOutcome.ALLOW
    assert audit == []


# ---------------------------------------------------------------------------
# NormGuard (step 6)
# ---------------------------------------------------------------------------

def test_norm_guard_emits_norm_violated_on_deny() -> None:
    """Step 6 DENY produces a NormViolated audit event."""
    ctx = _make_ctx(norms=NormCatalog(entries=(), strict=True))
    _, audit = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert len(audit) == 1
    assert audit[0].event_type == "NormViolated"


def test_norm_guard_allows_explicit_entry() -> None:
    """Step 6: ALLOW when actor/action has an explicit 'allowed' entry."""
    ctx = _make_ctx(norms=NormCatalog(entries=(_allow_entry(),), strict=True))
    result, _ = run_guard_pipeline(ctx, "cmd", "llm", "implement_task", None, (), ())
    assert result.outcome is GuardOutcome.ALLOW


# ---------------------------------------------------------------------------
# stop_on_deny=False
# ---------------------------------------------------------------------------

def test_stop_on_deny_false_collects_all_audit_events() -> None:
    """stop_on_deny=False continues the pipeline and collects audit events from all denying guards."""
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    state = _make_state(tasks_done_ids=())
    dag = DAG(deps={task_id: frozenset(["T-399"])})
    # DependencyGuard will deny at step 3; NormGuard will deny at step 6
    deny_norms = NormCatalog(entries=(), strict=True)
    ctx = _make_ctx(state=state, task=task, norms=deny_norms, task_graph=dag)

    result, audit = run_guard_pipeline(
        ctx, "cmd", "llm", "implement_task", task_id, (), (),
        stop_on_deny=False,
    )

    assert result.outcome is GuardOutcome.DENY
    event_types = {e.event_type for e in audit}
    assert "SDDEventRejected" in event_types
    assert "NormViolated" in event_types
