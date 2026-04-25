# Spec_v4_Commands — Phase 4: Commands Layer

Status: Draft
Baseline: Spec_v3_Guards.md (BC-GUARDS, BC-NORMS, BC-SCHEDULER, BC-INFRA, BC-CORE, BC-STATE, BC-TASKS)
Reference implementation: sdd_v1/.sdd/tools/update_state.py, validate_invariants.py, validate_config.py, report_error.py

---

## 0. Goal

Implement the full governance command layer as typed Python handlers in `src/sdd/commands/`.
After this phase:

- Every governance operation (complete task, validate task, sync state, check DoD, validate
  invariants, validate config, report error, record decision) is a typed `CommandHandler`
  implementation satisfying the `CommandHandler` Protocol from `core/types.py` (D-5)
- The `error_event_boundary` decorator enforces I-ERR-1: any exception inside `handle()` emits
  an `ErrorEvent` (with `retry_count` tracked per `command_id`) before re-raising (D-7, D-17)
- `handle()` is idempotent by `command_id`: duplicate submissions return `[]` without side
  effects (D-16, I-CMD-1)
- `CommandRunner` in `sdd_run.py` wires the Phase 3 guard pipeline into every command dispatch:
  a guard `DENY` prevents the handler from running and no events are emitted (D-5)
- New event dataclasses are defined for governance domain events (`TaskImplementedEvent`,
  `TaskValidatedEvent`, `PhaseCompletedEvent`, `DecisionRecordedEvent`) with full C-1 compliance
- `infra/event_log.py` gains `exists_command(command_id)` and `get_error_count(command_id)`
  to support idempotency and retry tracking

This phase produces no CLI entry points (Phase 6) and no query/metrics commands (Phase 5).

**SSOT model (applies to all Phase 4 handlers):**

- `EventLog` is the single source of truth — `EventStore.append(events)` is the ONLY write path
- Handlers emit events ONLY; they do NOT write files or mutate state directly
- `TaskSet.md` and `State_index.yaml` are projections derived from the EventLog
- Write order invariant: events are appended atomically FIRST; projections are rebuilt AFTER
- Guards are pure functions — they return `(GuardResult, audit_events)` without side effects;
  `CommandRunner` appends `audit_events` when a guard returns `DENY`
- `EventStore` is the unified emit interface — `sdd_append` / `sdd_append_batch` route through it
- Semantic idempotency key `(command_type, task_id, phase_id)` supplements `command_id`
- Norm default is `DENY`; every allowed action requires explicit `ALLOW` entry in norm catalog
- Dependency guard enforces task DAG: all declared dependencies must be `DONE` before `ALLOW`

---

## 1. Scope

### In-Scope

- BC-COMMANDS: `src/sdd/commands/` — eight command handler modules + runner + public interface
- BC-CORE extension: `core/events.py` — new event dataclasses + C-1 compliance
- BC-CORE extension: `core/errors.py` — `DoDNotMet` error type
- BC-INFRA extension: `infra/event_log.py` — `exists_command`, `get_error_count`
- BC-STATE extension: `domain/state/reducer.py` — handlers for `TaskImplemented`, `TaskValidated`
  (if not already in `_EVENT_SCHEMA` from Phase 2)
- 80%+ test coverage for all new and modified modules
- Invariants I-ES-1..5, I-CMD-1..13, I-ERR-1

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### §2.0 Canonical Data Flow

```
Command
  ↓
CommandRunner.run()
  ↓
run_guard_pipeline(ctx)          ← pure function: (GuardContext) → (result, audit_events)
  ↓  DENY → EventStore.append(audit_events) → return []
  ↓  ALLOW
handler.handle(command)          ← pure emitter: returns list[DomainEvent], NO store access
  ↓
EventStore.append(events)        ← ONLY place events are written to EventLog
  ↓
projections.rebuild_*(...)       ← eventually consistent file views
```

**Invariants of this flow:**
- Guards: pure in, pure out — no I/O, no mutations
- Handlers: compute events, return them — no I/O to EventLog
- EventStore: single atomic write point
- Projections: rebuilt AFTER append; eventually consistent, not transactional with append
- `error_event_boundary`: sole exception — appends `ErrorEvent` via `sdd_append(self._db_path, ...)`
  on exception before re-raising (cannot return a list when propagating an exception).
  **MUST reuse the same low-level `sdd_append` function used by `EventStore.append()` internally**
  — same transaction semantics, same schema validation, same audit trail.
  This is the ONLY permitted second write path; no further "special" write paths are allowed after this.

### BC-COMMANDS: `src/sdd/commands/`

```
src/sdd/commands/
  __init__.py           ← re-exports: all Command dataclasses, all Handler classes,
                          CommandRunner, error_event_boundary
  _base.py              ← error_event_boundary decorator, retry_count lookup (I-ERR-1),
                          CommandHandlerBase (idempotency + EventStore injection)
  update_state.py       ← CompleteTaskHandler, ValidateTaskHandler,
                          SyncStateHandler, CheckDoDHandler
  validate_invariants.py ← ValidateInvariantsHandler (I-CMD-6)
  validate_config.py    ← ValidateConfigHandler
  report_error.py       ← ReportErrorHandler (emits ErrorEvent, I-ERR-1 complement)
  record_decision.py    ← RecordDecisionHandler (emits DecisionRecordedEvent)
  sdd_run.py            ← CommandRunner: pure guard pipeline + EventStore dispatch (I-CMD-7)
                          Guards return (GuardResult, audit_events); CommandRunner appends
                          audit_events on DENY; handler is NOT called on DENY (I-ES-3)
```

### BC-CORE extensions (`src/sdd/core/`)

```
core/events.py   ← add: TaskImplementedEvent, TaskValidatedEvent,
                         PhaseCompletedEvent, DecisionRecordedEvent dataclasses
                         + V1_L1_EVENT_TYPES and _EVENT_SCHEMA / _KNOWN_NO_HANDLER
                           entries (C-1 compliance — same task as reducer.py changes)
core/errors.py   ← add: DoDNotMet(SDDError)
```

### BC-INFRA extensions (`src/sdd/infra/`)

```
infra/event_store.py ← NEW: EventStore — single write path for all domain events
                           EventStore.append(events: list[DomainEvent], source: str) → atomic
                           Routes internally to sdd_append_batch; ONLY CommandRunner calls this
infra/event_log.py  ← add: exists_command(command_id: str) -> bool
                           get_error_count(command_id: str) -> int
                           exists_semantic(command_type: str, task_id: str, phase_id: int) -> bool
infra/projections.py ← NEW: rebuild_taskset(db_path, taskset_path) → writes TaskSet.md from EventLog
                             rebuild_state(db_path, state_path) → writes State_index.yaml from EventLog
```

### BC-STATE extensions (`src/sdd/domain/state/`)

```
domain/state/reducer.py  ← add _EVENT_SCHEMA handlers for "TaskImplemented"
                            and "TaskValidated" if not already present from Phase 2.
                            Must be in same task as core/events.py changes (C-1).
```

### Dependencies

```text
BC-COMMANDS → BC-GUARDS     : CommandRunner calls run_guard_pipeline; guards return
                               (GuardResult, list[DomainEvent]) — pure, no side effects (I-ES-3)
BC-COMMANDS → BC-STATE      : SyncStateHandler + CheckDoDHandler call read_state (read-only);
                               state writes happen ONLY via projections.rebuild_state (I-ES-4)
BC-COMMANDS → BC-TASKS      : CompleteTaskHandler reads parse_taskset for validation only;
                               TaskSet writes happen ONLY via projections.rebuild_taskset (I-ES-4)
BC-COMMANDS → BC-INFRA      : all handlers emit via EventStore.append (single write path, I-ES-1);
                               idempotency via exists_command + exists_semantic (I-CMD-10);
                               retry via get_error_count (I-EL-9)
BC-COMMANDS → BC-CORE       : handlers raise/emit SDDError subclasses and DomainEvent subclasses
BC-COMMANDS → BC-NORMS      : CommandRunner injects NormCatalog into GuardContext;
                               norm default = DENY (I-CMD-12)
BC-COMMANDS → BC-CONTEXT    : CommandRunner may call build_context for STANDARD depth (optional; Phase 6 wires CLI)
```

### §2.1 Command Taxonomy

| Command class | Handler | Emitted events (L1 unless noted) | Idempotent? |
|---|---|---|---|
| `CompleteTaskCommand` | `CompleteTaskHandler` | `TaskImplementedEvent`, `MetricRecorded` (L2, batch) | Yes — by `command_id` + semantic key + payload_hash |
| `ValidateTaskCommand` | `ValidateTaskHandler` | `TaskValidatedEvent` | Yes |
| `SyncStateCommand` | `SyncStateHandler` | `StateSyncedEvent` (L2) | Yes |
| `CheckDoDCommand` | `CheckDoDHandler` | `PhaseCompletedEvent` | Yes |
| `ValidateInvariantsCommand` | `ValidateInvariantsHandler` | `TestRunCompletedEvent`, `MetricRecorded` (L2) | Yes |
| `ValidateConfigCommand` | `ValidateConfigHandler` | none (raises on failure) | Yes |
| `ReportErrorCommand` | `ReportErrorHandler` | `ErrorEvent` | Yes |
| `RecordDecisionCommand` | `RecordDecisionHandler` | `DecisionRecordedEvent` | Yes |

---

## 3. Domain Events

All event dataclasses MUST be frozen, with hashable fields only. No `list` or `dict` fields —
use `tuple` or `str`.

### New Event Dataclasses (Phase 4)

#### TaskImplementedEvent

Emitted by `CompleteTaskHandler` when a task transitions TODO → DONE.

```python
@dataclass(frozen=True)
class TaskImplementedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskImplemented"
    task_id:    str     # e.g. "T-401"
    phase_id:   int     # current phase number
    timestamp:  str     # ISO8601 UTC
```

#### TaskValidatedEvent

Emitted by `ValidateTaskHandler` after a validation run, recording the result.

```python
@dataclass(frozen=True)
class TaskValidatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskValidated"
    task_id:     str    # e.g. "T-401"
    phase_id:    int
    result:      str    # "PASS" | "FAIL"
    timestamp:   str    # ISO8601 UTC
```

#### PhaseCompletedEvent

Emitted by `CheckDoDHandler` when ALL tasks DONE + invariants PASS + tests PASS.
L1 terminal event — never triggers further reducer state changes.

```python
@dataclass(frozen=True)
class PhaseCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseCompleted"
    phase_id:      int
    total_tasks:   int
    timestamp:     str   # ISO8601 UTC
```

#### DecisionRecordedEvent

NEW event type (not in v1). Emitted by `RecordDecisionHandler` to persist design decisions
in the EventLog for audit and replay.

```python
@dataclass(frozen=True)
class DecisionRecordedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "DecisionRecorded"
    decision_id:  str   # e.g. "D-16" — must match a D-* entry in sdd_plan.md
    title:        str
    summary:      str   # ≤ 500 chars
    phase_id:     int
    timestamp:    str   # ISO8601 UTC
```

**Usage constraints (scope guard):**
- `decision_id` MUST match a declared D-* identifier from the plan; free-form IDs are rejected
- This event records **architectural decisions** only — it is NOT a general-purpose audit log
- Frequency limit: at most one `DecisionRecorded` per D-* id per phase (idempotency by decision_id + phase_id)
- Emitter: LLM planner during planning phase; NOT emitted from implementation handlers
- Motivation: prevents EventLog from being polluted with human-readable notes masquerading as domain events

### C-1 Classification (Phase 4 — BLOCKING)

`DecisionRecordedEvent` is a NEW L1 event type not present in `V1_L1_EVENT_TYPES`. Per C-1
(§2.4 of Spec_v3), modifying `V1_L1_EVENT_TYPES`, `_KNOWN_NO_HANDLER`, and adding
the dataclass MUST happen in a single task. Violation → `AssertionError` on import.

`TaskImplementedEvent`, `TaskValidatedEvent`, `PhaseCompletedEvent` use event_type strings
that already exist in `V1_L1_EVENT_TYPES` from Phase 1 (they are v1 governance events).
Phase 4 adds their frozen dataclass definitions and, if missing from `_EVENT_SCHEMA` in
Phase 2's reducer, adds the reducer handlers in the SAME task (C-1).

**Reducer classification for Phase 4 events:**

| Event type string | `_EVENT_SCHEMA` handler needed? | Rationale |
|---|---|---|
| `"TaskImplemented"` | YES — increments `tasks.completed`, adds to `tasks.done_ids` | State must be reconstructable from events (I-ST-9) |
| `"TaskValidated"` | YES — sets `invariants.status` or `tests.status` based on `result` | State reconstruction |
| `"PhaseCompleted"` | NO — add to `_KNOWN_NO_HANDLER` | Terminal event; no further state transitions in SDDState |
| `"DecisionRecorded"` | NO — add to `_KNOWN_NO_HANDLER` | Audit-only; does not affect SDDState |

### Event Catalog (Phase 4)

| Event | Emitter | Level | Description |
|---|---|---|---|
| `TaskImplemented` | `CompleteTaskHandler` | L1 Domain | Task transitions TODO → DONE |
| `TaskValidated` | `ValidateTaskHandler` | L1 Domain | Validation result recorded for a task |
| `PhaseCompleted` | `CheckDoDHandler` | L1 Domain | All DoD conditions met; phase closed |
| `DecisionRecorded` | `RecordDecisionHandler` | L1 Domain | Design decision persisted in EventLog |
| `StateSynced` | `SyncStateHandler` | L2 Operational | State_index.yaml rebuilt from TaskSet |
| `TestRunCompleted` | `ValidateInvariantsHandler` | L1 Domain | Build-command subprocess run completed |
| `MetricRecorded` | `CompleteTaskHandler`, `ValidateInvariantsHandler` | L2 Operational | task.lead_time / quality.* recorded |
| `ErrorOccurred` | `error_event_boundary` | L1 Domain | Exception in handle() captured as event |

**Note:** `ErrorOccurred` uses the `ErrorEvent` dataclass defined in Phase 1 (T-103). Its
`EVENT_TYPE` string must match the v1 name exactly (I-EL-6). Verify against `core/events.py`
before implementation.

---

## 4. Types & Interfaces

### 4.0 Command Base + Command dataclasses (`core/types.py` — already defined Phase 1)

The `CommandHandler` Protocol and `Command` base are already in `core/types.py` (T-104).
Phase 4 implements concrete handlers; it does NOT modify the Protocol.

```python
# Already defined in Phase 1 — shown for reference
class CommandHandler(Protocol):
    def handle(self, command: "Command") -> list["DomainEvent"]: ...

@dataclass(frozen=True)
class Command:
    command_id: str   # globally unique — used for idempotency
```

Each Phase 4 command is a frozen dataclass extending `Command`:

```python
@dataclass(frozen=True)
class CompleteTaskCommand(Command):
    task_id:      str   # e.g. "T-401"
    phase_id:     int
    taskset_path: str   # exact path to TaskSet_vN.md
    state_path:   str   # exact path to State_index.yaml

@dataclass(frozen=True)
class ValidateTaskCommand(Command):
    task_id:      str
    phase_id:     int
    result:       str   # "PASS" | "FAIL"
    state_path:   str

@dataclass(frozen=True)
class SyncStateCommand(Command):
    phase_id:     int
    taskset_path: str
    state_path:   str

@dataclass(frozen=True)
class CheckDoDCommand(Command):
    phase_id:     int
    state_path:   str

@dataclass(frozen=True)
class ValidateInvariantsCommand(Command):
    phase_id:       int
    task_id:        str | None       # None = phase-level check
    config_path:    str
    cwd:            str              # explicit working directory; never derived from os.getcwd()
    env_whitelist:  tuple[str, ...]  # env var names to pass to subprocess; empty = empty env
    timeout_secs:   int              # subprocess timeout; 0 = use config default

@dataclass(frozen=True)
class ValidateConfigCommand(Command):
    phase_id:     int
    config_path:  str

@dataclass(frozen=True)
class ReportErrorCommand(Command):
    error_type:   str
    message:      str
    source:       str
    recoverable:  bool

@dataclass(frozen=True)
class RecordDecisionCommand(Command):
    decision_id:  str
    title:        str
    summary:      str
    phase_id:     int
```

### 4.1 `error_event_boundary` decorator (`commands/_base.py`)

```python
def error_event_boundary(source: str) -> Callable:
    """Decorator factory for CommandHandler.handle() methods.

    On any exception raised by the decorated method:
      1. Query get_error_count(command.command_id) to determine retry_count
      2. Emit ErrorEvent(
             error_type = type(exc).__name__,
             source     = source,   # module name passed to factory
             recoverable = isinstance(exc, RecoverableError),
             retry_count = prior_error_count,
             context    = {"message": str(exc)},
         ) via sdd_append(self._db_path, ErrorEvent(...))
         — MUST call the same low-level sdd_append used by EventStore.append() internally;
         NOT via a higher-level EventStore wrapper (those require a return path impossible during
         exception propagation). This is the only place handlers write to the EventLog directly.
         (I-ERR-1; see §2.0 write-path note)
      3. Re-raise the original exception — NEVER suppress it (I-CMD-3)

    If emit itself raises: log to fallback_log (stderr / structlog) to preserve
    the original exception context, then re-raise the ORIGINAL exception — never
    lose the root cause (I-CMD-3, fix #11).
    Idempotency check (I-CMD-1) runs BEFORE this decorator's try/except —
    idempotent returns skip error_event_boundary entirely.

    Usage:
        class MyHandler:
            @error_event_boundary(source=__name__)
            def handle(self, command: Command) -> list[DomainEvent]: ...
    """
```

### 4.2 `CommandHandlerBase` (`commands/_base.py`)

Base class providing idempotency check. Concrete handlers inherit from it.
Handlers do NOT hold a reference to `EventStore` — they are pure emitters (§2.0).

```python
class CommandHandlerBase:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path  # used ONLY by error_event_boundary for ErrorEvent emission

    def _check_idempotent(self, command: Command) -> bool:
        """Return True if this command was already processed (I-CMD-1, I-CMD-2b).

        Two-level check (both must be False to proceed):
          1. Structural:  exists_command(self._db_path, command.command_id)
                          — exact replay guard
          2. Semantic:    exists_semantic(self._db_path,
                              type(command).__name__,
                              getattr(command, "task_id", None),
                              getattr(command, "phase_id", None),
                              command_payload_hash(command))
                          — prevents duplicate effects with a new command_id (I-CMD-2b)
                          — payload_hash guards against false positives on retry with changed fields
        """
        ...
```

**Design rule:** `handle()` returns `list[DomainEvent]` — it NEVER calls `EventStore.append()`.
`CommandRunner` receives the list and calls `EventStore.append(events)` after handler returns.
The sole exception is `error_event_boundary`: it uses `self._db_path` to write exactly one
`ErrorEvent` before re-raising, because list return is impossible during exception propagation.

All eight handlers inherit `CommandHandlerBase`. Each `handle()` starts with:
```python
if self._check_idempotent(command):
    return []
```

### 4.3 `CompleteTaskHandler` (`commands/update_state.py`)

```python
class CompleteTaskHandler(CommandHandlerBase):
    """Mark a task DONE in TaskSet_vN.md, sync State_index.yaml,
    emit TaskImplementedEvent + MetricRecorded(task.lead_time) via sdd_append_batch.

    Idempotency: returns [] if command_id already in EventLog (I-CMD-1).
    Error boundary: @error_event_boundary(source=__name__) (I-ERR-1).
    Batch write: TaskImplementedEvent + MetricRecorded written atomically (I-CMD-4, I-EL-11).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: CompleteTaskCommand) -> list[DomainEvent]:
        """
        Emit-first protocol (I-ES-1, I-ES-2):
          1. _check_idempotent → return [] if already done (I-CMD-1, I-CMD-2b)
          2. parse_taskset(command.taskset_path) — find task_id (validation only; TaskSet is projection)
          3. Raise MissingContext if task not found
          4. Raise InvalidState if task.status == "DONE"
          5. Compute lead_time from task timestamps
          6. Build TaskImplementedEvent + MetricRecorded(task.lead_time)
          7. EventStore.append([TaskImplementedEvent, MetricRecorded], source=__name__)  ← atomic (I-ES-1, I-CMD-4)
          8. projections.rebuild_taskset(db_path, command.taskset_path)  ← projection rebuilt AFTER event (I-ES-4)
          9. Return [TaskImplementedEvent, MetricRecorded]

        NOTE: TaskSet.md is NEVER written before the event is appended (I-ES-1 write-order rule).
        """
        ...
```

### 4.4 `ValidateTaskHandler` (`commands/update_state.py`)

```python
class ValidateTaskHandler(CommandHandlerBase):
    """Record validation result (PASS|FAIL) in State_index.yaml.
    Emits TaskValidatedEvent + MetricRecorded(task.validation_attempts).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ValidateTaskCommand) -> list[DomainEvent]:
        """
        Emit-first protocol (I-ES-1, I-ES-2):
          1. _check_idempotent → return [] if already done
          2. read_state(command.state_path) — read-only; state is projection
          3. Build TaskValidatedEvent + MetricRecorded(task.validation_attempts)
          4. EventStore.append([TaskValidatedEvent, MetricRecorded], source=__name__)  ← atomic (I-ES-1)
          5. projections.rebuild_state(db_path, command.state_path)  ← State_index.yaml rebuilt AFTER event (I-ES-4)
          6. Return [TaskValidatedEvent, MetricRecorded]

        NOTE: State_index.yaml is NEVER written before the event is appended.
        Invariants.status / tests.status are derived by the reducer from the appended event.
        """
        ...
```

### 4.5 `SyncStateHandler` (`commands/update_state.py`)

```python
class SyncStateHandler(CommandHandlerBase):
    """Rebuild State_index.yaml from TaskSet_vN.md (SSOT).
    Emits StateSyncedEvent (L2). Uses atomic_write (I-CMD-8, I-PK-5).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: SyncStateCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. Build StateSyncedEvent (L2)
          3. EventStore.append([StateSyncedEvent], source=__name__)  ← atomic (I-ES-1)
          4. projections.rebuild_state(db_path, command.state_path)  ← rebuild from EventLog (I-ES-4)
          5. Return [StateSyncedEvent]
        """
        ...
```

### 4.6 `CheckDoDHandler` (`commands/update_state.py`)

```python
class CheckDoDHandler(CommandHandlerBase):
    """Check Definition of Done: ALL tasks DONE + invariants PASS + tests PASS.
    Emits PhaseCompletedEvent + MetricRecorded(phase.completion_time) via batch.
    Raises DoDNotMet if any condition fails (I-CMD-5).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: CheckDoDCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. read_state(command.state_path)  ← projection; read-only
          3. Check: tasks.completed == tasks.total (I-CMD-5)
          4. Check: invariants.status == "PASS"
          5. Check: tests.status == "PASS"
          6. Any check fails → raise DoDNotMet(message="<which condition failed>")
          7. Build PhaseCompletedEvent + MetricRecorded(phase.completion_time)
          8. EventStore.append([PhaseCompletedEvent, MetricRecorded], source=__name__)  ← atomic (I-ES-1)
          9. Return [PhaseCompletedEvent, MetricRecorded]

        NOTE: No projection rebuild needed — PhaseCompleted is in _KNOWN_NO_HANDLER;
        read_state is used for validation only, not mutated here.
        """
        ...
```

### 4.7 `ValidateInvariantsHandler` (`commands/validate_invariants.py`)

```python
class ValidateInvariantsHandler(CommandHandlerBase):
    """Run build.commands from project_profile.yaml as subprocesses.
    Emits TestRunCompletedEvent (L1) + MetricRecorded(quality.*) (L2) per command.
    Does NOT emit events if config load fails — raises ConfigValidationError instead.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ValidateInvariantsCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. load_config(command.config_path) → get build.commands + execution constraints (I-CMD-6)
          3. For each build command (lint, typecheck, test, build):
               a. Run as subprocess with determinism constraints (I-CMD-13):
                    cwd     = command.cwd (explicit; never os.getcwd())
                    env     = command.env_whitelist (explicit allowlist; never os.environ pass-through)
                    timeout = command.timeout_secs (default from config; raises on expiry)
               b. Capture returncode + stdout/stderr
               c. Normalize stdout: truncate to first 4096 bytes, strip ANSI codes
               d. Build TestRunCompletedEvent(name, returncode, stdout_normalized, duration_ms)
               e. Build MetricRecorded(quality.<name>, value=returncode)
               f. Append to events list (do NOT call EventStore here — handler is pure emitter)
          4. Return list of all events
        Note: individual command failures do NOT abort the loop — all commands run.
        The caller (or CLI) decides whether any failure is terminal.

        Determinism guarantee:
        ValidateInvariantsHandler is deterministic WITHIN a fixed environment snapshot:
        same source + same config + same dependency versions → same returncode + output.
        Cross-environment reproducibility (different machines, OS versions, dependency
        installations) is NOT guaranteed and MUST NOT be assumed. Use env_whitelist and
        an explicit cwd to maximise isolation (I-CMD-13), but the subprocess is inherently
        an external system and may vary with filesystem state, tool versions, or time.
        """
        ...
```

### 4.8 `ValidateConfigHandler` (`commands/validate_config.py`)

```python
class ValidateConfigHandler(CommandHandlerBase):
    """Validate project_profile.yaml + phases/phase_N.yaml structure.
    Pure validation — emits nothing on success.
    Raises ConfigValidationError on schema violation.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ValidateConfigCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. load_config(command.config_path) with schema validation
          3. Check required fields: stack.language, build.commands, testing.coverage_threshold
          4. Check phases/phase_N.yaml if present
          5. Raise ConfigValidationError with field path on any violation
          6. Return [] on success (no events emitted)

        Idempotency note: this handler emits no events — _check_idempotent() will always
        return False (nothing to find in EventLog). Its idempotency is behavioral: the
        same config → same validation outcome. Re-running is safe by design; the handler
        is a pure read-only check with no side effects on success. The _check_idempotent
        call is retained for structural consistency with all other handlers only.
        """
        ...
```

### 4.9 `ReportErrorHandler` (`commands/report_error.py`)

```python
class ReportErrorHandler(CommandHandlerBase):
    """Manually emit an ErrorEvent — for structured error reporting outside
    automatic error_event_boundary (e.g., report_error.py tool invocation).
    Sets retry_count=0 always (manual reports are not retries).
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ReportErrorCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. Build ErrorEvent(error_type=..., source=..., recoverable=...,
                              retry_count=0, context={"message": command.message})
          3. Return [ErrorEvent]   ← CommandRunner calls EventStore.append()
        """
        ...
```

### 4.10 `RecordDecisionHandler` (`commands/record_decision.py`)

```python
class RecordDecisionHandler(CommandHandlerBase):
    """Persist a design decision in the EventLog as DecisionRecordedEvent.
    Used to record D-* entries from sdd_plan.md into the immutable event log.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: RecordDecisionCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done (also checks decision_id+phase_id semantic key)
          2. Validate: decision_id matches known D-* format; summary ≤ 500 chars
          3. Build DecisionRecordedEvent(decision_id, title, summary, phase_id, timestamp)
          4. Return [DecisionRecordedEvent]   ← CommandRunner calls EventStore.append()
        """
        ...
```

### 4.11 `CommandRunner` (`commands/sdd_run.py`)

```python
class CommandRunner:
    """Orchestrates: pure guard pipeline → EventStore dispatch → handler.

    Guard pipeline order per §R.6:
      1. PhaseGuard.check(ctx, command_str)          → (GuardResult, audit_events)
      2. TaskGuard.check(ctx, task_id)               → (GuardResult, audit_events)  [task-scoped]
      3. DependencyGuard.check(ctx, task_id)         → (GuardResult, audit_events)  [task-scoped]
      4. TaskStartGuard.check_requires_invariants(ctx, task_id, required_ids)       [task-scoped]
      5. ScopeGuard.check_read(ctx, path) × inputs   → (GuardResult, audit_events)  [task-scoped]
      6. NormGuard.check(ctx, actor, action)         → (GuardResult, audit_events)

    Guards are PURE: they return (GuardResult, list[DomainEvent]) without any side effects (I-ES-3).
    If any guard returns DENY:
      - CommandRunner calls EventStore.append(audit_events) to persist the audit trail
      - Returns [] — handler is NOT called (I-CMD-7)
    """

    def __init__(
        self,
        event_store:  "EventStore",
        state_path:   str,
        config_path:  str,
        taskset_path: str,
        reports_dir:  str,
        norm_path:    str,
    ) -> None: ...

    def run(
        self,
        command:       "Command",
        command_str:   str,               # human-readable e.g. "Implement T-401"
        actor:         str = "llm",
        action:        str = "implement_task",
        task_id:       str | None = None,
        required_ids:  tuple[str, ...] = (),
        input_paths:   tuple[str, ...] = (),
    ) -> list["DomainEvent"]:
        """
        Steps:
          1. Pre-run rebuild (projection sync for external readers):
             projections.rebuild_state(db_path, state_path) ensures the YAML file on disk
             is in sync with EventLog for callers that read the file directly between commands.
             GuardContext.state is built from EventLog replay in step 2 (authoritative) —
             NOT from this file. Step 1 and step 2 serve distinct roles and MUST NOT be merged.
          2. Build GuardContext from EventLog replay:
               state = reduce(replay_events(db_path))   ← authoritative; never from YAML
               event_log = EventLogView(db_path)
               task_graph = load_dag(taskset_path)
               norms = NormCatalog.load(norm_path)  # default = DENY
               now = utc_now_iso()
             Optimization note: full replay is O(N) and correct now. A future phase MAY
             replace replay_all_events() with snapshot + tail replay when EventLog grows
             large. The CommandRunner API is stable; only the internal state reconstruction
             changes. Full replay MUST remain the default until snapshotting is specced.
          3. result, audit_events = run_guard_pipeline(ctx, ...)
          4. If DENY: self._store.append(audit_events, source="guards") → return []
          5. events = handler.handle(command)   ← handler is pure emitter
          6. self._store.append(events, source=handler_module)  ← EventStore is sole appender
          7. Post-append rebuild (projection consistency after write):
             projections.rebuild_*(db_path, ...) ensures YAML files reflect the appended events.
             Role is distinct from step 1: step 1 = pre-flight sync; step 7 = post-write
             consistency. In a future parallel-execution context these two roles will need
             separate locking strategies — keep them structurally separated now.
          8. return events

        Does NOT catch exceptions from handler — error_event_boundary handles them.
        error_event_boundary may also call EventStore internally (ErrorEvent path).
        """
        ...
```

`run_guard_pipeline` is a **standalone module-level function** (not a method), so it can be
tested and reasoned about independently of `CommandRunner`:

```python
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
    """Pure function: runs all guards in order, returns (result, audit_events).
    No I/O, no mutations. (I-ES-3, I-GRD-4)
    """
    ...
```

### 4.12 `EventStore` (`infra/event_store.py`) — NEW

```python
class EventStore:
    """Single write path for all domain events (I-ES-1).

    Callers in production:
      - CommandRunner.run()  — after handler returns events on success path
      - CommandRunner.run()  — audit_events on guard DENY path
      - error_event_boundary — ErrorEvent on exception path (sole handler-side exception)
    Nothing else calls append() directly.

    append() is atomic: uses sdd_append_batch internally so that a list of events
    is written in a single DB transaction. A crash after append() leaves the EventLog
    consistent; a crash before append() leaves files unchanged (I-ES-1 write-order).

    Projections (TaskSet.md, State_index.yaml) are rebuilt AFTER append() succeeds.
    They are eventually consistent: a crash between append() and rebuild() leaves the
    EventLog correct but the projection stale — the next run will rebuild it (I-ES-5).
    """

    def __init__(self, db_path: str) -> None: ...

    def append(self, events: list[DomainEvent], source: str) -> None:
        """Atomically append events to the EventLog.
        source: module name of the emitter (for audit trail).
        Raises EventStoreError if DB write fails — callers must NOT fall back to
        direct file mutation on failure.
        """
        ...
```

### 4.13 `GuardContext` (`domain/guards/context.py` — Phase 3, referenced here)

```python
@dataclass(frozen=True)
class GuardContext:
    """Immutable snapshot passed to every guard (I-ES-3).

    Guards are pure functions over GuardContext — they inspect fields and return
    (GuardResult, list[DomainEvent]) without mutating anything.
    """
    state:       SDDState
    phase:       PhaseState
    task:        Task | None
    norms:       NormCatalog        # default = DENY (I-CMD-12)
    event_log:   EventLogView       # read-only projection of EventLog
    task_graph:  DAG                # task dependency graph for DependencyGuard (I-CMD-11)
    now:         str                # ISO8601 UTC timestamp — injected for determinism
```

`GuardContext` is constructed by `CommandRunner` before calling `run_guard_pipeline`.
Phase 3 defines the guards; Phase 4 adds `task_graph` field and `DependencyGuard`.

**Construction rule (I-CMD-11 stale-state fix):**
`state` MUST be derived from `reduce(replay_events(db_path))` — i.e. from EventLog replay —
not from reading `State_index.yaml`. The YAML file is a projection and may lag behind the
EventLog by one rebuild cycle. Using a stale projection in `DependencyGuard` could allow a
task to run before its dependency is DONE according to the EventLog truth.

```python
# CommandRunner constructs GuardContext:
state = sdd_reducer(replay_all_events(db_path))   # authoritative; full replay now
event_log = EventLogView(db_path)                 # read-only window
task_graph = load_dag(taskset_path)               # dependency declarations
norms = NormCatalog.load(norm_path)               # default = DENY
now = utc_now_iso()                               # injected for determinism
ctx = GuardContext(state, phase, task, norms, event_log, task_graph, now)

# Optimization note (future phase):
# State MAY be built from snapshot + tail replay instead of full O(N) replay once a
# snapshotting mechanism is implemented. GuardContext construction API is stable —
# only the internal replay_all_events() implementation changes. Full replay is correct
# now; snapshot optimization is explicitly architecturally permitted when needed.
```

### 4.14 `exists_command` + `get_error_count` + `exists_semantic` (`infra/event_log.py` extension)

```python
def exists_command(db_path: str, command_id: str) -> bool:
    """Return True if any event with payload.command_id == command_id exists in EventLog.
    Pure DB read — no writes, no side effects (I-CMD-10).
    Uses sdd_replay or direct query; MUST NOT call duckdb.connect outside infra/db.py (I-EL-9).
    """
    ...

def exists_semantic(
    db_path: str,
    command_type: str,
    task_id: str | None,
    phase_id: int | None,
    payload_hash: str,
) -> bool:
    """Return True if an event matching (command_type, task_id, phase_id, payload_hash)
    already exists in EventLog.

    Semantic idempotency guard — prevents duplicate effects even with a new command_id.
    payload_hash guards against false positives: a retry with legitimately different
    fields (e.g. result="FAIL" vs "PASS") must NOT be blocked (I-CMD-2b).

    payload_hash = sha256(canonical_json(command fields excluding command_id)).

    canonical_json MUST be stable across Python versions and platforms:
      - JSON object keys sorted alphabetically at every nesting level
      - No whitespace (separators=(',', ':'))
      - datetime values serialized as ISO8601 UTC strings ("YYYY-MM-DDTHH:MM:SSZ")
      - float values: standard JSON number representation (no scientific notation)
    Any deviation produces "phantom non-idempotent commands": identical semantics
    hash to different values, causing legitimate duplicates to bypass the guard.

    Pure DB read (I-CMD-10).
    """
    ...

def get_error_count(db_path: str, command_id: str) -> int:
    """Return count of ErrorEvent records with payload.command_id == command_id.
    Used by error_event_boundary to set retry_count.
    Pure DB read (I-CMD-10).
    """
    ...
```

### 4.15 `DoDNotMet` error type (`core/errors.py` extension)

```python
class DoDNotMet(SDDError):
    """Raised by CheckDoDHandler when DoD conditions are not all satisfied.

    Fields (via message string or structured context):
      - failed_conditions: list of failed checks (not all tasks done / invariants FAIL / tests FAIL)
    """
```

---

## 5. Invariants

### New Invariants (Phase 4)

**EventStore / SSOT invariants:**

| ID | Statement | Enforced by |
|---|---|---|
| I-ES-1 | `EventStore.append()` is the ONLY write path to the EventLog; events are appended atomically BEFORE any file mutation; a crash before `append()` leaves both EventLog and files unchanged | `tests/unit/infra/test_event_store.py` |
| I-ES-2 | Handlers emit events ONLY — they do NOT write `TaskSet.md`, `State_index.yaml`, or any other file directly; all file writes happen via `projections.rebuild_*` AFTER `EventStore.append()` succeeds | `tests/unit/commands/test_*.py` (all handler tests) |
| I-ES-3 | Guards are pure functions: every guard returns `(GuardResult, list[DomainEvent])` without calling `emit`, writing files, or mutating any shared state; `CommandRunner` appends the returned `audit_events` via `EventStore` on `DENY` | `tests/unit/commands/test_sdd_run.py` |
| I-ES-4 | `TaskSet.md` and `State_index.yaml` are projections of the EventLog; after any handler succeeds, the relevant projection is rebuilt via `projections.rebuild_taskset()` or `projections.rebuild_state()`; the EventLog is always the authoritative source | `tests/unit/commands/test_complete_task.py`, `test_validate_task.py`, `test_sync_state.py` |
| I-ES-5 | Projections are **eventually consistent**, not transactionally atomic with `EventStore.append()`; a crash after `append()` but before `rebuild_*()` leaves the EventLog correct and the projection stale; the next `rebuild_*()` call MUST recover the correct state from EventLog replay | `tests/unit/infra/test_projections.py` — `test_rebuild_recovers_after_partial_crash` |

**Command handler invariants:**

| ID | Statement | Enforced by |
|---|---|---|
| I-CMD-1 | `handle(command)` is idempotent: if `command_id` already appears in the EventLog, `handle()` returns `[]` without emitting events or modifying files | `tests/unit/commands/test_*.py` (all handler tests) |
| I-CMD-2 | `error_event_boundary` calls `EventStore.append([ErrorEvent(...)])` BEFORE re-raising the exception; emit is called exactly once per exception; the original exception is always re-raised (I-CMD-3) | `tests/unit/commands/test_base.py` |
| I-CMD-2b | Semantic idempotency: if `exists_semantic(command_type, task_id, phase_id, payload_hash)` returns True, `handle()` returns `[]`; `payload_hash = sha256(canonical_json(command fields ∖ command_id))`; `canonical_json` MUST use sorted keys + no whitespace + ISO8601 UTC datetimes + no scientific notation — any deviation produces phantom non-idempotent commands; a retry with changed meaningful fields (different `result`, different `summary`) is NOT blocked | `tests/unit/commands/test_*.py` (all handler tests) |
| I-CMD-3 | `error_event_boundary` NEVER suppresses exceptions; if `EventStore.append(ErrorEvent)` itself raises, the decorator logs to `fallback_log` and re-raises the ORIGINAL exception — the root cause is never lost | `tests/unit/commands/test_base.py` |
| I-CMD-4 | `CompleteTaskHandler.handle()` appends `[TaskImplementedEvent, MetricRecorded(task.lead_time)]` via a single `EventStore.append()` call — never appended separately (I-EL-11) | `tests/unit/commands/test_complete_task.py` |
| I-CMD-5 | `CheckDoDHandler` emits `PhaseCompletedEvent` ONLY when `tasks.completed == tasks.total AND invariants.status == "PASS" AND tests.status == "PASS"`; any other state → raises `DoDNotMet` (SDD-6) | `tests/unit/commands/test_check_dod.py` |
| I-CMD-6 | `ValidateInvariantsHandler` runs every command listed in `build.commands` from the loaded project_profile config; no commands are skipped, no commands outside `build.commands` are added; results recorded via MetricRecorded | `tests/unit/commands/test_validate_invariants.py` |
| I-CMD-7 | `CommandRunner.run()` executes the pure guard pipeline BEFORE invoking any handler; a guard returning `GuardResult(DENY)` causes `run()` to append `audit_events` via `EventStore` then return `[]` without calling `handler.handle()`; handler emits no events | `tests/unit/commands/test_sdd_run.py` |
| I-CMD-8 | `SyncStateHandler.handle()` rebuilds `State_index.yaml` via `projections.rebuild_state()` AFTER appending `StateSyncedEvent`; uses `atomic_write` internally (I-PK-5) | `tests/unit/commands/test_sync_state.py` |
| I-CMD-9 | Every `DomainEvent` subclass emitted by Phase 4 handlers has its `EVENT_TYPE` string present in `V1_L1_EVENT_TYPES`; `DecisionRecordedEvent` is also in `_KNOWN_NO_HANDLER`; `TaskImplementedEvent` and `TaskValidatedEvent` are in `_EVENT_SCHEMA` with reducer handlers | `tests/unit/core/test_events_commands.py` (C-1 assert passes after import) |
| I-CMD-10 | `exists_command`, `exists_semantic`, and `get_error_count` are pure DB reads: no writes, no side effects, no direct `duckdb.connect` outside `infra/db.py` (I-EL-9) | `tests/unit/infra/test_event_log_commands.py` |
| I-CMD-11 | `DependencyGuard` checks the task DAG (`GuardContext.task_graph`) and returns `DENY` if any declared dependency of `task_id` is not yet `DONE` in the EventLog projection; dependency check runs as guard step 3 in CommandRunner (task-scoped) | `tests/unit/commands/test_sdd_run.py`, `tests/unit/guards/test_dependency_guard.py` |
| I-CMD-12 | `NormCatalog` default policy is `DENY`; every permitted action requires an explicit `ALLOW` entry; `NormGuard.check()` returns `DENY` for any actor/action pair not in the catalog | `tests/unit/guards/test_norm_guard_default_deny.py` |
| I-CMD-13 | `ValidateInvariantsHandler` runs subprocesses with explicit `cwd`, `env_whitelist`, and `timeout_secs`; stdout is normalized (≤4096 bytes, ANSI stripped); these fields are declared on `ValidateInvariantsCommand` and MUST NOT fall back to `os.getcwd()` or `os.environ`; determinism guarantee is WITHIN a fixed environment snapshot only — cross-environment reproducibility is not guaranteed and must not be assumed | `tests/unit/commands/test_validate_invariants.py` — `test_subprocess_uses_explicit_cwd`, `test_subprocess_env_whitelist`, `test_subprocess_timeout_raises` |
| I-ERR-1 | `@error_event_boundary` appends `ErrorEvent(retry_count=get_error_count(command_id))` via `sdd_append(self._db_path, ...)` before re-raising any exception from `handle()`; first occurrence has `retry_count=0`; MUST call the same low-level `sdd_append` function used by `EventStore.append()` internally — same transaction semantics, same schema; this is the ONLY permitted handler-side write path and NO additional special write paths may be introduced | `tests/unit/commands/test_base.py` |

### Preserved Invariants (referenced)

| ID | Statement |
|---|---|
| I-EL-9 | No direct `duckdb.connect` outside `infra/db.py` — handlers use `EventStore` which routes through `infra/db.py` |
| I-EL-11 | `TaskImplementedEvent + MetricRecorded` written in a single `EventStore.append()` call (single transaction) |
| I-PK-5 | `atomic_write` uses tmp file + `os.replace` — used by `projections.rebuild_*` for file writes |
| I-GRD-4 | `run_guard_pipeline` is a pure orchestrator — guards return `(result, audit_events)`; `CommandRunner` handles side effects |
| I-ST-9 | `SDDState` schema is identical between YAML read (projection) and reducer replay — Phase 4 reducer extensions must maintain this |

### §PHASE-INV (must ALL be PASS before Phase 4 can be COMPLETE)

```
[I-ES-1, I-ES-2, I-ES-3, I-ES-4, I-ES-5,
 I-CMD-1, I-CMD-2, I-CMD-2b, I-CMD-3, I-CMD-4, I-CMD-5, I-CMD-6,
 I-CMD-7, I-CMD-8, I-CMD-9, I-CMD-10, I-CMD-11, I-CMD-12, I-CMD-13, I-ERR-1]
```

---

## 6. Pre/Post Conditions

### CompleteTaskHandler.handle(command: CompleteTaskCommand)

**Pre:**
- `command.command_id` is a unique string
- `command.taskset_path` points to a readable `TaskSet_vN.md`
- `command.task_id` matches an entry in the TaskSet with `status == "TODO"`
- EventLog accessible at `self._db_path`

**Post:**
- `command_id` already in EventLog OR semantic key matches → returns `[]`, no changes (I-CMD-1, I-CMD-2b)
- `task_id` not found → raises `MissingContext`
- `task_id` found with `status == "DONE"` → raises `InvalidState`
- Success: `EventStore.append([TaskImplementedEvent, MetricRecorded])` called atomically FIRST (I-ES-1, I-CMD-4);
  `projections.rebuild_taskset()` called AFTER to update `TaskSet.md` (I-ES-4)
- Any exception → `ErrorEvent` appended via `EventStore` before re-raise (I-ERR-1, I-CMD-3)

### CheckDoDHandler.handle(command: CheckDoDCommand)

**Pre:**
- `command.state_path` points to a readable `State_index.yaml`
- `command.phase_id` matches `state.phase_current`

**Post:**
- `command_id` already in EventLog → returns `[]` (I-CMD-1)
- `tasks.completed < tasks.total` → raises `DoDNotMet("not all tasks DONE")`
- `invariants.status != "PASS"` → raises `DoDNotMet("invariants not PASS")`
- `tests.status != "PASS"` → raises `DoDNotMet("tests not PASS")`
- All conditions met → `PhaseCompletedEvent + MetricRecorded(phase.completion_time)` written atomically
- Any exception → `ErrorEvent` emitted before re-raise (I-ERR-1)

### ValidateInvariantsHandler.handle(command: ValidateInvariantsCommand)

**Pre:**
- `command.config_path` points to a readable `project_profile.yaml` with `build.commands`
- Working directory has `src/` accessible for lint/typecheck/test execution

**Post:**
- `command_id` already in EventLog → returns `[]` (I-CMD-1)
- Each build command runs as subprocess; `TestRunCompletedEvent + MetricRecorded` emitted per command
- Individual subprocess failure does NOT abort the loop — all commands run (I-CMD-6)
- Any exception from config load → `ConfigValidationError` raised; `ErrorEvent` emitted (I-ERR-1)

### CommandRunner.run(command, command_str, ...)

**Pre:**
- `db_path`, `state_path`, `config_path`, `taskset_path` all accessible
- `emit` callable not None
- `actor ∈ {"llm", "human"}`

**Post:**
- Any guard returns `DENY` → `CommandRunner` appends `audit_events` via `EventStore`; returns `[]`; handler NOT invoked (I-CMD-7, I-ES-3)
- All guards `ALLOW` → `handler.handle(command)` result returned
- Guard audit_events appended by `CommandRunner`, not by guards themselves (I-ES-3)
- Handler exceptions propagate (error_event_boundary handles them inside handler)

### exists_command(db_path, command_id)

**Pre:** `db_path` points to a DuckDB file; `command_id` is a string

**Post:**
- Returns `True` if any event with `payload.command_id == command_id` exists
- Returns `False` otherwise
- No writes, no side effects (I-CMD-10)

---

## 7. Use Cases

### UC-4-1: Complete task T-401

**Actor:** §R.6 post-execution protocol
**Trigger:** `Implement T-401` completed; `update_state.py complete T-401` called
**Pre:** Phase 4 ACTIVE, T-401 status TODO, `TaskSet_v4.md` present
**Steps:**
1. Build `CompleteTaskCommand(command_id=uuid(), task_id="T-401", phase_id=4, ...)`
2. `CommandRunner.run(command, "Implement T-401", actor="llm", action="implement_task", task_id="T-401", ...)`
3. Guard pipeline: PhaseGuard → TaskGuard → TaskStartGuard → ScopeGuard × inputs → NormGuard → all ALLOW
4. `CompleteTaskHandler.handle(command)`:
   a. `_check_idempotent` → False (new command_id, no semantic match)
   b. `parse_taskset` → find T-401, status TODO (validation only — TaskSet is projection)
   c. Build `TaskImplementedEvent + MetricRecorded(task.lead_time)`
   d. `EventStore.append([TaskImplementedEvent, MetricRecorded])` ← atomic (I-ES-1)
   e. `projections.rebuild_taskset(db_path, taskset_path)` ← T-401 → DONE in projection (I-ES-4)
5. Returns `[TaskImplementedEvent, MetricRecorded]`
**Post:** Two events in EventLog (SSOT); TaskSet.md rebuilt as projection; state derivable from events replay

### UC-4-2: Idempotent re-run of complete T-401

**Actor:** §R.11 Idempotency rule
**Trigger:** `complete T-401` called again with same `command_id`
**Pre:** T-401 already DONE in EventLog from UC-4-1
**Steps:**
1. `CompleteTaskHandler.handle(command)`:
   a. `_check_idempotent` → True (`command_id` in EventLog)
   b. Return `[]` immediately
**Post:** No events emitted; no files modified; TaskSet unchanged

### UC-4-3: Error boundary captures handler exception

**Actor:** `error_event_boundary` decorator
**Trigger:** `ValidateInvariantsHandler.handle()` raises `subprocess.CalledProcessError`
**Pre:** Phase 4 ACTIVE, config loaded, but subprocess fails unexpectedly
**Steps:**
1. `@error_event_boundary(source="sdd.commands.validate_invariants")` wraps `handle()`
2. Exception raised inside `handle()`
3. Decorator: `count = get_error_count(db_path, command.command_id)` → 0 (first occurrence)
4. Decorator: `self._emit(ErrorEvent(error_type="CalledProcessError", source="sdd.commands.validate_invariants", recoverable=False, retry_count=0, context={"message": str(exc)}))`
5. Decorator: re-raises `CalledProcessError`
**Post:** `ErrorEvent` with `retry_count=0` in EventLog; exception propagates to caller (I-ERR-1, I-CMD-3)

### UC-4-4: Check DoD — not all tasks done

**Actor:** §R.7 validate --check-dod protocol
**Trigger:** `CheckDoDCommand` called with 18/22 tasks complete
**Pre:** `state.tasks.completed == 18`, `state.tasks.total == 22`
**Steps:**
1. `CheckDoDHandler.handle(command)`:
   a. `_check_idempotent` → False
   b. `read_state(command.state_path)`
   c. `tasks.completed (18) != tasks.total (22)` → raise `DoDNotMet("not all tasks DONE: 18/22")`
2. `error_event_boundary` catches → emit `ErrorEvent(retry_count=0)` → re-raise
**Post:** `DoDNotMet` propagates; `ErrorEvent` in EventLog; phase NOT marked COMPLETE (I-CMD-5)

### UC-4-5: Guard DENY blocks command handler

**Actor:** `CommandRunner`
**Trigger:** LLM attempts `Implement T-401` but `phase.status != "ACTIVE"`
**Pre:** `State_index.yaml` shows `phase.status == "COMPLETE"`
**Steps:**
1. `CommandRunner.run(command, "Implement T-401", ...)`:
   a. Build `GuardContext(state=..., phase=..., task=None, norms=catalog, event_log=view, task_graph=dag, now=...)`
   b. `PhaseGuard.check(ctx, "Implement T-401")` → `(DENY, [SDDEventRejected(...)])` — pure, no side effects (I-ES-3)
   c. `run_guard_pipeline` returns on first `DENY` (stop_on_deny=True)
   d. `CommandRunner` calls `EventStore.append([SDDEventRejected])` ← audit trail persisted by runner, not guard (I-ES-3)
   e. Returns `[]`; handler NOT called (I-CMD-7)
**Post:** No handler events; `SDDEventRejected` in EventLog (appended by CommandRunner); no files modified

### UC-4-6: Record design decision D-16

**Actor:** LLM (planner phase)
**Trigger:** Persisting D-16 (command idempotency contract) to EventLog
**Pre:** Phase 4 ACTIVE
**Steps:**
1. `RecordDecisionHandler.handle(RecordDecisionCommand(decision_id="D-16", title="command idempotency by command_id", summary="...", phase_id=4, command_id=uuid()))`
2. `_check_idempotent` → False
3. Build `DecisionRecordedEvent(decision_id="D-16", ...)`
4. `sdd_append(DecisionRecordedEvent, event_source="meta")`
5. Return `[DecisionRecordedEvent]`
**Post:** D-16 persisted in EventLog as L1 domain event; auditable; replayable

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|---|---|---|
| BC-GUARDS (`guards/`) | BC-COMMANDS → | `CommandRunner` constructs `GuardContext` (incl. `task_graph`), calls pure `run_guard_pipeline`; appends returned `audit_events` via `EventStore` on DENY (I-ES-3, I-CMD-7) |
| BC-STATE (`domain/state/`) | BC-COMMANDS → | `SyncStateHandler`, `ValidateTaskHandler`, `CheckDoDHandler` call `read_state` (read-only); `projections.rebuild_state()` writes AFTER event append (I-ES-4) |
| BC-TASKS (`domain/tasks/parser.py`) | BC-COMMANDS → | `CompleteTaskHandler` calls `parse_taskset` for validation only; `projections.rebuild_taskset()` writes AFTER event append (I-ES-4) |
| BC-INFRA (`infra/event_store.py`) | BC-COMMANDS → | `EventStore.append()` is the single write path for all events (I-ES-1) |
| BC-INFRA (`infra/event_log.py`) | BC-COMMANDS → | `exists_command`, `exists_semantic`, `get_error_count` — pure reads (I-CMD-10, I-EL-9) |
| BC-INFRA (`infra/projections.py`) | BC-COMMANDS → | `rebuild_taskset`, `rebuild_state` — projection rebuilds post-append (I-ES-4) |
| BC-INFRA (`infra/config_loader.py`) | BC-COMMANDS → | `ValidateConfigHandler`, `ValidateInvariantsHandler` call `load_config` |
| BC-INFRA (`infra/metrics.py`) | BC-COMMANDS → | `CompleteTaskHandler`, `ValidateInvariantsHandler` emit via `record_metric` wrapper |
| BC-CORE (`core/errors.py`) | BC-COMMANDS → | Handlers raise `MissingContext`, `InvalidState`, `DoDNotMet`, `ConfigValidationError` |
| BC-NORMS (`domain/norms/catalog.py`) | BC-COMMANDS → | `CommandRunner` loads `NormCatalog` (default=DENY, I-CMD-12) to inject into `GuardContext` |

### Integration with §R.6 / §R.7 Protocols

Phase 4 command handlers are the Python-level implementation of the §R.6 and §R.7 protocols:

```
§R.6 step f (Implement outputs)     → CompleteTaskHandler.handle()
§R.6 step g (update_state complete) → CompleteTaskHandler.handle() emits TaskImplementedEvent
§R.7 step c (validate_invariants)   → ValidateInvariantsHandler.handle()
§R.7 step d (ValidationReport)      → caller writes .sdd/reports/ValidationReport_T-NNN.md
§R.7 step e (update_state validate) → ValidateTaskHandler.handle() emits TaskValidatedEvent
```

Until Phase 8 (thin adapters), `.sdd/tools/*.py` governance scripts remain independent.
Phase 4 builds the `src/sdd/commands/` Python package that Phase 8 will wire in.

### C-1 Compliance (Phase 4 — single task requirement)

```python
# core/events.py — add to V1_L1_EVENT_TYPES (DecisionRecorded is NEW)
V1_L1_EVENT_TYPES: frozenset[str] = frozenset({
    # ... all existing types ...
    "DecisionRecorded",   # Phase 4 — RecordDecisionHandler
})

# domain/state/reducer.py — ensure TaskImplemented + TaskValidated in _EVENT_SCHEMA
_EVENT_SCHEMA = {
    # ... existing handlers ...
    "TaskImplemented": _handle_task_implemented,   # increments completed, adds done_id
    "TaskValidated":   _handle_task_validated,     # sets invariants/tests status
}

# DecisionRecorded + PhaseCompleted in _KNOWN_NO_HANDLER (no reducer state change)
_KNOWN_NO_HANDLER: frozenset[str] = frozenset({
    # ... existing entries ...
    "DecisionRecorded",
    "PhaseCompleted",     # if not already present from Phase 1/2
})
```

Task T-401 MUST modify `core/events.py`, `domain/state/reducer.py`, and the dataclass
definitions in the same task. Splitting triggers the import-time assert.

### Integration with Phase 5 (Query, Metrics & Reporting)

Phase 4 establishes the event contract that Phase 5 queries:
- `MetricRecorded` events (L2) emitted here are queried by `metrics_report.py` in Phase 5
- `TestRunCompletedEvent` events emitted by `ValidateInvariantsHandler` feed Phase 5 coverage reports
- Phase 5 `query_events.py` module reads `DecisionRecordedEvent`, `TaskImplementedEvent`, etc.

---

## 9. Verification

| # | Test File | Key Tests | Invariant(s) |
|---|---|---|---|
| 1 | `tests/unit/core/test_events_commands.py` | `test_task_implemented_event_is_frozen`, `test_c1_assert_passes_after_import`, `test_decision_recorded_in_v1_l1_types`, `test_reducer_handles_task_implemented`, `test_reducer_handles_task_validated` | I-CMD-9, C-1 |
| 2a | `tests/unit/infra/test_event_store.py` | `test_append_is_atomic`, `test_append_only_write_path`, `test_crash_before_append_leaves_files_unchanged`, `test_event_store_routes_through_infra_db` | I-ES-1 |
| 2b | `tests/unit/infra/test_event_log_commands.py` | `test_exists_command_returns_false_when_absent`, `test_exists_command_returns_true_after_append`, `test_exists_semantic_returns_false_when_absent`, `test_exists_semantic_prevents_duplicate_effect`, `test_get_error_count_zero_on_no_errors`, `test_get_error_count_increments`, `test_exists_command_no_side_effects`, `test_no_direct_duckdb_connect` | I-CMD-10, I-CMD-2b, I-EL-9 |
| 3 | `tests/unit/commands/test_base.py` | `test_error_boundary_emits_before_reraise`, `test_error_boundary_reraises_always`, `test_error_boundary_does_not_suppress`, `test_retry_count_zero_on_first_error`, `test_retry_count_increments_on_second_error`, `test_emit_failure_reraises_original_not_emit_error`, `test_emit_failure_logs_to_fallback`, `test_idempotent_check_skips_boundary`, `test_semantic_idempotent_skips_boundary` | I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3 |
| 4 | `tests/unit/commands/test_complete_task.py` | `test_complete_task_appends_event_before_file_write`, `test_complete_task_rebuilds_projection_after_append`, `test_complete_task_emits_batch`, `test_complete_task_idempotent`, `test_complete_task_semantic_idempotent`, `test_complete_task_missing_task_raises`, `test_complete_task_already_done_raises`, `test_batch_is_atomic_on_failure`, `test_no_direct_file_write_in_handler` | I-CMD-1, I-CMD-2b, I-CMD-4, I-ES-1, I-ES-2, I-ES-4, I-EL-11 |
| 5 | `tests/unit/commands/test_validate_task.py` | `test_validate_pass_updates_state`, `test_validate_fail_updates_state`, `test_validate_task_idempotent`, `test_validate_emits_task_validated_event` | I-CMD-1 |
| 6 | `tests/unit/commands/test_sync_state.py` | `test_sync_state_writes_atomically`, `test_sync_state_emits_synced_event`, `test_sync_state_idempotent`, `test_sync_uses_atomic_write` | I-CMD-1, I-CMD-8, I-PK-5 |
| 7 | `tests/unit/commands/test_check_dod.py` | `test_check_dod_emits_phase_completed_when_all_pass`, `test_check_dod_raises_if_tasks_incomplete`, `test_check_dod_raises_if_invariants_fail`, `test_check_dod_raises_if_tests_fail`, `test_check_dod_idempotent`, `test_phase_completed_batch_atomic` | I-CMD-1, I-CMD-5 |
| 8 | `tests/unit/commands/test_validate_invariants.py` | `test_runs_all_build_commands`, `test_emits_metric_per_command`, `test_continues_on_failure`, `test_no_extra_commands`, `test_validate_inv_idempotent` | I-CMD-1, I-CMD-6 |
| 9 | `tests/unit/commands/test_validate_config.py` | `test_valid_config_returns_empty`, `test_missing_required_field_raises`, `test_validate_config_idempotent` | I-CMD-1 |
| 10 | `tests/unit/commands/test_report_error.py` | `test_report_error_emits_error_event`, `test_report_error_retry_count_zero`, `test_report_error_idempotent` | I-CMD-1, I-ERR-1 |
| 11 | `tests/unit/commands/test_record_decision.py` | `test_record_decision_emits_event`, `test_record_decision_idempotent`, `test_decision_recorded_event_fields` | I-CMD-1, I-CMD-9 |
| 12 | `tests/unit/commands/test_sdd_run.py` | `test_guard_deny_skips_handler`, `test_guard_allow_runs_handler`, `test_guard_deny_returns_empty`, `test_guard_deny_appends_audit_events_via_event_store`, `test_guard_deny_emits_no_handler_events`, `test_guards_are_pure_no_side_effects`, `test_dependency_guard_wired_as_step3`, `test_norm_default_deny`, `test_all_guards_wired`, `test_runner_does_not_catch_handler_exceptions` | I-CMD-7, I-CMD-11, I-CMD-12, I-ES-3, I-GRD-4 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|---|---|
| `query_events.py` Python module (EventLog query API) | Phase 5 |
| `metrics_report.py` Python module (aggregate metrics) | Phase 5 |
| `build_context.py` CLI wiring into commands | Phase 6 |
| `log_tool.py` / `log_bash.py` Python modules | Phase 6 |
| `cli.py` Click router (all CLI entry points) | Phase 6 |
| Retry policy for failed commands (retry_count > 0 escalation) | Phase 7 |
| `PhaseActivated` event (closing EventLog governance gap for phase_status transitions) | Phase 7 |
| v1↔v2 full replay compatibility test — I-EL-4 | Phase 7 |
| Parallel execution engine (scheduler layers → concurrent handlers) | Phase 7 |
| Thin adapter migration of `.sdd/tools/` to `src/sdd/commands/` | Phase 8 |
| Multi-process / concurrent command writers | Out of scope until explicitly specced |

---

## Appendix: Task Breakdown (~27 tasks)

| Task | Outputs | produces_inv | requires_inv |
|---|---|---|---|
| T-401 | `core/events.py` (TaskImplementedEvent, TaskValidatedEvent, PhaseCompletedEvent, DecisionRecordedEvent); `domain/state/reducer.py` (_EVENT_SCHEMA handlers for TaskImplemented + TaskValidated; _KNOWN_NO_HANDLER for PhaseCompleted + DecisionRecorded; C-1 single task) | I-CMD-9 | I-TS-2, I-EL-9, I-ST-10 |
| T-402 | `tests/unit/core/test_events_commands.py` | — | I-CMD-9 |
| T-403 | `infra/event_store.py` (EventStore.append — single write path, atomic via sdd_append_batch; called only by CommandRunner and error_event_boundary) | I-ES-1 | I-EL-9, I-PK-2, I-PK-3 |
| T-404 | `tests/unit/infra/test_event_store.py` | — | I-ES-1 |
| T-405 | `infra/projections.py` (rebuild_taskset, rebuild_state — projections rebuilt from EventLog; eventual consistency recovery test) | I-ES-4, I-ES-5 | I-ES-1, I-PK-5, I-ST-9 |
| T-406 | `infra/event_log.py` (exists_command, exists_semantic + payload_hash, get_error_count) | I-CMD-10, I-CMD-2b | I-EL-9 |
| T-407 | `tests/unit/infra/test_event_log_commands.py`; `tests/unit/infra/test_projections.py` | — | I-CMD-10, I-CMD-2b, I-ES-5 |
| T-408 | `commands/_base.py` (error_event_boundary with fallback_log on emit failure; CommandHandlerBase with db_path only — no _store; semantic idempotency with payload_hash) | I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3 | I-CMD-10, I-ES-1 |
| T-409 | `tests/unit/commands/test_base.py` | — | I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3 |
| T-410 | `commands/update_state.py` (CompleteTaskHandler — emit-first, then rebuild_taskset) | I-CMD-1, I-CMD-4, I-ES-2 | I-ERR-1, I-CMD-2, I-CMD-2b, I-ES-1, I-ES-4, I-EL-11, I-TS-1 |
| T-411 | `tests/unit/commands/test_complete_task.py` | — | I-CMD-1, I-CMD-4, I-ES-1, I-ES-2, I-ES-4 |
| T-412 | `commands/update_state.py` (+ ValidateTaskHandler — emit-first, then rebuild_state) | I-CMD-1, I-ES-2 | I-ERR-1, I-CMD-2, I-ES-1, I-ES-4, I-ST-3 |
| T-413 | `tests/unit/commands/test_validate_task.py` | — | I-CMD-1, I-ES-2 |
| T-414 | `commands/update_state.py` (+ SyncStateHandler — emit-first, then rebuild_state) | I-CMD-1, I-CMD-8, I-ES-2 | I-ERR-1, I-CMD-2, I-ES-1, I-ES-4, I-PK-5 |
| T-415 | `tests/unit/commands/test_sync_state.py` | — | I-CMD-1, I-CMD-8, I-ES-2 |
| T-416 | `commands/update_state.py` (+ CheckDoDHandler); `core/errors.py` (+ DoDNotMet) | I-CMD-1, I-CMD-5, I-ES-2 | I-ERR-1, I-CMD-2, I-ES-1, I-ST-3 |
| T-417 | `tests/unit/commands/test_check_dod.py` | — | I-CMD-1, I-CMD-5 |
| T-418 | `commands/validate_invariants.py` (ValidateInvariantsHandler — pure emitter; explicit cwd/env_whitelist/timeout_secs; stdout normalization) | I-CMD-1, I-CMD-6, I-CMD-13, I-ES-2 | I-ERR-1, I-CMD-2, I-ES-1, I-PK-4 |
| T-419 | `tests/unit/commands/test_validate_invariants.py` | — | I-CMD-1, I-CMD-6, I-CMD-13 |
| T-420 | `commands/validate_config.py` (ValidateConfigHandler) | I-CMD-1 | I-ERR-1, I-CMD-2, I-ES-1, I-PK-4 |
| T-421 | `tests/unit/commands/test_validate_config.py` | — | I-CMD-1 |
| T-422 | `commands/report_error.py` (ReportErrorHandler); `commands/record_decision.py` (RecordDecisionHandler) | I-CMD-1 | I-ERR-1, I-CMD-2, I-CMD-9, I-ES-1 |
| T-423 | `tests/unit/commands/test_report_error.py`; `tests/unit/commands/test_record_decision.py` | — | I-CMD-1, I-CMD-9 |
| T-424 | `domain/guards/dependency_guard.py` (DependencyGuard — pure, returns (result, audit_events)); `domain/guards/context.py` (GuardContext.task_graph field; state built from EventLog replay); `domain/norms/catalog.py` (default=DENY) | I-CMD-11, I-CMD-12, I-ES-3 | I-GRD-4, I-GRD-1..9 |
| T-425 | `tests/unit/guards/test_dependency_guard.py`; `tests/unit/guards/test_norm_guard_default_deny.py`; `tests/unit/guards/test_guard_context_from_replay.py` | — | I-CMD-11, I-CMD-12 |
| T-426 | `commands/sdd_run.py` (CommandRunner — pure guard pipeline via run_guard_pipeline standalone fn; EventStore.append after handler; GuardContext from EventLog replay; DependencyGuard as step 3); `commands/__init__.py` | I-CMD-7, I-ES-3 | I-CMD-1, I-ES-1, I-ES-5, I-GRD-4, I-CMD-11, I-CMD-12, T-424 |
| T-427 | `tests/unit/commands/test_sdd_run.py`; `tests/unit/commands/test_run_guard_pipeline.py`; `.sdd/reports/ValidationReport_T-427.md` (§PHASE-INV coverage) | — | I-CMD-7, I-ES-3, all above |
