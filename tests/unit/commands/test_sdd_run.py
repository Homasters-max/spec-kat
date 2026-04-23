"""Tests for CommandRunner + run_guard_pipeline — guard pipeline orchestration.

Invariants covered: I-CMD-7, I-CMD-11, I-CMD-12, I-ES-3, I-GRD-4
Spec ref: Spec_v4 §4.11, §9 Verification row 12
"""
from __future__ import annotations

import dataclasses
import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.commands.sdd_run import CommandRunner, run_guard_pipeline
from sdd.core.events import DomainEvent, EventLevel, TaskImplementedEvent
from sdd.core.types import Command
from sdd.domain.guards.context import DAG, EventLogView, GuardContext, GuardOutcome, GuardResult, PhaseState
from sdd.domain.norms.catalog import NormCatalog, NormEntry


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class _FakeCommand(Command):
    task_id: str | None = None
    phase_id: int | None = None


def _cmd(task_id: str = "T-401") -> _FakeCommand:
    return _FakeCommand(
        command_id=str(uuid.uuid4()),
        command_type="_FakeCommand",
        payload={},
        task_id=task_id,
        phase_id=4,
    )


def _make_event() -> DomainEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id=str(uuid.uuid4()),
        appended_at=1_700_000_000_000,
        level=EventLevel.L1,
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id="T-401",
        phase_id=4,
        timestamp="2026-01-01T00:00:00Z",
    )


def _allow_result(task_id: str | None = None) -> GuardResult:
    return GuardResult(GuardOutcome.ALLOW, "NormGuard", "actor permitted", None, task_id)


def _deny_result(task_id: str | None = None) -> GuardResult:
    return GuardResult(GuardOutcome.DENY, "PhaseGuard", "phase mismatch", None, task_id)


# ---------------------------------------------------------------------------
# Helpers for run_guard_pipeline direct tests
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
# Handlers used in CommandRunner tests
# ---------------------------------------------------------------------------

class _TrackingHandler(CommandHandlerBase):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.called = False

    @error_event_boundary(source="test._tracking_handler")
    def handle(self, command: Command) -> list[DomainEvent]:
        self.called = True
        return []


class _EventHandler(CommandHandlerBase):
    def __init__(self, db_path: str, events: list[DomainEvent]) -> None:
        super().__init__(db_path)
        self._events = events

    @error_event_boundary(source="test._event_handler")
    def handle(self, command: Command) -> list[DomainEvent]:
        return list(self._events)


# ---------------------------------------------------------------------------
# CommandRunner factory
# ---------------------------------------------------------------------------

def _make_runner(tmp_db_path: str) -> CommandRunner:
    from sdd.infra.event_store import EventStore
    return CommandRunner(
        event_store=EventStore(db_path=tmp_db_path),
        state_path="fake/State_index.yaml",
        config_path="fake/project_profile.yaml",
        taskset_path="fake/TaskSet_v4.md",
        reports_dir="fake/reports",
        norm_path="fake/norm_catalog.yaml",
    )


def _patch_infra(
    monkeypatch: pytest.MonkeyPatch,
    guard_return: tuple[GuardResult, list[DomainEvent]] | None = None,
) -> None:
    """Patch all I/O dependencies so CommandRunner.run() executes without real files."""
    monkeypatch.setattr("sdd.commands.sdd_run.rebuild_state", MagicMock())
    monkeypatch.setattr("sdd.commands.sdd_run._fetch_events_for_reduce", MagicMock(return_value=[]))
    mock_state = MagicMock()
    mock_state.phase_current = 4
    mock_state.phase_status = "ACTIVE"
    mock_reducer = MagicMock()
    mock_reducer.reduce.return_value = mock_state
    monkeypatch.setattr("sdd.commands.sdd_run.EventReducer", MagicMock(return_value=mock_reducer))
    monkeypatch.setattr("sdd.commands.sdd_run.parse_taskset", MagicMock(return_value=[]))
    monkeypatch.setattr("sdd.commands.sdd_run.load_catalog", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("sdd.commands.sdd_run.load_dag", MagicMock(return_value=DAG(deps={})))
    if guard_return is not None:
        monkeypatch.setattr("sdd.commands.sdd_run.run_guard_pipeline", MagicMock(return_value=guard_return))


# ===========================================================================
# CommandRunner tests (I-CMD-7, I-ES-3)
# ===========================================================================


def test_guard_allow_runs_handler(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """ALLOW from guard pipeline → handler.handle() is invoked (I-CMD-7)."""
    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))
    runner = _make_runner(tmp_db_path)
    handler = _TrackingHandler(tmp_db_path)
    runner.run(_cmd(), "Implement T-401", handler)
    assert handler.called


def test_guard_deny_skips_handler(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """DENY from guard pipeline → handler.handle() is NOT invoked (I-CMD-7)."""
    _patch_infra(monkeypatch, guard_return=(_deny_result(), []))
    runner = _make_runner(tmp_db_path)
    handler = _TrackingHandler(tmp_db_path)
    runner.run(_cmd(), "Implement T-401", handler)
    assert not handler.called


def test_guard_deny_returns_empty(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """DENY from guard pipeline → CommandRunner.run() returns [] (I-CMD-7)."""
    _patch_infra(monkeypatch, guard_return=(_deny_result(), []))
    runner = _make_runner(tmp_db_path)
    result = runner.run(_cmd(), "Implement T-401", _TrackingHandler(tmp_db_path))
    assert result == []


def test_guard_deny_appends_audit_events_via_event_store(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DENY → CommandRunner appends audit_events via EventStore, not the guard (I-ES-3, I-CMD-7)."""
    audit_event = _make_event()
    _patch_infra(monkeypatch, guard_return=(_deny_result(), [audit_event]))
    mock_store = MagicMock()
    runner = _make_runner(tmp_db_path)
    runner._store = mock_store
    runner.run(_cmd(), "Implement T-401", _TrackingHandler(tmp_db_path))
    mock_store.append.assert_called_once()
    appended = mock_store.append.call_args[0][0]
    assert audit_event in appended


def test_guard_deny_emits_no_handler_events(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DENY → runner returns [] — no handler events in the result (I-CMD-7, I-ES-3)."""
    _patch_infra(monkeypatch, guard_return=(_deny_result(), [_make_event()]))
    runner = _make_runner(tmp_db_path)
    result = runner.run(_cmd(), "Implement T-401", _TrackingHandler(tmp_db_path))
    assert result == []


def test_runner_does_not_catch_handler_exceptions(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CommandRunner.run() does not catch handler exceptions — they propagate (Spec_v4 §4.11)."""
    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))

    class _BoomHandler(CommandHandlerBase):
        def handle(self, command: Command) -> list[DomainEvent]:
            raise RuntimeError("handler exploded")

    runner = _make_runner(tmp_db_path)
    with pytest.raises(RuntimeError, match="handler exploded"):
        runner.run(_cmd(), "Implement T-401", _BoomHandler(tmp_db_path))


# ===========================================================================
# run_guard_pipeline direct tests (I-GRD-4, I-CMD-11, I-CMD-12)
# ===========================================================================


def test_guards_are_pure_no_side_effects() -> None:
    """run_guard_pipeline returns identical results on repeated calls with same context (I-ES-3, I-GRD-4)."""
    ctx = _make_ctx()
    r1, e1 = run_guard_pipeline(ctx, "Implement T-401", "llm", "implement_task", None, (), ())
    r2, e2 = run_guard_pipeline(ctx, "Implement T-401", "llm", "implement_task", None, (), ())
    assert r1 == r2
    assert len(e1) == len(e2)


def test_dependency_guard_wired_as_step3() -> None:
    """DependencyGuard runs as step 3: DENY when declared dependency is not yet DONE (I-CMD-11)."""
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    state = _make_state(tasks_done_ids=())
    dag = DAG(deps={task_id: frozenset(["T-399"])})  # T-399 not done
    ctx = _make_ctx(state=state, task=task, task_graph=dag)

    result, audit = run_guard_pipeline(
        ctx, "Implement T-401", "llm", "implement_task", task_id, (), ()
    )

    assert result.outcome is GuardOutcome.DENY
    assert result.guard_name == "DependencyGuard"
    assert any(e.event_type == "SDDEventRejected" for e in audit)


def test_norm_default_deny() -> None:
    """NormGuard denies when action is absent from catalog (default=DENY, I-CMD-12)."""
    deny_norms = NormCatalog(entries=(), strict=True)
    ctx = _make_ctx(norms=deny_norms)

    result, audit = run_guard_pipeline(
        ctx, "Implement T-401", "llm", "implement_task", None, (), ()
    )

    assert result.outcome is GuardOutcome.DENY
    assert result.guard_name == "NormGuard"
    assert any(e.event_type == "NormViolated" for e in audit)


def test_all_guards_wired() -> None:
    """PhaseGuard, DependencyGuard, and NormGuard are all wired into the pipeline.

    Verifies each guard independently denies when its precondition is violated.
    """
    # Step 1 — PhaseGuard fires on phase_current mismatch
    ctx_bad_phase = _make_ctx(state=_make_state(phase_current=99))
    r1, _ = run_guard_pipeline(ctx_bad_phase, "cmd", "llm", "implement_task", None, (), ())
    assert r1.guard_name == "PhaseGuard" and r1.outcome is GuardOutcome.DENY

    # Step 3 — DependencyGuard fires on unmet dependency
    task_id = "T-401"
    task = MagicMock()
    task.task_id = task_id
    task.status = "TODO"
    dag = DAG(deps={task_id: frozenset(["T-399"])})
    ctx_bad_dep = _make_ctx(task=task, task_graph=dag)
    r2, _ = run_guard_pipeline(ctx_bad_dep, "cmd", "llm", "implement_task", task_id, (), ())
    assert r2.guard_name == "DependencyGuard" and r2.outcome is GuardOutcome.DENY

    # Step 6 — NormGuard fires on forbidden action (strict=True, no entries)
    ctx_bad_norm = _make_ctx(norms=NormCatalog(entries=(), strict=True))
    r3, _ = run_guard_pipeline(ctx_bad_norm, "cmd", "llm", "implement_task", None, (), ())
    assert r3.guard_name == "NormGuard" and r3.outcome is GuardOutcome.DENY


# ===========================================================================
# Phase 5 named tests (Spec_v5 §9 Verification row 4)
# I-ES-1 (final), I-ES-6, I-CMD-3
# ===========================================================================


def test_runner_appends_error_events_via_store(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CommandRunner appends error events via EventStore, not via direct sdd_append (I-ES-1 final)."""
    from sdd.core.events import ErrorEvent, EventLevel

    error_event = ErrorEvent(
        event_type="ErrorEvent",
        event_id="err-1",
        appended_at=0,
        level=EventLevel.L2,
        event_source="runtime",
        caused_by_meta_seq=None,
        error_type="RuntimeError",
        source="test",
        recoverable=False,
        retry_count=0,
        context={"message": "boom"},
    )

    class _BoomHandler(CommandHandlerBase):
        def handle(self, command: Command) -> list[DomainEvent]:
            exc = RuntimeError("boom")
            exc._sdd_error_events = [error_event]  # type: ignore[attr-defined]
            raise exc

    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))
    mock_store = MagicMock()
    runner = _make_runner(tmp_db_path)
    runner._store = mock_store

    with pytest.raises(RuntimeError, match="boom"):
        runner.run(_cmd(), "Implement T-401", _BoomHandler(tmp_db_path))

    # Must have called append for error events via the store
    calls = mock_store.append.call_args_list
    error_call = next(
        (c for c in calls if c.kwargs.get("source") == "error_boundary" or
         (c.args and error_event in c.args[0])),
        None,
    )
    assert error_call is not None, "CommandRunner must append error events via EventStore"


def test_runner_catches_and_reraises(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CommandRunner re-raises the original exception after appending error events (I-CMD-3)."""
    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))

    class _BoomHandler(CommandHandlerBase):
        def handle(self, command: Command) -> list[DomainEvent]:
            raise RuntimeError("handler exploded")

    runner = _make_runner(tmp_db_path)
    with pytest.raises(RuntimeError, match="handler exploded"):
        runner.run(_cmd(), "Implement T-401", _BoomHandler(tmp_db_path))


def test_runner_logs_on_store_failure(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If EventStore.append fails while appending error events, CommandRunner logs and
    still re-raises the original exception (I-CMD-3)."""
    import logging

    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))

    class _BoomHandler(CommandHandlerBase):
        def handle(self, command: Command) -> list[DomainEvent]:
            exc = RuntimeError("original error")
            exc._sdd_error_events = [MagicMock()]  # type: ignore[attr-defined]
            raise exc

    mock_store = MagicMock()
    mock_store.append.side_effect = OSError("store unavailable")
    runner = _make_runner(tmp_db_path)
    runner._store = mock_store

    with patch("sdd.commands.sdd_run.logging") as mock_logging:
        with pytest.raises(RuntimeError, match="original error"):
            runner.run(_cmd(), "Implement T-401", _BoomHandler(tmp_db_path))
    mock_logging.error.assert_called()


def test_runner_no_append_on_empty_events(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CommandRunner must NOT call EventStore.append when handler returns [] (I-ES-6)."""
    _patch_infra(monkeypatch, guard_return=(_allow_result(), []))
    mock_store = MagicMock()
    runner = _make_runner(tmp_db_path)
    runner._store = mock_store

    result = runner.run(_cmd(), "Implement T-401", _TrackingHandler(tmp_db_path))
    assert result == []
    # append must not have been called for an empty event list
    success_append_calls = [
        c for c in mock_store.append.call_args_list
        if c.kwargs.get("source") not in ("guards", "error_boundary")
        and (not c.args or c.args[0] != [])
    ]
    assert success_append_calls == [], "append must not be called with empty events (I-ES-6)"
