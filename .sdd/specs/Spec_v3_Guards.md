# Spec_v3_Guards — Phase 3: Norm, Guards & Scheduler

Status: Draft
Baseline: Spec_v2_State.md (BC-TASKS, BC-STATE, BC-CONTEXT, BC-INFRA, BC-CORE)

---

## 0. Goal

Build the guard pipeline (`guards/`), norm catalog reader (`domain/norms/`), and task DAG
scheduler (`domain/tasks/scheduler.py`) for `src/sdd/`. After this phase:

- **Guard pipeline**: `ScopeGuard`, `PhaseGuard`, `TaskGuard`, `TaskStartGuard`, `NormGuard` and
  `run_guard_pipeline` are executable as pure-ish functions backed by injected emit callables
- **TaskStartGuard** enforces the `requires_invariants` dependency chain (D-4), blocking task
  start until all prerequisite invariants have PASS status in their producing ValidationReports
- **NormCatalog** makes actor permissions machine-queryable without YAML parsing at the call site
- **Task scheduler**: DAG builder + topological ordering with parallel groups (D-20), enabling
  planners to identify which tasks may execute concurrently
- **BC-TASKS extension**: `Task` dataclass gains `depends_on` and `parallel_group` fields so the
  scheduler and future execution engine can consume the dependency graph declared in TaskSet files

This phase produces no CLI entry points and no command handlers. It is the governance substrate
that Phase 4 (commands) and Phase 6 (CLI + hooks) build on.

---

## 1. Scope

### In-Scope

- BC-GUARDS: `src/sdd/guards/` — five guard modules + pipeline runner
- BC-NORMS: `src/sdd/domain/norms/catalog.py` — norm catalog loader and query interface
- BC-SCHEDULER: `src/sdd/domain/tasks/scheduler.py` — `TaskNode`, `build_dag`, `topological_order`
- BC-TASKS extension: `Task` dataclass adds `depends_on: tuple[str, ...]` and `parallel_group: str | None`; `parse_taskset` updated accordingly
- New L1 event types `NormViolated` + `TaskStartGuardRejected` (C-1 compliance in `core/events.py` + `domain/state/reducer.py`)
- New error types `CyclicDependency(SDDError)`, `ParallelGroupConflict(SDDError)` in `core/errors.py`
- 80%+ test coverage for all new and modified modules
- Invariants I-GRD-1..9, I-NRM-1..3, I-SCH-1..6

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-GUARDS: `src/sdd/guards/`

```
src/sdd/guards/
  __init__.py       ← re-exports: EmitFn, GuardContext, GuardOutcome, GuardResult,
                      run_guard_pipeline,
                      ScopeGuard, PhaseGuard, TaskGuard, TaskStartGuard, NormGuard
  scope.py          ← ScopeGuard: check_read(ctx, path), check_write(ctx, path) (I-GRD-1, I-GRD-2)
  phase.py          ← PhaseGuard: check(ctx, command) (I-GRD-3)
  task.py           ← TaskGuard: check(ctx, task_id) (I-GRD-5)
  task_start.py     ← TaskStartGuard: check_requires_invariants(ctx, task_id, required_ids) (I-GRD-6, D-4)
  norm.py           ← NormGuard: check(ctx, actor, action, task_id) (I-GRD-7)
  runner.py         ← EmitFn, GuardContext, GuardOutcome, GuardResult,
                      run_guard_pipeline (I-GRD-4)
```

### BC-NORMS: `src/sdd/domain/norms/`

```
src/sdd/domain/norms/
  __init__.py       ← re-exports: NormEntry, NormCatalog, load_catalog
  catalog.py        ← NormEntry, NormCatalog, load_catalog(path) (I-NRM-1, I-NRM-2)
```

### BC-SCHEDULER: `src/sdd/domain/tasks/` (extension)

```
src/sdd/domain/tasks/
  scheduler.py      ← TaskNode, CyclicDependency (re-raised), build_dag,
                      topological_order (D-20; I-SCH-1..5)
  __init__.py       ← add re-exports: TaskNode, build_dag, topological_order
  parser.py         ← extend Task dataclass: +depends_on, +parallel_group;
                      update parse_taskset to populate new fields
```

### BC-CORE extensions (`src/sdd/core/`)

```
core/errors.py      ← add CyclicDependency(SDDError), ParallelGroupConflict(SDDError)
core/events.py      ← add NormViolated + TaskStartGuardRejected to V1_L1_EVENT_TYPES
domain/state/reducer.py ← add "NormViolated", "TaskStartGuardRejected" to _KNOWN_NO_HANDLER
```

**C-1 constraint (BLOCKING):** The three changes above (V1_L1_EVENT_TYPES, _KNOWN_NO_HANDLER,
event dataclasses) MUST be committed in the same task. The import-time `assert` in
`EventReducer` fires if any L1 type is in `V1_L1_EVENT_TYPES` but absent from both
`_EVENT_SCHEMA` and `_KNOWN_NO_HANDLER`. Splitting across tasks → `AssertionError` on import →
entire process fails to start.

### Dependencies

```text
BC-GUARDS    → BC-STATE  : PhaseGuard reads SDDState via read_state (I-ST-3)
BC-GUARDS    → BC-TASKS  : TaskGuard + TaskStartGuard use parse_taskset (I-TS-1, I-TS-2)
BC-GUARDS    → BC-NORMS  : NormGuard receives an injected NormCatalog (no direct load)
BC-GUARDS    → BC-CORE   : raises ScopeViolation, InvalidState, MissingContext;
                           emits NormViolatedEvent, TaskStartGuardRejectedEvent,
                           SDDEventRejected (already L1)
BC-GUARDS    → BC-INFRA  : emits via injected emit callable — no direct duckdb.connect (I-EL-9)
BC-NORMS     → stdlib    : yaml, dataclasses — pure I/O; no infra dependency
BC-SCHEDULER → BC-TASKS  : reads Task.depends_on + Task.parallel_group from parse_taskset;
                           no infra dependency — pure functions (I-SCH-3)
BC-SCHEDULER → BC-CORE   : raises CyclicDependency(SDDError), ParallelGroupConflict(SDDError), MissingContext
```

### §2.1 Guard Behavioral Contract

Guards follow two distinct failure modes depending on the error class. This contract is
formal and MUST NOT be violated by implementations.

| Guard | Failure mode | On DENY: raises? | On DENY: emits event? | Rationale |
|-------|-------------|:-----------------:|:---------------------:|-----------|
| `ScopeGuard` | Integrity (programming error, config violation) | **Yes** — `ScopeViolation` | No | Scope violation = broken invariant; caller cannot recover |
| `PhaseGuard` | Policy (phase state doesn't allow this command) | No | **Yes** — `SDDEventRejected` | Phase mismatch is a normal, recoverable rejection; audit trail required |
| `TaskGuard.DONE` | Integrity (task already complete) | **Yes** — `InvalidState` | No | Duplicate task execution = broken state; must abort immediately |
| `TaskGuard.MISSING` | Integrity (task_id not found) | **Yes** — `MissingContext` | No | Missing task = configuration error; cannot proceed |
| `TaskStartGuard` | Policy (invariant not yet PASS) | No | **Yes** — `TaskStartGuardRejected` | Missing prerequisite is expected during incremental work |
| `NormGuard` | Policy (actor not permitted) | No | **Yes** — `NormViolated` | Norm violation must be audited as L1 event; caller decides next step |

**I-GRD-9 contract:** Integrity guards (ScopeGuard, TaskGuard) raise an `SDDError` subclass
synchronously. Policy guards (PhaseGuard, TaskStartGuard, NormGuard) return `GuardResult(DENY)`
and emit an L1 event. No guard raises AND emits for the same check.

**I-GRD-8 contract:** In all policy guards, `emit(event)` is called BEFORE `return GuardResult(DENY)`.
If `emit` raises, the exception propagates — the guard does NOT suppress emit failures.

---

## 3. Domain Events

### New L1 Events (C-1 — see §2 BC-CORE extensions)

#### NormViolatedEvent

Emitted by `NormGuard.check()` when an actor attempts a forbidden action.

```python
@dataclass(frozen=True)
class NormViolatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "NormViolated"
    actor: str                   # "llm" | "human"
    action: str                  # action that was attempted
    norm_id: str                 # e.g. "NORM-ACTOR-001"
    task_id: str | None          # None if not task-scoped
    timestamp: str               # ISO8601 UTC
```

#### TaskStartGuardRejectedEvent

Emitted by `TaskStartGuard.check_requires_invariants()` when a required invariant is not PASS.

```python
@dataclass(frozen=True)
class TaskStartGuardRejectedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskStartGuardRejected"
    task_id: str                      # task being started
    missing_invariant: str            # first invariant not at PASS status
    required_ids: tuple[str, ...]     # all required invariant ids
    timestamp: str                    # ISO8601 UTC
```

### Event Catalog (Phase 3)

| Event | Emitter | Level | Description |
|-------|---------|-------|-------------|
| `NormViolated` | `guards/norm.py` | L1 (no reducer handler — audit only) | Actor attempted a forbidden action per norm_catalog |
| `TaskStartGuardRejected` | `guards/task_start.py` | L1 (no reducer handler — audit only) | Required invariant not yet PASS |
| `SDDEventRejected` | `guards/phase.py` | L1 (already in _KNOWN_NO_HANDLER) | Phase/plan precondition failed; re-uses existing event type |

**Reducer classification (I-ST-10):** Both new types go into `_KNOWN_NO_HANDLER`. Neither
affects `SDDState`. Their retention is forever (L1 audit trail).

### SDDEventRejected payload (Phase 3 emitter: PhaseGuard)

```python
# PhaseGuard emits via sdd_append with this payload structure:
payload = {
    "command":          str,   # e.g. "Implement T-301"      — required
    "rejection_reason": str,   # e.g. "phase.status != ACTIVE" — required
    "phase_id":         str,   # state.phase_current as str   — required
    "failed_check":     str,   # "PG-1" | "PG-2" | "PG-3"    — required
    "timestamp":        str,   # ISO8601 UTC                   — required
}
```

---

## 4. Types & Interfaces

### 4.0 EmitFn + GuardContext (`guards/runner.py`)

```python
from typing import Callable

# Formal type alias for the event emission callable injected into all policy guards.
# Contract:
#   - MUST NOT be None
#   - If emit raises, the exception propagates — guards do not suppress emit failures (I-GRD-8)
#   - Called exactly once per DENY in policy guards, BEFORE returning GuardResult (I-GRD-8)
EmitFn = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class GuardContext:
    """Shared environment carrier for all guard calls.

    Bundles all cross-cutting inputs so guard methods receive a single typed object
    instead of a variable-length kwargs list. Guards MUST NOT store ctx — receive it
    as a parameter, read what they need, return GuardResult. No mutations (I-GRD-9).
    """
    state:        "SDDState"      # authoritative state from read_state()
    config:       dict            # loaded project_profile.yaml (via load_config)
    taskset_path: str             # exact path to active TaskSet_vN.md
    reports_dir:  str             # path to .sdd/reports/ (for TaskStartGuard)
    emit:         EmitFn          # event emission callable — injected, never None (I-EL-9)
    catalog:      "NormCatalog"   # loaded norm catalog (for NormGuard)
```

### 4.1 GuardOutcome + GuardResult (`guards/runner.py`)

```python
from enum import Enum
from dataclasses import dataclass

class GuardOutcome(Enum):
    ALLOW = "allow"
    DENY  = "deny"

@dataclass(frozen=True)
class GuardResult:
    outcome:    GuardOutcome
    guard_name: str          # which guard produced this result
    message:    str          # human-readable reason (empty string on ALLOW)
    norm_id:    str | None   # populated for NormGuard DENY results
    task_id:    str | None   # populated for task-scoped checks
```

### 4.2 ScopeGuard (`guards/scope.py`)

```python
class ScopeGuard:
    """Check file access against allowed/forbidden dir lists from project_profile.yaml.
    Integrity guard: DENY → raises ScopeViolation (§2.1 contract, I-GRD-9).
    Pure function of path + ctx.config (I-GRD-1). No I/O, no randomness, no emit.
    """

    @staticmethod
    def check_read(ctx: GuardContext, path: str) -> GuardResult:
        """ALLOW if path is not under any forbidden_dir in ctx.config.
        DENY + raise ScopeViolation if path matches a forbidden pattern (I-GRD-1, I-GRD-9).
        Pure: same ctx.config + path → same result.
        """
        ...

    @staticmethod
    def check_write(ctx: GuardContext, path: str) -> GuardResult:
        """Same rules as check_read PLUS:
        Always DENY + raise ScopeViolation for any path matching '.sdd/specs/**'
        (NORM-SCOPE-004, I-SDD-9, I-GRD-2, I-GRD-9).
        """
        ...
```

### 4.3 PhaseGuard (`guards/phase.py`)

```python
class PhaseGuard:
    """Enforce PG-1..PG-3 preconditions for Implement / Validate commands.
    Policy guard: DENY → emit SDDEventRejected, return GuardResult(DENY); no raise (§2.1).
    """

    @staticmethod
    def check(ctx: GuardContext, command: str) -> GuardResult:
        """Check using ctx.state and ctx.config:
          PG-1: ctx.state.phase_current == N (N extracted from command)
          PG-2: ctx.state.plan_version == ctx.state.tasks_version == N
          PG-3: ctx.state.phase_status == "ACTIVE"

          ALLOW if all three pass.
          DENY: emit SDDEventRejected (payload per §3) via ctx.emit BEFORE returning (I-GRD-8).
          Does NOT raise — returns GuardResult(DENY) (I-GRD-3, §2.1).
        """
        ...
```

### 4.4 TaskGuard (`guards/task.py`)

```python
class TaskGuard:
    """Verify task status == TODO before implementation starts.
    Integrity guard: DENY → raises SDDError subclass; no emit (§2.1, I-GRD-9).
    """

    @staticmethod
    def check(ctx: GuardContext, task_id: str) -> GuardResult:
        """Parse parse_taskset(ctx.taskset_path), find task_id.
          ALLOW: task.status == "TODO".
          DENY + raise InvalidState:    task.status == "DONE" (already complete — I-GRD-5, I-GRD-9).
          DENY + raise MissingContext:  task_id not found in taskset (I-GRD-5, I-GRD-9).
        """
        ...
```

### 4.5 TaskStartGuard (`guards/task_start.py`)

```python
class TaskStartGuard:
    """Enforce requires_invariants dependency chain (D-4).
    Policy guard: DENY → emit TaskStartGuardRejectedEvent, return DENY; no raise (§2.1).
    Reads only ValidationReport files — no DB calls (I-EL-9).
    """

    @staticmethod
    def check_requires_invariants(
        ctx: GuardContext,
        task_id: str,
        required_ids: tuple[str, ...],
    ) -> GuardResult:
        """For each invariant_id in required_ids:
          1. Scan ctx.reports_dir per §4.5.1 parsing contract.
          2. If any invariant is not found or not PASS:
             - emit TaskStartGuardRejectedEvent via ctx.emit BEFORE returning (I-GRD-8)
             - return GuardResult(DENY)

          If required_ids is empty: always ALLOW (no preconditions — I-GRD-6).
          File reads only — no duckdb.connect (I-EL-9).
        """
        ...
```

#### §4.5.1 ValidationReport parsing contract (I-GRD-10)

`TaskStartGuard` locates reports by scanning `ctx.reports_dir` for files matching the glob
`ValidationReport_T-*.md`. For each required `invariant_id`:

**Step 1 — find candidate files:**

Candidate file = any `ValidationReport_T-NNN.md` that contains a line matching:

```
produces_invariants:  I-XXX, I-YYY, ...
```

Pattern (case-sensitive, leading whitespace ignored):

```
^\s*produces_invariants:\s+.*\bINVARIANT_ID\b
```

where `INVARIANT_ID` is the exact string (e.g. `I-GRD-1`).

**Step 2 — check result status:**

In the same candidate file, look for a line matching:

```
^\s*\*\*Result:\*\*\s+PASS\s*$
```

OR the plain form:

```
^\s*Result:\s+PASS\s*$
```

**Step 3 — decision:**

- If at least one candidate file satisfies both Step 1 and Step 2 for `invariant_id` → invariant is PASS, continue to next `required_id`.
- Otherwise → `invariant_id` is not satisfied → DENY.

**I-GRD-10:** `TaskStartGuard` MUST use this exact line-pattern contract, not ad-hoc parsing.
Tests MUST provide fixture ValidationReport files in the canonical format and verify correct
detection of both PASS and FAIL states.

### 4.6 NormGuard (`guards/norm.py`)

```python
class NormGuard:
    """Machine-readable norm enforcement backed by NormCatalog (D-9).
    Policy guard: DENY → emit NormViolatedEvent, return DENY; no raise (§2.1).
    Catalog is taken from ctx — guard does not load YAML itself (I-EL-9).
    """

    @staticmethod
    def check(
        ctx: GuardContext,
        actor: str,            # "llm" | "human"
        action: str,           # e.g. "implement_task", "emit_phase_completed"
        task_id: str | None,
    ) -> GuardResult:
        """Query ctx.catalog.is_allowed(actor, action).
          ALLOW if True.
          DENY: emit NormViolatedEvent via ctx.emit BEFORE returning (I-GRD-7, I-GRD-8).
          No direct DB calls (I-EL-9).
        """
        ...
```

### 4.7 run_guard_pipeline (`guards/runner.py`)

```python
def run_guard_pipeline(
    guards: list[Callable[[], GuardResult]],
    stop_on_deny: bool = True,
) -> list[GuardResult]:
    """Run a list of zero-argument guard callables (partial-applied checks) in order.

    stop_on_deny=True (default): stop at first DENY, return [that result].
    stop_on_deny=False: run all guards regardless, return all results in order.

    Pure orchestration — each guard callable already has its arguments bound.
    Does not inspect or interpret guard logic (I-GRD-4).
    Returns [] if guards list is empty.
    """
    ...
```

### 4.8 NormEntry + NormCatalog + load_catalog (`domain/norms/catalog.py`)

```python
@dataclass(frozen=True)
class NormEntry:
    norm_id:     str   # e.g. "NORM-ACTOR-001"
    actor:       str   # "llm" | "human" | "any"
    action:      str   # action identifier string
    result:      str   # "allowed" | "forbidden"
    description: str   # human-readable rule description
    severity:    str   # "hard" | "soft" | "informational"


@dataclass(frozen=True)
class NormCatalog:
    entries: tuple[NormEntry, ...]  # immutable after load
    strict:  bool = False           # security mode flag — see I-NRM-3

    def is_allowed(self, actor: str, action: str) -> bool:
        """Return False if any matching entry has result="forbidden".
        Matching: (entry.actor == actor OR entry.actor == "any") AND entry.action == action.

        Unknown action (no entry matches actor+action):
          strict=False (default): return True  — open-by-default, explicit deny only (I-NRM-2)
          strict=True:            return False — closed-by-default, explicit allow only (I-NRM-3)

        Security note (I-NRM-3): strict=False is the default for backwards compatibility and
        development convenience. Production guard enforcement for safety-critical actions
        (e.g. emit_phase_completed, approve_spec) SHOULD use strict=True to avoid
        silent permission grants for actions missing from the catalog.
        """
        ...

    def get_norm(self, norm_id: str) -> NormEntry | None:
        """Look up entry by norm_id. Returns None if not found."""
        ...


def load_catalog(path: str, strict: bool = False) -> NormCatalog:
    """Parse .sdd/norms/norm_catalog.yaml → NormCatalog(strict=strict).
    Raises MissingContext if file absent.
    Deterministic: same file + same strict flag → structurally equal NormCatalog (I-NRM-1).
    """
    ...
```

### 4.9 Task extension (`domain/tasks/parser.py`)

Two new fields added to the existing `Task` frozen dataclass (default to empty/None — backwards-compatible with TaskSet files that omit them):

```python
@dataclass(frozen=True)
class Task:
    # --- existing fields (Phase 2) ---
    task_id:              str
    title:                str
    status:               str
    spec_section:         str
    inputs:               tuple[str, ...]
    outputs:              tuple[str, ...]
    checks:               tuple[str, ...]
    spec_refs:            tuple[str, ...]
    produces_invariants:  tuple[str, ...]
    requires_invariants:  tuple[str, ...]
    # --- new fields (Phase 3) ---
    depends_on:           tuple[str, ...]  # task_ids; default ()
    parallel_group:       str | None       # group name; default None
```

`parse_taskset` updated to populate `depends_on` and `parallel_group` from TaskSet markdown
(optional fields; absent → defaults). Existing tests continue to pass (no existing fixture
has these fields → they default to empty values, I-TS-1 updated).

### 4.10 TaskNode + Scheduler (`domain/tasks/scheduler.py`)

```python
@dataclass(frozen=True)
class TaskNode:
    task_id:        str
    depends_on:     tuple[str, ...]   # task_ids this task must wait for
    parallel_group: str | None        # tasks with same group → same execution layer


class CyclicDependency(SDDError):
    """Raised by build_dag / topological_order when depends_on graph has a cycle."""


class ParallelGroupConflict(SDDError):
    """Raised by topological_order when tasks in the same parallel_group have a
    depends_on ordering between them (A and B in group "g" but A depends_on B).
    This is a TaskSet authoring error — parallel_group and depends_on are contradictory.
    Not a CyclicDependency: the DAG itself may be acyclic, but the co-location
    constraint cannot be satisfied.
    """


def build_dag(tasks: list[Task]) -> dict[str, TaskNode]:
    """Build dependency graph from task list.

    Raises CyclicDependency if depends_on references form a cycle (I-SCH-4).
    Raises MissingContext if depends_on references an unknown task_id (I-SCH-4).
    Pure function: no I/O, no randomness (I-SCH-3).
    tasks=[] → returns {}.
    """
    ...


def topological_order(dag: dict[str, TaskNode]) -> list[list[str]]:
    """Return execution layers for the dependency graph.

    Algorithm:
      - Layer 0: tasks with no depends_on (or all depends satisfied)
      - Layer N: tasks whose depends_on are all in layers 0..N-1
      - Tasks in same parallel_group are co-located in the earliest layer
        that satisfies all their depends_on constraints
      - If two tasks share a parallel_group but one depends_on the other:
        raises ParallelGroupConflict (I-SCH-5, I-SCH-6) — authoring error

    Guarantees:
      I-SCH-1: result contains no dependency-order violations (verified by post-check)
      I-SCH-2: every task_id appears exactly once across all layers
      I-SCH-5: same parallel_group → same layer (or ParallelGroupConflict if impossible)
      I-SCH-6: parallel_group constraint is never silently ignored

    Raises CyclicDependency if depends_on cycle detected (I-SCH-1).
    Raises ParallelGroupConflict if parallel_group + depends_on conflict (I-SCH-6).
    Pure function (I-SCH-3).
    dag={} → returns [].
    """
    ...
```

---

## 5. Invariants

### New Invariants (Phase 3)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-GRD-1 | `ScopeGuard.check_read(path)` and `check_write(path)` are pure functions of `path` and `config`: no I/O, no randomness, same inputs → same `GuardResult` | `tests/unit/guards/test_scope.py` |
| I-GRD-2 | `ScopeGuard.check_write` ALWAYS returns `DENY` for any path matching `.sdd/specs/**` (NORM-SCOPE-004, I-SDD-9) | `tests/unit/guards/test_scope.py` |
| I-GRD-3 | `PhaseGuard.check()` returns `DENY` and emits `SDDEventRejected` when any of PG-1, PG-2, or PG-3 fails; does NOT raise an exception | `tests/unit/guards/test_phase.py` |
| I-GRD-4 | `run_guard_pipeline()` is a pure orchestrator: it calls the provided callables in order and collects results; it does not inspect or interpret guard logic | `tests/unit/guards/test_runner.py` |
| I-GRD-5 | `TaskGuard.check()` raises `InvalidState` when `task.status == "DONE"`; raises `MissingContext` when task_id not found; both count as `DENY` | `tests/unit/guards/test_task.py` |
| I-GRD-6 | `TaskStartGuard.check_requires_invariants()` returns `ALLOW` when `required_ids` is empty; returns `DENY` and emits `TaskStartGuardRejectedEvent` when any required invariant lacks a PASS ValidationReport | `tests/unit/guards/test_task_start.py` |
| I-GRD-7 | `NormGuard.check()` returns `DENY` and emits `NormViolatedEvent` when `ctx.catalog.is_allowed(actor, action) == False`; all guard modules make NO direct `duckdb.connect` calls (I-EL-9) | `tests/unit/guards/test_norm.py` |
| I-GRD-8 | In all policy guards (PhaseGuard, TaskStartGuard, NormGuard), `ctx.emit(event)` is called exactly once BEFORE `return GuardResult(DENY)`. If `ctx.emit` raises, the exception propagates — the guard does NOT suppress it | `tests/unit/guards/test_phase.py`, `test_task_start.py`, `test_norm.py` |
| I-GRD-9 | Integrity guards (ScopeGuard, TaskGuard) raise an `SDDError` subclass on DENY and do NOT emit events. Policy guards (PhaseGuard, TaskStartGuard, NormGuard) emit an L1 event and return `GuardResult(DENY)` without raising. No guard both raises AND emits for the same check | `tests/unit/guards/test_scope.py`, `test_task.py`, `test_phase.py`, `test_task_start.py`, `test_norm.py` |
| I-GRD-10 | `TaskStartGuard` locates ValidationReports using the exact line-pattern contract in §4.5.1: `produces_invariants:` line + `Result: PASS` line. No ad-hoc parsing; tests use canonical fixture files | `tests/unit/guards/test_task_start.py` |
| I-NRM-1 | `load_catalog(path, strict)` is deterministic: same file + same `strict` flag → structurally equal `NormCatalog`; raises `MissingContext` if file absent | `tests/unit/domain/norms/test_catalog.py` |
| I-NRM-2 | `NormCatalog.is_allowed(actor, action)` with `strict=False` (default): returns `True` for unknown actions — open-by-default, explicit deny only | `tests/unit/domain/norms/test_catalog.py` |
| I-NRM-3 | `NormCatalog.is_allowed(actor, action)` with `strict=True`: returns `False` for unknown actions — closed-by-default. The `strict` flag is immutable after construction (frozen dataclass). Production enforcement of safety-critical actions SHOULD use `strict=True` | `tests/unit/domain/norms/test_catalog.py` |
| I-SCH-1 | `topological_order(dag)` output contains no dependency-order violations: each task's `depends_on` are fully covered by earlier layers (verified by post-check in the function itself) | `tests/unit/domain/tasks/test_scheduler.py` |
| I-SCH-2 | Every `task_id` in `dag` appears exactly once across all layers returned by `topological_order(dag)` | `tests/unit/domain/tasks/test_scheduler.py` |
| I-SCH-3 | `build_dag()` and `topological_order()` are pure functions: no I/O, no randomness, same inputs → same outputs | `tests/unit/domain/tasks/test_scheduler.py` |
| I-SCH-4 | `build_dag()` raises `CyclicDependency` when `depends_on` graph contains a cycle; raises `MissingContext` when `depends_on` references an unknown `task_id` | `tests/unit/domain/tasks/test_scheduler.py` |
| I-SCH-5 | Tasks with the same `parallel_group` value are always placed in the same layer by `topological_order`; if their `depends_on` constraints make co-location impossible, raises `ParallelGroupConflict` (NOT `CyclicDependency`) | `tests/unit/domain/tasks/test_scheduler.py` |
| I-SCH-6 | `parallel_group` constraint is NEVER silently ignored by `topological_order`: a conflict between parallel_group co-location and depends_on ordering MUST always raise `ParallelGroupConflict` | `tests/unit/domain/tasks/test_scheduler.py` |

### Preserved Invariants (referenced from Phase 1 & 2)

| ID | Statement |
|----|-----------|
| I-EL-9 | No direct `duckdb.connect` outside `infra/db.py` — guards use injected `emit` callable |
| I-TS-1 | `Task` has `requires_invariants` (+ new `depends_on`, `parallel_group`) fields; all default to empty when absent |
| I-TS-2 | `parse_taskset()` is deterministic; guards may call it multiple times safely |
| I-ST-3 | `read_state` / `write_state` roundtrip — `PhaseGuard` calls `read_state` to get `SDDState` |
| I-ST-10 | Every L1 event type classified: `NormViolated` + `TaskStartGuardRejected` added to `V1_L1_EVENT_TYPES` + `_KNOWN_NO_HANDLER` (C-1 compliance) |

### §PHASE-INV (must ALL be PASS before Phase 3 can be COMPLETE)

```
[I-GRD-1, I-GRD-2, I-GRD-3, I-GRD-4, I-GRD-5, I-GRD-6, I-GRD-7,
 I-GRD-8, I-GRD-9, I-GRD-10,
 I-NRM-1, I-NRM-2, I-NRM-3,
 I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6]
```

---

## 6. Pre/Post Conditions

### ScopeGuard.check_read(ctx, path) / check_write(ctx, path)

**Pre:**
- `ctx.config` loaded via `load_config`
- `path` is a string (need not exist on disk — guard checks config rules only)

**Post:**
- `check_read`: returns `ALLOW` if path not under any forbidden dir; raises `ScopeViolation` (integrity — I-GRD-9) if forbidden
- `check_write`: same PLUS always raises `ScopeViolation` for `.sdd/specs/**` (I-GRD-2)
- Does NOT call `ctx.emit` — integrity guards never emit (I-GRD-9)

### PhaseGuard.check(ctx, command)

**Pre:**
- `command` matches pattern `"Implement T-NNN"` or `"Validate T-NNN"`
- `ctx.state` is a valid `SDDState`; `ctx.emit` is not None

**Post:**
- `ALLOW`: PG-1, PG-2, PG-3 all hold
- `DENY`: calls `ctx.emit(SDDEventRejected(...))` THEN returns `GuardResult(DENY)`; does NOT raise (I-GRD-8, I-GRD-9)

### TaskGuard.check(ctx, task_id)

**Pre:**
- `task_id` is a string like `"T-301"`
- `ctx.taskset_path` points to a readable `TaskSet_vN.md`

**Post:**
- `ALLOW`: task found with `status == "TODO"`
- Raises `InvalidState`: task found with `status == "DONE"` (I-GRD-5, I-GRD-9)
- Raises `MissingContext`: task_id not found (I-GRD-5, I-GRD-9)
- Does NOT call `ctx.emit` (I-GRD-9)

### TaskStartGuard.check_requires_invariants(ctx, task_id, required_ids)

**Pre:**
- `task_id` non-empty string
- `required_ids` may be empty tuple
- `ctx.reports_dir` is a readable directory; `ctx.emit` is not None

**Post:**
- `required_ids == ()` → always returns `ALLOW` (I-GRD-6)
- All invariants found PASS per §4.5.1 → returns `ALLOW`
- Any invariant not found or not PASS → calls `ctx.emit(TaskStartGuardRejectedEvent(...))` THEN returns `GuardResult(DENY)` (I-GRD-8)
- No `duckdb.connect` calls (I-EL-9)

### NormGuard.check(ctx, actor, action, task_id)

**Pre:**
- `actor ∈ {"llm", "human"}`
- `action` non-empty string
- `ctx.catalog` loaded `NormCatalog`; `ctx.emit` is not None

**Post:**
- `ctx.catalog.is_allowed(actor, action) == True` → returns `ALLOW`
- `ctx.catalog.is_allowed(actor, action) == False` → calls `ctx.emit(NormViolatedEvent(...))` THEN returns `GuardResult(DENY)` (I-GRD-7, I-GRD-8)

### load_catalog(path)

**Pre:**
- `path` points to a YAML file following `norm_catalog.yaml` structure

**Post:**
- Returns `NormCatalog` with all entries loaded; same file → same result (I-NRM-1)
- Raises `MissingContext` if file absent

### build_dag(tasks)

**Pre:**
- `tasks: list[Task]`; may be empty

**Post:**
- `tasks == []` → returns `{}`
- Returns `dict[str, TaskNode]` mapping `task_id → TaskNode`
- Raises `CyclicDependency` if `depends_on` graph has a cycle (I-SCH-4)
- Raises `MissingContext` if any `depends_on` references a `task_id` absent from `tasks` (I-SCH-4)
- Pure: no I/O (I-SCH-3)

### topological_order(dag)

**Pre:**
- `dag` is output of `build_dag` (expected acyclic, but function re-verifies)
- May be empty dict

**Post:**
- `dag == {}` → returns `[]`
- Returns `list[list[str]]`; every `task_id` in `dag` appears exactly once (I-SCH-2)
- Each task's `depends_on` are in earlier layers (I-SCH-1)
- Tasks with same `parallel_group` in the same layer (I-SCH-5)
- Raises `CyclicDependency` if cycle detected during post-check (I-SCH-1)
- Pure: no I/O (I-SCH-3)

---

## 7. Use Cases

### UC-3-1: Guard pipeline for Implement T-NNN

**Actor:** §R.6 pre-execution protocol
**Trigger:** `Implement T-301` issued
**Pre:** Phase 3 ACTIVE, `TaskSet_v3.md` present, `State_index.yaml` present
**Steps:**
1. `ctx = GuardContext(state=read_state(state_path), config=cfg, taskset_path=..., reports_dir=..., emit=sdd_append_wrapper, catalog=load_catalog(norm_path))`
2. `PhaseGuard.check(ctx, "Implement T-301")` — PG-1..3
3. `TaskGuard.check(ctx, "T-301")` — task must be `TODO`
4. `task = [t for t in parse_taskset(ctx.taskset_path) if t.task_id == "T-301"][0]`
5. `TaskStartGuard.check_requires_invariants(ctx, "T-301", task.requires_invariants)`
6. For each file in `task.inputs`: `ScopeGuard.check_read(ctx, file)`
7. All guards return `ALLOW` → implementation begins
**Post:** Guard results available for audit; any `DENY` aborts the flow before any file is touched

### UC-3-2: NormGuard blocks LLM from emitting PhaseCompleted

**Actor:** NormGuard (called from Phase 4 command handler)
**Trigger:** LLM command handler attempts action `"emit_phase_completed"`
**Pre:** `norm_catalog.yaml` loaded; `NORM-ACTOR-003` entry forbids `llm` from emitting `PhaseCompleted`
**Steps:**
1. `NormGuard.check(ctx, "llm", "emit_phase_completed", task_id=None)`
2. `ctx.catalog.is_allowed("llm", "emit_phase_completed") == False`
3. Calls `ctx.emit(NormViolatedEvent(..., norm_id="NORM-ACTOR-003", ...))` — L1 event written first
4. Returns `GuardResult(DENY, norm_id="NORM-ACTOR-003", message="...")`
**Post:** LLM blocked; L1 audit event persisted forever; LLM MUST STOP (§0.8 SEM-5)

### UC-3-3: TaskStartGuard blocks T-303 pending T-302 validation

**Actor:** TaskStartGuard
**Trigger:** Attempt to implement T-303 which has `requires_invariants: ["I-GRD-1"]`
**Pre:** T-302 not yet validated; `ValidationReport_T-302.md` absent or status FAIL
**Steps:**
1. `TaskStartGuard.check_requires_invariants(ctx, "T-303", ("I-GRD-1",))`
2. Scans `ctx.reports_dir` per §4.5.1: looks for `ValidationReport_T-*.md` with `produces_invariants: ... I-GRD-1 ...` and `Result: PASS`
3. No PASS report found → calls `ctx.emit(TaskStartGuardRejectedEvent(task_id="T-303", missing_invariant="I-GRD-1", ...))` first
4. Returns `GuardResult(DENY, message="I-GRD-1 not PASS — no qualifying report found")`
**Post:** T-303 cannot proceed; human must validate T-302 first

### UC-3-5: ParallelGroupConflict caught at planning time

**Actor:** Planner agent / TaskSet author validation
**Trigger:** TaskSet declares tasks T-A and T-B in `parallel_group: "infra"`, but T-B has `depends_on: [T-A]`
**Pre:** `parse_taskset()` succeeds — no syntax error
**Steps:**
1. `dag = build_dag(tasks)` — builds graph; no cycle, so no `CyclicDependency`
2. `topological_order(dag)` — detects that T-A and T-B share `parallel_group="infra"` but T-B must be in a later layer than T-A due to `depends_on`
3. Raises `ParallelGroupConflict("T-B and T-A share group 'infra' but T-B depends_on T-A")`
**Post:** Author sees specific error distinguishing DAG cycle from co-location conflict; can fix by removing one task from the group or dropping the dependency

### UC-3-4: Compute parallel execution layers for TaskSet

**Actor:** Planner agent (decomposing a future phase)
**Trigger:** Decompose Phase N — identify which tasks can execute in parallel
**Pre:** `TaskSet_vN.md` parsed; `Task.depends_on` and `Task.parallel_group` populated
**Steps:**
1. `tasks = parse_taskset("...TaskSet_vN.md")`
2. `dag = build_dag(tasks)` — constructs `TaskNode` graph; raises on cycle or missing dep
3. `layers = topological_order(dag)` — returns execution layers
4. Tasks in same `parallel_group` guaranteed co-located
**Post:** Planner knows precise sequential dependencies and parallelisation opportunities

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-STATE (`domain/state/`) | BC-GUARDS → | `PhaseGuard` calls `read_state` to obtain authoritative `SDDState` |
| BC-TASKS (`domain/tasks/parser.py`) | BC-GUARDS → | `TaskGuard` + `TaskStartGuard` call `parse_taskset`; `Task.requires_invariants` used |
| BC-NORMS (`domain/norms/`) | BC-GUARDS → | `NormGuard` receives an injected `NormCatalog` |
| BC-INFRA (`infra/event_log.py`) | BC-GUARDS → | Events emitted via injected `emit` callable — no direct DB calls (I-EL-9) |
| BC-CORE (`core/errors.py`) | BC-GUARDS/SCHED → | `ScopeViolation`, `InvalidState`, `MissingContext`, `CyclicDependency` (new) |
| BC-CORE (`core/events.py`) | all → | `NormViolatedEvent`, `TaskStartGuardRejectedEvent`, `SDDEventRejected` |
| | BC-SCHEDULER → BC-TASKS | scheduler reads `Task.depends_on` + `Task.parallel_group` from `parse_taskset` |

### C-1 Compliance (blocking — must be in same task)

```python
# core/events.py — add to V1_L1_EVENT_TYPES
V1_L1_EVENT_TYPES: frozenset[str] = frozenset({
    # ... all existing types ...
    "NormViolated",              # Phase 3 — NormGuard rejection
    "TaskStartGuardRejected",    # Phase 3 — TaskStartGuard rejection
})

# domain/state/reducer.py — add to _KNOWN_NO_HANDLER
_KNOWN_NO_HANDLER: frozenset[str] = frozenset({
    # ... all existing entries ...
    "NormViolated",
    "TaskStartGuardRejected",
})
```

Task modifying `core/events.py` MUST also modify `reducer.py` in the same commit/task.
Splitting triggers the import-time assert → `AssertionError` on any import.

### Integration with Phase 4 (Commands)

Phase 4 command handlers will construct a `GuardContext` and call `run_guard_pipeline([...])` as
their pre-execution check. The `GuardContext` + guard interface defined here MUST remain stable
(CEP-7). Phase 4 binds guard callables with `functools.partial` or lambdas over a shared `ctx`;
`run_guard_pipeline` runs them in order without knowing which guard produced each result.

### Integration with §R.6 Protocol

The Python modules implemented here back the §R.6 pre-execution steps:

```
§R.6 step 1 (phase_guard.py tool) → PhaseGuard.check()                (I-GRD-3)
§R.6 step 2 (task_guard.py tool)  → TaskGuard.check()                 (I-GRD-5)
§R.6 step 3 (task_start.py tool)  → TaskStartGuard.check_requires...  (I-GRD-6, D-4)
§R.6 step 4 (check_scope.py tool) → ScopeGuard.check_read()           (I-GRD-1)
§R.6 step 5 (norm_guard.py tool)  → NormGuard.check()                 (I-GRD-7)
```

Until Phase 8 (thin adapters), `.sdd/tools/*.py` governance scripts remain independent.
Phase 3 builds the `src/sdd/guards/` Python package that Phase 8 will wire in.

---

## 9. Verification

| # | Test File | Tests | Invariant(s) |
|---|-----------|-------|--------------|
| 1 | `tests/unit/guards/test_scope.py` | `test_scope_allows_valid_path`, `test_scope_denies_forbidden_dir`, `test_scope_write_always_denies_specs_dir`, `test_scope_is_pure_function`, `test_scope_does_not_call_emit` | I-GRD-1, I-GRD-2, I-GRD-9 |
| 2 | `tests/unit/guards/test_phase.py` | `test_phase_guard_allows_active_phase`, `test_phase_guard_denies_wrong_phase_number`, `test_phase_guard_denies_inactive_plan`, `test_phase_guard_emits_sdd_event_rejected`, `test_phase_guard_denies_version_mismatch`, `test_phase_guard_does_not_raise`, `test_phase_guard_emit_called_before_return`, `test_phase_guard_emit_failure_propagates` | I-GRD-3, I-GRD-8, I-GRD-9 |
| 3 | `tests/unit/guards/test_task.py` | `test_task_guard_allows_todo_task`, `test_task_guard_denies_done_task_raises_invalid_state`, `test_task_guard_raises_missing_context_unknown_id`, `test_task_guard_does_not_call_emit` | I-GRD-5, I-GRD-9 |
| 4 | `tests/unit/guards/test_task_start.py` | `test_task_start_allows_empty_requires`, `test_task_start_allows_all_pass`, `test_task_start_denies_missing_report`, `test_task_start_denies_fail_report`, `test_task_start_emits_rejected_event`, `test_task_start_emit_called_before_return`, `test_task_start_no_direct_db_calls`, `test_task_start_canonical_report_format_pass`, `test_task_start_canonical_report_format_fail` | I-GRD-6, I-GRD-8, I-GRD-10, I-EL-9 |
| 5 | `tests/unit/guards/test_norm.py` | `test_norm_allows_permitted_action`, `test_norm_denies_forbidden_action`, `test_norm_emits_norm_violated_event`, `test_norm_unknown_action_allows_non_strict`, `test_norm_unknown_action_denies_strict`, `test_norm_emit_called_before_return`, `test_norm_no_direct_db_calls` | I-GRD-7, I-GRD-8, I-GRD-9, I-NRM-2, I-NRM-3, I-EL-9 |
| 6 | `tests/unit/guards/test_runner.py` | `test_runner_stops_on_first_deny_default`, `test_runner_runs_all_when_stop_false`, `test_runner_returns_all_allow_results`, `test_runner_empty_guards_returns_empty`, `test_runner_is_pure_orchestrator` | I-GRD-4 |
| 7 | `tests/unit/domain/norms/test_catalog.py` | `test_load_catalog_deterministic`, `test_load_catalog_missing_raises`, `test_is_allowed_known_permitted`, `test_is_allowed_known_forbidden`, `test_is_allowed_unknown_action_non_strict`, `test_is_allowed_unknown_action_strict`, `test_get_norm_by_id`, `test_any_actor_applies_to_all`, `test_strict_flag_immutable` | I-NRM-1, I-NRM-2, I-NRM-3 |
| 8 | `tests/unit/domain/tasks/test_scheduler.py` | `test_build_dag_empty_returns_empty`, `test_build_dag_raises_cyclic_dependency`, `test_build_dag_raises_missing_context_unknown_dep`, `test_topological_order_empty_dag`, `test_topological_order_simple_chain`, `test_topological_order_parallel_group_colocated`, `test_topological_order_no_duplicates`, `test_topological_order_raises_on_cycle`, `test_topological_order_raises_parallel_group_conflict`, `test_parallel_group_conflict_not_cyclic_dependency`, `test_scheduler_pure_functions_deterministic` | I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6 |
| 9 | `tests/unit/domain/tasks/test_parser.py` (extend) | `test_parse_task_has_depends_on_field`, `test_parse_task_has_parallel_group_field`, `test_parse_missing_new_fields_default_empty` | I-TS-1 (extended) |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Command handlers (`complete`, `validate`, `sdd_run`) | Phase 4 |
| `error_event_boundary` decorator — I-ERR-1 | Phase 4 |
| Command idempotency by `command_id` — I-CMD-1b | Phase 4 |
| Wiring guard pipeline into command handlers | Phase 4 |
| `query_events.py` Python module | Phase 5 |
| `metrics_report.py` Python module | Phase 5 |
| CLI entry point (`cli.py`) | Phase 6 |
| `log_tool.py` / `log_bash.py` Python modules | Phase 6 |
| `build_context.py` CLI wiring | Phase 6 |
| `PhaseActivated` event — closing EventLog governance gap for `phase_status` | Phase 7 |
| v1↔v2 full replay compatibility test — I-EL-4 | Phase 7 |
| Parallel execution engine (scheduler produces order; execution not in scope) | Phase 7 |
| Task retry / escalation policy | Phase 7 |
| Thin adapter migration of `.sdd/tools/` to `src/sdd/` | Phase 8 |
| Multi-process / concurrent writers | Out of scope until explicitly specced |
