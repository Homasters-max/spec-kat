"""CommandRunner + run_guard_pipeline — Spec_v5 §4.5, §4.11, I-GUARD-1, I-GUARD-2, I-CMD-7, I-ES-3."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import partial

from sdd.commands._base import CommandHandlerBase
from sdd.core.events import DomainEvent
from sdd.core.types import Command
from sdd.domain.guards.context import (
    DAG,
    EventLogView,
    GuardContext,
    GuardOutcome,
    GuardResult,
    PhaseState,
    load_dag,
)
from sdd.domain.guards.dependency_guard import DependencyGuard
from sdd.domain.guards.norm_guard import make_norm_guard
from sdd.domain.guards.phase_guard import make_phase_guard
from sdd.domain.guards.pipeline import run_guard_pipeline as _run_domain_pipeline
from sdd.domain.guards.task_guard import make_task_guard
from sdd.domain.norms.catalog import load_catalog
from sdd.domain.state.reducer import EventReducer
from sdd.domain.tasks.parser import Task, parse_taskset
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_store import EventStore
from sdd.infra.projections import rebuild_state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_events_for_reduce(db_path: str) -> list[dict]:
    """Fetch all events from EventLog in format required by EventReducer."""
    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, payload, level, event_source "
            "FROM events ORDER BY seq ASC"
        ).fetchall()
    finally:
        conn.close()
    events: list[dict] = []
    for event_type, payload_str, level, event_source in rows:
        try:
            payload: dict = json.loads(payload_str) if payload_str else {}
        except Exception:
            payload = {}
        e: dict = {
            "event_type": event_type,
            "level": level,
            "event_source": event_source,
        }
        e.update(payload)
        events.append(e)
    return events


# ---------------------------------------------------------------------------
# run_guard_pipeline — adapter (I-GRD-4, I-GUARD-2)
# ---------------------------------------------------------------------------

def run_guard_pipeline(
    ctx:          GuardContext,
    command_str:  str,
    actor:        str,
    action:       str,
    task_id:      str | None,
    required_ids: tuple[str, ...],
    input_paths:  tuple[str, ...],
    stop_on_deny: bool = True,
) -> tuple[GuardResult, list[DomainEvent]]:
    """Adapter: builds domain Guard callables and delegates to domain pipeline.

    Guard order (Spec_v5 §4.11):
      1. PhaseGuard  — policy guard (domain/guards/phase_guard.py)
      2. TaskGuard   — integrity guard; raises on violation (domain/guards/task_guard.py)
      3. DependencyGuard — policy guard (domain/guards/dependency_guard.py)
      4. NormGuard   — policy guard (domain/guards/norm_guard.py)
    """
    guards = [make_phase_guard(command_str, task_id)]
    if task_id is not None:
        guards.append(make_task_guard(task_id))
        guards.append(partial(DependencyGuard.check, task_id=task_id))
    guards.append(make_norm_guard(actor, action, task_id))

    return _run_domain_pipeline(ctx, guards, stop_on_deny=stop_on_deny)


# ---------------------------------------------------------------------------
# CommandRunner
# ---------------------------------------------------------------------------

class CommandRunner:
    """Orchestrates: pure guard pipeline → handler → post-rebuild (Spec_v4 §4.11).

    Guard pipeline is pure (run_guard_pipeline has no I/O).
    On DENY: CommandRunner appends audit_events via EventStore, returns [] (I-CMD-7).
    Handler is NOT called on DENY (I-CMD-7).
    GuardContext.state is always from EventLog replay — never from State_index.yaml (I-CMD-11).
    Pre-run rebuild (step 1) and post-append rebuild (step 7) are structurally separate.
    """

    def __init__(
        self,
        event_store:  EventStore,
        state_path:   str,
        config_path:  str,
        taskset_path: str,
        reports_dir:  str,
        norm_path:    str,
    ) -> None:
        self._store = event_store
        self._db_path: str = event_store._db_path
        self._state_path = state_path
        self._config_path = config_path
        self._taskset_path = taskset_path
        self._reports_dir = reports_dir
        self._norm_path = norm_path

    def run(
        self,
        command:      Command,
        command_str:  str,
        handler:      CommandHandlerBase,
        actor:        str = "llm",
        action:       str = "implement_task",
        task_id:      str | None = None,
        required_ids: tuple[str, ...] = (),
        input_paths:  tuple[str, ...] = (),
    ) -> list[DomainEvent]:
        """Orchestrate guard pipeline → handler for a single command.

        Steps:
          1. Pre-run rebuild: rebuild_state syncs State_index.yaml for external readers.
          2. Build GuardContext from EventLog replay (authoritative; never from YAML).
          3. run_guard_pipeline(ctx, ...) — pure, returns (result, audit_events).
          4. DENY: self._store.append(audit_events, source="guards") → return [].
          5. ALLOW: events = handler.handle(command) — wrapped in try/except.
             On exception: reads exc._sdd_error_events, appends via EventStore (I-ES-1),
             logs on EventStore failure (I-CMD-3), re-raises original.
          6. if events: self._store.append(events, ...) — sole success write path (I-ES-6).
          7. Post-append rebuild: rebuild_state ensures State_index.yaml reflects new events.
          8. return events.
        """
        rebuild_state(self._db_path, self._state_path)

        events_raw = _fetch_events_for_reduce(self._db_path)
        state = EventReducer().reduce(events_raw)
        phase = PhaseState(phase_id=state.phase_current, status=state.phase_status)

        task: Task | None = None
        if task_id is not None:
            all_tasks = parse_taskset(self._taskset_path)
            task = next((t for t in all_tasks if t.task_id == task_id), None)

        norms = load_catalog(self._norm_path, strict=True)
        event_log = EventLogView(db_path=self._db_path)
        task_graph = load_dag(self._taskset_path)
        now = _utc_now_iso()

        ctx = GuardContext(
            state=state,
            phase=phase,
            task=task,
            norms=norms,
            event_log=event_log,
            task_graph=task_graph,
            now=now,
        )

        guard_result, audit_events = run_guard_pipeline(
            ctx=ctx,
            command_str=command_str,
            actor=actor,
            action=action,
            task_id=task_id,
            required_ids=required_ids,
            input_paths=input_paths,
        )

        if guard_result.outcome is GuardOutcome.DENY:
            self._store.append(audit_events, source="guards")
            return []

        try:
            handler_events = handler.handle(command)
        except Exception as exc:
            error_events = getattr(exc, "_sdd_error_events", [])
            if error_events:
                try:
                    self._store.append(error_events, source="error_boundary")
                except Exception:
                    logging.error(
                        "EventStore.append failed for error_events; original exc follows"
                    )
            raise

        if handler_events:
            self._store.append(handler_events, source=type(handler).__module__)

        rebuild_state(self._db_path, self._state_path)

        return handler_events
