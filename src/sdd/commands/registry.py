"""Command registry + Write Kernel (BC-15-REGISTRY) — Spec_v15 §2.

Invariants: I-IDEM-SCHEMA-1, I-IDEM-LOG-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1,
            I-ATOMICITY-1, I-RETRY-POLICY-1, I-CMD-PAYLOAD-PHASE-1,
            I-CMD-PHASE-RESOLVE-1, I-SYNC-NO-PHASE-GUARD-1,
            I-DECISION-AUDIT-1, I-READ-ONLY-EXCEPTION-1,
            I-CMD-IDEM-1, I-IDEM-SCHEMA-1
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any, Callable, Literal, cast

from sdd.commands._base import CommandHandlerBase, NoOpHandler
from sdd.core.execution_context import kernel_context
from sdd.core.errors import (
    CommitError,
    GuardViolationError,
    InvariantViolationError,
    KernelInvariantError,
    ProjectionError,
    StaleStateError,
)
from sdd.core.events import (
    DecisionRecordedEvent,
    DomainEvent,
    EventLevel,
    InvariantRegistered,
    PhaseCompletedEvent,
    PhaseInitializedEvent,
    PhaseStartedEvent,
    SessionDeclaredEvent,
    TaskImplementedEvent,
    TaskSetDefinedEvent,
    TaskValidatedEvent,
    compute_command_id,
    compute_trace_id,
)
from sdd.domain.guards.context import (
    DAG,
    EventLogView,
    GuardContext,
    GuardOutcome,
    PhaseState,
    load_dag,
)
from sdd.domain.session.policy import SessionDedupPolicy
from sdd.domain.guards.dependency_guard import DependencyGuard
from sdd.domain.guards.norm_guard import make_norm_guard
from sdd.domain.guards.phase_guard import make_phase_guard
from sdd.domain.guards.pipeline import run_guard_pipeline as _run_domain_pipeline
from sdd.domain.guards.task_guard import make_task_guard
from sdd.domain.norms.catalog import load_catalog
from sdd.domain.state.reducer import SDDState
from sdd.domain.tasks.parser import Task, parse_taskset
from sdd.infra.event_log import EventLog, EventLogError, EventLogKernelProtocol, open_event_log
from sdd.infra.paths import (
    audit_log_file,
    event_store_url as event_store_url,
    norm_catalog_file,
    state_file,
    taskset_file,
)
from sdd.infra.projections import RebuildMode, get_current_state as get_current_state, rebuild_state, rebuild_taskset

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ProjectionType
# ---------------------------------------------------------------------------

class ProjectionType(Enum):
    NONE       = "none"        # no projection after write
    STATE_ONLY = "state_only"  # rebuild State_index only
    FULL       = "full"        # rebuild State_index + TaskSet


# ---------------------------------------------------------------------------
# CommandSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandSpec:
    """Contract for a single SDD write command (I-SPEC-EXEC-1)."""
    name:                  str
    handler_class:         type[CommandHandlerBase]
    actor:                 Literal["llm", "human", "any"]
    action:                str                                # passed to NormGuard
    projection:            ProjectionType
    uses_task_id:          bool                               # True → TaskGuard+DependencyGuard run
    event_schema:          tuple[type[DomainEvent], ...]      # expected output event types
    preconditions:         tuple[str, ...]
    postconditions:        tuple[str, ...]
    requires_active_phase: bool = True                        # A-20: False → PhaseGuard skipped
    apply_task_guard:      bool = True                        # False → skip make_task_guard (e.g. validate needs DONE tasks)
    description:           str = ""
    idempotent:            bool = True                        # False for navigation cmds (I-CMD-IDEM-1)
    guard_factory: Callable[[Any], list[Any]] | None = field(default=None, hash=False, compare=False)
    dedup_policy:          SessionDedupPolicy | None = field(default=None, hash=False, compare=False)

    def __post_init__(self) -> None:
        if not self.action or not self.action.strip():
            raise ValueError(f"CommandSpec {self.name!r}: action must be a non-empty string (I-CMD-ACTION-1)")

    def build_guards(self, cmd: Any) -> list[Any]:
        """Return guard list for this command (I-CMD-GUARD-FACTORY-2).

        Delegates to guard_factory(cmd) if set; otherwise uses _default_build_guards.
        """
        if self.guard_factory is not None:
            return self.guard_factory(cmd)
        return _default_build_guards(self, cmd)


# ---------------------------------------------------------------------------
# REGISTRY — 6 write commands (I-READ-ONLY-EXCEPTION-1: read-only cmds excluded)
# ---------------------------------------------------------------------------

def _lazy_complete_handler() -> type[CommandHandlerBase]:
    from sdd.commands.update_state import CompleteTaskHandler
    return CompleteTaskHandler


def _lazy_validate_handler() -> type[CommandHandlerBase]:
    from sdd.commands.update_state import ValidateTaskHandler
    return ValidateTaskHandler


def _lazy_check_dod_handler() -> type[CommandHandlerBase]:
    from sdd.commands.update_state import CheckDoDHandler
    return CheckDoDHandler


def _lazy_activate_phase_handler() -> type[CommandHandlerBase]:
    from sdd.commands.activate_phase import ActivatePhaseHandler
    return ActivatePhaseHandler


def _lazy_record_decision_handler() -> type[CommandHandlerBase]:
    from sdd.commands.record_decision import RecordDecisionHandler
    return RecordDecisionHandler


def _lazy_switch_phase_handler() -> type[CommandHandlerBase]:
    from sdd.commands.switch_phase import SwitchPhaseHandler
    return SwitchPhaseHandler


def _lazy_switch_phase_guard_factory(cmd: Any) -> list[Any]:
    from sdd.commands.switch_phase import _switch_phase_guard_factory
    return _switch_phase_guard_factory(cmd)


def _lazy_invalidate_event_handler() -> type[CommandHandlerBase]:
    from sdd.commands.invalidate_event import InvalidateEventHandler
    return InvalidateEventHandler


def _lazy_record_session_handler() -> type[CommandHandlerBase]:
    from sdd.commands.record_session import RecordSessionHandler
    return RecordSessionHandler


def _lazy_approve_spec_handler() -> type[CommandHandlerBase]:
    from sdd.commands.approve_spec import ApproveSpecHandler
    return ApproveSpecHandler


def _lazy_amend_plan_handler() -> type[CommandHandlerBase]:
    from sdd.commands.amend_plan import AmendPlanHandler
    return AmendPlanHandler


def _lazy_amend_plan_guard_factory(cmd: Any) -> list[Any]:
    from sdd.commands.amend_plan import _amend_plan_guard_factory
    return _amend_plan_guard_factory(cmd)


def _lazy_init_project_handler() -> type[CommandHandlerBase]:
    from sdd.commands.init_project import InitProjectHandler
    return InitProjectHandler


def _lazy_rebuild_state_handler() -> type[CommandHandlerBase]:
    from sdd.commands.rebuild_state import RebuildStateHandler
    return RebuildStateHandler


def _lazy_next_tasks_handler() -> type[CommandHandlerBase]:
    from sdd.commands.next_tasks import NextTasksHandler
    return NextTasksHandler


def _lazy_sync_invariants_handler() -> type[CommandHandlerBase]:
    from sdd.commands.sync_invariants import SyncInvariantsHandler
    return SyncInvariantsHandler


def _lazy_analytics_refresh_handler() -> type[CommandHandlerBase]:
    from sdd.commands.analytics_refresh import AnalyticsRefreshHandler
    return AnalyticsRefreshHandler


REGISTRY: dict[str, CommandSpec] = {
    "complete": CommandSpec(
        name="complete",
        handler_class=_lazy_complete_handler(),
        actor="llm",
        action="implement_task",
        projection=ProjectionType.FULL,
        uses_task_id=True,
        event_schema=(TaskImplementedEvent, DomainEvent),
        preconditions=("phase.status == ACTIVE", "task.status == TODO"),
        postconditions=("task.status == DONE", "tasks.completed += 1"),
        description="Mark a task DONE after implementation",
    ),
    "validate": CommandSpec(
        name="validate",
        handler_class=_lazy_validate_handler(),
        actor="llm",
        action="validate_task",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=True,
        apply_task_guard=False,
        event_schema=(TaskValidatedEvent, DomainEvent),
        preconditions=("task.status == DONE", "--result in {PASS, FAIL}"),
        postconditions=("invariants.status updated", "tests.status updated"),
        description="Validate a task's invariants and tests",
    ),
    "check-dod": CommandSpec(
        name="check-dod",
        handler_class=_lazy_check_dod_handler(),
        actor="llm",
        action="check_dod",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=False,
        event_schema=(PhaseCompletedEvent, DomainEvent),
        preconditions=(
            "tasks.completed == tasks.total",
            "invariants.status == PASS",
            "tests.status == PASS",
        ),
        postconditions=("phase.status == COMPLETE",),
        description="Check Definition of Done for current phase",
    ),
    "activate-phase": CommandSpec(
        name="activate-phase",
        handler_class=_lazy_activate_phase_handler(),
        actor="human",
        action="activate_phase",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=False,
        requires_active_phase=False,  # activating a new phase; current may be PLANNED/COMPLETE
        event_schema=(PhaseStartedEvent, PhaseInitializedEvent),
        preconditions=("actor == human",),
        postconditions=("phase.current == N", "phase.status == ACTIVE"),
        description="Activate a new phase (human-only gate)",
    ),
    "sync-state": CommandSpec(
        name="sync-state",
        handler_class=NoOpHandler,
        actor="any",
        action="sync_state",
        projection=ProjectionType.FULL,
        uses_task_id=False,
        requires_active_phase=False,   # A-20: recovery; PhaseGuard skipped (I-SYNC-NO-PHASE-GUARD-1)
        event_schema=(),
        preconditions=(),
        postconditions=("State_index.yaml rebuilt from EventLog",),
        description="Rebuild State_index.yaml from EventLog (recovery utility)",
    ),
    "record-decision": CommandSpec(
        name="record-decision",
        handler_class=_lazy_record_decision_handler(),
        actor="human",
        action="record_decision",
        projection=ProjectionType.NONE,  # decisions are audit-only; no state change (I-DECISION-AUDIT-1)
        uses_task_id=False,
        event_schema=(DecisionRecordedEvent,),
        preconditions=("decision_id matches D-<number>", "summary <= 500 chars"),
        postconditions=("DecisionRecordedEvent in EventLog",),
        description="Record a design decision in the EventLog (Amendment A-1)",
    ),
    "switch-phase": CommandSpec(
        name="switch-phase",
        handler_class=_lazy_switch_phase_handler(),
        actor="human",
        action="switch_phase",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=False,
        requires_active_phase=False,   # switch-phase works regardless of current phase status
        event_schema=(),               # PhaseContextSwitchedEvent — imported lazily
        preconditions=("actor == human", "phase_id in phases_known", "phase_id != phase_current"),
        postconditions=("phase.current == phase_id", "flat fields restored from snapshot"),
        description="Switch working context to a previously activated phase",
        idempotent=False,              # NAVIGATION: every call = unique history fact (I-CMD-IDEM-1)
        guard_factory=_lazy_switch_phase_guard_factory,
    ),
    "invalidate-event": CommandSpec(
        name="invalidate-event",
        handler_class=_lazy_invalidate_event_handler(),
        actor="human",
        action="invalidate_event",
        projection=ProjectionType.NONE,    # audit-only; no state change
        uses_task_id=False,
        requires_active_phase=False,       # works regardless of phase status
        event_schema=(),                   # EventInvalidatedEvent — imported lazily
        preconditions=(
            "target_seq exists in EventLog",
            "event_type NOT in EventReducer._EVENT_SCHEMA",
            "event_type != 'EventInvalidated'",
            "no prior EventInvalidated for target_seq",
        ),
        postconditions=("EventInvalidated in EventLog",),
        description="Neutralize invalid EventLog entry (kernel violation recovery)",
        idempotent=True,
    ),
    "record-session": CommandSpec(
        name="record-session",
        handler_class=_lazy_record_session_handler(),
        actor="llm",
        action="declare_session",
        projection=ProjectionType.NONE,    # audit-only; no state change (I-SESSION-DECLARED-1)
        uses_task_id=False,
        requires_active_phase=False,       # valid for PLANNED phases (e.g. PLAN Phase N session)
        event_schema=(SessionDeclaredEvent,),
        preconditions=("session_type is a valid SDD session type",),
        postconditions=("SessionDeclaredEvent in EventLog",),
        description="Declare session type for audit trail (I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1)",
        dedup_policy=SessionDedupPolicy(),  # BC-48-D: I-SESSION-DEDUP-2
    ),
    "approve-spec": CommandSpec(
        name="approve-spec",
        handler_class=_lazy_approve_spec_handler(),
        actor="human",
        action="approve_spec",
        projection=ProjectionType.NONE,    # audit-only; no state change
        uses_task_id=False,
        requires_active_phase=False,       # spec approval may occur before phase activation
        event_schema=(),                   # SpecApproved — imported lazily in approve_spec.py
        preconditions=(
            "actor == human",
            "Spec_vN.md exists in specs_draft/",
            "Spec_vN.md NOT yet in specs/ (not already approved)",
        ),
        postconditions=("SpecApproved in EventLog",),
        description="Approve a spec draft — records SpecApproved event (BC-31-1)",
        idempotent=False,                  # each approval is a unique audit fact (I-CMD-IDEM-1, BC-31-1)
    ),
    "amend-plan": CommandSpec(
        name="amend-plan",
        handler_class=_lazy_amend_plan_handler(),
        actor="human",
        action="amend_plan",
        projection=ProjectionType.NONE,    # audit-only; no state change
        uses_task_id=False,
        requires_active_phase=False,       # custom guard enforces ACTIVE/COMPLETE; not PLANNED
        guard_factory=_lazy_amend_plan_guard_factory,
        event_schema=(),                   # PlanAmended — imported lazily in amend_plan.py
        preconditions=(
            "Plan_vN.md exists in plans/",
            "phase_status != PLANNED (phase must be activated)",
        ),
        postconditions=("PlanAmended in EventLog",),
        description="Record plan amendment after post-activation edit (BC-31-2)",
    ),
    "init-project": CommandSpec(
        name="init-project",
        handler_class=_lazy_init_project_handler(),
        actor="human",
        action="init_project",
        projection=ProjectionType.NONE,    # PostgreSQL DDL; no SDD state change
        uses_task_id=False,
        requires_active_phase=False,       # bootstrap command; runs before any phase
        event_schema=(),                   # ProjectInitializedEvent — imported lazily
        preconditions=(
            "payload.name matches [a-z][a-z0-9_]* (I-DB-SCHEMA-1)",
            "SDD_DATABASE_URL or payload.db_url set (I-DB-1)",
        ),
        postconditions=(
            "shared schema exists",
            "p_{name} schema exists",
            "shared.projects has record for name",
        ),
        description="Create PostgreSQL project schema and register it (BC-32-0, BC-32-1, I-DB-SCHEMA-1)",
    ),
    "rebuild-state": CommandSpec(
        name="rebuild-state",
        handler_class=_lazy_rebuild_state_handler(),
        actor="llm",
        action="rebuild_state",
        projection=ProjectionType.FULL,    # full replay from seq=0 (I-STATE-REBUILD-1, I-1)
        uses_task_id=False,
        requires_active_phase=False,       # maintenance/recovery command
        event_schema=(),
        preconditions=(),
        postconditions=("State_index.yaml rebuilt from seq=0 (I-STATE-REBUILD-1)",),
        description="Rebuild full projection from seq=0 via IncrementalReducer (I-STATE-REBUILD-1, I-1)",
    ),
    "sync-invariants": CommandSpec(
        name="sync-invariants",
        handler_class=_lazy_sync_invariants_handler(),
        actor="llm",
        action="sync_invariants",
        projection=ProjectionType.NONE,    # InvariantRegistered is in _KNOWN_NO_HANDLER; no SDDState change
        uses_task_id=False,
        requires_active_phase=False,       # catalog sync; independent of phase lifecycle
        event_schema=(InvariantRegistered,),
        preconditions=("norm_catalog.yaml readable",),
        postconditions=("InvariantRegistered in EventLog for each norm in catalog",),
        description="Sync norm catalog invariants to EventLog (I-SYNC-INVARIANTS-1)",
    ),
    "analytics-refresh": CommandSpec(
        name="analytics-refresh",
        handler_class=_lazy_analytics_refresh_handler(),
        actor="llm",
        action="refresh_analytics",
        projection=ProjectionType.NONE,    # PostgreSQL DDL; no SDD state change
        uses_task_id=False,
        requires_active_phase=False,       # observability command; independent of phase lifecycle
        event_schema=(),                   # AnalyticsRefreshedEvent — imported lazily
        preconditions=(
            "payload.name matches [a-z][a-z0-9_]* (I-DB-SCHEMA-1)",
            "SDD_DATABASE_URL or payload.db_url set (I-DB-1)",
        ),
        postconditions=(
            "analytics.all_events FROM references p_{name}",
            "analytics.all_tasks FROM references p_{name}",
            "analytics.all_phases FROM references p_{name}",
            "analytics.all_invariants FROM references p_{name}",
        ),
        description="Refresh analytics views for a project schema (BC-32-4, I-DB-SCHEMA-1)",
    ),
}


# ---------------------------------------------------------------------------
# Private kernel error event (Phase 15 fields — events.py has old ErrorEvent)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _KernelErrorEvent(DomainEvent):
    """L2 observability event emitted by execute_command on kernel failure.
    Uses event_type='ErrorOccurred' (registered in _KNOWN_NO_HANDLER — I-ERROR-L2-1).
    """
    stage:              str         # BUILD_CONTEXT | GUARD | EXECUTE | COMMIT | PROJECT
    command:            str         # spec.name
    error_type:         str
    reason:             str         # machine-readable structured code
    human_reason:       str         # ≤140 chars, no internal IDs
    violated_invariant: str | None
    trace_id:           str         # 16 hex chars
    context_hash:       str         # 32 hex chars, or "FAIL:<ExcType>" sentinel
    error_code:         int         # 1–7 (A-15, A-16, I-ERROR-CODE-1)


# ---------------------------------------------------------------------------
# Kernel helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_context_hash(state: SDDState) -> str:
    """Stable 32-hex-char hash of the replayed state (A-22, I-DIAG-1)."""
    return state.state_hash[:32]


def _make_error_event(
    stage: str,
    spec: CommandSpec,
    error_type: str,
    reason: str,
    human_reason: str,
    violated_invariant: str | None,
    trace_id: str,
    context_hash: str,
    error_code: int,
) -> _KernelErrorEvent:
    return _KernelErrorEvent(
        event_type="ErrorOccurred",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L2,
        event_source="runtime",
        caused_by_meta_seq=None,
        stage=stage,
        command=spec.name,
        error_type=error_type,
        reason=reason,
        human_reason=human_reason[:140],
        violated_invariant=violated_invariant,
        trace_id=trace_id,
        context_hash=context_hash,
        error_code=error_code,
    )


def _write_error_to_audit_log(
    error_event: _KernelErrorEvent,
    audit_path: str | None = None,
) -> None:
    """Append error event to audit_log.jsonl (fallback when DuckDB is unavailable)."""
    path = audit_path or str(audit_log_file())
    try:
        line = json.dumps(dataclasses.asdict(error_event), sort_keys=True) + "\n"
        import os
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        _log.error("_write_error_to_audit_log: failed to write to %s", path)


def _extract_task_id(cmd: Any) -> str | None:
    """Extract task_id from command payload or direct attribute."""
    if hasattr(cmd, "task_id"):
        return cast(str | None, cmd.task_id)
    payload = getattr(cmd, "payload", {})
    return cast(str | None, payload.get("task_id"))


def _find_task(taskset_path: str, task_id: str) -> Task | None:
    """Find a task by ID in the TaskSet file; returns None if not found."""
    try:
        all_tasks = parse_taskset(taskset_path)
        return next((t for t in all_tasks if t.task_id == task_id), None)
    except Exception:
        return None


def _build_spec_guards(
    spec: CommandSpec,
    task_id: str | None,
    cmd: Any = None,
) -> list[Any]:
    """Build guard list respecting spec.requires_active_phase (A-20, I-SYNC-NO-PHASE-GUARD-1)."""
    guards: list[Any] = []
    if spec.requires_active_phase:
        guards.append(make_phase_guard(spec.name, task_id))
    if spec.name == "switch-phase" and cmd is not None:
        from sdd.commands.switch_phase import make_switch_phase_guard
        guards.append(make_switch_phase_guard(getattr(cmd, "phase_id", 0)))
    if task_id is not None and spec.uses_task_id:
        if spec.apply_task_guard:
            guards.append(make_task_guard(task_id))
        guards.append(partial(DependencyGuard.check, task_id=task_id))
    guards.append(make_norm_guard(spec.actor, spec.action, task_id))
    return guards


def _default_build_guards(spec: CommandSpec, cmd: Any) -> list[Any]:
    """Standard guard assembly from spec flags. Private to registry.py (I-CMD-GUARD-FACTORY-3)."""
    task_id = _extract_task_id(cmd)
    guards: list[Any] = []
    if spec.requires_active_phase:
        guards.append(make_phase_guard(spec.name, task_id))
    if task_id is not None and spec.uses_task_id:
        if spec.apply_task_guard:
            guards.append(make_task_guard(task_id))
        guards.append(partial(DependencyGuard.check, task_id=task_id))
    guards.append(make_norm_guard(spec.actor, spec.action, task_id))
    return guards


# ---------------------------------------------------------------------------
# Projector helpers (BC-43-F)
# ---------------------------------------------------------------------------

def _build_projector_if_configured() -> Any:  # Projector | None
    """Construct Projector from SDD_DATABASE_URL if set (BC-43-F, I-PROJ-SAFE-1)."""
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if not pg_url:
        return None
    try:
        from sdd.infra.projector import Projector  # lazy: avoid circular at module level
        return Projector(pg_url)
    except Exception as exc:
        _log.warning("_build_projector_if_configured: cannot build Projector: %s", exc)
        return None


def _apply_projector_safe(projector: Any, events: list[DomainEvent]) -> None:
    """Apply events to Projector; swallow exceptions (I-PROJ-SAFE-1, I-FAIL-1).

    Projector failure MUST NOT propagate — TX1 (event_log INSERT) is already committed.
    YAML rebuild (step 3 of execute_and_project) runs regardless of failure here.
    """
    if projector is None or not events:
        return
    for event in events:
        try:
            projector.apply(event)
        except Exception as exc:
            _log.warning(
                "Projector failed for %s: %s — Run sdd rebuild-state to recover (I-PROJ-SAFE-1)",
                event.event_type,
                exc,
            )


# ---------------------------------------------------------------------------
# Write Kernel: execute_command
# ---------------------------------------------------------------------------

def execute_command(
    spec: CommandSpec,
    cmd: Any,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
    event_log: EventLogKernelProtocol | None = None,
) -> list[DomainEvent]:
    """Write Kernel: build GuardContext → guard pipeline → handler (pure) → EventLog.append.

    Implements Spec_v15 §2 BC-15-REGISTRY steps 0–5 (A-7..A-22).
    event_log: injected EventLog implementation (I-ELK-PROTO-1); defaults to EventLog(db_path).
    """
    with kernel_context("execute_command"):
        _db  = db_path    or event_store_url()
        _st  = state_path or str(state_file())
        _ts_override = taskset_path   # A-18: deferred — resolved from state.phase_current after step 1
        _nrm = norm_path  or str(norm_catalog_file())
        _el: EventLogKernelProtocol = event_log if event_log is not None else open_event_log(_db)

        # Pre-Step: session dedup view — built iff spec.dedup_policy is set (I-SESSIONS-VIEW-LOCAL-1, I-PROJECTION-FRESH-1)
        sessions_view = None
        if spec.dedup_policy is not None:
            _pg_url = os.environ.get("SDD_DATABASE_URL")
            if _pg_url:
                from sdd.db.connection import open_db_connection as _open_db_conn  # noqa: PLC0415
                from sdd.infra.projector import _sync_p_sessions, build_sessions_view  # noqa: PLC0415
                _dedup_conn = _open_db_conn(_pg_url)
                try:
                    _sync_p_sessions(_dedup_conn)
                    sessions_view = build_sessions_view(_dedup_conn)
                finally:
                    _dedup_conn.close()

        # Step 0: stable idempotency key + per-execution trace correlation (A-7, A-9)
        command_id = compute_command_id(cmd)          # A-7: payload-only, stable across all retries
        context_hash: str = "FAIL:UNKNOWN"            # A-10: overwritten on success or exc type known
        try:
            head_seq: int | None = _el.max_seq()
        except Exception:
            head_seq = None                            # A-9: trace_id fallback path
        trace_id = compute_trace_id(cmd, head_seq)    # A-9: None-safe; diagnostic per-execution ID

        # Step 1: build GuardContext from EventLog replay (NEVER from YAML — I-CMD-11)
        try:
            state = get_current_state(_db)
        except Exception as exc:
            exc_type = type(exc).__name__[:20]
            context_hash = f"FAIL:{exc_type}"         # A-10: type-specific sentinel
            error_event = _make_error_event(
                stage="BUILD_CONTEXT", spec=spec,
                error_type=type(exc).__name__,
                reason=f"EVENTLOG_REPLAY_FAILED.{type(exc).__name__}",
                human_reason="EventLog replay failed — database may be inaccessible or corrupted",
                violated_invariant=None,
                trace_id=trace_id,
                context_hash=context_hash,
                error_code=5,
            )
            _write_error_to_audit_log(error_event)
            raise

        context_hash = compute_context_hash(state)

        # A-18: resolve taskset path from replay-derived phase (I-CMD-PHASE-RESOLVE-1)
        _ts = _ts_override or str(taskset_file(state.phase_current))

        # A-13: validate phase_id in task-scoped payloads (I-CMD-PAYLOAD-PHASE-1)
        if spec.uses_task_id:
            payload = getattr(cmd, "payload", {})
            cmd_phase_id = payload.get("phase_id") if hasattr(payload, "get") else getattr(cmd, "phase_id", None)
            if cmd_phase_id is not None and cmd_phase_id != state.phase_current:
                raise InvariantViolationError(
                    f"I-CMD-PAYLOAD-PHASE-1: payload.phase_id={cmd_phase_id} "
                    f"!= state.phase_current={state.phase_current}"
                )

        phase = PhaseState(phase_id=state.phase_current, status=state.phase_status)
        task_id = _extract_task_id(cmd)
        task = _find_task(_ts, task_id) if (spec.uses_task_id and task_id) else None
        norms = load_catalog(_nrm, strict=True)
        ctx = GuardContext(
            state=state,
            phase=phase,
            task=task,
            norms=norms,
            event_log=EventLogView(db_path=_db),
            task_graph=load_dag(_ts) if spec.uses_task_id else DAG(deps={}),
            now=_utc_now_iso(),
        )

        # Step 2: guard pipeline — pure; returns (result, audit_events) (A-20)
        guards = spec.build_guards(cmd)
        guard_result, audit_events = _run_domain_pipeline(ctx, guards, stop_on_deny=True)

        # A-15: DENY without diagnostic fields is a kernel programming error (I-GUARD-REASON-1)
        if guard_result.outcome is GuardOutcome.DENY and guard_result.reason is None:
            error_event = _make_error_event(
                stage="GUARD", spec=spec, error_type="KernelInvariantError",
                reason="KERNEL_INVARIANT.I-GUARD-REASON-1",
                human_reason="Internal kernel error: guard returned DENY without diagnostic fields",
                violated_invariant="I-GUARD-REASON-1",
                trace_id=trace_id, context_hash=context_hash, error_code=7,
            )
            try:
                _el.append([error_event], source="kernel_invariant_check")
            except Exception:
                _write_error_to_audit_log(error_event)
            raise KernelInvariantError("I-GUARD-REASON-1: DENY result must populate reason")

        # Step 3: DENY — append audit + ErrorEvent; raise GuardViolationError
        if guard_result.outcome is GuardOutcome.DENY:
            error_event = _make_error_event(
                stage="GUARD", spec=spec,
                error_type="GuardViolationError",
                reason=guard_result.reason or "GUARD_DENIED",
                human_reason=guard_result.human_reason or guard_result.message,
                violated_invariant=guard_result.violated_invariant,
                trace_id=trace_id, context_hash=context_hash, error_code=1,
            )
            try:
                _el.append(audit_events + [error_event], source="guards")
            except Exception:
                _write_error_to_audit_log(error_event)
            raise GuardViolationError(guard_result.message)

        # Step 2.5: session dedup policy check — only if spec.dedup_policy is set
        # (I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1, I-DEDUP-NOT-STRONG-1)
        if spec.dedup_policy is not None and sessions_view is not None:
            _s_type = getattr(cmd, "session_type", None)
            _s_phase = getattr(cmd, "phase_id", None)
            if not spec.dedup_policy.should_emit(sessions_view, cmd):
                _log.info("Session deduplicated: type=%s phase=%s", _s_type, _s_phase)
                from sdd.infra.metrics import record_metric as _record_metric  # noqa: PLC0415
                _record_metric(
                    "session_dedup_skipped_total",
                    value=1,
                    phase_id=_s_phase,
                    context={"session_type": _s_type, "phase_id": _s_phase},
                    db_path=_db,
                )
                return []

        # Step 4: call handler (pure: no I/O inside handle())
        try:
            handler_events = spec.handler_class(_db).handle(cmd)
        except Exception as exc:
            error_events = getattr(exc, "_sdd_error_events", [])
            error_code = 2 if isinstance(exc, InvariantViolationError) else 3
            error_event = _make_error_event(
                stage="EXECUTE", spec=spec,
                error_type=type(exc).__name__,
                reason=f"HANDLER_EXCEPTION.{type(exc).__name__}",
                human_reason=getattr(exc, "human_reason", f"Handler failed: {type(exc).__name__}")[:140],
                violated_invariant=getattr(exc, "invariant_id", None),
                trace_id=trace_id, context_hash=context_hash, error_code=error_code,
            )
            try:
                _el.append(error_events + [error_event], source="error_boundary")
            except Exception:
                _write_error_to_audit_log(error_event)
            raise

        # Step 5: atomic check+write — A-17 eliminates TOCTOU between max_seq() read and INSERT.
        # EventLog.append verifies max_seq == head_seq inside a DuckDB transaction before INSERT
        # (I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1). StaleStateError raised by append if head has advanced.
        # For idempotent=False (navigation cmds): uuid4() prevents dedup while preserving traceability
        # (I-CMD-IDEM-1). expected_head kept in both cases — optimistic lock is independent of idempotency.
        if handler_events:
            effective_command_id = command_id if spec.idempotent else str(uuid.uuid4())
            try:
                _el.append(
                    handler_events,
                    source=spec.handler_class.__module__,
                    command_id=effective_command_id,
                    expected_head=head_seq,   # A-17: transaction-level check before INSERT
                )
            except StaleStateError:
                error_event = _make_error_event(
                    stage="COMMIT", spec=spec, error_type="StaleStateError",
                    reason=f"EVENTLOG_CHANGED.expected={head_seq}",
                    human_reason="Event log was modified during execution — please retry the command",
                    violated_invariant="I-OPTLOCK-1",
                    trace_id=trace_id, context_hash=context_hash, error_code=6,
                )
                try:
                    _el.append([error_event], source="optimistic_lock")
                except Exception:
                    _write_error_to_audit_log(error_event)
                raise
            except Exception as commit_exc:
                error_event = _make_error_event(
                    stage="COMMIT", spec=spec,
                    error_type="CommitError",
                    reason=f"EVENT_COMMIT_FAILED.{type(commit_exc).__name__}",
                    human_reason="EventLog write failed — database may be locked or corrupted",
                    violated_invariant=None,
                    trace_id=trace_id, context_hash=context_hash, error_code=4,
                )
                _write_error_to_audit_log(error_event)
                raise CommitError(str(commit_exc)) from commit_exc

        return handler_events


# ---------------------------------------------------------------------------
# Projection Engine: project_all
# ---------------------------------------------------------------------------

def project_all(
    projection: ProjectionType,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
) -> None:
    """Projection Engine: always uses RebuildMode.STRICT (I-REBUILD-EMERGENCY-1).

    Single EventLog replay: rebuild_state result propagated to rebuild_taskset (I-REPLAY-1).
    """
    if projection == ProjectionType.NONE:
        return
    _db = db_path    or event_store_url()
    _st = state_path or str(state_file())
    state = rebuild_state(_db, _st, mode=RebuildMode.STRICT)
    if projection == ProjectionType.FULL and taskset_path:
        rebuild_taskset(_db, taskset_path, state=state)


# ---------------------------------------------------------------------------
# CLI convenience: execute_and_project
# ---------------------------------------------------------------------------

def execute_and_project(
    spec: CommandSpec,
    cmd: Any,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
    projector: Any = None,  # Projector | None
) -> list[DomainEvent]:
    """CLI convenience: execute_command → _apply_projector_safe → project_all(spec.projection).

    Pipeline (BC-43-F):
      TX1: execute_command (event_log INSERT)
      TX2: _apply_projector_safe (p_* UPDATE, swallows exceptions — I-PROJ-SAFE-1)
      TX3: project_all → YAML rebuild (conditional on spec.projection)
    PROJECT-stage failures emit ErrorEvent to audit_log.jsonl (A-16, I-ERROR-1).
    """
    events = execute_command(spec, cmd, db_path, state_path, taskset_path, norm_path)

    # Step 2: TX2 — apply to p_* tables via Projector (BC-43-F, I-PROJ-SAFE-1)
    _proj = projector if projector is not None else _build_projector_if_configured()
    try:
        _apply_projector_safe(_proj, events)
    finally:
        if _proj is not None and projector is None:
            _proj.close()

    if spec.projection == ProjectionType.NONE:
        return events

    _db = db_path or event_store_url()
    try:
        project_all(spec.projection, db_path, state_path, taskset_path)
    except Exception as proj_exc:
        # Events committed successfully; only projection failed.
        try:
            post_head: int | None = open_event_log(_db).max_seq()
        except Exception:
            post_head = None
        trace_id = compute_trace_id(cmd, post_head)
        error_event = _make_error_event(
            stage="PROJECT", spec=spec,
            error_type=type(proj_exc).__name__,
            reason=f"PROJECTION_FAILED.{type(proj_exc).__name__}",
            human_reason="State projection failed after commit — run sdd sync-state to recover",
            violated_invariant=None,
            trace_id=trace_id,
            context_hash="FAIL:PROJECTION",
            error_code=5,
        )
        _write_error_to_audit_log(error_event)
        raise ProjectionError(str(proj_exc)) from proj_exc
    return events
