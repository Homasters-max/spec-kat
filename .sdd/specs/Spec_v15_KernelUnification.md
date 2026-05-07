# Spec_v15 — Phase 15: Kernel Unification & Event-Sourced Control Plane

Status: ACTIVE
Baseline: Spec_v14_ControlPlaneMigration.md; gap-corrected plan at /root/.claude/plans/enumerated-swimming-horizon.md

---

## 0. Goal

Unify the SDD command execution model around a single authoritative registry of command
contracts (`CommandSpec`), eliminate I/O side effects from command handlers (making them
pure functions), and complete the event-sourced control plane so that `State_index.yaml`
is always 100% a snapshot of `reduce(events)` with no YAML-as-truth residue.

Three foundational invariants are added to `CLAUDE.md §0` and made machine-enforceable:

```
I-1: All state        = reduce(events)           YAML = readonly snapshot
I-2: All commands     = execute(spec)            single execution path
I-3: All side-effects = kernel only              handlers are pure
```

After this phase:
- Every write CLI command routes through `REGISTRY[name] → execute_and_project(spec, ...)`
- `handle()` methods return events only — zero I/O, zero EventStore calls, zero projection calls
- Phase transitions emit canonical `PhaseStarted` + `TaskSetDefined` events that the reducer
  understands directly, making `phase.current` derivable from EventLog alone without reading YAML
- `rebuild_state()` defaults to `STRICT` mode (YAML ignored entirely)
- Handler purity and kernel boundary rules are enforced by CI grep-rules and an AST test,
  not by convention
- `execute_command` absorbs and replaces `CommandRunner.run()` as the unified Write Kernel;
  `CommandRunner` is deleted entirely (Step 4)

### Architecture Closure Decisions (applied before any task begins)

Six amendments close gaps that would otherwise break CI enforcement at Step 3:

| ID | Gap | Fix |
|----|-----|-----|
| A-1 | `record-decision` calls `EventStore.append` directly — second write path | Add to REGISTRY; purify handler |
| A-2 | `validate-config` calls `handler.handle()` — violates `.handle(` grep rule | Replace with plain function; no REGISTRY entry |
| A-3 | `run_guard_pipeline` stranded in `sdd_run.py` after `CommandRunner` deleted | Move to `guards/pipeline.py`; import there directly |
| A-4 | `guards/phase.py`, `guards/task.py` read YAML as fallback — second truth source | Remove fallback; fail hard with JSON error |
| A-5 | `RebuildMode.EMERGENCY` has no usage constraint — could enter normal paths | Only operator-direct call; never via `execute_and_project` |
| A-6 | EventLog replay failure at `BUILD_CONTEXT` stage → `context_hash` unavailable | Use sentinel `"BUILD_CONTEXT_FAILED"` instead of `None`; `context_hash: str` is always non-None (superseded by A-10) |
| A-7 | `execute_command` is not idempotent: retry after `project_all` crash duplicates events | Separate `command_id = sha256(payload_only)` (stable across retries) from `trace_id` (per-execution with `head_seq`); DuckDB `UNIQUE(command_id, event_index)` + `INSERT … ON CONFLICT DO NOTHING` + log when rows_inserted == 0 |
| A-8 | Reducer trusts PhaseStarted ordering; reordered or manually injected events yield logically impossible state | Soft guard in PhaseStarted handler: if `event.phase_id ≠ state.phase_current + 1` → log warning, return unchanged state |
| A-9 | `trace_id` depends on `head_seq` from EventStore; if EventStore is down at step 0, trace_id is uncomputable | `compute_trace_id(cmd, head_seq: int | None)` — when `head_seq is None`, fallback to `sha256(command_type + str(payload))[:16]` |
| A-10 | `context_hash=None` (A-6 original) breaks diagnostic completeness — `None` is not a string diagnostic value | Replace `None` with failure-type sentinel `f"FAIL:{exc_type}"` (e.g. `"FAIL:duckdb.Error"`); `context_hash: str` always non-None; different failure types are distinguishable |
| A-11 | Guard pipeline and handler see same `state` snapshot, but EventLog may change between BUILD_CONTEXT and EXECUTE in concurrent or retry scenarios | Optimistic lock: verify `EventStore.max_seq() == head_seq` at step 5a before append; raise `StaleStateError` (error_code=6) on mismatch |
| A-12 | `RebuildMode.EMERGENCY` has no runtime enforcement — developer error (wrong call site) is allowed silently | Hard env-var guard: `assert os.environ.get("SDD_EMERGENCY") == "1"` at top of `rebuild_state` when `mode == EMERGENCY` |
| A-13 | `compute_command_id` uses `str(cmd.payload)` — non-deterministic for complex types; key not phase-scoped so same task in re-activated phase is permanently blocked by `ON CONFLICT DO NOTHING` | Use `dataclasses.asdict(cmd.payload)` + `json.dumps(sort_keys=True)`; key extended to 32 hex chars; task-scoped payloads MUST include `phase_id` field (I-CMD-PAYLOAD-PHASE-1) |
| A-14 | `ActivatePhaseHandler._check_idempotent` reads EventLog inside `handle()` — violates I-HANDLER-PURE-1 | Remove `_check_idempotent`; partial failure is impossible with atomic `sdd_append_batch`; re-run safety via `command_id` UNIQUE constraint (I-HANDLER-BATCH-PURE-1) |
| A-15 | `assert` enforcing I-GUARD-REASON-1 is disabled by Python `-O` and fires before Error Boundary → no ErrorEvent emitted, violates I-ERROR-1 | Replace `assert` with structured `KernelInvariantError` (error_code=7) check that emits ErrorEvent before raising; `KernelInvariantError` added to error hierarchy |
| A-16 | PROJECT-stage `ErrorEvent` never emitted — `project_all` is called from `execute_and_project` outside `execute_command`; I-ERROR-1 coverage gap | Wrap `project_all` in `execute_and_project` with try/except; emit PROJECT ErrorEvent to `audit_log.jsonl`; raise `ProjectionError` |
| A-17 | Optimistic lock (A-11) has TOCTOU gap: `max_seq()` read and `INSERT` are separate DuckDB calls — concurrent writer can insert between them | Add `expected_head: int | None` parameter to `EventStore.append`; perform check+INSERT inside a single DuckDB transaction (I-OPTLOCK-ATOMIC-1); remove separate step 5a from `execute_command` |
| A-18 | `_current_phase(_db)` called before `head_seq` capture — if events inserted between the two calls, taskset path mismatches the replayed state | Defer taskset path resolution to after step 1 (`_ts = _ts_override or str(taskset_file(state.phase_current))`); I-CMD-PHASE-RESOLVE-1 |
| A-19 | `TaskSetDefined` reducer handler has no ordering guard (unlike `PhaseStarted` A-8) — out-of-order event sets `tasks_total` for wrong phase | Soft guard in `_handle_taskset_defined`: if `event.phase_id ≠ state.phase_current` → log warning, return unchanged state (I-TASKSET-ORDER-1) |
| A-20 | `sync-state` runs full guard pipeline including PhaseGuard (PG-3: `phase.status == ACTIVE`); blocked in COMPLETE/PLANNED states — exactly when recovery is needed | Add `requires_active_phase: bool = True` to `CommandSpec`; set `False` for `sync-state`; `run_guard_pipeline` skips PhaseGuard when flag is False (I-SYNC-NO-PHASE-GUARD-1) |
| A-21 | `ErrorEvent(phase_id=None, ...)` may conflict with frozen `DomainEvent.phase_id: int` — type error at runtime and mypy; breaking change per §0.15 if not declared | Explicitly declare `DomainEvent.phase_id: int \| None = None` as backward-compatible §0.15(a) extension; add I-ERROR-PHASE-NULL-1 |
| A-22 | `command_id` and `context_hash` truncated to 16 hex chars (64 bits) — birthday paradox collision risk for `command_id` causes legitimate commands silently dropped | Increase `command_id` and `context_hash` to 32 hex chars (128 bits); keep `trace_id` at 16 hex chars |

---

## 1. Scope

### In-Scope

- **BC-15-REGISTRY**: new `src/sdd/commands/registry.py` — `CommandSpec`, `REGISTRY`,
  `execute_command` (absorbs `CommandRunner`), `project_all`, `execute_and_project`
- **BC-15-GUARDS-PIPELINE**: new `src/sdd/guards/pipeline.py` — `run_guard_pipeline` moved
  from `sdd_run.py` (Amendment A-3); `registry.py` imports directly from here
- **BC-1 core/events.py**: add `PhaseStartedEvent`, `TaskSetDefinedEvent`, `ErrorEvent`;
  wire into `V1_L1_EVENT_TYPES` and `classify_event_level` — **must be a single atomic commit
  with the reducer changes** (C-1 atomicity rule, see §2 BC-1)
- **BC-2 domain/state/reducer.py**: 4 handler changes — PhaseCompleted, PhaseStarted,
  TaskSetDefined, PhaseInitialized backward-compat reset
- **BC-2 infra/projections.py**: add `RebuildMode(STRICT|EMERGENCY)`, simplify
  `rebuild_state` to pure-reduce path, add graceful `rebuild_taskset` missing-file guard
- **BC-4 commands/update_state.py**: purify `CompleteTaskHandler`, `ValidateTaskHandler`,
  `CheckDoDHandler`; replace `SyncStateHandler` with `NoOpHandler`; route `main()` via
  `execute_and_project`
- **BC-4 commands/activate_phase.py**: emit `PhaseStartedEvent`; add `--tasks N` arg;
  route `main()` via `execute_and_project`; remove direct `EventStore.append` from `main()`
- **BC-4 commands/record_decision.py**: purify handler; add to REGISTRY (Amendment A-1)
- **BC-4 commands/validate_config.py**: replace handler with plain function (Amendment A-2)
- **BC-4 guards/phase.py**, **guards/task.py**: remove YAML fallback (Amendment A-4)
- **Technical enforcement**: CI grep-rules in `Makefile` + new
  `tests/unit/test_handler_purity.py` (AST-based) + `tests/unit/test_registry_contract.py`
- **Delete**: `src/sdd/commands/sdd_run.py` (Step 4); `tests/unit/commands/test_sdd_run.py`
- **Tests**: reducer, rebuild_state, execute_command, integration Phase N→N+1
- **CLAUDE.md**: §0 invariants, §0.5 Status Transition Table, §0.8 SEM-10/SEM-11, §0.10 Tool
  Reference, §R.6/R.7 pre-exec guard steps, §0.15 frozen interfaces, §0.16 new invariants,
  §0.17 Phase FSM, §0.18 Responsibility Matrix, §0.19 Error Semantics quick-reference

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-15-REGISTRY: `src/sdd/commands/registry.py`

```
src/sdd/commands/
  registry.py          # CommandSpec, REGISTRY, Write Kernel, Projection Engine
src/sdd/guards/
  pipeline.py          # run_guard_pipeline (moved from sdd_run.py — Amendment A-3)
```

This module is the sole execution path for all SDD write CLI commands (I-SPEC-EXEC-1).

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLI (adapter)     cli.py: REGISTRY[name] → execute_and_project     │
├─────────────────────────────────────────────────────────────────────┤
│  REGISTRY          dict[str, CommandSpec] — single source of truth  │
├─────────────────────────┬───────────────────────────────────────────┤
│  Write Kernel           │  Projection Engine                         │
│  execute_command():     │  project_all():                            │
│   build GuardContext    │   rebuild_state(STRICT)                    │
│   run_guard_pipeline    │   rebuild_taskset() if FULL                │
│   DENY → append + raise │                                            │
│   handler.handle(cmd)   │                                            │
│   error_boundary        │                                            │
│   EventStore.append()   │                                            │
├─────────────────────────┴───────────────────────────────────────────┤
│  EventLog (DuckDB)          single source of truth                   │
├─────────────────────────────────────────────────────────────────────┤
│  Reducer (pure)             reduce(events) → SDDState                │
├─────────────────────────────────────────────────────────────────────┤
│  State_index.yaml           snapshot of reduce(events)               │
└─────────────────────────────────────────────────────────────────────┘
```

**`execute_command` absorbs `CommandRunner.run()`**: the existing `CommandRunner` class in
`sdd_run.py` contains the correct logic for building `GuardContext` from EventLog replay,
running the guard pipeline, appending audit events on DENY, catching handler exceptions,
and appending handler events. `execute_command` is a redesigned form of this logic, with
`CommandSpec` replacing per-call keyword arguments.

### BC-15-GUARDS-PIPELINE: `src/sdd/guards/pipeline.py` (Amendment A-3)

`run_guard_pipeline` is moved from `sdd_run.py` to `guards/pipeline.py`. This is not a
transitional adapter — it is the permanent home for guard pipeline composition logic.

**Why not `guards_adapter.py`:** an adapter module between `registry.py` and `guards/`
creates a permanent indirection layer that has no semantic purpose once `sdd_run.py` is
deleted. `guards/pipeline.py` is semantically coherent: it composes guard domain objects
into a pipeline. `registry.py` imports directly:

```python
from sdd.guards.pipeline import run_guard_pipeline
```

`sdd_run.py` retains `run_guard_pipeline` temporarily during Step 1 (copy, not move).
It is deleted entirely in Step 4 (I-SDDRUN-DEAD-1).

### BC-15-REGISTRY: Read-Only Path Architecture (Amendment A-2)

`validate-config`, `show-task`, `show-spec`, `show-plan`, `show-state`, `query-events`,
`metrics-report`, `report-error` are **read-only commands** that MUST NOT appear in `REGISTRY`.

**Invariant I-READ-ONLY-EXCEPTION-1** defines the hard boundary these commands must obey:
a read-only command bypassing REGISTRY is permitted if and only if it never:
- calls `EventStore.append` (no write path)
- calls `rebuild_state` or `sync_projections` (no projection)
- calls any `handler.handle()` (no kernel invocation)
- reads or writes `State_index.yaml` as truth (no YAML mutation)

Violation of any rule → command MUST be moved to REGISTRY. This invariant prevents
read-only commands from accumulating side effects and becoming a shadow kernel over time
(I-READ-ONLY-EXCEPTION-1, new SEM-11 behavioral norm).

### BC-15-REGISTRY: `CommandSpec` dataclass

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Literal

class ProjectionType(Enum):
    NONE       = "none"        # no projection after write
    STATE_ONLY = "state_only"  # rebuild State_index only
    FULL       = "full"        # rebuild State_index + TaskSet

@dataclass(frozen=True)
class CommandSpec:
    name:                  str
    handler_class:         type[CommandHandlerBase]
    actor:                 Literal["llm", "human", "any"]
    action:                str                                # passed to NormGuard
    projection:            ProjectionType
    uses_task_id:          bool                               # True → TaskGuard+DependencyGuard run
    event_schema:          tuple[type[DomainEvent], ...]      # expected output event types
    preconditions:         tuple[str, ...]
    postconditions:        tuple[str, ...]
    requires_active_phase: bool = True                        # A-20: False → PhaseGuard skipped (I-SYNC-NO-PHASE-GUARD-1)
    description:           str = ""
```

**No `guards` field**: the guard pipeline is always the fixed sequence (phase → task →
dependency → norm). What varies per command is `actor`, `action`, `uses_task_id`, and
`requires_active_phase`. `execute_command` builds the pipeline from these fields:
- `requires_active_phase=False` → PhaseGuard skipped (e.g., `sync-state` — A-20)
- `uses_task_id=False` → TaskGuard + DependencyGuard skipped
- NormGuard always runs

`event_schema` enables contract tests: the handler, when invoked with a mock context,
MUST emit exactly those event types. `preconditions` and `postconditions` are
machine-readable strings for auto-generated documentation and integration test assertions.

### BC-15-REGISTRY: `REGISTRY`

```python
REGISTRY: dict[str, CommandSpec] = {
    "complete": CommandSpec(
        name="complete",
        handler_class=CompleteTaskHandler,
        actor="llm",
        action="implement_task",
        projection=ProjectionType.FULL,
        uses_task_id=True,
        event_schema=(TaskImplementedEvent, MetricRecordedEvent),
        preconditions=("phase.status == ACTIVE", "task.status == TODO"),
        postconditions=("task.status == DONE", "tasks.completed += 1"),
    ),
    "validate": CommandSpec(
        name="validate",
        handler_class=ValidateTaskHandler,
        actor="llm",
        action="validate_task",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=True,
        event_schema=(TaskValidatedEvent, MetricRecordedEvent),
        preconditions=("task.status == DONE", "--result in {PASS, FAIL}"),
        postconditions=("invariants.status updated", "tests.status updated"),
    ),
    "check-dod": CommandSpec(
        name="check-dod",
        handler_class=CheckDoDHandler,
        actor="llm",
        action="check_dod",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=False,
        event_schema=(PhaseCompletedEvent, MetricRecordedEvent),
        preconditions=(
            "tasks.completed == tasks.total",
            "invariants.status == PASS",
            "tests.status == PASS",
        ),
        postconditions=("phase.status == COMPLETE",),
    ),
    "activate-phase": CommandSpec(
        name="activate-phase",
        handler_class=ActivatePhaseHandler,
        actor="human",
        action="activate_phase",
        projection=ProjectionType.STATE_ONLY,
        uses_task_id=False,
        event_schema=(PhaseStartedEvent, TaskSetDefinedEvent),
        preconditions=("actor == human",),
        postconditions=("phase.current == N", "phase.status == ACTIVE"),
    ),
    "sync-state": CommandSpec(
        name="sync-state",
        handler_class=NoOpHandler,
        actor="any",
        action="sync_state",
        projection=ProjectionType.FULL,
        uses_task_id=False,
        requires_active_phase=False,   # A-20: recovery utility; PhaseGuard skipped (I-SYNC-NO-PHASE-GUARD-1)
        event_schema=(),
        preconditions=(),
        postconditions=("State_index.yaml rebuilt from EventLog",),
    ),
    "record-decision": CommandSpec(
        name="record-decision",
        handler_class=RecordDecisionHandler,
        actor="human",
        action="record_decision",
        projection=ProjectionType.NONE,   # decisions are audit-only; no state change
        uses_task_id=False,
        event_schema=(DecisionRecordedEvent,),
        preconditions=("decision_id matches D-<number>", "summary <= 500 chars"),
        postconditions=("DecisionRecordedEvent in EventLog",),
    ),
}

# Note on DecisionRecordedEvent forward-compat (🟡8):
# DecisionRecordedEvent carries schema_version: int = 1 (frozen at Phase 15).
# This field exists exclusively for future schema evolution — if a new decision type
# ever needs state-mutation semantics, a distinct event type with schema_version=2 and
# its own reducer handler MUST be introduced. DecisionRecordedEvent (schema_version=1)
# MUST NEVER affect execution semantics — it is a pure audit record (I-DECISION-AUDIT-1).
```

**REGISTRY scope**: contains only write commands that emit events or trigger projections.
Read-only commands (`show-task`, `show-spec`, `show-plan`, `show-state`, `query-events`,
`report-error`, `metrics-report`, `validate-config`) are NOT in REGISTRY — they never
pass through the Write Kernel. See I-REGISTRY-COMPLETE-1 and I-READ-ONLY-EXCEPTION-1.

**`record-decision` projection=NONE rationale**: `DecisionRecordedEvent` MUST be in
`_KNOWN_NO_HANDLER` in the reducer — it has no state-reconstruction semantics. It is
a pure audit event. Phase transitions, task completions, and DoD outcomes are never
triggered by a decision record. If a future decision type requires state mutation, a new
event type with a reducer handler and a non-NONE projection MUST be specified separately
(I-DECISION-AUDIT-1).

### BC-15-REGISTRY: `execute_command`

```python
def execute_command(
    spec: CommandSpec,
    cmd: Command,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
) -> list[DomainEvent]:
    """Write Kernel: build GuardContext → guard pipeline → handler (pure) → EventStore.append."""
    _db  = db_path    or str(event_store_file())
    _st  = state_path or str(state_file())
    _ts_override = taskset_path   # A-18: deferred — resolved from state.phase_current after step 1 (I-CMD-PHASE-RESOLVE-1)
    _nrm = norm_path  or str(norm_catalog_file())

    # Step 0: stable idempotency key + per-execution trace correlation (A-7, A-9)
    command_id = compute_command_id(cmd)          # A-7: payload-only, stable across all retries
    context_hash: str = "FAIL:UNKNOWN"            # A-10: overwritten on success or exc type known
    try:
        head_seq: int | None = EventStore(_db).max_seq()
    except Exception:
        head_seq = None                            # A-9: trace_id fallback path
    trace_id = compute_trace_id(cmd, head_seq)    # A-9: None-safe; diagnostic per-execution ID

    # Step 1: build GuardContext from EventLog replay (NEVER from YAML — I-CMD-11)
    # On failure: emit ErrorEvent to audit_log.jsonl (EventStore unavailable here — I-ERROR-1)
    try:
        events_raw = _fetch_events_for_reduce(_db)
        state = EventReducer().reduce(events_raw)
    except Exception as exc:
        exc_type = type(exc).__name__[:20]
        context_hash = f"FAIL:{exc_type}"         # A-10: type-specific sentinel; "FAIL:" prefix
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
        _write_error_to_audit_log(error_event)   # DuckDB unavailable; audit_log is the fallback
        raise

    # context_hash computable only after successful state construction (I-DIAG-1 + A-6)
    context_hash = compute_context_hash(state)

    # A-18: resolve taskset path from replay-derived phase — consistent with state (I-CMD-PHASE-RESOLVE-1)
    _ts = _ts_override or str(taskset_file(state.phase_current))

    # A-13: validate phase_id in task-scoped payloads matches replayed state (I-CMD-PAYLOAD-PHASE-1)
    if spec.uses_task_id and hasattr(cmd.payload, "phase_id"):
        if cmd.payload.phase_id != state.phase_current:
            raise InvariantViolationError(
                f"I-CMD-PAYLOAD-PHASE-1: payload.phase_id={cmd.payload.phase_id} "
                f"!= state.phase_current={state.phase_current}"
            )

    phase = PhaseState(phase_id=state.phase_current, status=state.phase_status)
    task_id = _extract_task_id(cmd)
    task = _find_task(_ts, task_id) if spec.uses_task_id else None
    norms = load_catalog(_nrm, strict=True)
    ctx = GuardContext(
        state=state, phase=phase, task=task, norms=norms,
        event_log=EventLogView(db_path=_db),
        task_graph=load_dag(_ts) if spec.uses_task_id else DAG(deps={}),
        now=_utc_now_iso(),
    )

    # Step 2: guard pipeline — pure; returns (result, audit_events)
    guard_result, audit_events = run_guard_pipeline(
        ctx=ctx, command_str=spec.name, actor=spec.actor, action=spec.action,
        task_id=task_id, required_ids=(), input_paths=(),
        skip_phase_guard=not spec.requires_active_phase,   # A-20, I-SYNC-NO-PHASE-GUARD-1
    )
    # A-15: I-GUARD-REASON-1 — DENY without diagnostic fields is a kernel programming error.
    # Must emit ErrorEvent (I-ERROR-1) before raising; never use assert (disabled by -O).
    if guard_result.outcome is GuardOutcome.DENY and guard_result.reason is None:
        error_event = _make_error_event(
            stage="GUARD", spec=spec, error_type="KernelInvariantError",
            reason="KERNEL_INVARIANT.I-GUARD-REASON-1",
            human_reason="Internal kernel error: guard returned DENY without diagnostic fields",
            violated_invariant="I-GUARD-REASON-1",
            trace_id=trace_id, context_hash=context_hash, error_code=7,
        )
        try:
            EventStore(_db).append([error_event], source="kernel_invariant_check")
        except Exception:
            _write_error_to_audit_log(error_event)
        raise KernelInvariantError("I-GUARD-REASON-1: DENY result must populate reason")

    # Step 3: DENY — append audit + ErrorEvent; raise GuardViolationError
    if guard_result.outcome is GuardOutcome.DENY:
        error_event = _make_error_event(
            stage="GUARD", spec=spec,
            error_type="GuardViolationError",
            reason=guard_result.reason,
            human_reason=guard_result.human_reason,
            violated_invariant=guard_result.violated_invariant,
            trace_id=trace_id, context_hash=context_hash, error_code=1,
        )
        EventStore(_db).append(audit_events + [error_event], source="guards")
        raise GuardViolationError(guard_result.message)

    # Step 4: call handler (pure: no I/O inside handle()) — error boundary per I-ES-1
    try:
        handler_events = spec.handler_class().handle(cmd)
    except Exception as exc:
        error_events = getattr(exc, "_sdd_error_events", [])   # legacy — Phase 16 removes
        error_code = 2 if isinstance(exc, InvariantViolationError) else 3
        error_event = _make_error_event(
            stage="EXECUTE", spec=spec,
            error_type=type(exc).__name__,
            reason=f"HANDLER_EXCEPTION.{type(exc).__name__}",
            human_reason=getattr(exc, "human_reason", f"Handler failed: {type(exc).__name__}"),
            violated_invariant=getattr(exc, "invariant_id", None),
            trace_id=trace_id, context_hash=context_hash, error_code=error_code,
        )
        try:
            EventStore(_db).append(error_events + [error_event], source="error_boundary")
        except Exception:
            _write_error_to_audit_log(error_event)
        raise

    # Step 5: atomic check+write — A-17 eliminates TOCTOU between max_seq() read and INSERT.
    # EventStore.append verifies max_seq == head_seq inside a DuckDB transaction before INSERT
    # (I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1). StaleStateError raised by append if head has advanced.
    # command_id (payload-only, stable) enables idempotent retry; trace_id is diagnostic only.
    if handler_events:
        try:
            EventStore(_db).append(
                handler_events,
                source=spec.handler_class.__module__,
                command_id=command_id,
                expected_head=head_seq,   # A-17: transaction-level check before INSERT
            )
            # EventStore.append logs INFO when rows_inserted==0 (duplicate detected — A-7, I-IDEM-LOG-1)
        except StaleStateError:
            error_event = _make_error_event(
                stage="COMMIT", spec=spec, error_type="StaleStateError",
                reason=f"EVENTLOG_CHANGED.expected={head_seq}",
                human_reason="Event log was modified during execution — please retry the command",
                violated_invariant="I-OPTLOCK-1",
                trace_id=trace_id, context_hash=context_hash, error_code=6,
            )
            try:
                EventStore(_db).append([error_event], source="optimistic_lock")
            except Exception:
                _write_error_to_audit_log(error_event)
            raise
        except Exception as commit_exc:
            error_event = _make_error_event(
                stage="COMMIT", spec=spec,
                error_type="CommitError",
                reason=f"EVENT_COMMIT_FAILED.{type(commit_exc).__name__}",
                human_reason="EventStore write failed — database may be locked or corrupted",
                violated_invariant=None,
                trace_id=trace_id, context_hash=context_hash, error_code=4,
            )
            _write_error_to_audit_log(error_event)   # DuckDB down — audit_log fallback
            raise CommitError(str(commit_exc)) from commit_exc

    return handler_events
```

**Key points:**
- Step 0: `command_id = compute_command_id(cmd)` (stable, `dataclasses.asdict`-based, 32 hex chars — A-13, A-22); `trace_id` computed separately with `head_seq` (A-7, A-9)
- Step 1: EventLog replay → `state`; taskset path resolved from `state.phase_current` (A-18, I-CMD-PHASE-RESOLVE-1); if EventStore unreadable, ErrorEvent goes to `audit_log.jsonl`; `context_hash = f"FAIL:{type(exc).__name__[:20]}"` (A-10)
- Step 1 post-replay: task-scoped payloads validated for `phase_id == state.phase_current` (A-13, I-CMD-PAYLOAD-PHASE-1)
- Step 2: PhaseGuard skipped when `spec.requires_active_phase=False` (A-20); DENY-without-reason → `KernelInvariantError` with ErrorEvent (A-15, replaces `assert`)
- Step 5: atomic check+write via `expected_head=head_seq` inside DuckDB transaction — eliminates TOCTOU (A-17, I-OPTLOCK-ATOMIC-1); separate step 5a removed
- `context_hash` in later stages: `compute_context_hash(state)` — 32 hex chars real hash (A-22)
- No YAML reads anywhere in this function (I-CMD-11)

### BC-15-REGISTRY: Projection Engine and CLI convenience

```python
def project_all(
    projection: ProjectionType,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
) -> None:
    """Projection Engine: always uses RebuildMode.STRICT (I-REBUILD-EMERGENCY-1)."""
    if projection == ProjectionType.NONE:
        return
    rebuild_state(db_path, state_path, mode=RebuildMode.STRICT)
    if projection == ProjectionType.FULL and taskset_path:
        rebuild_taskset(db_path, taskset_path)


def execute_and_project(
    spec: CommandSpec,
    cmd: Command,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
) -> list[DomainEvent]:
    """CLI convenience: execute_command → project_all(spec.projection).
    PROJECT-stage failures emit ErrorEvent to audit_log.jsonl (A-16, I-ERROR-1)."""
    events = execute_command(spec, cmd, db_path, state_path, taskset_path, norm_path)
    if spec.projection == ProjectionType.NONE:
        return events

    _db = db_path or str(event_store_file())
    try:
        project_all(spec.projection, db_path, state_path, taskset_path)
    except Exception as proj_exc:
        # Events committed successfully; only projection failed.
        # trace_id uses post-commit head (EventLog has advanced past original head_seq).
        try:
            post_head: int | None = EventStore(_db).max_seq()
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
            context_hash="FAIL:PROJECTION",  # "FAIL:" prefix detectable; state was good, projection failed
            error_code=5,
        )
        _write_error_to_audit_log(error_event)   # EventStore may be down — audit_log fallback
        raise ProjectionError(str(proj_exc)) from proj_exc
    return events
```

`project_all` calls `rebuild_state` with `RebuildMode.STRICT` exclusively.
`RebuildMode.EMERGENCY` MUST NOT be called from `execute_and_project` or any automatic path
(I-REBUILD-EMERGENCY-1). EMERGENCY is operator-only via direct `rebuild_state(mode=RebuildMode.EMERGENCY)`.

### BC-1 `core/events.py`: new events — C-1 atomicity rule

```python
@dataclass(frozen=True)
class PhaseStartedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseStarted"
    phase_id:   int
    actor:      str   # "human"

@dataclass(frozen=True)
class TaskSetDefinedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskSetDefined"
    phase_id:    int
    tasks_total: int

@dataclass(frozen=True)
class ErrorEvent(DomainEvent):
    """L2 observability — emitted by execute_command on kernel failure. Reducer ignores."""
    EVENT_TYPE: ClassVar[str] = "ErrorOccurred"
    stage:              str         # BUILD_CONTEXT | GUARD | EXECUTE | COMMIT | PROJECT
    command:            str         # spec.name
    error_type:         str         # GuardViolationError | CommitError | ...
    reason:             str         # machine-readable structured code
    human_reason:       str         # ≤140 chars, no internal IDs
    violated_invariant: str | None  # "I-PHASE-RESET-1" if applicable
    trace_id:           str         # sha256(command_type + str(head_seq) + payload)[:16]; A-9 fallback omits head
    context_hash:       str         # A-10: always non-None; "FAIL:{ExcType[:20]}" sentinel at step 1 failure; "FAIL:" prefix detectable
    error_code:         int         # 1–6 semantic code (6 = StaleStateError — A-11)
```

**Single ErrorEvent class — no duplication**: there is exactly one `ErrorEvent` type in the
system (in `core/events.py`). The `stage` field already differentiates kernel phases:
`BUILD_CONTEXT | GUARD | EXECUTE | COMMIT | PROJECT`. No `KernelErrorEvent` sub-type is
introduced. The existing `_sdd_error_events` pattern in `_base.py` is deprecated in Phase 15
(still consumed via `getattr(exc, "_sdd_error_events", [])` for backward compat) and removed
in Phase 16 cleanup. Creating a second error event class would create two semantic layers
with no distinguishing boundary; the `stage` field is sufficient (I-ERROR-SINGLE-TYPE-1).

**C-1 atomicity rule**: `V1_L1_EVENT_TYPES` and `_EVENT_SCHEMA` are checked at import time.
Adding a new type to `V1_L1_EVENT_TYPES` without simultaneously adding its handler to
`_EVENT_SCHEMA` causes `ImportError` on next import. T-1501 (events.py) and the reducer
changes (also T-1501, one atomic commit) MUST be committed together.

`ErrorEvent` is NOT in `V1_L1_EVENT_TYPES` and NOT in `_EVENT_SCHEMA`. It is in
`_KNOWN_NO_HANDLER`. Replay of EventLog containing `ErrorEvent` entries produces identical
state as replay without them (I-ERROR-L2-1).

### BC-2 `domain/state/reducer.py`: 4 handler changes

**A — PhaseCompleted** (currently in `_KNOWN_NO_HANDLER`):
- Move to `_EVENT_SCHEMA`; add handler: `phase_status = COMPLETE; plan_status = COMPLETE`

**B — PhaseStarted** (new):
- Handler: `phase_current = event.phase_id; phase_status = ACTIVE; plan_status = ACTIVE`
  + reset tasks (total=0, completed=0, done_ids=[]) + reset invariants/tests to UNKNOWN

**C — TaskSetDefined** (new):
- Handler: `tasks_total = event.tasks_total`
- **Soft guard (A-19, I-TASKSET-ORDER-1):** if `event.phase_id ≠ state.phase_current` → `logging.warning(...)`, return unchanged state (deterministic no-op; analogous to A-8 for PhaseStarted)
- Prevents `tasks_total` being overwritten for the wrong phase from injected/reordered events

**D — PhaseInitialized** (backward compat fix):
- Existing handler MUST also reset tasks state (same fields as PhaseStarted handler)
- Prevents cross-phase task count bleed when replaying full EventLog for phases 1–14

These four changes make the reducer **self-resetting** and **single-pass**:
`reduce(all_events) → correct state` without external filter, without 2-pass, without YAML.

### BC-2 `infra/projections.py`: RebuildMode + simplification

```python
class RebuildMode(Enum):
    STRICT    = "strict"     # YAML ignored entirely (default, always correct post-Phase 15)
    EMERGENCY = "emergency"  # break-glass: empty EventLog bootstrap only (operator-direct)
```

`EMERGENCY` activates only on `phase_current == 0 AND YAML exists` — a condition that
cannot occur in a healthy, non-empty EventLog.

```python
def rebuild_state(
    db_path: str | None = None,
    state_path: str | None = None,
    mode: RebuildMode = RebuildMode.STRICT,
) -> None:
    state = EventReducer().reduce(_replay_all(db_path))
    if mode == RebuildMode.EMERGENCY and state.phase_current == 0:
        yaml_phase = _read_yaml_phase_current(state_path)
        if yaml_phase > 0:
            state = state._replace(phase_current=yaml_phase)
    _write_state(state, state_path)
```

`rebuild_taskset` adds existence check:
```python
def rebuild_taskset(db_path, taskset_path):
    if not Path(taskset_path).exists():
        logging.warning("rebuild_taskset: %s not found — skipping (I-ES-REPLAY-1)", taskset_path)
        return
```

### BC-4 Commands: purification summary

**`update_state.py`** — remove from each `handle()`:
- `CompleteTaskHandler`: `EventStore.append(...)` + `sync_projections(...)` → return events
- `ValidateTaskHandler`: `EventStore.append(...)` + `rebuild_state(...)` → return events
- `CheckDoDHandler`: `EventStore.append(...)` → return events
- `SyncStateHandler` → replaced by `NoOpHandler(return [])`

**`activate_phase.py`** — emit `PhaseStartedEvent` + optional `TaskSetDefinedEvent`; route `main()` via `execute_and_project`.

**`record_decision.py`** (Amendment A-1) — remove `EventStore(self._db_path).append(...)` from `handle()`; remove EventStore import; return `[DecisionRecordedEvent]`. `cli.py record-decision` switches to `execute_and_project(REGISTRY["record-decision"], ...)`.

**`validate_config.py`** (Amendment A-2):
- Delete `ValidateConfigHandler` class and `ValidateConfigCommand` dataclass
- Add `validate_project_config(phase_id: int, config_path: str) -> None` (raises `ConfigValidationError` on failure)
- `cli.py validate-config` calls the function directly — no `.handle()` call, so grep rule not violated
- Remove `ValidateConfig` from `COMMAND_REGISTRY` in `payloads.py`
- I-READ-ONLY-EXCEPTION-1 confirmed: function accesses no EventStore, no projections, no runtime state mutations

### BC-4 Guards: YAML fallback removal (Amendment A-4)

**`guards/phase.py`** — lines 59–65: remove YAML fallback block. If `--state` not provided:

```python
# BEFORE (removed):
if not args.state:
    state = read_state()   # second truth source — VIOLATION

# AFTER:
if not args.state:
    print(json.dumps({
        "error_type": "UsageError",
        "message": "--state is required; guards do not read YAML",
        "exit_code": 1,
    }), file=sys.stderr)
    sys.exit(1)
```

**This is a CLI-layer error, NOT a kernel error.** Missing argument = misuse of the CLI
adapter, not a guard violation in the semantic sense. Therefore:
- No trace_id (kernel not entered)
- No context_hash (state not built)
- No ErrorEvent (no kernel failure occurred)
- Exit 1 with JSON error satisfies I-FAIL-1 and I-CLI-API-1

The guard pipeline itself (`run_guard_pipeline` in `guards/pipeline.py`) MUST NOT call
`sys.exit`. It returns `GuardResult` with `DENY` outcome. `execute_command` catches DENY
and emits a full `ErrorEvent` with trace_id and context_hash through the normal path.
This preserves full diagnostic completeness for semantic guard violations (I-GUARD-CLI-1).

Same change applies to **`guards/task.py`** lines 98–105 (`--taskset` argument).

### BC-15-DURABILITY: Amendments A-7 through A-12

This subsection specifies the durability, idempotency, and safety mechanisms added by
amendments A-7..A-12. These do not change the happy-path protocol; they harden retry,
replay, concurrency, and misuse scenarios.

#### A-7: Command Idempotency

`execute_command` is atomic at the EventStore level (single INSERT — I-ATOMICITY-1) but is
**not idempotent**: if `project_all` crashes after the INSERT, a retry replays the handler
and produces duplicate events. The root problem is that the EventLog has no per-command
deduplication key.

**command_id vs trace_id — critical separation:**

Using `command_id = trace_id` would break idempotency in two cases:
- Retry after EventLog advances: `head_seq` changes → `trace_id` changes → new `command_id` → duplicate allowed
- A-9 fallback: if step 0 fails (EventStore down), `head_seq=None` → `trace_id` changes vs a prior full-hash `trace_id`

Fix: introduce `compute_command_id` as a **payload-only** stable key, distinct from `trace_id`:

```python
def compute_command_id(cmd: Command) -> str:
    """Stable idempotency key — invariant under retry, head_seq, and A-9 fallback.
    Same logical command always yields same command_id regardless of EventLog state."""
    payload = json.dumps(
        {"cmd": cmd.command_type, "payload": str(cmd.payload)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

`trace_id` retains its per-execution diagnostic role (includes `head_seq` when available).
They serve different purposes:

| Key | Scope | Changes on retry? | Purpose |
|-----|-------|-------------------|---------|
| `command_id` | logical command (payload) | No | Idempotency deduplication key |
| `trace_id` | execution attempt | Yes (head_seq changes) | Diagnostic correlation across stages |

Fix — four coordinated changes:

1. **New `compute_command_id`** function in `core/events.py` (alongside `compute_trace_id`).

2. **DuckDB schema**: add column `command_id TEXT` to the `events` table.
   `UNIQUE(command_id, event_index)` index is added. `command_id` is `NULL` for all legacy
   events; `NOT NULL` only for events emitted by Phase 15+ handlers (I-IDEM-SCHEMA-1).

3. **`EventStore.append`**: when `command_id` is supplied, executes
   `INSERT INTO events … ON CONFLICT (command_id, event_index) DO NOTHING`.
   **Not silent**: when `rows_inserted == 0`, emit a `logging.info("duplicate command
   detected", command_id=command_id)` — visible in debug output and distinguishable from
   logic errors (I-IDEM-LOG-1).

4. **`execute_command` step 0 + step 5**:
   - Step 0: `command_id = compute_command_id(cmd)` (before `head_seq` computation)
   - Step 5: `EventStore(_db).append(handler_events, source=…, command_id=command_id)`

`ErrorEvent` rows do NOT carry `command_id` — they are observability events, never
deduplicated (I-ERROR-L2-1 preserved). Audit events from guard DENY are also excluded.

#### A-8: Reducer Soft Guard for Event Ordering

The reducer currently assumes PhaseStarted events arrive in monotonic phase order. A
manually injected event (or a replay from a partially-corrupted log) can produce
`PhaseStarted(N+1)` before `PhaseCompleted(N)`, yielding logically impossible state and
non-deterministic replay results.

Fix — soft guard in the `PhaseStarted` reducer handler:

```python
def _handle_phase_started(state: SDDState, event: PhaseStartedEvent) -> SDDState:
    expected_next = state.phase_current + 1
    if event.phase_id != expected_next:
        logging.warning(
            "I-PHASE-ORDER-1: ignoring out-of-order PhaseStarted — "
            "expected phase_id=%d, got %d",
            expected_next, event.phase_id,
        )
        return state   # deterministic no-op; replay is stable
    # ... normal reset logic
```

"Soft" means the guard never raises — it logs and skips. Replay with reordered events
produces a deterministic, reproducible state (the out-of-order events are silently ignored).
This preserves I-PHASE-SEQ-1 for well-ordered logs and adds determinism for corrupted ones.

`PhaseInitialized` does NOT get this guard (it has no predecessor phase by definition).

**Observability note**: `logging.warning(...)` is the minimum required by this spec.
For production environments, a future phase MAY add an L2 `ReducerWarningEvent` (emitted
to EventLog, not to DuckDB — audit_log.jsonl or a separate observability sink) to make
ignored events queryable. This is deferred to Phase 16+ to avoid expanding the event schema
before the kernel is stable.

#### A-9: `trace_id` Fallback When EventStore Is Unavailable

`compute_trace_id` currently requires `head_seq = EventStore.max_seq()` (step 0). If
EventStore is inaccessible (DuckDB locked, file missing), step 0 fails before `trace_id`
is computed — breaking error observability before it starts.

Fix — `compute_trace_id` accepts `head_seq: int | None`:

```python
def compute_trace_id(cmd: Command, head_seq: int | None) -> str:
    if head_seq is not None:
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload), "head": head_seq},
            sort_keys=True,
        )
    else:
        # A-9 fallback: EventStore unavailable; payload-only hash (less unique but always computable)
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload)},
            sort_keys=True,
        )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

In `execute_command` step 0:

```python
try:
    head_seq: int | None = EventStore(_db).max_seq()
except Exception:
    head_seq = None   # A-9: trace_id will use payload-only fallback
trace_id = compute_trace_id(cmd, head_seq)
```

The fallback `trace_id` is less unique (two identical commands with different `head_seq`
get the same ID), but it is always computable and always non-None. All error paths retain
full observability even when the EventStore is completely inaccessible (I-TRACE-FALLBACK-1).

#### A-10: `context_hash` Sentinel Instead of None

Amendment A-6 (original) allowed `context_hash=None` at BUILD_CONTEXT stage. `None` is
an absent value, not a diagnostic value — it cannot be correlated, stored, or reasoned
about in a structured way.

**Sentinel collision problem**: a single fixed sentinel `"BUILD_CONTEXT_FAILED"` makes all
BUILD_CONTEXT failures indistinguishable in the EventLog. A DuckDB timeout and a corrupt
file produce identical `context_hash` values, making root-cause analysis harder.

Fix — use a **failure-type sentinel** `f"FAIL:{type(exc).__name__[:20]}"`:

```python
context_hash: str = f"FAIL:{type(exc).__name__[:20]}"  # e.g. "FAIL:duckdb.IOException"
```

- `ErrorEvent.context_hash: str` (type changed; no longer `str | None`)
- `_make_error_event` parameter: `context_hash: str` (always non-None)
- At BUILD_CONTEXT failure: `context_hash = f"FAIL:{type(exc).__name__[:20]}"`
- At step 0 init (before first try block): `context_hash: str = "FAIL:UNKNOWN"` (overwritten)
- All diagnostic tooling treats `context_hash` as always-present string; sentinels are
  recognizable by the `"FAIL:"` prefix

This also removes the `context_hash=None` assertion in `_make_error_event` — the sentinel
is always a valid string. The I-DIAG-1 exception for BUILD_CONTEXT is retired.

Sentinel format is frozen: `"FAIL:{ExcType[:20]}"` — max 25 chars. Diagnostic tooling
MUST NOT parse sentinel values; MUST treat any `context_hash` starting with `"FAIL:"` as
a BUILD_CONTEXT failure indicator (I-CONTEXT-HASH-SENTINEL-1).

#### A-11: Optimistic Locking Before Append

The guard pipeline (step 2) and handler (step 4) both consume `state` derived from
`head_seq` captured at step 0. If another command writes to EventLog between step 1
(BUILD_CONTEXT) and step 5 (append), the handler's events are based on stale state —
violating the "guard sees what handler sees" contract.

Fix — verify `EventLog head` has not advanced before the atomic append (step 5a):

```python
# Step 5a: optimistic lock — verify EventLog unchanged since BUILD_CONTEXT (A-11, I-OPTLOCK-1)
try:
    current_head = EventStore(_db).max_seq()
except Exception as exc:
    _write_error_to_audit_log(_make_error_event(
        stage="COMMIT", spec=spec, error_type="StaleStateError",
        reason="OPTLOCK_CHECK_FAILED", human_reason="Could not verify event log head before commit",
        violated_invariant="I-OPTLOCK-1",
        trace_id=trace_id, context_hash=context_hash, error_code=6,
    ))
    raise StaleStateError("EventLog head unreadable before commit") from exc

if current_head != head_seq:
    error_event = _make_error_event(
        stage="COMMIT", spec=spec, error_type="StaleStateError",
        reason=f"EVENTLOG_CHANGED.expected={head_seq},current={current_head}",
        human_reason="Event log was modified during execution — please retry the command",
        violated_invariant="I-OPTLOCK-1",
        trace_id=trace_id, context_hash=context_hash, error_code=6,
    )
    EventStore(_db).append([error_event], source="optimistic_lock")
    raise StaleStateError(f"EventLog head changed: {head_seq} → {current_head}")
```

`StaleStateError` is a new `SDDError` subclass (added to `core/errors.py`) with
`error_code=6`. The CLI produces exit 1 + JSON stderr per I-FAIL-1. The caller SHOULD
retry — `execute_command` is safe to retry thanks to A-7 idempotency.

**Scope note**: DuckDB in single-writer file mode has low concurrency risk, but sequential
retries (e.g., `project_all` crash and re-run) are a realistic scenario. The optimistic
lock costs one `MAX(seq)` query — negligible overhead.

**Livelock risk and retry ownership (I-RETRY-POLICY-1)**:

With two concurrent callers both reading `head_seq=N`, one will always get `StaleStateError`.
The kernel does NOT retry internally — it is a fail-fast boundary. Retry is the caller's
explicit responsibility:

| Caller | Retry strategy |
|--------|---------------|
| CLI (human-invoked) | User re-runs command; no auto-retry |
| LLM agent | Re-issue `sdd complete T-NNN`; idempotent via `command_id` (A-7) |
| External orchestrator | Backoff + retry; `command_id` prevents duplicate events |

The kernel MUST NOT retry `StaleStateError` internally — the retry loop would create hidden
control flow that violates the "pure function" model of `execute_command` (I-RETRY-POLICY-1).
`StaleStateError` is an informational signal to the caller, not a transient error to absorb.

#### A-12: `RebuildMode.EMERGENCY` Requires Env-Var

`I-REBUILD-EMERGENCY-1` prohibits calling `EMERGENCY` mode from automatic paths, but
relies on convention only. A developer can accidentally call
`rebuild_state(mode=RebuildMode.EMERGENCY)` in the wrong context.

Fix — hard runtime gate at the top of `rebuild_state`:

```python
def rebuild_state(
    db_path: str | None = None,
    state_path: str | None = None,
    mode: RebuildMode = RebuildMode.STRICT,
) -> None:
    if mode == RebuildMode.EMERGENCY:
        if os.environ.get("SDD_EMERGENCY") != "1":
            raise AssertionError(
                "I-REBUILD-EMERGENCY-2: RebuildMode.EMERGENCY requires "
                "SDD_EMERGENCY=1 environment variable — this is an operator-only break-glass mode"
            )
    state = EventReducer().reduce(_replay_all(db_path))
    ...
```

`SDD_EMERGENCY=1` must be set explicitly in the operator's shell before running the
break-glass command. `execute_and_project` → `project_all` → `rebuild_state(STRICT)` never
sets this variable — I-REBUILD-EMERGENCY-1 is now mechanically enforced (I-REBUILD-EMERGENCY-2).

### Dependencies

```text
registry.py           → infra/event_store.py, infra/projections.py
                        guards/pipeline.py (run_guard_pipeline — Amendment A-3)
                        commands/*, guards/context.py, domain/state/reducer.py
                        core/errors.py (error type hierarchy)
                        core/events.py (ErrorEvent, compute_trace_id, compute_context_hash)
guards/pipeline.py    → guards/context.py, guards/phase.py, guards/task.py
                        guards/dependency.py, guards/norm.py
commands/update_state.py → registry.py (routing)
commands/activate_phase.py → registry.py (routing), core/events.py (PhaseStartedEvent)
commands/record_decision.py → registry.py (routing)
commands/validate_config.py → [standalone function, no registry dependency]
core/events.py        → core/types.py
core/errors.py        → core/types.py (SDDError base)   ← new module
domain/state/reducer.py → core/events.py
infra/projections.py  → domain/state/reducer.py, infra/event_log.py
guards/context.py     → [extended: GuardResult.reason/human_reason/violated_invariant]
```

---

## 3. Domain Events

### New Events

| Event | Emitter | Level | Description |
|-------|---------|-------|-------------|
| `PhaseStartedEvent` | `ActivatePhaseHandler` | L1 | Canonical phase start: resets all phase state in reducer |
| `TaskSetDefinedEvent` | `ActivatePhaseHandler` | L1 | Declares `tasks_total` for the phase |
| `ErrorEvent` | `execute_command` (kernel) | L2 | Emitted at every kernel failure; reducer ignores; fields: `stage`, `error_type`, `reason`, `human_reason`, `violated_invariant`, `trace_id`, `context_hash`, `error_code` |

### Backward-Compat Events (preserved, reducer handlers updated)

| Event | Change |
|-------|--------|
| `PhaseInitialized` | Handler gains tasks-reset (same fields as PhaseStarted handler) |
| `PhaseActivated` | No change — handler unchanged |
| `PhaseCompleted` | Moved from `_KNOWN_NO_HANDLER` → `_EVENT_SCHEMA`; handler added |
| `StateSynced` | Not in `V1_L1_EVENT_TYPES`; silently ignored. Historical entries remain. No new `StateSynced` after Phase 15 |
| `DecisionRecordedEvent` | Added to `_KNOWN_NO_HANDLER` (audit-only, no reducer handler) |

### Event atomicity: PhaseStarted + TaskSetDefined

Both events are returned as a single list from `ActivatePhaseHandler.handle()` and
appended via one `EventStore.append([PhaseStartedEvent, TaskSetDefinedEvent])` call.
`sdd_append_batch` inserts via a single `INSERT INTO … VALUES (…), (…)` statement —
DuckDB commits it all-or-nothing. **Partial failure is impossible** (no "PhaseStarted written
but TaskSetDefined missing" intermediate state).

Re-run safety (A-14, I-HANDLER-BATCH-PURE-1): both events carry the same `command_id`. On
retry, DuckDB `ON CONFLICT DO NOTHING` skips both; `rows_inserted == 0` is logged at INFO
(I-IDEM-LOG-1). `ActivatePhaseHandler` has **no `_check_idempotent` method** — reading the
EventLog inside `handle()` would violate I-HANDLER-PURE-1; purity is unconditional.

---

## 4. Types & Interfaces

### `CommandSpec` (frozen — added to §0.15)

See §2. Fields `name`, `handler_class`, `actor`, `action`, `projection`,
`uses_task_id`, `event_schema`, `preconditions`, `postconditions`, `description`.
Optional-parameter-only extensions allowed per §0.15(a).

### `ProjectionType` (frozen)

```python
class ProjectionType(Enum):
    NONE = "none"
    STATE_ONLY = "state_only"
    FULL = "full"
```

### `RebuildMode` (new, in `infra/projections.py`)

```python
class RebuildMode(Enum):
    STRICT    = "strict"    # default; YAML not read
    EMERGENCY = "emergency" # operator-only break-glass; NEVER called automatically
```

### `NoOpHandler`

```python
class NoOpHandler(CommandHandlerBase):
    def handle(self, command: Any) -> list[DomainEvent]:
        return []
```

### `DomainEvent.phase_id` — backward-compatible extension (Amendment A-21)

`DomainEvent.phase_id` is declared as `int | None = None` (optional field with default).
This is a **§0.15(a) backward-compatible extension**: all existing event constructors that
pass an explicit `int` continue to work without modification. Only `ErrorEvent` uses `None`
(cross-cutting observability event not bound to any phase).

The mypy frozen-module tests (I-KERNEL-REG, I-KERNEL-SIG-1) MUST be updated to expect
`int | None` for this field. The change MUST NOT affect the `sdd_append` / `sdd_replay`
signatures (those accept `DomainEvent` generically — unaffected).

**I-ERROR-PHASE-NULL-1** (new): `ErrorEvent.phase_id` MUST always be `None`. Any
`ErrorEvent` instance with a non-None `phase_id` is a kernel bug.

### `validate_project_config` (Amendment A-2)

```python
def validate_project_config(phase_id: int, config_path: str) -> None:
    """Read-only config validation. Raises ConfigValidationError on failure.
    Not in REGISTRY: no events, no projections, no state mutations (I-READ-ONLY-EXCEPTION-1)."""
```

### Error Type Hierarchy (new `core/errors.py`)

```python
SDDError (base — existing; I-FAIL-1: all SDDError subclasses → CLI exit 1)
├── GuardViolationError      stage=GUARD,          error_code=1
├── InvariantViolationError  stage=EXECUTE|GUARD,  error_code=2
├── ExecutionError           stage=EXECUTE,         error_code=3
├── CommitError              stage=COMMIT,          error_code=4
├── ProjectionError          stage=PROJECT,         error_code=5
├── StaleStateError          stage=COMMIT,          error_code=6  # A-11: optimistic lock failure
└── KernelInvariantError     stage=GUARD,           error_code=7  # A-15: programming error in guard (DENY without reason)
```

`SDDError` base gains `error_code: int = 1` (backward-compatible; existing
`SDDError("message")` gets `error_code=1`). `error_code` is a semantic classification
field in JSON stderr — NOT an OS exit code. CLI exit code contract (I-FAIL-1: SDDError→1,
Exception→2) is unchanged (I-ERROR-CODE-1).

`StaleStateError` (error_code=6): raised when `EventStore.max_seq()` at step 5a
returns a value different from `head_seq` captured at step 0. The command SHOULD be
retried — `execute_command` is idempotent with respect to `command_id` (A-7, I-IDEM-1),
so retry is safe.

### Error Observability Helpers (in `registry.py`)

```python
def _make_error_event(
    stage: str, spec: CommandSpec, error_type: str,
    reason: str, human_reason: str, violated_invariant: str | None,
    trace_id: str, context_hash: str,   # A-10: always str; "FAIL:{ExcType}" sentinel at BUILD_CONTEXT
    error_code: int,
) -> ErrorEvent:
    assert len(human_reason) <= 140, "I-HUMAN-REASON-1 violated"
    return ErrorEvent(
        phase_id=None,  # ErrorEvents carry no phase_id — cross-cutting
        stage=stage, command=spec.name, error_type=error_type,
        reason=reason, human_reason=human_reason,
        violated_invariant=violated_invariant,
        trace_id=trace_id, context_hash=context_hash, error_code=error_code,
    )

def _write_error_to_audit_log(event: ErrorEvent) -> None:
    """COMMIT-stage + BUILD_CONTEXT fallback — I-ERROR-COMMIT-FALLBACK-1."""
    audit_path = audit_log_file()
    with open(audit_path, "a") as f:
        f.write(json.dumps({"event": "ErrorOccurred", **asdict(event)}) + "\n")
```

### `command_id`, `trace_id`, and `context_hash` computation

```python
def compute_command_id(cmd: Command) -> str:
    """Stable idempotency key — deterministic via dataclasses.asdict, 32 hex chars.
    Invariant under retry and EventLog state (A-7, A-13, A-22, I-IDEM-1).
    Uses dataclasses.asdict for recursive deterministic serialization (not str()) —
    immune to __repr__ variations, new fields, frozenset ordering.
    Task-scoped commands include phase_id in payload → naturally phase-scoped (I-CMD-PAYLOAD-PHASE-1)."""
    payload_dict = (
        dataclasses.asdict(cmd.payload)
        if dataclasses.is_dataclass(cmd.payload)
        else {"raw": repr(cmd.payload)}
    )
    serialized = json.dumps(
        {"cmd": cmd.command_type, "payload": payload_dict},
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]   # A-22: 32 hex = 128 bits

def compute_trace_id(cmd: Command, head_seq: int | None) -> str:
    """Deterministic correlation ID — 16 hex chars (diagnostic; collisions tolerable).
    head_seq = MAX(seq) before step 1; None when EventStore unavailable (A-9 fallback).
    Fallback hash is less unique but always computable and non-None (I-TRACE-FALLBACK-1)."""
    if head_seq is not None:
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload), "head": head_seq},
            sort_keys=True,
        )
    else:
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload)},
            sort_keys=True,
        )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]   # 16 hex = 64 bits; diagnostic only

def compute_context_hash(state: SDDState) -> str:
    """Reproducible state fingerprint — 32 hex chars (128 bits, A-22).
    sha256(json(asdict(state), sort_keys=True))[:32]."""
    return hashlib.sha256(
        json.dumps(asdict(state), sort_keys=True).encode()
    ).hexdigest()[:32]   # A-22: 32 hex = 128 bits for collision resistance
```

### `GuardResult` Extension

```python
@dataclass(frozen=True)
class GuardResult:
    outcome:            GuardOutcome
    message:            str
    reason:             str | None = None           # GUARD_DENY.<guard>.<rule_id>
    human_reason:       str | None = None           # ≤140 chars, no internal IDs
    violated_invariant: str | None = None           # I-* if applicable
```

`run_guard_pipeline` (in `guards/pipeline.py`) raises `AssertionError` if any DENY result
has `reason=None` (I-GUARD-REASON-1). This is a programming contract — guards returning
DENY MUST populate all three fields.

### CI Phase-16 Migration Whitelist (maximum 2 files)

```makefile
# Files excluded from CI purity rules — MUST be migrated in Phase 16 (I-PHASE16-MIGRATION-STRICT-1)
CI_PURITY_EXCEPTIONS := \
    src/sdd/commands/validate_invariants.py \
    src/sdd/commands/report_error.py
```

The whitelist contains at most 2 files. If Phase 16 adds any file to this list, it is a
spec violation. If Phase 16 does not fully migrate these 2 files, Phase 16 CANNOT be
marked COMPLETE (I-PHASE16-MIGRATION-STRICT-1).

---

## 5. Invariants

### New Invariants (Phase 15)

| ID | Statement | Phase |
|----|-----------|-------|
| I-1 | All SDD state = reduce(events); State_index.yaml is a readonly snapshot, never a truth source | 15 |
| I-2 | All write commands execute via REGISTRY[name] → execute_and_project(spec, ...) | 15 |
| I-3 | All side-effects (EventStore.append, projection rebuilds) occur in the Write Kernel only | 15 |
| I-SPEC-EXEC-1 | CLI contains only: REGISTRY lookup + execute_and_project call; no direct EventStore, rebuild_state, or handler calls outside registry.py | 15 |
| I-HANDLER-PURE-1 | `handle()` methods return events only — no EventStore, no rebuild_state, no sync_projections calls | 15 |
| I-KERNEL-WRITE-1 | `EventStore.append` called exclusively inside `execute_command` in `registry.py` | 15 |
| I-KERNEL-PROJECT-1 | `rebuild_state` called exclusively inside `project_all` in `registry.py` | 15 |
| I-READ-ONLY-EXCEPTION-1 | Read-only commands MAY bypass REGISTRY, but MUST NOT: call EventStore.append, call rebuild_state/sync_projections, call any handler.handle(), or mutate State_index.yaml; violation requires moving to REGISTRY | 15 |
| I-PHASE-STARTED-1 | `phase.current` is derivable from `PhaseStarted` or `PhaseInitialized` events in EventLog without reading YAML | 15 |
| I-PHASE-RESET-1 | Reducer MUST reset tasks state on `PhaseStarted` and `PhaseInitialized` events | 15 |
| I-PHASE-COMPLETE-1 | `PhaseCompletedEvent` MUST transition `phase_status = COMPLETE` and `plan_status = COMPLETE` in reducer | 15 |
| I-PHASE-SEQ-1 | Replay of PhaseCompleted(N) followed by PhaseStarted(N+1) MUST yield phase_current=N+1, phase_status=ACTIVE | 15 |
| I-ES-REPLAY-1 | `rebuild_taskset` MUST succeed (no-op with warning) when taskset file does not exist | 15 |
| I-REBUILD-STRICT-1 | Default `RebuildMode` is `STRICT`; YAML is not read during rebuild in normal operation | 15 |
| I-REBUILD-EMERGENCY-1 | `execute_and_project` and `project_all` MUST call `rebuild_state` with `RebuildMode.STRICT` only; EMERGENCY mode is exclusively for direct operator invocation and MUST NOT be entered from any automatic code path | 15 |
| I-ATOMICITY-1 | `execute_command` MUST use `sdd_append_batch` (single INSERT) when handler returns multiple events | 15 |
| I-CI-PURITY-1 | CI Makefile `check-handler-purity` fails on `EventStore(` outside `registry.py`/`event_store.py` (with max 2 whitelisted exceptions) | 15 |
| I-CI-PURITY-2 | CI Makefile fails on `rebuild_state\|sync_projections` outside `registry.py`/`projections.py` | 15 |
| I-CI-PURITY-3 | CI Makefile fails on `.handle(` outside `registry.py`/`_base.py` (with max 2 whitelisted exceptions) | 15 |
| I-PHASE16-MIGRATION-STRICT-1 | Files whitelisted from CI purity rules MUST be migrated in Phase 16; the whitelist MUST contain at most 2 files; Phase 16 CANNOT complete if either file remains unmigrated | 15 |
| I-REGISTRY-COMPLETE-1 | Every SDD write command (complete, validate, check-dod, activate-phase, sync-state, record-decision) has a corresponding entry in `REGISTRY`; read-only commands are explicitly excluded | 15 |
| I-C1-ATOMIC-1 | T-1501 (events.py + reducer.py) MUST be a single atomic commit; partial state where PhaseStarted/TaskSetDefined are in V1_L1_EVENT_TYPES but not in _EVENT_SCHEMA is forbidden | 15 |
| I-ERROR-1 | The Write Kernel MUST emit `ErrorEvent` before raising at every failure stage: (a) GUARD/EXECUTE/COMMIT errors in `execute_command` → append to EventLog (fallback: audit_log.jsonl); (b) BUILD_CONTEXT error in `execute_command` → write to audit_log.jsonl; (c) PROJECT error in `execute_and_project` → write to audit_log.jsonl (A-16). Raising SDDError without a corresponding ErrorEvent is a kernel bug. | 15 |
| I-ERROR-TRACE-1 | Every `ErrorEvent` MUST carry `trace_id = sha256(command_type + str(head_seq))[:16]`; computed at step 0 before any state mutation | 15 |
| I-DIAG-1 | Every kernel failure MUST answer: (1) where — `stage`; (2) why — `reason` + `violated_invariant`; (3) what state — `context_hash` + `trace_id`. `context_hash` is always a non-None `str`: at BUILD_CONTEXT failure it is `f"FAIL:{type(exc).__name__[:20]}"` (recognizable by `"FAIL:"` prefix); in all later stages it is a real sha256 hash. `trace_id` is always a 16-hex string (A-9 fallback). (A-10 supersedes A-6) | 15 |
| I-ERROR-COMMIT-FALLBACK-1 | COMMIT-stage and BUILD_CONTEXT-stage `ErrorEvent` MUST be written to `audit_log.jsonl`; this is the only permitted direct write to `audit_log.jsonl` from `execute_command` | 15 |
| I-HUMAN-REASON-1 | `ErrorEvent.human_reason` MUST be ≤140 chars, contain no internal IDs (I-*, PG-*, module/class names), and explain in plain language why the command was rejected or failed | 15 |
| I-GUARD-REASON-1 | Any `GuardResult` with `outcome=DENY` MUST populate `reason`, `human_reason`, `violated_invariant`; `execute_command` MUST check this after step 2 and raise `KernelInvariantError` (error_code=7) with an ErrorEvent emitted before raising — MUST NOT use `assert` (disabled by `-O`); `run_guard_pipeline` validates internally and raises before returning if a DENY lacks required fields (A-15) | 15 |
| I-GUARD-CLI-1 | Guard CLI adapters (phase_guard, task_guard) MUST NOT read YAML; missing required args → exit 1 with JSON error (CLI-layer error, not kernel error — no ErrorEvent emitted); guard pipeline itself MUST NOT call sys.exit | 15 |
| I-ERROR-L2-1 | `ErrorEvent` is L2 (observability); MUST be in `_KNOWN_NO_HANDLER`; MUST NOT appear in `V1_L1_EVENT_TYPES`; replay with or without ErrorEvent entries produces identical state | 15 |
| I-ERROR-CODE-1 | `error_code` (1–7) is included in JSON stderr as an additive field; CLI exit code (I-FAIL-1: SDDError→1, Exception→2) is NOT changed; error_code=7 = `KernelInvariantError` (A-15) | 15 |
| I-ERROR-SINGLE-TYPE-1 | There is exactly one ErrorEvent dataclass in the system; no KernelErrorEvent, no sub-types; `stage` field differentiates kernel phases; the `_sdd_error_events` handler pattern in `_base.py` is deprecated in Phase 15 and removed in Phase 16 | 15 |
| I-DECISION-AUDIT-1 | `DecisionRecordedEvent` MUST be in `_KNOWN_NO_HANDLER`; `projection=NONE` for record-decision is correct because decisions have no state-reconstruction semantics; any future decision type requiring state mutation MUST use a separate event type with a reducer handler | 15 |
| I-IMPL-ORDER-1 | Step 1 tasks (add) must be DONE before any Step 2 task (switch) begins; Step 2 must be complete before Step 3 (enforce); Step 3 before Step 4 (delete); `pytest tests/ -q` green is the gate at each boundary | 15 |
| I-TASK-SCOPE-1 | No task adds `registry.py` AND wires a `main()` call in the same task; structure and routing changes are always separate tasks (§K.13 TG-1) | 15 |
| I-SDDRUN-DEAD-1 | `CommandRunner` class MUST NOT exist in `src/sdd/` after Step 4; `guards/pipeline.py` is the permanent home for `run_guard_pipeline`; `test_sdd_run.py` MUST be deleted | 15 |
| I-PIPELINE-HOME-1 | `run_guard_pipeline` resides in `guards/pipeline.py` (not in any adapter module); `registry.py` imports directly from `guards.pipeline`; no intermediate adapter module exists | 15 |
| I-IDEM-1 | `execute_command` MUST be idempotent with respect to `command_id = compute_command_id(cmd)` (payload-only via `dataclasses.asdict`, 32 hex chars, stable across retries — A-7, A-13, A-22); `command_id` MUST NOT be `trace_id`; task-scoped payloads include `phase_id` making the key naturally phase-scoped; a retry with the same payload MUST NOT produce duplicate events | 15 |
| I-IDEM-SCHEMA-1 | DuckDB `events` table MUST have column `command_id TEXT` and `UNIQUE(command_id, event_index)` index; `command_id` is NULL for legacy (pre-Phase-15) events and NOT NULL for all Phase 15+ handler events; `ErrorEvent` rows are excluded from `command_id` tagging | 15 |
| I-IDEM-LOG-1 | `EventStore.append` MUST emit `logging.info("duplicate command detected", command_id=…)` when `rows_inserted == 0`; silent drops are NOT permitted — the duplicate MUST be distinguishable from logic errors in debug output | 15 |
| I-RETRY-POLICY-1 | `execute_command` MUST NOT retry `StaleStateError` internally; retry is the caller's explicit responsibility (CLI: user re-runs; LLM: re-issues command; orchestrator: backoff+retry); the kernel is a fail-fast boundary — internal retry loops would create hidden control flow violating the pure-function model | 15 |
| I-PHASE-ORDER-1 | Reducer `PhaseStarted` handler MUST ignore (log warning, return unchanged state) any event where `event.phase_id ≠ state.phase_current + 1`; replay with reordered or injected PhaseStarted events MUST produce a deterministic, reproducible result (A-8) | 15 |
| I-TRACE-FALLBACK-1 | `compute_trace_id(cmd, head_seq: int \| None)` MUST succeed even when `head_seq` is unavailable (EventStore down); fallback = `sha256(command_type + str(payload))[:16]`; `trace_id` MUST always be a non-None 16-hex string (A-9) | 15 |
| I-CONTEXT-HASH-SENTINEL-1 | `context_hash` in `ErrorEvent` and `_make_error_event` MUST be `str` (not `str \| None`); at BUILD_CONTEXT failure, value is `f"FAIL:{type(exc).__name__[:20]}"` (e.g. `"FAIL:duckdb.IOException"`); at PROJECT failure in `execute_and_project`, value is `"FAIL:PROJECTION"`; different failure types MUST produce different sentinels; non-sentinel `context_hash` is 32 hex chars (A-22); diagnostic tooling MUST recognize any `context_hash` starting with `"FAIL:"` as a failure sentinel (A-10) | 15 |
| I-OPTLOCK-1 | `execute_command` MUST verify `EventStore.max_seq() == head_seq` before the append; if head has advanced, raise `StaleStateError` (error_code=6) and append an `ErrorEvent`; the command is safe to retry due to I-IDEM-1; the check+write MUST be atomic — see I-OPTLOCK-ATOMIC-1 (A-11, A-17) | 15 |
| I-REBUILD-EMERGENCY-2 | `rebuild_state(mode=RebuildMode.EMERGENCY)` MUST assert `os.environ.get("SDD_EMERGENCY") == "1"` and raise `AssertionError` if the var is absent or wrong; this runtime gate mechanically enforces I-REBUILD-EMERGENCY-1 (A-12) | 15 |
| I-CMD-PAYLOAD-PHASE-1 | Every task-scoped Command payload (`spec.uses_task_id=True`) MUST include a `phase_id: int` field; `execute_command` validates `cmd.payload.phase_id == state.phase_current` after step 1 and raises `InvariantViolationError` on mismatch — makes `command_id` naturally phase-scoped (A-13) | 15 |
| I-HANDLER-BATCH-PURE-1 | Handlers returning multiple events MUST NOT read EventLog inside `handle()` to determine which events to emit; recovery from partial batch failure is the kernel's responsibility via `command_id` UNIQUE constraint + `sdd_append_batch` atomicity (A-14) | 15 |
| I-OPTLOCK-ATOMIC-1 | `EventStore.append` MUST perform the `max_seq` check AND the INSERT inside a single DuckDB transaction when `expected_head` is supplied; no TOCTOU gap between check and write (A-17) | 15 |
| I-CMD-PHASE-RESOLVE-1 | The taskset file path MUST be resolved from `state.phase_current` (step 1 replay output), never from a pre-step-1 `_current_phase()` call; ensures taskset path and replayed state are always consistent (A-18) | 15 |
| I-TASKSET-ORDER-1 | Reducer `TaskSetDefined` handler MUST ignore (log warning, return unchanged state) any event where `event.phase_id ≠ state.phase_current`; replay with mismatched events MUST produce deterministic state (A-19) | 15 |
| I-SYNC-NO-PHASE-GUARD-1 | `sync-state` command MUST set `requires_active_phase=False`; PhaseGuard MUST be skipped for it; `sync-state` MUST be available in any phase status (PLANNED, ACTIVE, COMPLETE) as a recovery utility (A-20) | 15 |
| I-ERROR-PHASE-NULL-1 | `ErrorEvent.phase_id` MUST always be `None`; ErrorEvent is a cross-cutting observability event not bound to any specific phase; a non-None `phase_id` on any ErrorEvent is a kernel bug (A-21) | 15 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-SDD-9 | `.sdd/specs/` is immutable |
| I-KERNEL-EXT-1 | Frozen interfaces extended only via backward-compatible additions |
| I-FAIL-1 | SDDError → exit 1 + JSON stderr; Exception → exit 2 + JSON stderr |
| I-CLI-API-1 | JSON error fields `error_type`, `message`, `exit_code` are frozen |
| I-EXEC-ISOL-1 | Tests use `tmp_path`-isolated DuckDB; project `sdd_events.duckdb` never touched by tests |
| I-PATH-1 | No literal `.sdd/` strings in `src/sdd/**/*.py` except `infra/paths.py` |
| I-ES-1 | EventLog is the source of truth; `_sdd_error_events` appended before re-raise |
| I-ES-6 | EventStore.append is the sole success write path |
| I-CMD-11 | GuardContext.state is always from EventLog replay, never from YAML |

---

## 6. Pre/Post Conditions

### `execute_command(spec, cmd, ...)`

**Pre:**
- `spec` is a `CommandSpec` from `REGISTRY`
- `cmd` is a valid `Command` envelope for `spec.handler_class`
- EventLog (DuckDB) is accessible at resolved `db_path`

**Post:**
- If EventLog replay fails (BUILD_CONTEXT): ErrorEvent written to audit_log.jsonl; exception re-raised; EventLog unchanged
- GuardContext built from EventLog replay (I-CMD-11 preserved)
- Guard DENY: audit_events + ErrorEvent appended to DuckDB; `GuardViolationError` raised; handler NOT called
- Guard ALLOW: `spec.handler_class().handle(cmd)` invoked exactly once (pure)
- Handler exception: error_events + ErrorEvent appended to DuckDB (fallback: audit_log); original exception re-raised
- Optimistic lock (step 5a): if EventLog head advanced since step 0, `StaleStateError` raised with `ErrorEvent` (error_code=6); handler output discarded; command is safe to retry (I-OPTLOCK-1, I-IDEM-1)
- Handler success: events appended via `sdd_append_batch` with `command_id=compute_command_id(cmd)` (payload-stable; `trace_id` is diagnostic-only and NOT used as deduplication key — A-7, I-ATOMICITY-1, I-IDEM-1); duplicate INSERT silently skipped by DuckDB UNIQUE constraint and logged at INFO level (I-IDEM-LOG-1)
- `context_hash` in all ErrorEvents is always a non-None string (I-CONTEXT-HASH-SENTINEL-1)
- Returns the appended `list[DomainEvent]`

### `project_all(projection, ...)`

**Pre:** EventLog readable; `state_path` writable (for STATE_ONLY or FULL)

**Post:**
- `NONE`: no file writes
- `STATE_ONLY`: `State_index.yaml = reduce(replay(db_path))`; mode = STRICT always
- `FULL`: same + `TaskSet_vN.md` rebuilt; mode = STRICT always
- YAML never read in STRICT mode (I-REBUILD-STRICT-1)

### `validate_project_config(phase_id, config_path)`

**Pre:** `config_path` is a readable file path

**Post:** Returns `None` on success. Raises `ConfigValidationError` on invalid config.
Zero EventStore accesses. Zero YAML state mutations. Zero handler invocations. (I-READ-ONLY-EXCEPTION-1)

### `PhaseCompleted(N) → PhaseStarted(N+1)` replay

**Pre:** EventLog contains `PhaseCompleted(phase_id=N)` followed by `PhaseStarted(phase_id=N+1)`

**Post:** `phase_current=N+1`, `phase_status=ACTIVE`, `tasks_total=0`; no Phase N state leaks (I-PHASE-SEQ-1)

### `sdd activate-phase N [--tasks T]`

**Pre:** Actor = human (NormGuard MUST allow)

**Post:**
- `PhaseStartedEvent(N, "human")` + (if `--tasks T`) `TaskSetDefinedEvent(N, T)` in EventLog
- `State_index.yaml`: `phase.current=N, phase.status=ACTIVE, tasks.total=T`
- No YAML hand-edit required

---

## 7. Use Cases

### UC-15-1: LLM completes a task via pure kernel path

**Actor:** LLM
**Trigger:** `sdd complete T-1501`
**Pre:** Phase 15 ACTIVE; T-1501 status TODO
**Steps:**
1. `update_state.main()` calls `execute_and_project(REGISTRY["complete"], CompleteTaskCommand(...))`
2. `execute_command`: step 0 captures `head_seq` and `trace_id`
3. Step 1: EventLog replay → `state`; `context_hash` computed
4. Steps 2–3: guard pipeline → PhaseGuard ALLOW → TaskGuard ALLOW → NormGuard ALLOW
5. Step 4: `CompleteTaskHandler.handle(cmd)` returns `[TaskImplementedEvent, MetricRecordedEvent]` — pure
6. Step 5: `sdd_append_batch` appends both events atomically
7. `project_all(FULL)`: `rebuild_state(STRICT)` + `rebuild_taskset()`
8. `State_index.yaml` updated; `tasks.completed` incremented
**Post:** Handler had zero I/O; YAML is consistent snapshot of EventLog state

### UC-15-2: Human activates Phase 16 without touching YAML

**Actor:** Human
**Trigger:** `sdd activate-phase 16 --tasks 20`
**Pre:** Phase 15 status COMPLETE in EventLog
**Steps:**
1. `activate_phase.main()` calls `execute_and_project(REGISTRY["activate-phase"], ...)`
2. NormGuard(actor=human → ALLOW)
3. `ActivatePhaseHandler.handle()` returns `[PhaseStartedEvent(16, "human"), TaskSetDefinedEvent(16, 20)]`
4. Single `sdd_append_batch` call appends both events atomically
5. `project_all(STATE_ONLY)` → YAML: `phase.current=16, ACTIVE, tasks.total=20`
**Post:** No YAML hand-edit; phase transition fully event-sourced

### UC-15-3: Guard DENY with full diagnostic

**Actor:** LLM (wrong phase)
**Trigger:** `sdd complete T-1501` when `phase.current ≠ 15`
**Pre:** Phase 13 ACTIVE
**Steps:**
1. `execute_command` step 0: `trace_id` captured; step 1: `context_hash` computed
2. PhaseGuard DENY: PG-1 fails; result has `reason="GUARD_DENY.PhaseGuard.PG-1"`, `human_reason="Phase not active — task implementation requires an active phase"`, `violated_invariant="I-PHASE-RESET-1"`
3. `run_guard_pipeline` assertion: reason is non-None ✓
4. `execute_command` emits `ErrorEvent(stage="GUARD", trace_id=..., context_hash=...)` to DuckDB
5. `GuardViolationError` raised → CLI: exit 1, JSON stderr with `error_code=1`
**Post:** No handler called; full diagnostic in DuckDB; trace_id correlates CLI output to event

### UC-15-4E: EventStore fails at BUILD_CONTEXT

**Actor:** LLM
**Trigger:** `sdd complete T-1502` when DuckDB inaccessible
**Pre:** DuckDB file locked or deleted
**Steps:**
1. `execute_command` step 0: `EventStore.max_seq()` fails; OR step 1: `_fetch_events_for_reduce` fails
2. `context_hash` remains `None` (state never built — A-6)
3. `ErrorEvent(stage="BUILD_CONTEXT", context_hash=f"FAIL:{exc_type}", trace_id=...)` written to `audit_log.jsonl` (A-10: type-specific sentinel, always non-None str)
4. Exception re-raised → CLI: exit 2 (non-SDDError) or exit 1 (if SDDError subclass)
**Post:** audit_log.jsonl has full diagnostic; EventLog unchanged; idempotent retry safe

### UC-15-5: validate-config as plain function (Amendment A-2)

**Actor:** LLM
**Trigger:** `sdd validate-config --phase 15`
**Pre:** `project_profile.yaml` exists
**Steps:**
1. `cli.py validate-config` calls `validate_project_config(15, config_path)` directly
2. Function reads YAML file; validates schema; raises `ConfigValidationError` on failure
3. No `handler.handle()` call — CI grep rule not violated
4. No EventStore access — I-READ-ONLY-EXCEPTION-1 satisfied
**Post:** Config validated; no state mutations; zero kernel involvement

### UC-15-6: CI enforces handler purity

**Actor:** CI system
**Trigger:** PR touches `src/sdd/commands/update_state.py`
**Steps:**
1. `make check-handler-purity`
2. grep rule 1: no `EventStore(` outside kernel + 2 whitelisted exceptions → PASS
3. grep rule 2: no `rebuild_state` outside projections → PASS
4. grep rule 3: no `.handle(` outside kernel + 2 whitelisted exceptions → PASS
**Post:** Kernel boundary enforced without manual review; whitelist count verified ≤ 2

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-15-REGISTRY | → BC-1 infra/event_store.py | EventStore.append (in execute_command only) |
| BC-15-REGISTRY | → BC-2 infra/projections.py | project_all calls rebuild_state, rebuild_taskset |
| BC-15-REGISTRY | → guards/pipeline.py | run_guard_pipeline (Amendment A-3) |
| BC-15-REGISTRY | → BC-3 guards/context.py | GuardContext construction |
| BC-4 commands/update_state.py | → BC-15-REGISTRY | main() uses execute_and_project |
| BC-4 commands/activate_phase.py | → BC-15-REGISTRY | main() uses execute_and_project |
| BC-4 commands/record_decision.py | → BC-15-REGISTRY | main() uses execute_and_project |
| BC-1 core/events.py | adds PhaseStartedEvent, TaskSetDefinedEvent, ErrorEvent | |
| BC-2 domain/state/reducer.py | extends _EVENT_SCHEMA for new + fixed events | |
| BC-2 infra/projections.py | adds RebuildMode; simplifies rebuild_state | |

### `CommandRunner` disposition

`CommandRunner` is **superseded by `execute_command`** as the unified Write Kernel.
`sdd_run.py` is deleted entirely in Step 4. `run_guard_pipeline` moves to
`guards/pipeline.py` in Step 1 (copied, not moved yet; `sdd_run.py` not touched in Step 1).

### Frozen Interface Extensions (§0.15)

| Module | Change | Compatibility |
|--------|--------|---------------|
| `commands/registry.py` | new frozen module | N/A (new) |
| `guards/pipeline.py` | new module (moved from sdd_run.py) | N/A (new) |
| `infra/projections.py` | `rebuild_state` gains `mode: RebuildMode = RebuildMode.STRICT` | optional param |
| `core/events.py` | PhaseStartedEvent, TaskSetDefinedEvent, ErrorEvent added | additive |
| `core/errors.py` | new module: SDDError subclass hierarchy | N/A (new) |
| `domain/state/reducer.py` | new handlers added to `_EVENT_SCHEMA` | additive |
| `guards/context.py` | `GuardResult` gains `reason`, `human_reason`, `violated_invariant` with defaults `None` | optional params (§0.15(a)) |

### CLAUDE.md changes (atomic with code — §K.9 CEP-1)

- **§0** (new §0.A): Four foundational invariants I-1, I-2, I-3, I-SPEC-EXEC-1 above §0.1
- **§0.5 Status Transition Table**: Remove "Direct YAML edit" entries; replace with
  `sdd activate-phase N` CLI command
- **§0.8 Operational Rules**: Add `SEM-10` (LLM MUST use `reason` + `violated_invariant`
  from JSON stderr; MUST NOT infer cause intuitively); Add `SEM-11` (read-only CLI bypass
  of REGISTRY MUST satisfy I-READ-ONLY-EXCEPTION-1 — any violation requires moving command to REGISTRY)
- **§0.10 Tool Reference**: Add `activate-phase --tasks N`; note "all write commands: REGISTRY in registry.py"
- **§0.15**: Add `commands/registry.py`, `guards/pipeline.py`, `core/errors.py` rows
- **§0.16**: Add all new invariants from §5
- **§R.6 Implement Protocol**: Simplify — guards invoked automatically by execute_command
- **§0.17** (new): Phase FSM + Phase N→N+1 transition table (YAML-free)
- **§0.18** (new): Responsibility Matrix derived from REGISTRY.actor field
- **§0.19** (new): Error Semantics quick-reference — error_code table, stage taxonomy,
  trace_id/context_hash definitions, COMMIT+BUILD_CONTEXT fallback path

---

## 9. Verification

| # | Test / Check | Invariant(s) | Command |
|---|-------------|--------------|---------|
| 1 | `test_phase_started_resets_tasks` | I-PHASE-RESET-1 | `pytest tests/unit/domain/test_reducer.py::test_phase_started_resets_tasks -v` |
| 2 | `test_phase_started_sets_active` | I-PHASE-STARTED-1 | `pytest tests/unit/domain/test_reducer.py::test_phase_started_sets_active -v` |
| 3 | `test_phase_completed_sets_complete` | I-PHASE-COMPLETE-1 | `pytest tests/unit/domain/test_reducer.py::test_phase_completed_sets_complete -v` |
| 4 | `test_taskset_defined_sets_total` | I-2 | `pytest tests/unit/domain/test_reducer.py::test_taskset_defined_sets_total -v` |
| 5 | `test_phase_initialized_backward_compat_resets` | I-PHASE-RESET-1 | `pytest tests/unit/domain/test_reducer.py::test_phase_initialized_backward_compat_resets -v` |
| 6 | `test_c1_assertion_holds_after_registration` | I-C1-ATOMIC-1 | `pytest tests/unit/core/test_events.py::test_c1_assertion_holds_after_registration -v` |
| 7 | `test_phase_completed_then_started_replay` | I-PHASE-SEQ-1 | `pytest tests/unit/domain/test_reducer.py::test_phase_completed_then_started_replay -v` |
| 8 | `test_strict_mode_ignores_yaml` | I-REBUILD-STRICT-1, I-1 | `pytest tests/unit/infra/test_projections.py::test_strict_mode_ignores_yaml -v` |
| 9 | `test_emergency_mode_fallback_empty_eventlog` | I-REBUILD-STRICT-1 | `pytest tests/unit/infra/test_projections.py::test_emergency_mode_fallback_empty_eventlog -v` |
| 10 | `test_strict_mode_correct_for_phases_1_14` | I-PHASE-STARTED-1 | `pytest tests/unit/infra/test_projections.py::test_strict_mode_correct_for_phases_1_14 -v` |
| 11 | `test_rebuild_taskset_graceful_missing` | I-ES-REPLAY-1 | `pytest tests/unit/infra/test_projections.py::test_rebuild_taskset_graceful_missing -v` |
| 12 | `test_execute_command_guard_deny_appends_audit_events` | I-KERNEL-WRITE-1, I-ES-1 | `pytest tests/unit/commands/test_registry.py::test_execute_command_guard_deny_appends_audit_events -v` |
| 13 | `test_execute_command_handler_exception_appends_error_events` | I-ES-1 | `pytest tests/unit/commands/test_registry.py::test_execute_command_handler_exception_appends_error_events -v` |
| 14 | `test_execute_command_uses_batch_append` | I-ATOMICITY-1 | `pytest tests/unit/commands/test_registry.py::test_execute_command_uses_batch_append -v` |
| 15 | `test_noop_handler_triggers_full_rebuild` | I-3 | `pytest tests/unit/commands/test_registry.py::test_noop_handler_triggers_full_rebuild -v` |
| 16 | `test_guard_context_built_from_eventlog_not_yaml` | I-CMD-11 | `pytest tests/unit/commands/test_registry.py::test_guard_context_built_from_eventlog_not_yaml -v` |
| 17 | `test_handlers_have_no_forbidden_imports` | I-HANDLER-PURE-1 | `pytest tests/unit/test_handler_purity.py -v` |
| 18 | `test_registry_write_commands_complete` | I-REGISTRY-COMPLETE-1 | `pytest tests/unit/test_registry_contract.py::test_registry_write_commands_complete -v` |
| 19 | `test_spec_event_schema_matches_handler_types` | I-2 | `pytest tests/unit/test_registry_contract.py::test_spec_event_schema_matches_handler_types -v` |
| 20 | Integration: Phase N→N+1 without YAML edit | I-1, I-2, I-3 | `pytest tests/integration/test_phase_transition_no_yaml.py -v` |
| 21 | CI grep-rule: EventStore outside kernel | I-KERNEL-WRITE-1, I-CI-PURITY-1 | `make check-handler-purity` |
| 22 | CI grep-rule: rebuild_state outside projections | I-KERNEL-PROJECT-1, I-CI-PURITY-2 | `make check-handler-purity` |
| 23 | CI grep-rule: `.handle(` outside kernel | I-HANDLER-PURE-1, I-CI-PURITY-3 | `make check-handler-purity` |
| 24 | Full test suite regression | all preserved | `pytest tests/ -q` |
| 25 | `test_error_event_emitted_on_guard_deny` | I-ERROR-1, I-DIAG-1 | `pytest tests/unit/commands/test_registry.py::test_error_event_emitted_on_guard_deny -v` |
| 26 | `test_error_event_emitted_on_handler_exception` | I-ERROR-1, I-ERROR-TRACE-1 | `pytest tests/unit/commands/test_registry.py::test_error_event_emitted_on_handler_exception -v` |
| 27 | `test_commit_failure_writes_to_audit_log` | I-ERROR-COMMIT-FALLBACK-1 | `pytest tests/unit/commands/test_registry.py::test_commit_failure_writes_to_audit_log -v` |
| 28 | `test_trace_id_determinism` | I-ERROR-TRACE-1 | `pytest tests/unit/commands/test_registry.py::test_trace_id_determinism -v` |
| 29 | `test_error_event_not_in_l1_types` | I-ERROR-L2-1 | `pytest tests/unit/core/test_events.py::test_error_event_not_in_l1_types -v` |
| 30 | `test_human_reason_constraint` | I-HUMAN-REASON-1 | `pytest tests/unit/commands/test_registry.py::test_human_reason_constraint -v` |
| 31 | `test_guard_deny_without_reason_raises_assertion` | I-GUARD-REASON-1 | `pytest tests/unit/commands/test_registry.py::test_guard_deny_without_reason_raises_assertion -v` |
| 32 | `test_error_code_in_json_stderr` | I-ERROR-CODE-1, I-CLI-API-1 | `pytest tests/integration/test_cli_error_semantics.py -v` |
| 33 | `test_build_context_error_writes_to_audit_log` | I-ERROR-1, I-DIAG-1, I-ERROR-COMMIT-FALLBACK-1 | `pytest tests/unit/commands/test_registry.py::test_build_context_error_writes_to_audit_log -v` |
| 34 | `test_build_context_error_context_hash_is_type_sentinel` — BUILD_CONTEXT ErrorEvent carries `f"FAIL:{exc_type}"` sentinel (not None, not fixed string); starts with `"FAIL:"` prefix | I-DIAG-1, I-CONTEXT-HASH-SENTINEL-1 (A-10) | `pytest tests/unit/commands/test_registry.py::test_build_context_error_context_hash_is_type_sentinel -v` |
| 35 | `test_project_all_always_uses_strict` | I-REBUILD-EMERGENCY-1 | `pytest tests/unit/commands/test_registry.py::test_project_all_always_uses_strict -v` |
| 36 | `test_validate_config_is_not_in_registry` | I-READ-ONLY-EXCEPTION-1 | `pytest tests/unit/test_registry_contract.py::test_validate_config_is_not_in_registry -v` |
| 37 | `test_validate_config_no_eventstore_access` | I-READ-ONLY-EXCEPTION-1 | `pytest tests/unit/commands/test_validate_config.py::test_validate_config_no_eventstore_access -v` |
| 38 | `test_decision_event_not_in_reducer` | I-DECISION-AUDIT-1 | `pytest tests/unit/domain/test_reducer.py::test_decision_event_not_in_reducer -v` |
| 39 | `test_run_guard_pipeline_importable_from_pipeline_module` | I-PIPELINE-HOME-1 | `pytest tests/unit/guards/test_pipeline.py::test_run_guard_pipeline_importable_from_pipeline_module -v` |
| 40 | `test_guard_cli_missing_arg_exits_without_error_event` | I-GUARD-CLI-1 | `pytest tests/unit/guards/test_pipeline.py::test_guard_cli_missing_arg_exits_without_error_event -v` |
| 41 | `test_ci_purity_whitelist_count_at_most_two` | I-PHASE16-MIGRATION-STRICT-1 | `pytest tests/unit/test_registry_contract.py::test_ci_purity_whitelist_count_at_most_two -v` |
| 42 | `test_single_error_event_type_exists` | I-ERROR-SINGLE-TYPE-1 | `pytest tests/unit/core/test_events.py::test_single_error_event_type_exists -v` |
| 43 | Integration: CommandRunner fully absent | I-SDDRUN-DEAD-1 | `grep -rn "CommandRunner" src/sdd/ \| wc -l == 0` |
| 44 | Integration: all write commands route through execute_and_project | I-IMPL-ORDER-1 | `make check-handler-purity && pytest tests/ -q` |
| 45 | `test_execute_command_idempotent_on_retry` — second call with same payload (→ same command_id) produces no new events, even if head_seq differs (trace_id changes); EventStore INSERT returns rows_inserted=0 and logs INFO | I-IDEM-1, I-IDEM-LOG-1 | `pytest tests/unit/commands/test_registry.py::test_execute_command_idempotent_on_retry -v` |
| 46 | `test_event_store_command_id_unique_constraint` — duplicate (command_id, event_index) is silently ignored | I-IDEM-SCHEMA-1 | `pytest tests/unit/infra/test_event_store.py::test_event_store_command_id_unique_constraint -v` |
| 47 | `test_reducer_ignores_out_of_order_phase_started` — PhaseStarted(N+2) when current=N returns unchanged state | I-PHASE-ORDER-1 | `pytest tests/unit/domain/test_reducer.py::test_reducer_ignores_out_of_order_phase_started -v` |
| 48 | `test_trace_id_fallback_when_head_seq_is_none` — compute_trace_id(cmd, None) returns 16-hex string | I-TRACE-FALLBACK-1 | `pytest tests/unit/commands/test_registry.py::test_trace_id_fallback_when_head_seq_is_none -v` |
| 49 | `test_context_hash_sentinel_format_at_build_context_failure` — BUILD_CONTEXT ErrorEvent carries `f"FAIL:{exc_type}"` (not None, not fixed string); starts with `"FAIL:"`; different exc types → different context_hash | I-CONTEXT-HASH-SENTINEL-1 | `pytest tests/unit/commands/test_registry.py::test_context_hash_sentinel_format_at_build_context_failure -v` |
| 50 | `test_execute_command_raises_stale_state_on_concurrent_write` — head advances between BUILD_CONTEXT and append; StaleStateError raised | I-OPTLOCK-1 | `pytest tests/unit/commands/test_registry.py::test_execute_command_raises_stale_state_on_concurrent_write -v` |
| 51 | `test_emergency_mode_requires_env_var` — rebuild_state(EMERGENCY) without SDD_EMERGENCY=1 raises AssertionError | I-REBUILD-EMERGENCY-2 | `pytest tests/unit/infra/test_projections.py::test_emergency_mode_requires_env_var -v` |
| 52 | `test_emergency_mode_allowed_with_env_var` — rebuild_state(EMERGENCY) with SDD_EMERGENCY=1 completes normally | I-REBUILD-EMERGENCY-2 | `pytest tests/unit/infra/test_projections.py::test_emergency_mode_allowed_with_env_var -v` |
| 53 | `test_command_id_stable_across_different_head_seq` — compute_command_id(cmd) returns same value regardless of EventLog state; ≠ compute_trace_id(cmd, head_seq) | I-IDEM-1 | `pytest tests/unit/commands/test_registry.py::test_command_id_stable_across_different_head_seq -v` |
| 54 | `test_duplicate_append_logs_info` — EventStore.append with duplicate command_id logs INFO message; no exception raised | I-IDEM-LOG-1 | `pytest tests/unit/infra/test_event_store.py::test_duplicate_append_logs_info -v` |
| 55 | `test_stale_state_error_not_retried_internally` — execute_command raises StaleStateError without retry; exactly one attempt | I-RETRY-POLICY-1 | `pytest tests/unit/commands/test_registry.py::test_stale_state_error_not_retried_internally -v` |
| 56 | `test_context_hash_sentinel_is_type_specific` — two different exc types at BUILD_CONTEXT produce different context_hash values; both start with "FAIL:" | I-CONTEXT-HASH-SENTINEL-1 | `pytest tests/unit/commands/test_registry.py::test_context_hash_sentinel_is_type_specific -v` |
| 57 | `test_compute_command_id_uses_asdict_not_str` — `compute_command_id` result is identical for two Command instances constructed identically; changes if payload field changes | I-IDEM-1, A-13 | `pytest tests/unit/commands/test_registry.py::test_compute_command_id_uses_asdict_not_str -v` |
| 58 | `test_command_id_is_phase_scoped` — same task_id but different phase_id in payload → different command_id; same task_id same phase_id → same command_id | I-CMD-PAYLOAD-PHASE-1, A-13 | `pytest tests/unit/commands/test_registry.py::test_command_id_is_phase_scoped -v` |
| 59 | `test_command_id_is_32_hex_chars` — `compute_command_id` returns exactly 32 hex characters | I-IDEM-1, A-22 | `pytest tests/unit/commands/test_registry.py::test_command_id_is_32_hex_chars -v` |
| 60 | `test_context_hash_is_32_hex_chars` — `compute_context_hash` returns exactly 32 hex characters | I-CONTEXT-HASH-SENTINEL-1, A-22 | `pytest tests/unit/commands/test_registry.py::test_context_hash_is_32_hex_chars -v` |
| 61 | `test_guard_deny_without_reason_emits_error_event` — guard returning DENY with reason=None triggers ErrorEvent (error_code=7) appended to EventLog | I-GUARD-REASON-1, A-15 | `pytest tests/unit/commands/test_registry.py::test_guard_deny_without_reason_emits_error_event -v` |
| 62 | `test_guard_deny_without_reason_raises_kernel_invariant_error` — raises KernelInvariantError (SDDError subclass → exit 1), not AssertionError (exit 2) | I-GUARD-REASON-1, A-15 | `pytest tests/unit/commands/test_registry.py::test_guard_deny_without_reason_raises_kernel_invariant_error -v` |
| 63 | `test_projection_failure_emits_project_error_event` — if project_all raises, execute_and_project writes PROJECT ErrorEvent to audit_log.jsonl and raises ProjectionError | I-ERROR-1, A-16 | `pytest tests/unit/commands/test_registry.py::test_projection_failure_emits_project_error_event -v` |
| 64 | `test_optlock_check_write_is_atomic` — concurrent insert between head capture and append is caught by EventStore transaction; StaleStateError raised | I-OPTLOCK-ATOMIC-1, A-17 | `pytest tests/unit/infra/test_event_store.py::test_optlock_check_write_is_atomic -v` |
| 65 | `test_taskset_path_resolved_from_replayed_state` — taskset path uses `state.phase_current` from step 1 replay, not a pre-step-1 `_current_phase()` call | I-CMD-PHASE-RESOLVE-1, A-18 | `pytest tests/unit/commands/test_registry.py::test_taskset_path_resolved_from_replayed_state -v` |
| 66 | `test_reducer_ignores_taskset_defined_wrong_phase` — `TaskSetDefinedEvent(phase_id=N+1)` when `phase_current=N` returns unchanged state; no tasks_total update | I-TASKSET-ORDER-1, A-19 | `pytest tests/unit/domain/test_reducer.py::test_reducer_ignores_taskset_defined_wrong_phase -v` |
| 67 | `test_sync_state_allowed_when_phase_not_active` — `sdd sync-state` succeeds when `phase.status == COMPLETE` or `PLANNED` (PhaseGuard bypassed) | I-SYNC-NO-PHASE-GUARD-1, A-20 | `pytest tests/integration/test_sync_state_recovery.py::test_sync_state_allowed_when_phase_not_active -v` |
| 68 | `test_error_event_phase_id_is_none` — every ErrorEvent produced by execute_command has `phase_id is None` | I-ERROR-PHASE-NULL-1, A-21 | `pytest tests/unit/commands/test_registry.py::test_error_event_phase_id_is_none -v` |
| 69 | `test_activate_phase_handler_has_no_check_idempotent` — AST check: `ActivatePhaseHandler.handle` contains no `EventStore` access, no `_check_idempotent` call | I-HANDLER-BATCH-PURE-1, A-14 | `pytest tests/unit/test_handler_purity.py::test_activate_phase_handler_has_no_check_idempotent -v` |

### CI grep-rules (Makefile target `check-handler-purity`)

```makefile
# I-PHASE16-MIGRATION-STRICT-1: exactly these 2 files are whitelisted — no more
CI_PURITY_EXCEPTIONS := \
    src/sdd/commands/validate_invariants.py \
    src/sdd/commands/report_error.py

check-handler-purity:
	@echo "Checking I-KERNEL-WRITE-1: EventStore outside kernel..."
	@! grep -rn "EventStore(" src/sdd/ \
	    | grep -v "src/sdd/commands/registry.py" \
	    | grep -v "src/sdd/infra/event_store.py" \
	    | grep -v "$(word 1,$(CI_PURITY_EXCEPTIONS))" \
	    | grep -v "$(word 2,$(CI_PURITY_EXCEPTIONS))" \
	    | grep -q . || (echo "FAIL I-KERNEL-WRITE-1" && exit 1)
	@echo "Checking I-KERNEL-PROJECT-1: rebuild_state outside projections..."
	@! grep -rn "rebuild_state\|sync_projections" src/sdd/ \
	    | grep -v "src/sdd/commands/registry.py" \
	    | grep -v "src/sdd/infra/projections.py" \
	    | grep -v "src/sdd/commands/show_state.py" \
	    | grep -q . || (echo "FAIL I-KERNEL-PROJECT-1" && exit 1)
	@echo "Checking I-HANDLER-PURE-1: .handle( outside kernel..."
	@! grep -rn "\.handle(" src/sdd/ \
	    | grep -v "src/sdd/commands/registry.py" \
	    | grep -v "src/sdd/commands/_base.py" \
	    | grep -v "$(word 1,$(CI_PURITY_EXCEPTIONS))" \
	    | grep -v "$(word 2,$(CI_PURITY_EXCEPTIONS))" \
	    | grep -q . || (echo "FAIL I-HANDLER-PURE-1" && exit 1)
	@echo "All kernel boundary checks passed."
```

**AST vs grep priority (🔴6)**: The AST-based test (`test_handler_purity.py`, check #17)
is the **primary** enforcement mechanism — it is import-safe, alias-safe, and refactor-safe.
The Makefile grep rules (`check-handler-purity`) are a **fast secondary** check for CI
pre-flight (milliseconds vs. seconds). Both MUST pass. If they disagree (grep passes, AST
fails), AST takes precedence — the grep rule MUST be tightened to match.

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Migrate `validate_invariants.py`, `report_error.py` to REGISTRY | Phase 16 (I-PHASE16-MIGRATION-STRICT-1 — MUST complete) |
| Remove `_sdd_error_events` handler pattern from `_base.py` | Phase 16 cleanup |
| Remove `EMERGENCY` mode / EventLog migration from phases 1–14 | Phase 17+ |
| Adding read-only commands to REGISTRY (show-task, show-spec, etc.) | Not planned — orthogonal |
| Auto-generating CLAUDE.md command table from REGISTRY at build time | Phase 16+ |
| `sdd show-taskset --phase N` (full TaskSet view) | Phase 15+ per Spec_v14 §10 |
| `sdd show-phases` command | Phase 15+ per Spec_v14 §10 |
| Per-command telemetry / tracing in execute_and_project | Phase 16+ |
| Parallel command execution | Out of SDD scope |

---

## 11. Implementation Order

**Principle:** never change behavior and structure in the same task.

```
Step 1: ADD    — registry.py + guards/pipeline.py exist and are tested; no main() calls them
Step 2: SWITCH — wire each command one at a time; existing tests are the safety net
Step 3: ENFORCE — CI grep-rules block new direct kernel calls; CommandRunner deprecated
Step 4: DELETE — sdd_run.py deleted; test_sdd_run.py deleted
```

`pytest tests/ -q` must be green after every task. Tasks within a Step are independent;
tasks in Step N+1 do not begin before Step N is complete and green.

### Step 1 — Add (infrastructure; no main() wiring)

| Task | Files | Key output |
|------|-------|------------|
| T-1501 | `core/events.py`, `domain/state/reducer.py` (atomic commit) | PhaseStartedEvent, TaskSetDefinedEvent, ErrorEvent; 4 reducer handlers |
| T-1502 | `infra/projections.py` | RebuildMode, rebuild_state(STRICT), rebuild_taskset graceful missing |
| T-1503 | `core/errors.py` | SDDError subclass hierarchy |
| T-1504 | `core/events.py`, `domain/guards/context.py` | compute_trace_id, compute_context_hash; GuardResult extended |
| T-1505 | `guards/pipeline.py` (new) | run_guard_pipeline + _fetch_events_for_reduce copied from sdd_run.py |
| T-1506 | `commands/registry.py` (new) | CommandSpec, REGISTRY, execute_command, project_all, execute_and_project |
| T-1507 | `commands/_base.py` | NoOpHandler |

### Step 2 — Switch (one command per task; structure and routing always separate tasks)

| Task | Files | Command switched |
|------|-------|-----------------|
| T-1510 | `commands/update_state.py` | sync-state via NoOpHandler + kernel |
| T-1511 | `commands/update_state.py` | complete via kernel |
| T-1512 | `commands/update_state.py` | validate via kernel |
| T-1513 | `commands/update_state.py` | check-dod via kernel |
| T-1514 | `commands/activate_phase.py` | activate-phase via kernel + PhaseStartedEvent |
| T-1515 | `commands/record_decision.py`, `cli.py` | record-decision via kernel (A-1) |
| T-1516 | `commands/validate_config.py`, `cli.py`, `commands/__init__.py`, `core/payloads.py` | validate-config → plain function (A-2) |
| T-1517 | `guards/phase.py` | remove YAML fallback (A-4) |
| T-1518 | `guards/task.py` | remove YAML fallback (A-4) |

### Step 3 — Enforce

| Task | Files | Purpose |
|------|-------|---------|
| T-1519 | `Makefile` | `check-handler-purity` with 3 grep-rules + whitelist (max 2 exceptions) |
| T-1520 | `tests/unit/test_handler_purity.py`, `tests/unit/test_registry_contract.py` | AST-based purity + contract tests |
| T-1521 | `commands/sdd_run.py` | Add deprecation comment above CommandRunner class |

### Step 4 — Delete

| Task | Files | Precondition |
|------|-------|-------------|
| T-1522 | `commands/sdd_run.py` (deleted entirely), `commands/__init__.py` (remove imports), `tests/unit/commands/test_sdd_run.py` (deleted) | `grep -rn "CommandRunner" src/sdd/` = 0; `pytest tests/ -q` green |

---

## 12. Verification Map

| Task | Key Tests | Invariants Proven |
|------|-----------|-------------------|
| T-1501 | test_reducer.py #1–7 | I-PHASE-RESET-1, I-PHASE-STARTED-1, I-PHASE-COMPLETE-1, I-PHASE-SEQ-1, I-C1-ATOMIC-1 |
| T-1502 | test_projections.py #8–11 | I-REBUILD-STRICT-1, I-ES-REPLAY-1 |
| T-1504 | test_events.py #6, #29, #42 | I-C1-ATOMIC-1, I-ERROR-L2-1, I-ERROR-SINGLE-TYPE-1 |
| T-1505 | test_pipeline.py #39–40 | I-PIPELINE-HOME-1, I-GUARD-CLI-1 |
| T-1506 | test_registry.py #12–16, #25–35 | I-KERNEL-WRITE-1, I-ATOMICITY-1, I-ERROR-1, I-DIAG-1, I-REBUILD-EMERGENCY-1 |
| T-1516 | test_validate_config.py #36–37 | I-READ-ONLY-EXCEPTION-1 |
| T-1519 | `make check-handler-purity` | I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1 |
| T-1520 | test_handler_purity.py, test_registry_contract.py | I-HANDLER-PURE-1, I-REGISTRY-COMPLETE-1, I-DECISION-AUDIT-1 |
| T-1522 | `grep CommandRunner src/sdd/ = 0` | I-SDDRUN-DEAD-1 |
| Integration | test_phase_transition_no_yaml.py | I-1, I-2, I-3 (end-to-end) |

### Final Criteria (Phase 15 Complete)

```
handler.handle()   → called only in registry.py
EventStore.append  → called only in registry.py (execute_command)
guards             → NEVER read YAML; pipeline.py is their canonical home
validate-config    → plain function; never in REGISTRY
record-decision    → in REGISTRY; handler pure; projection=NONE; DecisionRecordedEvent in _KNOWN_NO_HANDLER
read-only commands → bypass REGISTRY but satisfy I-READ-ONLY-EXCEPTION-1
ErrorEvent         → exactly one type; stage field differentiates kernel phases
context_hash       → always str; f"FAIL:{exc_type[:20]}" sentinel at BUILD_CONTEXT failure (recognizable by "FAIL:" prefix); real sha256 hash in all later stages (never None)
CI whitelist       → exactly 2 files (validate_invariants.py, report_error.py)
```
