# Spec_v5_CriticalFixes — Phase 5: Critical Fixes

Status: Draft
Baseline: Spec_v4_Commands.md (BC-COMMANDS, BC-CORE, BC-INFRA, BC-STATE, BC-GUARDS)

---

## 0. Goal

Close five correctness gaps discovered after Phase 4 implementation before any downstream
usage begins. After this phase:

- `phase_status` and `plan_status` transitions are driven by Commands and recorded as L1
  events, making the full SDD state replay-derivable from the EventLog alone (Q1 passes)
- `EventStore.append()` is the sole write path — `error_event_boundary` no longer calls
  `sdd_append` directly; `CommandRunner` handles the ErrorEvent path (I-ES-1 final form)
- The duplicate `GuardContext` in `guards/runner.py` is removed; all code uses the canonical
  `domain/guards/context.py` version
- The reducer's behaviour for unknown event types is an explicit invariant (I-REDUCER-1):
  NO-OP + `logging.warning` by default, `raise UnknownEventType` in strict mode
- Three tests replace the tautological `reduce(sdd_replay()) == read_state_from_yaml()`
  check: a golden-scenario test, a replay-determinism test, and a full Command → replay →
  state integration test (Q3 passes)

This phase does NOT introduce CLI entry points, extension points, API polish, or new
commands beyond `ActivatePhaseCommand` / `ActivatePlanCommand`.

---

## 1. Scope

### In-Scope

- BC-CORE extension: `core/events.py` — add `PhaseActivatedEvent`, `PlanActivatedEvent`
- BC-COMMANDS: `commands/activate_phase.py`, `commands/activate_plan.py` (new handlers)
- BC-STATE extension: `domain/state/reducer.py` — handlers for new events + I-REDUCER-1
- BC-INFRA extension: `infra/projections.py` — remove reliance on human-managed YAML fields
- BC-COMMANDS fix: `commands/_base.py` — `error_event_boundary` attaches events to exception
- BC-COMMANDS fix: `commands/sdd_run.py` — `CommandRunner` catches and appends error events
- BC-GUARDS cleanup: `guards/runner.py` — remove duplicate `GuardContext` class
- Tests: `tests/unit/domain/state/test_reducer.py` — golden scenario + determinism
- Tests: `tests/integration/test_full_chain.py` (new) — full Command → replay → state chain

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### §2.0 Motivation: Three Diagnostics

```
Q1: Can we delete State_index.yaml and recover from EventLog alone?
    BEFORE: NO — phase_status / plan_status are human-managed YAML fields, not events.
    AFTER:  YES — ActivatePhaseCommand → PhaseActivatedEvent → reducer sets phase_status="ACTIVE".

Q3: Can we replay any bug?
    BEFORE: NO — tautological test masks bugs; error_event_boundary uses a second write path.
    AFTER:  YES — golden scenario test + CommandRunner as sole write boundary.
```

### §2.1 Canonical Write Path (I-ES-1 final form)

```
Before Phase 5:
  CommandRunner.run()
    ↓
  handler.handle()  ──[exception]──→  error_event_boundary
                                            ↓
                                      sdd_append()  ← SECOND write path (violation)
    ↓ [success]
  EventStore.append()               ← first write path

After Phase 5:
  CommandRunner.run()
    ↓
  handler.handle()  ──[exception]──→  error_event_boundary
                                            ↓
                                      exc._sdd_error_events = [ErrorEvent(...)]
                                      raise  ← re-raise always (I-CMD-3)
    ↓ [success / re-raise caught by runner]
  self._store.append(events)        ← ONLY write path (always)

CommandRunner catches the re-raised exception:
  error_events = getattr(exc, "_sdd_error_events", [])
  if error_events:
      self._store.append(error_events, source="error_boundary")
  raise  ← re-raise original
```

No `sdd_append` call anywhere outside `EventStore.append()`. Fallback on
`EventStore.append` failure: `logging.error()` only — never a direct DB path.

### §2.2 New Commands

```
src/sdd/commands/
  activate_phase.py   ← ActivatePhaseCommand + ActivatePhaseHandler
  activate_plan.py    ← ActivatePlanCommand  + ActivatePlanHandler
```

These commands are callable by human actors (actor="human") only. They emit L1 events that
the reducer handles to set `phase_status` / `plan_status` in `SDDState`.

### §2.3 GuardContext Deduplication

```
BEFORE:
  src/sdd/guards/runner.py          — contains GuardContext (STALE copy from early Phase 3)
  src/sdd/domain/guards/context.py  — canonical GuardContext (used by CommandRunner)

AFTER:
  src/sdd/guards/runner.py          — GuardContext class removed; file kept if it contains
                                      other non-duplicate content (e.g. run_guard_pipeline
                                      helpers); imports changed to domain/guards/context
  src/sdd/domain/guards/context.py  — unchanged (canonical)
```

Removal protocol (mandatory order):
1. `grep -r "guards.runner" src/ tests/` — identify all import sites
2. Replace each import with `from sdd.domain.guards.context import GuardContext`
3. Remove `GuardContext` class from `guards/runner.py`
4. Verify no remaining references: `grep -r "guards.runner.*GuardContext" src/ tests/`

### §2.4 Reducer Invariant I-REDUCER-1

```
Unknown event_type (not in _EVENT_SCHEMA and not in _KNOWN_NO_HANDLER):
  default (strict_mode=False): NO-OP + logging.warning("Unknown event type: %s", event_type)
  strict_mode=True:            raise UnknownEventType(event_type)

This is an EXPLICIT INVARIANT, not an implementation detail.
Motivation: future phases add new event types; replay of old EventLogs must not break.

Observability note: unknown event occurrences SHOULD be counted for schema-drift detection.
Phase 5 provides only the warning log. Phase 6 (metrics layer) will add a counter/metric.
Until then, the warning log is the only signal — monitor it in production replay.
```

`UnknownEventType` is a new error class in `core/errors.py`.

### §2.5 Projections: Removing Human-Managed Field Reliance

`projections.rebuild_state()` currently reads `phase_status` and `plan_status` from the
existing `State_index.yaml` (human-managed) and writes them back unchanged. After Phase 5,
both fields are derivable from EventLog replay:

```python
# After Phase 5: rebuild_state uses compatibility mode (I-PROJ-2)
sdd_state = reduce(sdd_replay(db_path=db_path))

# Check whether activation events exist in this EventLog
has_phase_activation = sdd_state.phase_status is not None  # set by PhaseActivatedEvent handler

if has_phase_activation:
    # Full EventLog derivation — new EventLogs (Phase 5+)
    phase_status = sdd_state.phase_status
    plan_status  = sdd_state.plan_status
else:
    # Compatibility fallback — pre-Phase-5 EventLogs that lack activation events
    # YAML still contains human-managed values; use them as temporary source
    state_yaml   = read_state(state_path)
    phase_status = state_yaml.phase_status
    plan_status  = state_yaml.plan_status

rebuilt = {
    ...
    "phase": {"current": sdd_state.phase_current, "status": phase_status},
    "plan":  {"version": sdd_state.plan_version,  "status": plan_status},
    ...
}
```

**Migration note:** The compatibility fallback is explicitly temporary. Phase 8
(CLI + Kernel Stabilization) performs a one-time seeding step that emits
`PhaseActivatedEvent` / `PlanActivatedEvent` into existing EventLogs, after which
the fallback branch is unreachable and can be removed.

---

## 3. Domain Events

All event dataclasses MUST be frozen, with hashable fields only.

### PhaseActivatedEvent

Emitted by `ActivatePhaseHandler` when a human actor transitions a phase PLANNED → ACTIVE.

```python
@dataclass(frozen=True)
class PhaseActivatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseActivated"
    phase_id:   int    # the phase being activated
    actor:      str    # "human" — only human actor may emit this
    timestamp:  str    # ISO8601 UTC
```

### PlanActivatedEvent

Emitted by `ActivatePlanHandler` when a human actor transitions a plan PLANNED → ACTIVE.

```python
@dataclass(frozen=True)
class PlanActivatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PlanActivated"
    plan_version: int  # the plan version being activated
    actor:        str  # "human"
    timestamp:    str  # ISO8601 UTC
```

### C-1 Compliance (Phase 5 — BLOCKING)

`PhaseActivatedEvent` and `PlanActivatedEvent` are NEW L1 event types. Per C-1, adding them
to `V1_L1_EVENT_TYPES`, `_EVENT_SCHEMA`, and the dataclass definitions MUST happen in a
single task (T-5-01). Violation → `AssertionError` on import.

### Event Catalog (Phase 5)

| Event | Emitter | Level | Description |
|---|---|---|---|
| `PhaseActivated` | `ActivatePhaseHandler` | L1 Domain | Phase transitions PLANNED → ACTIVE |
| `PlanActivated` | `ActivatePlanHandler` | L1 Domain | Plan transitions PLANNED → ACTIVE |

### Reducer Classification

| Event type string | `_EVENT_SCHEMA` handler | Rationale |
|---|---|---|
| `"PhaseActivated"` | YES — sets `phase_status = "ACTIVE"` | State must be replay-derivable (Q1) |
| `"PlanActivated"` | YES — sets `plan_status = "ACTIVE"` | State must be replay-derivable (Q1) |

---

## 4. Types & Interfaces

### 4.1 `ActivatePhaseCommand` / `ActivatePlanCommand`

```python
@dataclass(frozen=True)
class ActivatePhaseCommand(Command):
    phase_id:   int
    actor:      str   # must be "human"

@dataclass(frozen=True)
class ActivatePlanCommand(Command):
    plan_version: int
    actor:        str   # must be "human"
```

### 4.2 `ActivatePhaseHandler` (`commands/activate_phase.py`)

```python
class ActivatePhaseHandler(CommandHandlerBase):
    """Transition phase_status PLANNED → ACTIVE by emitting PhaseActivatedEvent.

    Actor constraint: command.actor MUST be "human" (I-ACT-1).
    Guard: NormGuard must ALLOW actor="human", action="activate_phase".
    Idempotency:
      - command-level: based on command_id (I-CMD-1) — duplicate command_id → return []
      - domain rule: if phase_status already "ACTIVE" → raise AlreadyActivated (I-DOMAIN-1)
    These are distinct: command-level idempotency guards replay; domain rule guards business logic.
    A new command_id on an already-ACTIVE phase is NOT a replay — it is a domain error.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ActivatePhaseCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent(command.command_id) → return [] if command already processed (I-CMD-1)
          2. Validate: command.actor == "human" (raise InvalidActor otherwise) (I-ACT-1)
          3. Read current state: reduce(sdd_replay(self._db_path))
             If state.phase_status == "ACTIVE": raise AlreadyActivated(command.phase_id) (I-DOMAIN-1)
          4. Build PhaseActivatedEvent(phase_id, actor, timestamp=utc_now_iso())
          5. Return [PhaseActivatedEvent]  ← CommandRunner calls EventStore.append()
        """
        ...
```

### 4.3 `ActivatePlanHandler` (`commands/activate_plan.py`)

```python
class ActivatePlanHandler(CommandHandlerBase):
    """Transition plan_status PLANNED → ACTIVE by emitting PlanActivatedEvent.

    Actor constraint: command.actor MUST be "human" (I-ACT-1).
    Idempotency:
      - command-level: based on command_id (I-CMD-1) — duplicate command_id → return []
      - domain rule: if plan_status already "ACTIVE" → raise AlreadyActivated (I-DOMAIN-1)
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ActivatePlanCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent(command.command_id) → return [] if command already processed (I-CMD-1)
          2. Validate: command.actor == "human" (raise InvalidActor otherwise) (I-ACT-1)
          3. Read current state: reduce(sdd_replay(self._db_path))
             If state.plan_status == "ACTIVE": raise AlreadyActivated(command.plan_version) (I-DOMAIN-1)
          4. Build PlanActivatedEvent(plan_version, actor, timestamp=utc_now_iso())
          5. Return [PlanActivatedEvent]  ← CommandRunner calls EventStore.append()
        """
        ...
```

### 4.4 `error_event_boundary` (revised, `commands/_base.py`)

```python
def error_event_boundary(source: str) -> Callable:
    """Decorator factory for CommandHandler.handle() methods.

    Revised Phase 5 behaviour (I-ES-1 final form):
      On exception:
        1. Compute retry_count = get_error_count(self._db_path, command.command_id)
        2. Build ErrorEvent(error_type=..., source=source, recoverable=...,
                            retry_count=retry_count, context={"message": str(exc)})
        3. Attach: exc._sdd_error_events = [error_event]
        4. Re-raise always (I-CMD-3) — CommandRunner catches and appends via EventStore

      If get_error_count itself raises: log to fallback_log (stderr), set retry_count=0,
      continue to attach + re-raise. Root cause is never lost (I-CMD-3).

      No sdd_append call inside the decorator. Zero direct DB writes. (I-ES-1)

      retry_count semantics:
        retry_count is read BEFORE the ErrorEvent is written — in a concurrent context this
        creates a race: two concurrent failures may both read count=0 and both emit retry_count=0.
        retry_count is therefore best-effort and non-atomic; do not rely on exact retry
        sequencing. It is a diagnostic aid only, not a strong consistency guarantee.
    """
```

### 4.5 `CommandRunner.run()` (revised, `commands/sdd_run.py`)

```python
def run(self, command, command_str, actor="llm", action="implement_task",
        task_id=None, required_ids=(), input_paths=()):
    """
    Revised Phase 5 error path:
      ...
      try:
          events = handler.handle(command)
      except Exception as exc:
          error_events = getattr(exc, "_sdd_error_events", [])
          if error_events:
              try:
                  self._store.append(error_events, source="error_boundary")
              except Exception:
                  logging.error("EventStore.append failed for error_events; original exc follows")
          raise  # re-raise original — never suppress (I-CMD-3)

      if events:  # I-ES-6: MUST NOT call append with empty list
          self._store.append(events, source=handler_module)
      ...
    """
```

### 4.6 `UnknownEventType` error (`core/errors.py`)

```python
class UnknownEventType(SDDError):
    """Raised by EventReducer in strict_mode=True when event_type is not in
    _EVENT_SCHEMA and not in _KNOWN_NO_HANDLER.
    In default mode (strict_mode=False): NO-OP + logging.warning only.
    """
```

### 4.7 Reducer `_handle_unknown` policy (`domain/state/reducer.py`)

```python
# Inside EventReducer._reduce_one():
if event_type in self._EVENT_SCHEMA:
    self._EVENT_SCHEMA[event_type](state, event)
elif event_type in self._KNOWN_NO_HANDLER:
    pass  # intentional NO-OP; known event without state change
else:
    # I-REDUCER-1: unknown event type
    logging.warning("EventReducer: unknown event_type=%r — skipping (NO-OP)", event_type)
    if self._strict_mode:
        raise UnknownEventType(event_type)
```

### 4.8 New reducer handlers

**Non-mutation rule (I-REDUCER-2):** Handlers MUST NOT mutate the input state in-place.
Each handler MUST produce a new state object. Exact mechanism depends on the `PartitionState`
model already established in Phase 2: if `PartitionState` is a mutable dict, handlers must
work on a deep copy; if it is a dataclass, use `dataclasses.replace()`. The invariant is
behavioural — external callers must never observe mutation of the object passed in.

```python
@_handler("PhaseActivated")
def _handle_phase_activated(state: PartitionState, event: PhaseActivatedEvent) -> PartitionState:
    # I-REDUCER-2: produce new state, do not mutate input
    new_data = copy.deepcopy(state.data)
    new_data["phase"]["status"] = "ACTIVE"
    return state.copy(data=new_data)  # or dataclasses.replace(state, data=new_data)

@_handler("PlanActivated")
def _handle_plan_activated(state: PartitionState, event: PlanActivatedEvent) -> PartitionState:
    new_data = copy.deepcopy(state.data)
    new_data["plan"]["status"] = "ACTIVE"
    return state.copy(data=new_data)
```

---

## 5. Invariants

### New Invariants (Phase 5)

| ID | Statement | Enforced by |
|---|---|---|
| I-ES-1 (final) | `EventStore.append()` is the ONLY write path to the EventLog — including the error path. `error_event_boundary` attaches `ErrorEvent` to the exception; `CommandRunner` appends it via `EventStore`. No `sdd_append` call exists outside `infra/event_store.py`. | `tests/unit/commands/test_base.py` — `test_error_boundary_no_direct_sdd_append`; `tests/unit/commands/test_sdd_run.py` — `test_runner_appends_error_events_via_store` |
| I-ES-6 | `EventStore.append()` MUST NOT be called with an empty event list. `CommandRunner.run()` MUST check `if events:` before calling `self._store.append(events, ...)` on the success path. | `tests/unit/commands/test_sdd_run.py` — `test_runner_no_append_on_empty_events` |
| I-REDUCER-1 | Unknown `event_type` (not in `_EVENT_SCHEMA` and not in `_KNOWN_NO_HANDLER`): default → NO-OP + `logging.warning`; `strict_mode=True` → raise `UnknownEventType`. This is an explicit invariant guaranteeing forward-compatible replay. | `tests/unit/domain/state/test_reducer.py` — `test_unknown_event_noop_default`, `test_unknown_event_raises_strict` |
| I-REDUCER-2 | Reducer handlers MUST NOT mutate the input state in-place. Each handler MUST produce and return a new state object. Callers must never observe mutation of the state object they passed in. | `tests/unit/domain/state/test_reducer.py` — `test_handler_does_not_mutate_input` |
| I-SCHEMA-1 | Any addition of a reducer handler (new event type) requires that replay of all prior `schema_version` values remains correct. Phase 5 handlers (`PhaseActivated`, `PlanActivated`) MUST NOT break replay of Phase 0–4 events. | `tests/unit/domain/state/test_reducer.py` — `test_replay_old_events_after_phase5_handlers` |
| I-ACT-1 | `ActivatePhaseHandler` and `ActivatePlanHandler` accept only `actor == "human"`; any other value raises `InvalidActor`. NormGuard must have explicit ALLOW entry for `(actor="human", action="activate_phase")` and `(actor="human", action="activate_plan")`. | `tests/unit/commands/test_activate_phase.py` — `test_llm_actor_rejected`; norm catalog |
| I-DOMAIN-1 | Activating an already-ACTIVE phase or plan MUST raise `AlreadyActivated`, not silently return `[]`. Command-level idempotency (I-CMD-1) guards `command_id` replay only; it does not substitute for domain state validation. A new `command_id` on an already-ACTIVE phase is a domain error, not a replay. | `tests/unit/commands/test_activate_phase.py` — `test_already_active_raises`; `tests/unit/commands/test_activate_plan.py` — `test_already_active_plan_raises` |
| I-PROJ-1 | For new EventLogs (Phase 5+), `projections.rebuild_state()` derives `phase_status` and `plan_status` from `reduce(sdd_replay())` — NOT from reading `State_index.yaml`. The YAML is a pure projection; no human-managed field is copied from it during rebuild. | `tests/unit/infra/test_projections.py` — `test_rebuild_state_derives_from_eventlog` |
| I-PROJ-2 | `projections.rebuild_state()` MUST support compatibility mode: if no `PhaseActivatedEvent` exists in the EventLog (pre-Phase-5 log), fall back to reading `phase_status` / `plan_status` from the existing YAML file. The fallback is explicitly temporary; it is removed in Phase 8 after seeding. | `tests/unit/infra/test_projections.py` — `test_rebuild_state_compat_mode_no_activation_events` |

### Preserved Invariants (referenced)

| ID | Statement |
|---|---|
| I-CMD-3 | `error_event_boundary` NEVER suppresses exceptions; original exception always re-raised |
| I-ES-2 | Handlers emit events ONLY — no file writes inside `handle()` |
| I-ES-4 | Projections rebuilt AFTER `EventStore.append()` succeeds |
| I-ST-9 | `SDDState` schema identical between YAML read and reducer replay |
| C-1 | `V1_L1_EVENT_TYPES`, `_EVENT_SCHEMA`, and dataclass definition modified in a single task |

### §PHASE-INV (must ALL be PASS before Phase 5 can be COMPLETE)

```
[I-ES-1 (final), I-ES-6,
 I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1,
 I-ACT-1, I-DOMAIN-1,
 I-PROJ-1, I-PROJ-2,
 I-CMD-3, I-ES-2, I-ES-4, C-1]
```

---

## 6. Pre/Post Conditions

### ActivatePhaseHandler.handle(command: ActivatePhaseCommand)

**Pre:**
- `command.actor == "human"`
- `command.phase_id` identifies a known phase
- EventLog accessible at `self._db_path`

**Post:**
- `command_id` already in EventLog → return `[]` — command replay (I-CMD-1)
- `actor != "human"` → raise `InvalidActor`; `ErrorEvent` appended by CommandRunner (I-ACT-1)
- `phase_status` already `"ACTIVE"` → raise `AlreadyActivated` — domain error, not idempotency (I-DOMAIN-1)
- Success: `PhaseActivatedEvent` in EventLog; `phase_status` derivable as `"ACTIVE"` via replay (Q1)

### CommandRunner.run() — error path (revised)

**Pre:**
- `handler.handle(command)` raises any exception

**Post:**
- `exc._sdd_error_events` contains exactly one `ErrorEvent` (set by `error_event_boundary`)
- `CommandRunner` calls `self._store.append(error_events, source="error_boundary")` — the
  sole DB write for the error path
- If `EventStore.append` itself raises: `logging.error()` emitted; original exception re-raised
- Original exception always propagates (I-CMD-3); never swallowed

### projections.rebuild_state(db_path, state_path)

**Pre:**
- `db_path` is a valid DuckDB EventLog
- EventLog contains at least `PhaseInitializedEvent` (Phase 1 minimal) for phase_current
- After Phase 5 migration: EventLog also contains `PhaseActivatedEvent` if phase is ACTIVE

**Post:**
- `State_index.yaml` at `state_path` reflects `reduce(sdd_replay(db_path))`
- `phase_status` and `plan_status` in the written YAML match the reducer output (I-PROJ-1)
- No field is copied from the prior YAML content

---

## 7. Use Cases

### UC-5-1: Human activates Phase 5

**Actor:** Human
**Trigger:** Human runs `sdd activate-phase 5` (or directly submits `ActivatePhaseCommand`)
**Pre:** Phase 5 PLANNED in Phases_index.md; no `PhaseActivated` event for phase_id=5 in EventLog
**Steps:**
1. Build `ActivatePhaseCommand(command_id=uuid(), phase_id=5, actor="human")`
2. `CommandRunner.run(command, "activate phase 5", actor="human", action="activate_phase")`
3. NormGuard: ALLOW for `(actor="human", action="activate_phase")`
4. `ActivatePhaseHandler.handle(command)`:
   a. `_check_idempotent` → False
   b. Validate `actor == "human"` → OK
   c. Build `PhaseActivatedEvent(phase_id=5, actor="human", timestamp=...)`
   d. Return `[PhaseActivatedEvent]`
5. `CommandRunner`: `EventStore.append([PhaseActivatedEvent])`
6. `projections.rebuild_state()` → `State_index.yaml` now shows `phase_status: ACTIVE`
**Post:** Q1 satisfied — state derivable from EventLog; YAML is derived projection

### UC-5-2: Error boundary no longer writes directly to DB

**Actor:** Any handler that raises
**Trigger:** `CompleteTaskHandler.handle()` raises `MissingContext`
**Pre:** Phase 5 complete (`error_event_boundary` revised)
**Steps:**
1. `error_event_boundary` fires:
   a. `retry_count = get_error_count(db_path, command.command_id)` → 0
   b. Build `ErrorEvent(error_type="MissingContext", retry_count=0, ...)`
   c. `exc._sdd_error_events = [ErrorEvent]`
   d. Re-raise `MissingContext`
2. `CommandRunner.run()` catches `MissingContext`:
   a. `error_events = getattr(exc, "_sdd_error_events", [ErrorEvent])`
   b. `self._store.append(error_events, source="error_boundary")`  ← sole write path
   c. Re-raise `MissingContext`
**Post:** `ErrorEvent` in EventLog via `EventStore`; no direct `sdd_append` call; I-ES-1 holds

### UC-5-3: Unknown event type during replay

**Actor:** `EventReducer` (called by `reduce(sdd_replay(...))`)
**Trigger:** EventLog contains `"FuturePhase9Event"` (added in Phase 9), replayed in Phase 5 context
**Pre:** `strict_mode=False` (default for production)
**Steps:**
1. `EventReducer._reduce_one(state, event)` — `event_type = "FuturePhase9Event"`
2. Not in `_EVENT_SCHEMA`, not in `_KNOWN_NO_HANDLER`
3. `logging.warning("EventReducer: unknown event_type='FuturePhase9Event' — skipping")`
4. NO-OP; state unchanged
**Post:** Replay completes without raising; I-REDUCER-1 upheld; forward-compatible

### UC-5-4: Full Command → replay → state integration test

**Actor:** Test suite
**Trigger:** `test_full_chain` in `tests/integration/test_full_chain.py`
**Pre:** Fresh temporary DuckDB
**Steps:**
1. `sdd_append("PhaseInitialized", {phase_id=5, tasks_total=3, ...}, db_path=test_db)`
2. `runner = CommandRunner(event_store, ...)`
3. `events = runner.run(ActivatePhaseCommand(phase_id=5, actor="human"), ...)`
4. Assert `any(isinstance(e, PhaseActivatedEvent) for e in events)`
5. `state = reduce(sdd_replay(db_path=test_db))`
6. Assert `state.phase_status == "ACTIVE"`
7. Assert `state.phase_current == 5`
**Post:** Q3 satisfied — full chain verifiable; not a tautological test

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|---|---|---|
| BC-CORE (`core/events.py`) | BC-COMMANDS → | New event dataclasses; C-1 enforcement |
| BC-CORE (`core/errors.py`) | BC-COMMANDS → | `InvalidActor`, `UnknownEventType` (new); existing `SDDError` subtypes |
| BC-STATE (`domain/state/reducer.py`) | BC-COMMANDS → | New handlers for `PhaseActivated`, `PlanActivated`; I-REDUCER-1 |
| BC-INFRA (`infra/projections.py`) | BC-COMMANDS → | `rebuild_state` derives from EventLog replay (I-PROJ-1) |
| BC-COMMANDS (`commands/sdd_run.py`) | self | `CommandRunner` revised error path; sole `EventStore.append` caller |
| BC-COMMANDS (`commands/_base.py`) | self | `error_event_boundary` revised: attach, not append |
| BC-GUARDS (`guards/runner.py`) | BC-COMMANDS → | `GuardContext` import updated to `domain/guards/context` |

### Migration Safety

Phase 5 introduces a semantic change in `projections.rebuild_state()`. During Phase 8
(CLI + Kernel Stabilization), existing EventLogs that pre-date Phase 5 will need a seeding
step to emit `PhaseActivatedEvent` / `PlanActivatedEvent` for the current active phase.
This migration is **out of scope for Phase 5** — the projection change in Phase 5 is safe
for new EventLogs. Existing `.sdd/tools/*.py` tooling continues to write `State_index.yaml`
directly (as before) until Phase 8 wires the new commands in.

### Norm Catalog Updates Required

The `norm_catalog.yaml` must be extended before `ActivatePhaseHandler` / `ActivatePlanHandler`
can pass the `NormGuard` check:

```yaml
# .sdd/norms/norm_catalog.yaml — additions for Phase 5
- norm_id: NORM-ACTOR-ACTIVATE-PHASE
  actor: human
  action: activate_phase
  result: allow
  rationale: "Phase activation is a human-only action (§0.5 Status Transition Table)"

- norm_id: NORM-ACTOR-ACTIVATE-PLAN
  actor: human
  action: activate_plan
  result: allow
  rationale: "Plan activation is a human-only action (§0.5 Status Transition Table)"
```

---

## 9. Verification

| # | Test File | Key Tests | Invariant(s) |
|---|---|---|---|
| 1 | `tests/unit/core/test_events_phase5.py` | `test_phase_activated_event_is_frozen`, `test_plan_activated_event_is_frozen`, `test_c1_assert_phase5_import`, `test_phase_activated_in_v1_l1_types`, `test_reducer_handles_phase_activated`, `test_reducer_handles_plan_activated` | C-1, I-SCHEMA-1 |
| 2 | `tests/unit/domain/state/test_reducer.py` | `test_unknown_event_noop_default`, `test_unknown_event_logs_warning`, `test_unknown_event_raises_strict`, `test_replay_old_events_after_phase5_handlers`, `test_replay_golden_scenario`, `test_replay_is_deterministic`, `test_handler_does_not_mutate_input` | I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1 |
| 3 | `tests/unit/commands/test_base.py` | `test_error_boundary_no_direct_sdd_append`, `test_error_boundary_attaches_to_exception`, `test_error_boundary_reraises_always`, `test_retry_count_is_best_effort_note` | I-ES-1 (final), I-CMD-3 |
| 4 | `tests/unit/commands/test_sdd_run.py` | `test_runner_appends_error_events_via_store`, `test_runner_catches_and_reraises`, `test_runner_logs_on_store_failure`, `test_runner_no_append_on_empty_events` | I-ES-1 (final), I-ES-6, I-CMD-3 |
| 5 | `tests/unit/commands/test_activate_phase.py` | `test_activate_phase_emits_event`, `test_activate_phase_command_idempotent`, `test_already_active_raises`, `test_llm_actor_rejected`, `test_invalid_actor_raises` | I-ACT-1, I-CMD-1, I-DOMAIN-1 |
| 6 | `tests/unit/commands/test_activate_plan.py` | `test_activate_plan_emits_event`, `test_activate_plan_command_idempotent`, `test_already_active_plan_raises`, `test_llm_actor_rejected_plan` | I-ACT-1, I-CMD-1, I-DOMAIN-1 |
| 7 | `tests/unit/guards/test_no_duplicate_guard_context.py` | `test_guards_runner_imports_from_domain`, `test_no_stale_guard_context_in_runner` | deduplication |
| 8 | `tests/unit/infra/test_projections.py` | `test_rebuild_state_derives_from_eventlog`, `test_rebuild_state_no_yaml_copy`, `test_rebuild_after_phase_activated`, `test_rebuild_state_compat_mode_no_activation_events` | I-PROJ-1, I-PROJ-2 |
| 9 | `tests/integration/test_full_chain.py` | `test_full_chain_activate_phase`, `test_full_chain_phase_status_derivable`, `test_replay_deterministic_after_commands` | Q1, Q3, I-ES-1 (final) |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Extension point for `V1_L1_EVENT_TYPES` (`register_l1_event_type`) | Phase 7 |
| CLI entry points for `activate-phase`, `activate-plan` | Phase 8 |
| Upcasters / full schema migration strategy | Phase 8/9 |
| Snapshot + tail-replay optimization for CommandRunner | Future |
| Seeding existing EventLogs with `PhaseActivated` / `PlanActivated` events | Phase 8 |
| API polish, naming changes, refactoring outside the five problems above | Phase 7/8 |
| Parallel execution engine | Phase 7 |
| Hooks wiring (`log_tool.py`, `log_bash.py`) | Phase 8 |
| Query, Metrics & Reporting Python modules | Phase 6 |

---

## Appendix: Task Breakdown (5 tasks)

| Task | Outputs | Produces Invariants | Requires Invariants |
|------|---------|---------------------|---------------------|
| T-5-01 | `core/events.py` (+PhaseActivatedEvent, +PlanActivatedEvent, +V1_L1_EVENT_TYPES entries); `domain/state/reducer.py` (+_handle_phase_activated, +_handle_plan_activated — non-mutating, I-REDUCER-2); `commands/activate_phase.py` (ActivatePhaseCommand + ActivatePhaseHandler with AlreadyActivated check); `commands/activate_plan.py` (ActivatePlanCommand + ActivatePlanHandler with AlreadyActivated check); `core/errors.py` (+InvalidActor, +AlreadyActivated); `.sdd/norms/norm_catalog.yaml` (+NORM-ACTOR-ACTIVATE-PHASE, +NORM-ACTOR-ACTIVATE-PLAN) | C-1, I-ACT-1, I-DOMAIN-1, I-REDUCER-2, I-SCHEMA-1 (partial) | I-CMD-2, I-ERR-1, I-ES-1, I-EL-9 |
| T-5-02 | `commands/_base.py` (error_event_boundary: attach events to exception, no sdd_append); `commands/sdd_run.py` (CommandRunner.run: try/except catches error_events, appends via EventStore, re-raises) | I-ES-1 (final) | I-CMD-3, I-ERR-1 |
| T-5-03 | `guards/runner.py` (GuardContext class removed; imports updated to domain/guards/context); all import sites updated per grep output | deduplication | — |
| T-5-04 | `domain/state/reducer.py` (+logging.warning for unknown events, +strict_mode support); `core/errors.py` (+UnknownEventType) | I-REDUCER-1 | — |
| T-5-05 | `tests/unit/core/test_events_phase5.py`; `tests/unit/domain/state/test_reducer.py` (+golden, +determinism, +replay_old_events, +handler_does_not_mutate_input); `tests/unit/commands/test_base.py` (+no_direct_sdd_append, +attaches_to_exception); `tests/unit/commands/test_sdd_run.py` (+runner_appends_via_store, +no_append_on_empty_events); `tests/unit/commands/test_activate_phase.py` (+already_active_raises); `tests/unit/commands/test_activate_plan.py` (+already_active_plan_raises); `tests/unit/guards/test_no_duplicate_guard_context.py`; `tests/unit/infra/test_projections.py` (+derives_from_eventlog, +compat_mode_no_activation_events); `tests/integration/test_full_chain.py` | I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1, I-ACT-1, I-DOMAIN-1, I-PROJ-1, I-PROJ-2, I-ES-1 (final), I-ES-6, Q1, Q3 | T-5-01, T-5-02, T-5-03, T-5-04 |
