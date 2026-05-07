# Spec_v15 — Amendments A-13..A-22

**Parent spec:** `.sdd/specs/Spec_v15_KernelUnification.md`  
**Status:** DRAFT — awaiting human review and merge into Spec_v15  
**Source:** Security/correctness review, pre-implementation  
**Date:** 2026-04-23

Each amendment below:
1. Names the gap found in the original spec
2. Specifies the exact fix (pseudocode and/or invariant text)
3. Lists what changes in the spec (section, old text → new text guidance)

---

## A-13: `compute_command_id` — deterministic serialization + phase-scoped key

### Gap

`compute_command_id` uses `str(cmd.payload)` which:
1. Is non-deterministic if payload contains `frozenset`, nested dicts (pre-3.7), or future mutable fields — a new field added to a Command dataclass silently changes all historical `command_id` values, breaking idempotency.
2. Does not apply `sort_keys` to the payload itself (only to the outer `{"cmd", "payload"}` dict). `str()` of a dataclass does not sort keys.
3. More critically: if the same `task_id` string appears in two different phases (e.g., phase restarted or phase 16 uses task naming T-1601 but payload `task_id` field has same value as a prior run), the `command_id` is identical → second execution is silently blocked by `ON CONFLICT DO NOTHING`.

### Fix

Use `dataclasses.asdict` for deterministic, recursive dict serialization of the payload:

```python
import dataclasses

def compute_command_id(cmd: Command) -> str:
    """Stable idempotency key — deterministic recursive serialization via dataclasses.asdict.
    Invariant under retry and EventLog state (A-7, A-13, I-IDEM-1).
    Same logical command (same type + same payload fields) → same command_id.
    Different phase_id in payload → different command_id (phase-scoped idempotency)."""
    payload_dict = (
        dataclasses.asdict(cmd.payload)
        if dataclasses.is_dataclass(cmd.payload)
        else {"raw": repr(cmd.payload)}
    )
    serialized = json.dumps(
        {"cmd": cmd.command_type, "payload": payload_dict},
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
```

**Requirement added (I-CMD-PAYLOAD-PHASE-1):** Every task-scoped Command payload (where `spec.uses_task_id=True`) MUST include a `phase_id: int` field that matches `state.phase_current` at execution time. `execute_command` validates this after step 1: if `cmd.payload.phase_id != state.phase_current` → raise `InvariantViolationError`. This makes `command_id` naturally phase-scoped without extra logic.

### Spec changes

- §2 BC-15-DURABILITY A-7: replace `compute_command_id` implementation
- §4 Types: update `compute_command_id` code block
- §5 Invariants: update I-IDEM-1; add I-CMD-PAYLOAD-PHASE-1
- §9 Verification: update test #53 to cover determinism + phase-scoped difference

---

## A-14: `ActivatePhaseHandler._check_idempotent` violates I-HANDLER-PURE-1

### Gap

§3 "Event atomicity" states:
> "recovery: re-run `activate-phase N --tasks T`; the handler's `_check_idempotent` detects existing `PhaseStarted(N)` and re-emits only the missing `TaskSetDefined` if absent"

`_check_idempotent` requires reading the EventLog to detect prior events — direct I/O inside `handle()`. This violates I-HANDLER-PURE-1 ("handle() methods return events only — no EventStore, no rebuild_state, no sync_projections calls").

### Fix

Remove `_check_idempotent` from `ActivatePhaseHandler` entirely. Recovery is already handled correctly by two existing mechanisms:

1. **`sdd_append_batch` atomicity (I-ATOMICITY-1):** The batch `[PhaseStartedEvent, TaskSetDefinedEvent]` is inserted via a single SQL `INSERT` statement. DuckDB commits it all-or-nothing — there is no "PhaseStarted written but TaskSetDefined missing" partial state.

2. **`command_id` UNIQUE constraint (I-IDEM-1):** On re-run, both events carry the same `command_id`. DuckDB `ON CONFLICT DO NOTHING` skips both silently. `rows_inserted == 0` is logged at INFO (I-IDEM-LOG-1). No duplicate events created.

Therefore: if the batch INSERT succeeds — both events exist, re-run is a no-op. If the batch INSERT fails — neither event exists, re-run inserts both fresh. There is no partial-failure case that requires inspection of the EventLog.

### Spec changes

- §3 "Event atomicity: PhaseStarted + TaskSetDefined": replace the `_check_idempotent` paragraph with:

  > "Partial failure is impossible: `sdd_append_batch` uses a single atomic `INSERT INTO … VALUES (…), (…)` statement. Re-run safety is provided by the `command_id` UNIQUE constraint (I-IDEM-1): both events carry the same `command_id`, so a retry returns `rows_inserted=0` for both and logs INFO (I-IDEM-LOG-1). `ActivatePhaseHandler` has no `_check_idempotent` method — I-HANDLER-PURE-1 is not violated."

- §5 Invariants: add **I-HANDLER-BATCH-PURE-1**: handlers returning multiple events MUST NOT perform EventLog reads to determine which events to emit — purity is absolute; recovery is the kernel's responsibility via `command_id` + `sdd_append_batch` atomicity.

---

## A-15: `assert` (I-GUARD-REASON-1) bypasses Error Boundary and is disabled by `-O`

### Gap

In `execute_command` step 2:
```python
assert guard_result.outcome is not GuardOutcome.DENY or guard_result.reason is not None, \
    "I-GUARD-REASON-1: DENY result must populate reason"
```

Two bugs:
1. Python's `-O` / `PYTHONOPTIMIZE=1` disables `assert`. The invariant is silently bypassed in optimized builds.
2. `AssertionError` fires **before** the step 4 error boundary (`except Exception as exc`). Result: no `ErrorEvent` emitted (violates I-ERROR-1), CLI exits 2 without JSON (violates I-CLI-API-1), `AssertionError` reaches the user instead of a structured error.

### Fix

Replace the `assert` with a structured check inside a guarded block that emits an `ErrorEvent` and raises `KernelInvariantError` (new error class, error_code=7):

```python
# I-GUARD-REASON-1: programming contract — DENY must populate all diagnostic fields
if guard_result.outcome is GuardOutcome.DENY and guard_result.reason is None:
    error_event = _make_error_event(
        stage="GUARD", spec=spec,
        error_type="KernelInvariantError",
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
```

`KernelInvariantError` is a new `SDDError` subclass (error_code=7) added to `core/errors.py`. It signals a programming error in a guard implementation, not a user/domain error.

**Additionally:** `run_guard_pipeline` in `guards/pipeline.py` MUST validate all three fields (`reason`, `human_reason`, `violated_invariant`) for any DENY result before returning. This catches the programming error as early as possible, closest to the faulty guard.

### Spec changes

- §2 `execute_command` pseudocode: replace `assert` block with the structured check above
- §4 Error Type Hierarchy: add `KernelInvariantError` (error_code=7, stage=GUARD)
- §5 Invariants: update I-GUARD-REASON-1 (no `assert` → raise `KernelInvariantError`; ErrorEvent always emitted)
- §9 Verification: update test #31 (`test_guard_deny_without_reason_raises_assertion` → `test_guard_deny_without_reason_raises_kernel_invariant_error`); add test that `ErrorEvent` is emitted for this case

---

## A-16: PROJECT-stage `ErrorEvent` never emitted (gap in I-ERROR-1)

### Gap

I-ERROR-1 states:
> "execute_command MUST emit ErrorEvent before raising at every failure stage: GUARD/EXECUTE/**PROJECT**"

But `project_all` is called from `execute_and_project`, **not** from `execute_command`. `execute_command` returns before `project_all` runs. No code in `execute_and_project` emits a PROJECT-stage `ErrorEvent`. If `rebuild_state` fails in `project_all`, the error propagates as bare `Exception` → exit 2, no ErrorEvent, no audit trail.

### Fix

Wrap `project_all` call in `execute_and_project` with a try/except that emits a PROJECT-stage `ErrorEvent` to `audit_log.jsonl`:

```python
def execute_and_project(
    spec: CommandSpec,
    cmd: Command,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
) -> list[DomainEvent]:
    """CLI convenience: execute_command → project_all(spec.projection).
    PROJECT-stage failures emit ErrorEvent to audit_log.jsonl (I-ERROR-1, A-16)."""
    events = execute_command(spec, cmd, db_path, state_path, taskset_path, norm_path)
    if spec.projection == ProjectionType.NONE:
        return events

    _db = db_path or str(event_store_file())
    try:
        project_all(spec.projection, db_path, state_path, taskset_path)
    except Exception as proj_exc:
        # Events are already committed; projection failed.
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
            context_hash="FAIL:PROJECTION",  # state built successfully; only projection failed
            error_code=5,
        )
        _write_error_to_audit_log(error_event)   # EventStore may be down — fallback
        raise ProjectionError(str(proj_exc)) from proj_exc
    return events
```

**Note on `context_hash="FAIL:PROJECTION"`:** The `"FAIL:"` prefix is recognizable by diagnostic tooling (I-CONTEXT-HASH-SENTINEL-1). The suffix `"PROJECTION"` distinguishes this from BUILD_CONTEXT failures. The actual state was built successfully (that's how execute_command completed) — this sentinel marks the projection stage specifically.

### Spec changes

- §2 `execute_and_project` pseudocode: replace with the version above
- §5 Invariants: update I-ERROR-1 to clarify "GUARD/EXECUTE/COMMIT errors → execute_command; PROJECT errors → execute_and_project; all write to audit_log.jsonl when EventStore unavailable"
- §9 Verification: add test `test_projection_failure_emits_project_error_event`

---

## A-17: Optimistic lock TOCTOU — atomize check+write via `EventStore.append(expected_head=)`

### Gap

Step 5a (max_seq read) and step 5 (INSERT) are separate DuckDB calls. A concurrent writer can insert rows between them. The spec presents I-OPTLOCK-1 as a correctness guarantee, but technically it is a best-effort heuristic with a TOCTOU window.

### Fix

Add `expected_head: int | None` parameter to `EventStore.append()`. When supplied, the implementation wraps the read-and-write in a single DuckDB transaction:

```python
def append(
    self,
    events: list[DomainEvent],
    source: str,
    command_id: str | None = None,
    expected_head: int | None = None,   # A-17, I-OPTLOCK-ATOMIC-1: atomic check+write
) -> int:
    """Append events. When expected_head is supplied, verifies max(seq)==expected_head
    inside a transaction before INSERT — eliminating the TOCTOU gap between check and write."""
    with self._conn.transaction():
        if expected_head is not None:
            current = self._conn.execute(
                "SELECT COALESCE(max(seq), -1) FROM events"
            ).fetchone()[0]
            if current != expected_head:
                raise StaleStateError(
                    f"EventLog head changed: expected={expected_head}, current={current}"
                )
        rows_inserted = self._insert_batch(events, source, command_id)
        if rows_inserted == 0 and command_id is not None:
            logging.info("duplicate command detected", extra={"command_id": command_id})
    return rows_inserted
```

**`execute_command` changes:** Remove the separate step 5a block entirely. Pass `expected_head=head_seq` directly to `EventStore.append`. The `StaleStateError` raised inside `append` is caught in the step 5 except block:

```python
    # Step 5: atomic check+write — eliminates TOCTOU between max_seq() read and INSERT (A-17)
    if handler_events:
        try:
            EventStore(_db).append(
                handler_events,
                source=spec.handler_class.__module__,
                command_id=command_id,
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
            _write_error_to_audit_log(error_event)
            raise CommitError(str(commit_exc)) from commit_exc
```

**Backward compatibility:** `expected_head` defaults to `None` — existing callers (e.g., guard DENY audit append, error_boundary append) continue to work without the lock.

### Spec changes

- §2 `execute_command` pseudocode: remove step 5a block; merge into step 5 via `expected_head=head_seq`
- §2 BC-15-DURABILITY A-11: update text to describe atomic transaction approach
- §4 `EventStore.append` (frozen interface §0.15): add `expected_head: int | None = None` as optional backward-compatible parameter
- §5 Invariants: replace I-OPTLOCK-1 text with: "EventStore.append MUST verify `max_seq() == expected_head` atomically inside a DuckDB transaction before INSERT when `expected_head` is supplied; this eliminates the TOCTOU gap between the head check and the write"; add new **I-OPTLOCK-ATOMIC-1** for the transaction requirement
- §9 Verification: update test #50 (`test_execute_command_raises_stale_state_on_concurrent_write`) to verify the atomic transaction path

---

## A-18: `_current_phase(_db)` called before `head_seq` — phase mismatch risk

### Gap

In `execute_command` path resolution:
```python
_ts = taskset_path or str(taskset_file(_current_phase(_db)))  # ← extra EventLog read
head_seq: int | None = EventStore(_db).max_seq()              # ← head captured AFTER
```

`_current_phase(_db)` makes a DuckDB read to determine the current phase. If events are inserted between this read and the `head_seq` capture (e.g., a concurrent `activate-phase` call), `_ts` points to the wrong TaskSet version while `state` (built in step 1) reflects the new phase. Optimistic lock at step 5 catches that `head_seq` is stale and raises `StaleStateError`, but the taskset path was already wrong — `_find_task` could read the wrong file and silently return `None` or a stale task definition.

### Fix

Defer taskset path resolution to **after step 1** (state built from EventLog replay). At that point `state.phase_current` is authoritative and consistent with the replayed events:

```python
def execute_command(...):
    _db  = db_path    or str(event_store_file())
    _st  = state_path or str(state_file())
    _ts_override = taskset_path  # caller override stored; resolved after step 1
    _nrm = norm_path  or str(norm_catalog_file())

    # Step 0: head_seq + trace_id (no _current_phase call here)
    ...

    # Step 1: EventLog replay → state
    ...
    state = EventReducer().reduce(events_raw)

    # Resolve taskset path from replay-derived phase (I-CMD-PHASE-RESOLVE-1, A-18)
    _ts = _ts_override or str(taskset_file(state.phase_current))

    context_hash = compute_context_hash(state)
    phase = PhaseState(...)
    task = _find_task(_ts, task_id) if spec.uses_task_id else None
    ...
```

**New invariant I-CMD-PHASE-RESOLVE-1:** The taskset file path MUST be resolved from `state.phase_current` (derived from EventLog replay in step 1), never from a pre-step-1 `_current_phase()` call. This ensures taskset path and replayed state are always consistent.

### Spec changes

- §2 `execute_command` pseudocode: remove `_current_phase(_db)` from path resolution block; add `_ts_override = taskset_path`; add `_ts = _ts_override or str(taskset_file(state.phase_current))` after step 1
- §5 Invariants: add **I-CMD-PHASE-RESOLVE-1**
- §9 Verification: add test `test_taskset_path_resolved_from_replayed_state`

---

## A-19: `TaskSetDefined` reducer handler lacks ordering guard

### Gap

A-8 added a soft guard to the `PhaseStarted` reducer handler: out-of-order `PhaseStarted(N)` events are ignored (log warning, return unchanged state). However `TaskSetDefinedEvent` has no analogous guard.

Scenario with a corrupted or manually injected EventLog:
1. `PhaseStarted(16)` arrives out of order → soft guard ignores it (current phase stays 14)
2. `TaskSetDefined(16, 20)` arrives → **no guard** → applied to current state (phase_current=14)
3. Result: `tasks_total=20` with `phase_current=14` — logically impossible, indistinguishable from valid state

### Fix

Add a phase-consistency check to the `TaskSetDefined` reducer handler:

```python
def _handle_taskset_defined(state: SDDState, event: TaskSetDefinedEvent) -> SDDState:
    if event.phase_id != state.phase_current:
        logging.warning(
            "I-TASKSET-ORDER-1: ignoring TaskSetDefined — "
            "event.phase_id=%d does not match state.phase_current=%d",
            event.phase_id, state.phase_current,
        )
        return state  # deterministic no-op; replay is stable
    return state._replace(tasks_total=event.tasks_total)
```

The guard is "soft" (same policy as A-8): it logs and skips, never raises. Replay with injected/reordered events produces deterministic, reproducible state.

### Spec changes

- §2 BC-2 reducer section (item C — TaskSetDefined): add the soft guard to the handler description
- §5 Invariants: add **I-TASKSET-ORDER-1**: "Reducer `TaskSetDefined` handler MUST ignore (log warning, return unchanged state) any event where `event.phase_id ≠ state.phase_current`; replay with mismatched events MUST produce deterministic state"
- §9 Verification: add test `test_reducer_ignores_taskset_defined_wrong_phase`

---

## A-20: `sync-state` blocked by PhaseGuard in recovery scenarios

### Gap

`sync-state` runs the full guard pipeline including PhaseGuard (PG-3: `phase.status == ACTIVE`). But `sync-state` is a recovery utility — it is most useful precisely when the phase is NOT active: after `check-dod` completes (status=COMPLETE) or before `activate-phase` (status=PLANNED). In these states PhaseGuard returns DENY and `sync-state` is inaccessible.

### Fix

Add `requires_active_phase: bool = True` field to `CommandSpec`. For `sync-state`: `requires_active_phase=False`.

In `run_guard_pipeline`, add `skip_phase_guard: bool = False` parameter. When `True`, PhaseGuard is skipped entirely:

```python
def run_guard_pipeline(
    ctx: GuardContext,
    command_str: str,
    actor: str,
    action: str,
    task_id: str | None,
    required_ids: tuple[str, ...],
    input_paths: tuple[str, ...],
    skip_phase_guard: bool = False,     # A-20, I-SYNC-NO-PHASE-GUARD-1
) -> tuple[GuardResult, list[DomainEvent]]:
    guards = []
    if not skip_phase_guard:
        guards.append(PhaseGuard())
    if task_id:
        guards.extend([TaskGuard(), DependencyGuard()])
    guards.append(NormGuard())
    ...
```

In `execute_command` step 2:
```python
guard_result, audit_events = run_guard_pipeline(
    ...,
    skip_phase_guard=not spec.requires_active_phase,   # A-20
)
```

Updated `sync-state` REGISTRY entry:
```python
"sync-state": CommandSpec(
    name="sync-state",
    handler_class=NoOpHandler,
    actor="any",
    action="sync_state",
    projection=ProjectionType.FULL,
    uses_task_id=False,
    requires_active_phase=False,    # A-20: recovery utility; bypasses PhaseGuard
    event_schema=(),
    preconditions=(),
    postconditions=("State_index.yaml rebuilt from EventLog",),
),
```

### Spec changes

- §2 BC-15-REGISTRY `CommandSpec` dataclass: add `requires_active_phase: bool = True` field
- §2 REGISTRY dict: set `requires_active_phase=False` for `sync-state`
- §2 `execute_command` pseudocode step 2: pass `skip_phase_guard=not spec.requires_active_phase`
- §2 BC-15-GUARDS-PIPELINE: document `skip_phase_guard` parameter
- §5 Invariants: add **I-SYNC-NO-PHASE-GUARD-1**: "`sync-state` MUST bypass PhaseGuard (`requires_active_phase=False`); it is a recovery utility available in any phase status"
- §9 Verification: add test `test_sync_state_allowed_when_phase_not_active`

---

## A-21: `ErrorEvent.phase_id = None` — potential conflict with frozen `DomainEvent` interface

### Gap

`_make_error_event` constructs `ErrorEvent(phase_id=None, ...)`. If `DomainEvent.phase_id` is typed as `int` (not `int | None`), this is a type error at runtime and a mypy error. Per §0.15 (frozen interfaces), changing the type of `phase_id` in `DomainEvent` is a breaking change requiring a new spec.

### Fix

Explicitly declare `DomainEvent.phase_id: int | None = None` as an optional field with a default. This is a **backward-compatible extension** per §0.15(a) (adding optional parameter with default value). All existing event instantiations that pass a positional `int` continue to work. Only `ErrorEvent` uses `None`.

Add to §4 Types & Interfaces:

> **`DomainEvent.phase_id` is `int | None` (§0.15(a) extension):** The base field type is extended from `int` to `int | None` with `default=None`. This is backward-compatible per §0.15(a): all existing event constructors pass an explicit `int`; only `ErrorEvent` uses `None` (cross-cutting events carry no phase context). The mypy frozen-module tests (I-KERNEL-REG) MUST be updated to expect `int | None`.

**New invariant I-ERROR-PHASE-NULL-1:** `ErrorEvent.phase_id` MUST be `None`; it is a cross-cutting observability event not bound to any single phase. Any `ErrorEvent` instance with a non-None `phase_id` is a kernel bug.

### Spec changes

- §4 Types: add `DomainEvent.phase_id: int | None = None` clarification paragraph
- §5 Invariants: add **I-ERROR-PHASE-NULL-1**
- Update I-KERNEL-REG / I-KERNEL-SIG-1 notes to reflect the `int | None` type change as backward-compatible

---

## A-22: `context_hash` and `trace_id` — 16 hex chars (64 bits) insufficient for large EventLogs

### Gap

Both `context_hash` and `command_id` are truncated to 16 hex chars (64 bits). By birthday paradox, in a log with ~4 billion entries the collision probability for 64-bit hashes approaches 50%. For `command_id`, a collision means a legitimate command is silently dropped (DO NOTHING). For `context_hash`, two different states become indistinguishable in diagnostics.

`trace_id` at 16 chars is a diagnostic ID only — collisions are annoying but not safety-critical. Keep at 16.

### Fix

Increase `command_id` to **32 hex chars (128 bits)** — the deduplication key must be collision-resistant.  
Increase `context_hash` to **32 hex chars (128 bits)** — diagnostic state fingerprint.  
Keep `trace_id` at **16 hex chars** — per-execution diagnostic, short is fine for readability.

```python
def compute_command_id(cmd: Command) -> str:
    ...
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]   # was [:16]

def compute_context_hash(state: SDDState) -> str:
    ...
    return hashlib.sha256(
        json.dumps(asdict(state), sort_keys=True).encode()
    ).hexdigest()[:32]                                             # was [:16]

def compute_trace_id(cmd: Command, head_seq: int | None) -> str:
    ...
    return hashlib.sha256(payload.encode()).hexdigest()[:16]       # unchanged
```

**Sentinel format update (I-CONTEXT-HASH-SENTINEL-1):** `context_hash` sentinel remains `f"FAIL:{type(exc).__name__[:20]}"` (max 25 chars). Since non-sentinel `context_hash` is now 32 chars, the `"FAIL:"` prefix is unambiguous — no length-based collision with real hashes.

**DuckDB schema:** `command_id TEXT` column already exists (I-IDEM-SCHEMA-1). No schema migration needed — the column length constraint is not fixed in DuckDB TEXT type.

### Spec changes

- §2 A-7 `compute_command_id`: change `[:16]` → `[:32]`
- §4 `compute_command_id` and `compute_context_hash` code blocks: change `[:16]` → `[:32]`
- §5 I-CONTEXT-HASH-SENTINEL-1: update "max 25 chars" → note 32-char non-sentinel, 25-char sentinel max, prefix rule unchanged
- §9 tests: update test #53 and #56 to expect 32-char strings

---

## Summary of New Invariants

| ID | Statement | Fixes |
|----|-----------|-------|
| I-CMD-PAYLOAD-PHASE-1 | Task-scoped Command payloads MUST include `phase_id: int` matching `state.phase_current`; `execute_command` validates after step 1 | A-13 |
| I-HANDLER-BATCH-PURE-1 | Handlers returning multiple events MUST NOT read EventLog to choose which events to emit; recovery is the kernel's responsibility | A-14 |
| I-CMD-PHASE-RESOLVE-1 | Taskset file path MUST be resolved from `state.phase_current` (step 1 output), never from a pre-step-1 `_current_phase()` call | A-18 |
| I-TASKSET-ORDER-1 | Reducer `TaskSetDefined` handler MUST ignore (log warning) events where `event.phase_id ≠ state.phase_current` | A-19 |
| I-SYNC-NO-PHASE-GUARD-1 | `sync-state` MUST bypass PhaseGuard (`requires_active_phase=False`); available in any phase status | A-20 |
| I-ERROR-PHASE-NULL-1 | `ErrorEvent.phase_id` MUST be `None`; cross-cutting events carry no phase context | A-21 |
| I-OPTLOCK-ATOMIC-1 | `EventStore.append` MUST perform the `max_seq` check and the INSERT inside a single DuckDB transaction when `expected_head` is supplied | A-17 |

## Updated Invariants (changed wording)

| ID | Key change |
|----|-----------|
| I-IDEM-1 | `compute_command_id` uses `dataclasses.asdict` + `json.dumps(sort_keys=True)`; key is 32 hex chars; task-scoped commands include `phase_id` in payload |
| I-GUARD-REASON-1 | No `assert` — raise `KernelInvariantError` (error_code=7) with ErrorEvent emitted before raise |
| I-OPTLOCK-1 | Atomic check+write via `expected_head` parameter to `EventStore.append`; separate step 5a removed from `execute_command` |
| I-ERROR-1 | PROJECT-stage ErrorEvent emitted from `execute_and_project` (not `execute_command`); written to `audit_log.jsonl` |
| I-CONTEXT-HASH-SENTINEL-1 | `context_hash` is 32 hex chars for real hashes; sentinel format unchanged (`"FAIL:{ExcType[:20]}"`) |

## Updated Error Type Hierarchy

```python
SDDError (base)
├── GuardViolationError      stage=GUARD,          error_code=1
├── InvariantViolationError  stage=EXECUTE|GUARD,  error_code=2
├── ExecutionError           stage=EXECUTE,         error_code=3
├── CommitError              stage=COMMIT,          error_code=4
├── ProjectionError          stage=PROJECT,         error_code=5
├── StaleStateError          stage=COMMIT,          error_code=6
└── KernelInvariantError     stage=GUARD,           error_code=7  # A-15: programming error in guard
```

## New Verification Tests

| # | Test | Invariant | Command |
|---|------|-----------|---------|
| 57 | `test_compute_command_id_uses_asdict_not_str` | I-IDEM-1, A-13 | `pytest tests/unit/commands/test_registry.py::test_compute_command_id_uses_asdict_not_str` |
| 58 | `test_command_id_is_phase_scoped` | I-CMD-PAYLOAD-PHASE-1, A-13 | `pytest tests/unit/commands/test_registry.py::test_command_id_is_phase_scoped` |
| 59 | `test_guard_deny_without_reason_emits_error_event` | I-GUARD-REASON-1, A-15 | `pytest tests/unit/commands/test_registry.py::test_guard_deny_without_reason_emits_error_event` |
| 60 | `test_guard_deny_without_reason_raises_kernel_invariant_error` | I-GUARD-REASON-1, A-15 | `pytest tests/unit/commands/test_registry.py::test_guard_deny_without_reason_raises_kernel_invariant_error` |
| 61 | `test_projection_failure_emits_project_error_event` | I-ERROR-1, A-16 | `pytest tests/unit/commands/test_registry.py::test_projection_failure_emits_project_error_event` |
| 62 | `test_optlock_check_write_is_atomic` | I-OPTLOCK-ATOMIC-1, A-17 | `pytest tests/unit/infra/test_event_store.py::test_optlock_check_write_is_atomic` |
| 63 | `test_taskset_path_resolved_from_replayed_state` | I-CMD-PHASE-RESOLVE-1, A-18 | `pytest tests/unit/commands/test_registry.py::test_taskset_path_resolved_from_replayed_state` |
| 64 | `test_reducer_ignores_taskset_defined_wrong_phase` | I-TASKSET-ORDER-1, A-19 | `pytest tests/unit/domain/test_reducer.py::test_reducer_ignores_taskset_defined_wrong_phase` |
| 65 | `test_sync_state_allowed_when_phase_not_active` | I-SYNC-NO-PHASE-GUARD-1, A-20 | `pytest tests/integration/test_sync_state_recovery.py::test_sync_state_allowed_when_phase_not_active` |
| 66 | `test_error_event_phase_id_is_none` | I-ERROR-PHASE-NULL-1, A-21 | `pytest tests/unit/commands/test_registry.py::test_error_event_phase_id_is_none` |
| 67 | `test_command_id_is_32_hex_chars` | I-IDEM-1, A-22 | `pytest tests/unit/commands/test_registry.py::test_command_id_is_32_hex_chars` |
| 68 | `test_context_hash_is_32_hex_chars` | I-CONTEXT-HASH-SENTINEL-1, A-22 | `pytest tests/unit/commands/test_registry.py::test_context_hash_is_32_hex_chars` |
| 69 | `test_activate_phase_handler_has_no_check_idempotent` | I-HANDLER-BATCH-PURE-1, A-14 | `pytest tests/unit/commands/test_handler_purity.py::test_activate_phase_handler_has_no_check_idempotent` |
