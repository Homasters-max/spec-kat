# Spec_v2_State — Phase 2: State & Context

Status: Draft
Baseline: Spec_v1_Foundation.md (BC-CORE, BC-INFRA, I-PK-1..5, I-EL-1..12, I-CMD-1a, I-M-1)

---

## 0. Goal

Build the domain state layer for `src/sdd/` with:
- Pure event-sourced reducer that processes ONLY `source="runtime"`, `level="L1"` events (D-2, I-EL-3)
- YAML state persistence: read/write/sync/init for `State_index.yaml`; EventLog is the SSOT for task-level state (I-ST-6)
- TaskSet markdown parser extended with `spec_refs`, `produces_invariants`, `requires_invariants` fields (D-11)
- Staged context builder `build_context.py` (SEM-9, D-6) for coder and planner agents

This phase produces no CLI entry points and no command handlers. It is the domain substrate
that Phase 3 (guards) and Phase 4 (commands) build on.

### 0.1 Mental Model

```
Truth   = EventLog               ← sole authoritative source
State   = reduce(EventLog)       ← pure deterministic projection
YAML    = cache(State)           ← may be stale; refreshed by sync_state()
TaskSet = plan                   ← tasks_total + display of status (NOT truth)
Context = f(State, Plan, Spec)   ← deterministic function; no I/O side effects
```

**Consequence:** `TaskSet.status` field (TODO/DONE) is a display annotation only. It is NOT a
source of truth for task completion. The EventLog is the sole source. `sync_state()` cross-validates
the two and raises `Inconsistency` if they diverge — this is the reactive safety net. The mental
model eliminates the class of split-brain bugs where TaskSet and EventLog disagree silently.

---

## 1. Scope

### In-Scope

- BC-STATE: `src/sdd/domain/state/` — SDDState type + state_hash, reducer with diagnostics, yaml_state, sync, init_state
- BC-TASKS: `src/sdd/domain/tasks/parser.py` — Task dataclass + strict TaskSet markdown parser
- BC-CONTEXT: `src/sdd/context/build_context.py` — staged context loader with context_hash
- Invariants I-EL-3, I-ST-1..9, I-TS-1..3, I-CTX-1..6
- 80%+ test coverage for all new modules

### Concurrency Model

Unchanged from Phase 1: single-process, single-writer. Reducer is called synchronously
within a single process. No thread safety required.

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-STATE: `src/sdd/domain/state/`

```
src/sdd/domain/state/
  __init__.py       ← re-exports: SDDState, EMPTY_STATE, ReducerDiagnostics,
                      reduce, reduce_with_diagnostics, read_state, write_state,
                      compute_state_hash, sync_state, init_state,
                      StateDerivationCompletedEvent
  reducer.py        ← EventReducer, reduce(), reduce_with_diagnostics();
                      filters source+level (I-EL-3); internal set for dedup (R4)
  yaml_state.py     ← read_state(path) → SDDState; write_state(state, path)
  sync.py           ← sync_state(..., replay_fn): EventLog-authoritative projection (I-ST-6)
  init_state.py     ← init_state(phase_id, taskset_path, state_path, emit)
```

### BC-TASKS: `src/sdd/domain/tasks/`

```
src/sdd/domain/tasks/
  __init__.py       ← re-exports: Task, parse_taskset
  parser.py         ← Task dataclass; parse_taskset(path) → list[Task] (strict validation I-TS-3)
```

### BC-CONTEXT: `src/sdd/context/`

```
src/sdd/context/
  __init__.py       ← re-exports: build_context, ContextDepth, TOKEN_BUDGET
  build_context.py  ← build_context(agent_type, task_id, depth, config) → str
                      includes context_hash header (I-CTX-5); deterministic layer order (I-CTX-6)
```

### Projection Hierarchy (D-2, I-ST-6)

```
EventLog (sdd_replay, level=L1, source=runtime)
    │
    ▼  reduce()                 ← authoritative for tasks_completed, tasks_done_ids
SDDState (in-memory)

TaskSet_vN.md
    │
    ▼  parse_taskset()          ← source of tasks_total (planning record)
    Cross-validate with EventLog ← Inconsistency if DONE-count mismatches

State_index.yaml
    │
    ▼  read_state / write_state ← YAML projection (cache); may be stale
    ▼  sync_state()             ← refresh projection from EventLog + TaskSet
    ▼  phase_status/plan_status ← human-managed in YAML until Phase 7
```

### Dependencies

```text
BC-STATE   → BC-TASKS  : sync/init read TaskSet via parse_taskset
BC-STATE   → BC-INFRA  : sync.py consumes sdd_replay via injected replay_fn (default);
                          sync/init emit via injected emit callable (sdd_append)
BC-STATE   → BC-CORE   : imports DomainEvent, SDDError subclasses
BC-TASKS   → stdlib    : re, dataclasses (pure I/O; no infra dep)
BC-CONTEXT → BC-STATE  : reads SDDState via read_state
BC-CONTEXT → BC-TASKS  : reads task context via parse_taskset
BC-CONTEXT → BC-INFRA  : reads config via load_config
BC-CONTEXT → stdlib    : pathlib, hashlib (no infra writes — pure reads)
```

---

## 3. Domain Events

### StateDerivationCompletedEvent

Emitted by `sync.py` and `init_state.py` after writing `State_index.yaml`.

> **Classification note:** `StateDerivationCompleted` is retained as **L1** per `V1_L1_EVENT_TYPES`
> (immutable, I-EL-6) to preserve audit retention forever. However, the reducer has **no
> handler** for this event — it is a projection signal, not a domain truth. Task-level counts
> are derived from `TaskImplemented` events (I-ST-6). The reducer counts this event in
> `ReducerDiagnostics.events_known_no_handler`.

```python
@dataclass(frozen=True)
class StateDerivationCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "StateDerivationCompleted"
    phase_id: str           # e.g. "2"
    tasks_total: int
    tasks_completed: int
    derived_from: str       # "eventlog" (sync_state) | "initial" (init_state)
    timestamp: str          # ISO8601 UTC
```

### PhaseInitialized Event (payload definition)

`PhaseInitialized` is already in `V1_L1_EVENT_TYPES`. Phase 2 defines its canonical payload:

```python
# Emitted by init_state.py after creating State_index.yaml
payload = {
    "phase_id":    str,   # e.g. "2"       — required
    "tasks_total": int,   # planned count  — required
    "plan_version":int,   # = phase_id     — required
    "actor":       str,   # "llm"          — required
    "timestamp":   str,   # ISO8601 UTC    — required
}
```

### Event Catalog (Phase 2 — new emitters)

| Event | Emitter | Level | Description |
|-------|---------|-------|-------------|
| `StateDerivationCompleted` | `domain/state/sync.py`, `domain/state/init_state.py` | L1 (audit only — no reducer handler) | YAML projection written |
| `PhaseInitialized` | `domain/state/init_state.py` | L1 | Fresh phase initialised; payload now formally defined |

**Reducer-consumed events (L1 runtime — handler registered):**

| Event | Reducer handler | Effect on SDDState |
|-------|----------------|-------------------|
| `PhaseInitialized` | `_handle_phase_initialized` | sets `phase_current`, `phase_status=ACTIVE`, `plan_version`, `tasks_version` |
| `TaskImplemented` | `_handle_task_implemented` | appends `task_id` to `tasks_done_ids` (dedup); increments `tasks_completed` |
| `TaskValidated` | `_handle_task_validated` | updates `invariants_status` or `tests_status` per payload |
| `PhaseCompleted` | `_handle_phase_completed` | sets `phase_status=COMPLETE`, `plan_status=COMPLETE` |

**L1 events with no reducer handler (known but intentionally skipped):**

| Event | Reason |
|-------|--------|
| `StateDerivationCompleted` | Projection signal — not domain truth (R2) |
| `DecisionRecorded`, `SpecApproved`, `PlanActivated`, `SDDEventRejected`, `ExecutionWrapperAccepted`, `ExecutionWrapperRejected`, `TestRunCompleted`, `TaskRetryScheduled`, `TaskFailed` | Handled in later phases or governance-only |

---

## 4. Types & Interfaces

### 4.1 SDDState (`domain/state/reducer.py`)

```python
import hashlib, json
from dataclasses import dataclass, field, asdict
from typing import ClassVar

@dataclass(frozen=True)
class SDDState:
    # --- Derived fields: authoritative source = EventLog via reduce() ---
    phase_current: int
    plan_version: int
    tasks_version: int
    tasks_total: int               # from TaskSet (planning record)
    tasks_completed: int           # from EventLog via reduce() (I-ST-6)
    tasks_done_ids: tuple[str, ...]  # from EventLog; sorted, no duplicates (I-ST-6)
    invariants_status: str         # "UNKNOWN" | "PASS" | "FAIL"
    tests_status: str              # "UNKNOWN" | "PASS" | "FAIL"
    last_updated: str              # ISO8601 UTC
    schema_version: int            # = 1
    snapshot_event_id: int | None  # seq of last event folded into base (None = full replay)

    # --- Human-managed fields: YAML-only; NOT included in state_hash (I-ST-11) ---
    # These remain human-controlled until Phase 7 introduces PhaseActivated events.
    phase_status: str              # "PLANNED" | "ACTIVE" | "COMPLETE"
    plan_status: str               # "PLANNED" | "ACTIVE" | "COMPLETE"

    state_hash: str = field(default="", init=False)  # computed in __post_init__ (I-ST-8)

    # Reducer logic version — included in state_hash so reducer changes are detectable (I-ST-11).
    # MUST be incremented whenever handler logic changes (new handler, changed behaviour).
    REDUCER_VERSION: ClassVar[int] = 1

    # Human-managed fields excluded from state_hash (I-ST-11).
    _HUMAN_FIELDS: ClassVar[frozenset[str]] = frozenset({"phase_status", "plan_status", "state_hash"})

    def __post_init__(self) -> None:
        # state_hash covers derived fields + REDUCER_VERSION only (I-ST-8, I-ST-11).
        data = {k: v for k, v in asdict(self).items() if k not in self._HUMAN_FIELDS}
        data["reducer_version"] = self.REDUCER_VERSION
        h = hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()
        object.__setattr__(self, "state_hash", h)  # frozen-safe mutation


def _make_empty_state() -> SDDState:
    return SDDState(
        phase_current=0, plan_version=0, tasks_version=0,
        tasks_total=0, tasks_completed=0, tasks_done_ids=(),
        invariants_status="UNKNOWN", tests_status="UNKNOWN",
        last_updated="", schema_version=1, snapshot_event_id=None,
        phase_status="PLANNED", plan_status="PLANNED",
    )

EMPTY_STATE: SDDState = _make_empty_state()  # state_hash auto-computed


def compute_state_hash(state: SDDState) -> str:
    """Re-derive hash from derived fields only (for verification in read_state). Pure function."""
    data = {k: v for k, v in asdict(state).items() if k not in SDDState._HUMAN_FIELDS}
    data["reducer_version"] = SDDState.REDUCER_VERSION
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()
```

### 4.2 ReducerDiagnostics (`domain/state/reducer.py`)

```python
@dataclass(frozen=True)
class ReducerDiagnostics:
    events_total: int               # total events in input list
    events_filtered_source: int     # skipped: event_source != "runtime"
    events_filtered_level: int      # skipped: level != "L1"
    events_processed: int           # actually handled by a registered handler
    events_known_no_handler: int    # L1 runtime events with no registered handler
    events_unknown_type: int        # I-ST-7: unrecognised event_type — see R3
```

### 4.3 EventReducer + reduce (`domain/state/reducer.py`)

```python
class UnknownEventType(SDDError):
    """Raised by reduce() when strict_mode=True and an unrecognised event_type is encountered."""


class EventReducer:
    """Pure stateless reducer. No I/O, no side effects (I-ST-2).
    All public methods are pure functions of their arguments.
    
    Internal implementation note: uses set[str] for dedup during fold;
    converts to sorted tuple[str, ...] at result construction (I-TS-2 / O(1) ops — R4).
    """

    # Known L1 types intentionally without a handler (not unknown — I-ST-10).
    # Every L1 event type MUST appear either here or in a registered handler.
    # Add new L1 types here if they have no reducer effect; never leave an L1 type unclassified.
    _KNOWN_NO_HANDLER: frozenset[str] = frozenset({
        "StateDerivationCompleted",
        "DecisionRecorded", "SpecApproved", "PlanActivated", "SDDEventRejected",
        "ExecutionWrapperAccepted", "ExecutionWrapperRejected",
        "TestRunCompleted", "TaskRetryScheduled", "TaskFailed",
    })

    # Minimal event schema registry: required payload fields per handled event type.
    # Used for payload validation in strict_mode and by test_all_l1_events_classified (I-ST-10).
    _EVENT_SCHEMA: ClassVar[dict[str, frozenset[str]]] = {
        "PhaseInitialized": frozenset({"phase_id", "tasks_total", "plan_version", "actor", "timestamp"}),
        "TaskImplemented":  frozenset({"task_id", "phase_id"}),
        "TaskValidated":    frozenset({"task_id", "phase_id", "result"}),
        "PhaseCompleted":   frozenset({"phase_id"}),
    }

    def reduce(
        self,
        events: list[dict],
        strict_mode: bool = False,
    ) -> SDDState:
        """Fold events onto EMPTY_STATE.
        Filter: event_source == "runtime" AND level == "L1" (I-EL-3).
        Precondition: events MUST be sorted by seq ASC (I-EL-13). sdd_replay() guarantees
        this via I-PK-3. Caller is responsible when passing a custom list.
        Unknown event_type: counted in diagnostics; raises UnknownEventType if strict_mode=True (I-ST-7).
        """
        state, _ = self._fold(EMPTY_STATE, events, strict_mode=strict_mode)
        return state

    def reduce_incremental(
        self,
        base: SDDState,
        events: list[dict],
        strict_mode: bool = False,
    ) -> SDDState:
        """Apply new events on top of an existing base state (optimisation path).
        Same filter rules as reduce() (I-EL-3).
        Satisfies I-ST-9: reduce(all) == reduce_incremental(EMPTY_STATE, all).
        """
        state, _ = self._fold(base, events, strict_mode=strict_mode)
        return state

    def reduce_with_diagnostics(
        self,
        events: list[dict],
        strict_mode: bool = False,
    ) -> tuple[SDDState, ReducerDiagnostics]:
        """Same as reduce() but also returns ReducerDiagnostics."""
        return self._fold(EMPTY_STATE, events, strict_mode=strict_mode)

    def _fold(
        self,
        base: SDDState,
        events: list[dict],
        strict_mode: bool,
    ) -> tuple[SDDState, ReducerDiagnostics]: ...


# Module-level convenience functions (preferred API):
def reduce(events: list[dict], strict_mode: bool = False) -> SDDState:
    return EventReducer().reduce(events, strict_mode=strict_mode)

def reduce_with_diagnostics(
    events: list[dict], strict_mode: bool = False
) -> tuple[SDDState, ReducerDiagnostics]:
    return EventReducer().reduce_with_diagnostics(events, strict_mode=strict_mode)
```

### 4.4 yaml_state (`domain/state/yaml_state.py`)

```python
def read_state(path: str) -> SDDState:
    """Parse State_index.yaml → SDDState.
    Raises MissingState if file absent.
    tasks_done_ids: YAML list → tuple[str, ...].
    state_hash: recomputed from parsed fields and verified against stored value.
    Raises Inconsistency if stored hash != recomputed hash (detects corrupted YAML).
    """
    ...

def write_state(state: SDDState, path: str) -> None:
    """Serialise SDDState → State_index.yaml via atomic_write (I-PK-5).
    Preserves header comments. tasks_done_ids written as YAML list.
    state_hash written as a comment for human reference: # state_hash: <hex>
    """
    ...
```

### 4.5 sync_state (`domain/state/sync.py`)

```python
from sdd.infra.event_log import sdd_replay as _default_replay

def sync_state(
    taskset_path: str,
    state_path: str,
    emit: Callable[[DomainEvent], None],
    replay_fn: Callable[[], list[dict]] = _default_replay,  # injectable for tests
) -> SDDState:
    """Refresh YAML projection from EventLog + TaskSet (I-ST-6).

    Algorithm:
      1. authoritative = reduce(replay_fn())
         → authoritative.tasks_completed, tasks_done_ids from EventLog (SSOT)
      2. tasks = parse_taskset(taskset_path)
         → tasks_total = len(tasks); taskset_done = count(DONE)
      3. Cross-validate: taskset_done != authoritative.tasks_completed
         → raise Inconsistency (manual YAML edit without corresponding event)
      4. Build new_state: tasks.* from authoritative; tasks_total from TaskSet;
         phase/plan/inv/tests fields preserved from existing State_index.yaml
         (or authoritative values if state absent — first sync)
      5. write_state(new_state, state_path)
      6. emit(StateDerivationCompletedEvent(..., derived_from="eventlog"))

    No direct duckdb.connect calls (I-EL-9): replay_fn wraps sdd_replay.
    """
    ...
```

### 4.6 init_state (`domain/state/init_state.py`)

```python
def init_state(
    phase_id: int,
    taskset_path: str,
    state_path: str,
    emit: Callable[[DomainEvent], None],
) -> SDDState:
    """Create fresh State_index.yaml for a new phase (§K.1 Init State N).

    Precondition: state_path MUST NOT exist (raises InvalidState if present).

    Algorithm:
      1. parse_taskset(taskset_path) → tasks
         → tasks_total = len(tasks)
         → initial done_ids from DONE tasks (normally empty at phase start)
      2. Build SDDState: phase_current=phase_id, phase_status=ACTIVE,
         plan_version=phase_id, plan_status=ACTIVE, tasks_version=phase_id,
         tasks_total=len(tasks), tasks_completed=count(DONE),
         invariants_status=UNKNOWN, tests_status=UNKNOWN
      3. write_state(state, state_path)
      4. emit(PhaseInitializedEvent(phase_id=str(phase_id), tasks_total=len(tasks), ...))
      5. emit(StateDerivationCompletedEvent(..., derived_from="initial"))

    Note: init_state does NOT call replay_fn — EventLog is empty for a new phase.
    """
    ...
```

### 4.7 Task dataclass (`domain/tasks/parser.py`)

```python
@dataclass(frozen=True)
class Task:
    task_id: str                             # e.g. "T-201"
    title: str
    status: str                              # "TODO" | "DONE"
    spec_section: str                        # e.g. "Spec_v2 §3.1"
    inputs: tuple[str, ...]                  # exact file paths
    outputs: tuple[str, ...]                 # exact file paths
    checks: tuple[str, ...]                  # validation commands
    spec_refs: tuple[str, ...]               # e.g. ("Spec_v2 §3", "I-EL-3") — may be ()
    produces_invariants: tuple[str, ...]     # e.g. ("I-EL-3", "I-ST-2")    — may be ()
    requires_invariants: tuple[str, ...]     # e.g. ("I-PK-2",)             — may be ()


def parse_taskset(path: str) -> list[Task]:
    """Parse TaskSet_vN.md markdown → list[Task].
    Deterministic: same file → identical result (I-TS-2).
    Strict header validation: raises MissingContext if no recognisable ## T-NNN
    section headers found (I-TS-3). Missing optional fields default to ().
    Raises MissingContext if file absent.
    """
    ...
```

### 4.8 build_context (`context/build_context.py`)

```python
class ContextDepth:
    COMPACT  = "COMPACT"   # budget: 2 000 words
    STANDARD = "STANDARD"  # budget: 6 000 words
    VERBOSE  = "VERBOSE"   # budget: 12 000 words

# Token unit = word (whitespace-split). Deterministic, no external deps. (I-CTX-2a)
TOKEN_BUDGET: dict[str, int] = {
    ContextDepth.COMPACT:  2_000,
    ContextDepth.STANDARD: 6_000,
    ContextDepth.VERBOSE:  12_000,
}

# LLM tokens ≠ whitespace words. Safety factor prevents context window overflow.
# build_context enforces EFFECTIVE_BUDGET, not TOKEN_BUDGET directly (I-CTX-2).
_BUDGET_SAFETY_FACTOR: float = 0.75
EFFECTIVE_BUDGET: dict[str, int] = {
    k: int(v * _BUDGET_SAFETY_FACTOR) for k, v in TOKEN_BUDGET.items()
}
# COMPACT → 1 500 effective words | STANDARD → 4 500 | VERBOSE → 9 000


def build_context(
    agent_type: str,         # "coder" | "planner"
    task_id: str | None,     # required for coder; None for planner
    depth: str,              # ContextDepth constant
    config: dict,            # from load_config — paths to state, specs, plans, tasks
) -> str:
    """Staged context loader (SEM-9). Returns markdown string.

    Output format:
      <!-- context_hash: <sha256> -->   ← I-CTX-5
      <!-- agent_type: coder | planner, depth: COMPACT|STANDARD|VERBOSE -->
      <layer 0 content>
      <layer 1 content>
      ...

    Pure: no I/O beyond reads of the canonical §K.6 read order (I-CTX-1).
    Layer ordering strictly follows §4.8 table (I-CTX-6).
    Output word-count ≤ EFFECTIVE_BUDGET[depth] (I-CTX-2).
    Raises MissingContext if any required file is absent.
    """
    ...
```

**context_hash definition (I-CTX-5):**

```python
context_hash = SHA-256(
    json.dumps({
        "agent_type": agent_type,
        "task_id": task_id,
        "depth": depth,
        "files": {path: sha256(file_content) for path in loaded_files_sorted}
    }, sort_keys=True)
)
```

**Layer definitions by agent type and depth:**

| # | Layer | coder COMPACT | coder STANDARD | coder VERBOSE | planner COMPACT | planner STANDARD | planner VERBOSE |
|---|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | domain glossary (from project_profile.yaml) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 1 | State_index.yaml (summary) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Phases_index.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3 | Task row (single task only — task_id) | ✓ | ✓ | ✓ | — | — | — |
| 4 | Spec section referenced by task.spec_section | — | ✓ | ✓ | — | ✓ | ✓ |
| 5 | Plan milestone for this task | — | ✓ | ✓ | — | ✓ | ✓ |
| 6 | Full Spec_vN (active phase) | — | — | ✓ | — | — | ✓ |
| 7 | Full Plan_vN (active phase) | — | — | ✓ | — | — | ✓ |
| 8 | Task input file contents (task.inputs) | — | — | ✓ | — | — | — |

Layers are always appended in ascending order (0 → 8). If budget exhausted mid-layer,
the layer is truncated at the last complete paragraph boundary (I-CTX-6).

---

## 5. Invariants

### New Invariants (Phase 2)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-EL-3 | `reduce(events)` processes ONLY events where `event_source == "runtime"` AND `level == "L1"`. Meta events (`event_source="meta"`) MUST NOT alter SDDState. `StateDerivationCompleted` is L1 but has no reducer handler (projection signal, R2) | `tests/unit/domain/state/test_reducer.py` |
| I-ST-1 | `SDDState` is fully reconstructable by calling `reduce(sdd_replay())` — same sequence of L1 runtime events always produces the same SDDState | `tests/unit/domain/state/test_reducer.py` |
| I-ST-2 | `reduce(events)` is a pure total function: no I/O, no randomness, no global state; same `events` list → same `SDDState` | `tests/unit/domain/state/test_reducer.py` |
| I-ST-3 | `read_state(p)` → `write_state(s, p)` → `read_state(p)` roundtrip: second read returns equal `SDDState` (including recomputed `state_hash`) | `tests/unit/domain/state/test_yaml_state.py` |
| I-ST-4 | `sync_state(..., replay_fn)` derives `tasks_completed` and `tasks_done_ids` from `reduce(replay_fn())` (EventLog SSOT, I-ST-6). It reads TaskSet only to determine `tasks_total` and cross-validate DONE count. Raises `Inconsistency` if counts diverge | `tests/unit/domain/state/test_sync.py` |
| I-ST-5 | `init_state(phase_id, taskset_path, ...)` produces valid `State_index.yaml`: `tasks.total == len(parse_taskset(taskset_path))`, `tasks.completed == count(DONE)`, `tasks.done_ids == sorted([t.task_id for t in tasks if t.status=="DONE"])` | `tests/unit/domain/state/test_init_state.py` |
| I-ST-6 | EventLog (`sdd_replay(level="L1", source="runtime")`) is the **sole authoritative source** for `tasks_completed` and `tasks_done_ids`. `TaskSet_vN.md` `status` field (TODO/DONE) is a **display annotation only** — it is NOT a source of truth and MUST NOT be used for completion decisions. `State_index.yaml` is a cached projection and MAY be stale. `phase_status` / `plan_status` remain human-managed in YAML (governance gap — Phase 7 will close this) | `tests/unit/domain/state/test_sync.py` |
| I-ST-7 | Unknown `event_type` values (not in any handler table and not in `_KNOWN_NO_HANDLER`) MUST be counted in `ReducerDiagnostics.events_unknown_type`. With `strict_mode=True` MUST raise `UnknownEventType(SDDError)` | `tests/unit/domain/state/test_reducer.py` |
| I-ST-8 | `SDDState.state_hash` = `SHA-256(json.dumps(all_fields_except_state_hash, sort_keys=True))`. Computed in `__post_init__`. `read_state` verifies stored hash == recomputed hash; raises `Inconsistency` on mismatch | `tests/unit/domain/state/test_yaml_state.py` |
| I-ST-9 | `reduce(events) == reduce_incremental(EMPTY_STATE, events)` for any `events` list — incremental and full paths are equivalent | `tests/unit/domain/state/test_reducer.py` |
| I-TS-1 | `Task` dataclass has `spec_refs: tuple[str, ...]`, `produces_invariants: tuple[str, ...]`, `requires_invariants: tuple[str, ...]` fields; all default to `()` when absent in source | `tests/unit/domain/tasks/test_parser.py` |
| I-TS-2 | `parse_taskset(path)` is deterministic: calling it twice on the same unchanged file returns structurally equal `list[Task]` | `tests/unit/domain/tasks/test_parser.py` |
| I-TS-3 | `parse_taskset(path)` MUST raise `MissingContext` if the file contains no recognisable `## T-NNN` task headers — no silent empty list on malformed input | `tests/unit/domain/tasks/test_parser.py` |
| I-CTX-1 | `build_context(agent_type, task_id, depth, config)` is a pure function w.r.t. file contents: same files + same args → identical markdown string including `context_hash` | `tests/unit/context/test_build_context.py` |
| I-CTX-2 | `build_context` output word-count (whitespace-split) is ≤ `EFFECTIVE_BUDGET[depth]` (= `TOKEN_BUDGET[depth] * 0.75`) for any valid input. The safety factor guards against LLM token ≠ word divergence. | `tests/unit/context/test_build_context.py` |
| I-CTX-2a | "token" = word, defined as any whitespace-delimited substring. `TOKEN_BUDGET` values are in words. Rationale: deterministic, no external dependency, approximately proportional to LLM tokens | definition only |
| I-CTX-3 | `build_context(agent_type="coder", ...)` output MUST include the task's `Inputs` and `Outputs` fields and the referenced spec section; MUST NOT include TaskSet rows for tasks other than `task_id` | `tests/unit/context/test_build_context.py` |
| I-CTX-4 | `build_context(agent_type="planner", ...)` output MUST include `Phases_index.md`, `Spec_vN`, `Plan_vN` for the active phase; MUST NOT include individual task implementation rows | `tests/unit/context/test_build_context.py` |
| I-CTX-5 | `build_context` output MUST begin with `<!-- context_hash: <sha256> -->`. The hash covers `agent_type`, `task_id`, `depth`, and `sha256(content)` for each loaded file (sorted by path). Enables cache invalidation and audit trail | `tests/unit/context/test_build_context.py` |
| I-CTX-6 | Layer ordering is strictly deterministic: layers are appended in ascending index (0→8) as defined in §4.8 table, regardless of filesystem or config order. Truncation at budget occurs at layer boundary | `tests/unit/context/test_build_context.py` |
| I-EL-13 | Events passed to `reduce()` MUST be sorted by `seq` ASC. `sdd_replay()` guarantees this (I-PK-3). Callers constructing custom event lists are responsible for ordering. Out-of-order events produce undefined state (silently wrong, not an error). | `tests/unit/domain/state/test_reducer.py` |
| I-ST-10 | Every L1 event type MUST be classified: either (a) registered as a handler in `EventReducer`, or (b) explicitly listed in `_KNOWN_NO_HANDLER`. An L1 event that is neither counts as `events_unknown_type` and is an implementation gap. Verified by `test_all_l1_events_classified` which cross-checks `V1_L1_EVENT_TYPES` against both sets. | `tests/unit/domain/state/test_reducer.py` |
| I-ST-11 | `SDDState.state_hash` covers **derived fields + `REDUCER_VERSION`** only. Human-managed fields (`phase_status`, `plan_status`) are explicitly excluded from the hash. `REDUCER_VERSION` MUST be incremented whenever any handler's logic changes. This makes reducer logic changes detectable via hash comparison on replay. | `tests/unit/domain/state/test_yaml_state.py` |

### Preserved Invariants (referenced from Phase 1)

| ID | Statement |
|----|-----------|
| I-PK-4 | `classify_event_level` is a pure total function — used by reducer filter |
| I-PK-5 | `atomic_write` used by `write_state` — no partial YAML writes visible on disk |
| I-EL-2 | `sdd_replay(level="L1", source="runtime")` returns ONLY L1 runtime events — default input to `reduce()` |
| I-EL-9 | No direct `duckdb.connect` outside `infra/db.py` — `sync.py` injects `replay_fn`; `init_state.py` uses emit only |
| I-EL-10 | `sdd_replay()` defaults to `level="L1", source="runtime"` — no explicit args needed for state reconstruction |

### §PHASE-INV (must ALL be PASS before Phase 2 can be COMPLETE)

```
[I-EL-3, I-EL-13,
 I-ST-1, I-ST-2, I-ST-3, I-ST-4, I-ST-5, I-ST-6, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11,
 I-TS-1, I-TS-2, I-TS-3,
 I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
```

---

## 6. Pre/Post Conditions

### reduce(events, strict_mode=False)

**Pre:**
- `events` is `list[dict]`; may be empty; each dict has at least `event_type` key
- `events` MUST be sorted by `seq` ASC (I-EL-13); `sdd_replay()` guarantees this (I-PK-3)
- `strict_mode=False` (default) silently counts unknown types; `True` raises on first unknown

**Post:**
- Returns `SDDState`; never raises on empty input
- Only `event_source == "runtime"` AND `level == "L1"` events affect result (I-EL-3)
- `StateDerivationCompleted` counted in `diagnostics.events_known_no_handler`, not processed
- `events == []` → returns `EMPTY_STATE`
- `strict_mode=True` + unrecognised `event_type` → raises `UnknownEventType` (I-ST-7)

### read_state(path)

**Pre:**
- `path` exists (raises `MissingState` if absent)

**Post:**
- Returns `SDDState` with all fields; `tasks_done_ids` is `tuple[str, ...]`
- `state_hash` recomputed and verified; raises `Inconsistency` on mismatch (I-ST-8)

### write_state(state, path)

**Pre:**
- `state` is valid `SDDState`; parent directory exists

**Post:**
- YAML written atomically (I-PK-5)
- `read_state(path)` returns equal `SDDState` (I-ST-3)
- `state_hash` written as comment for reference

### sync_state(taskset_path, state_path, emit, replay_fn)

**Pre:**
- `taskset_path` points to a readable `TaskSet_vN.md`
- `state_path` parent directory exists
- `emit` callable accepts `DomainEvent`
- `replay_fn()` returns `list[dict]` (defaults to `sdd_replay`)

**Post:**
- `state_path` contains YAML with `tasks_completed`/`tasks_done_ids` from EventLog (I-ST-4, I-ST-6)
- `tasks_total` derived from `parse_taskset(taskset_path)`
- TaskSet DONE count == EventLog `tasks_completed`; else raises `Inconsistency` (I-ST-4)
- `emit` called exactly once with `StateDerivationCompletedEvent(derived_from="eventlog")`
- Phase/plan/inv/tests fields preserved from existing YAML (or from `reduce()` if YAML absent)

### init_state(phase_id, taskset_path, state_path, emit)

**Pre:**
- `state_path` MUST NOT exist (raises `InvalidState` if present)
- `taskset_path` readable

**Post:**
- Fresh `State_index.yaml` written; `phase_current=phase_id`, `phase_status=ACTIVE`
- `tasks_total = len(parse_taskset(...))`; `tasks_completed = count(DONE)` from TaskSet
- `emit` called exactly twice: `PhaseInitializedEvent`, then `StateDerivationCompletedEvent(derived_from="initial")`

### parse_taskset(path)

**Pre:**
- `path` exists (raises `MissingContext` if absent)
- File follows `TaskSet_template.md` structure with `## T-NNN` headers

**Post:**
- Returns `list[Task]` ordered by appearance; length ≥ 0
- Missing optional fields default to `()`
- Raises `MissingContext` if no `## T-NNN` headers found (I-TS-3)

### build_context(agent_type, task_id, depth, config)

**Pre:**
- `agent_type ∈ {"coder", "planner"}`; `task_id` required when `agent_type == "coder"`
- `depth ∈ {ContextDepth.COMPACT, ContextDepth.STANDARD, ContextDepth.VERBOSE}`
- `config` contains `state_path`, `phases_index`, `specs_dir`, `plans_dir`, `tasks_dir`

**Post:**
- Returns non-empty markdown string
- First line is `<!-- context_hash: <sha256> -->` (I-CTX-5)
- Word count ≤ `EFFECTIVE_BUDGET[depth]` (I-CTX-2)
- Layer order 0→8 strictly (I-CTX-6)
- Coder: task row + spec section included; other task rows excluded (I-CTX-3)
- Planner: Phases_index + Spec + Plan included; task rows excluded (I-CTX-4)
- Raises `MissingContext` if required file absent

---

## 7. Use Cases

### UC-2-1: Replay authoritative state from EventLog

**Actor:** Domain state module
**Trigger:** Guard or validation needs current SDDState
**Pre:** DuckDB reachable; ≥0 L1 runtime events
**Steps:**
1. `events = sdd_replay()` — defaults to `level="L1", source="runtime"` (I-EL-10)
2. `state = reduce(events)` — meta events and `StateDerivationCompleted` filtered (I-EL-3)
**Post:** Authoritative `SDDState` reflecting EventLog truth; no DB writes

### UC-2-2: Sync YAML projection after task completion

**Actor:** `update_state.py complete T-NNN` (governance script, Phase 8 thin adapter)
**Trigger:** Task implementation finished
**Pre:** `State_index.yaml` and `TaskSet_vN.md` exist; `TaskImplemented` event appended to DB
**Steps:**
1. Governance script appends `TaskImplemented` event to DB (existing logic)
2. Calls `sync_state(taskset_path, state_path, emit=sdd_append_wrapper)` (I-ST-4, I-ST-6)
3. `sync_state` calls `reduce(sdd_replay())` → gets authoritative `tasks_completed`
4. Cross-validates against TaskSet DONE count; raises `Inconsistency` on mismatch
5. Writes updated `State_index.yaml`; emits `StateDerivationCompleted`
**Post:** YAML reflects EventLog truth; any divergence surfaces as `Inconsistency` error

### UC-2-3: Divergence detected — TaskSet manually edited

**Actor:** sync_state (during UC-2-2)
**Trigger:** Human manually marked T-NNN as DONE in TaskSet without running update_state.py
**State:** TaskSet DONE count = N; EventLog tasks_completed = N-1
**Steps:**
1. `sync_state` detects mismatch → raises `Inconsistency`
2. Governance calls `report_error.py --type Inconsistency`
**Post:** Human resolves by either running `update_state.py complete T-NNN` (preferred)
         or reverting manual TaskSet edit. No auto-resolution.

### UC-2-4: Initialise state for new phase

**Actor:** `Init State N` command (§K.1)
**Trigger:** Phase N decomposition complete; `State_index.yaml` absent
**Pre:** `TaskSet_vN.md` exists; `State_index.yaml` absent
**Steps:**
1. `init_state(phase_id=N, taskset_path=..., state_path=..., emit=...)`
2. Writes `State_index.yaml`; emits `PhaseInitialized` + `StateDerivationCompleted`
**Post:** Fresh YAML state; two L1 events appended to DB

### UC-2-5: Load context for Coder Agent before Implement T-NNN

**Actor:** `build_context.py --agent coder --task T-NNN --depth STANDARD`
**Trigger:** SEM-9 pre-execution (§R.6 step 1)
**Pre:** State_index.yaml, TaskSet, active Spec all readable
**Steps:**
1. `config = load_config(phase=N)`
2. `ctx = build_context("coder", "T-NNN", ContextDepth.STANDARD, config)`
3. Output includes: `context_hash`, glossary, State, Phases_index, task row, spec section, plan milestone
**Post:** Markdown ≤ 6 000 words; coder sees only its task scope (I-CTX-3); hash enables cache validation

### UC-2-6: Load context for Planner Agent before Draft Spec_vN

**Actor:** `build_context.py --agent planner --depth VERBOSE`
**Trigger:** SEM-9 pre-execution for planning command
**Pre:** Phases_index, Spec_vN, Plan_vN readable
**Steps:**
1. `ctx = build_context("planner", None, ContextDepth.VERBOSE, config)`
2. Output includes: `context_hash`, glossary, State, Phases_index, full Spec, full Plan
**Post:** Markdown ≤ 12 000 words; no task-level noise (I-CTX-4)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-INFRA (`infra/event_log.py`) | BC-STATE → BC-INFRA | `sync.py`: `replay_fn` defaults to `sdd_replay`; `init_state.py`: `emit` wraps `sdd_append` |
| BC-INFRA (`infra/audit.py`) | BC-STATE → BC-INFRA | `write_state` uses `atomic_write` (I-PK-5) |
| BC-INFRA (`infra/config_loader.py`) | BC-CONTEXT → BC-INFRA | `build_context` reads file paths via `load_config` |
| BC-CORE (`core/errors.py`) | all → BC-CORE | `MissingState`, `MissingContext`, `InvalidState`, `Inconsistency`, `UnknownEventType` |
| BC-CORE (`core/events.py`) | BC-STATE → BC-CORE | `StateDerivationCompletedEvent` + `PhaseInitializedEvent` inherit `DomainEvent` |

### Projection Hierarchy (I-ST-6 — authoritative to derived)

```
Level 1 (authoritative)  EventLog: sdd_replay(level=L1, source=runtime)
                              │ reduce()
Level 2 (in-memory)      SDDState (tasks_completed, tasks_done_ids)
                              │ sync_state() cross-validates + writes
Level 3 (cached)         State_index.yaml (may be stale; refreshed by sync_state)
                              │ read_state() verifies state_hash
Level 4 (planning)       TaskSet_vN.md (tasks_total, DONE count for validation)
```

Human-managed fields (`phase_status`, `plan_status`) live at Level 3 only until Phase 7
introduces `PhaseActivated` events that close the governance gap.

### Reducer Integration with Phase 3 (Guards)

Phase 3 guards call `reduce(sdd_replay())` to obtain authoritative `SDDState`. They may
optionally call `reduce_with_diagnostics()` to log unknown event types as L2 events.
Guards treat `SDDState` as a pure value — no state mutation inside guards.

### Reducer Integration with Phase 4 (Commands)

`update_state.py complete T-NNN` (Phase 4) sequence:
1. Append `TaskImplemented` to EventLog via `sdd_append_batch` (with `MetricRecorded`, I-M-1)
2. Call `sync_state(...)` → projection refreshed from authoritative EventLog

The projection (`State_index.yaml`) is always derivable from EventLog via `reduce(sdd_replay())`.
Phase 4 MUST NOT write `State_index.yaml` directly; it MUST use `sync_state`.

### Reducer Handler Registration Pattern

```python
# reducer.py
@_handler("TaskImplemented")
def _handle_task_implemented(state: _MutableState, payload: dict) -> None:
    task_id = payload["task_id"]
    if task_id not in state._done_set:           # O(1) set lookup (R4)
        state._done_set.add(task_id)
        state.tasks_completed += 1

@_handler("PhaseCompleted")
def _handle_phase_completed(state: _MutableState, payload: dict) -> None:
    state.phase_status = "COMPLETE"
    state.plan_status = "COMPLETE"

# At fold completion: state.tasks_done_ids = tuple(sorted(state._done_set))
```

`_KNOWN_NO_HANDLER` set prevents `StateDerivationCompleted` and other projection/governance
events from being counted as unknown (they are known — deliberately not handled).

---

## 9. Verification

| # | Test File | Tests | Invariant(s) |
|---|-----------|-------|--------------|
| 1 | `tests/unit/domain/state/test_reducer.py` | `test_reduce_empty_returns_empty_state`, `test_reduce_filters_meta_events`, `test_reduce_filters_non_l1`, `test_reduce_state_derivation_has_no_handler`, `test_reduce_task_implemented_deduplicates`, `test_reduce_task_implemented_increments_count`, `test_reduce_phase_completed_sets_status`, `test_reduce_is_deterministic`, `test_reduce_unknown_type_counted_in_diagnostics`, `test_reduce_strict_mode_raises_on_unknown`, `test_reduce_incremental_equivalent_to_full`, `test_all_l1_events_classified`, `test_reduce_assumes_sorted_input` | I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10 |
| 2 | `tests/unit/domain/state/test_yaml_state.py` | `test_read_write_roundtrip`, `test_read_missing_raises_missing_state`, `test_write_uses_atomic_write`, `test_state_hash_verified_on_read`, `test_state_hash_mismatch_raises_inconsistency`, `test_state_hash_excludes_human_fields`, `test_state_hash_includes_reducer_version` | I-ST-3, I-ST-8, I-ST-11, I-PK-5 |
| 3 | `tests/unit/domain/state/test_sync.py` | `test_sync_uses_eventlog_for_task_counts`, `test_sync_raises_inconsistency_on_divergence`, `test_sync_preserves_phase_fields`, `test_sync_emits_state_derivation_event`, `test_sync_no_direct_db_calls`, `test_sync_replay_fn_injectable` | I-ST-4, I-ST-6, I-EL-9 |
| 4 | `tests/unit/domain/state/test_init_state.py` | `test_init_state_creates_yaml`, `test_init_state_raises_if_exists`, `test_init_state_counts_match_taskset`, `test_init_state_emits_phase_initialized_then_derivation` | I-ST-5 |
| 5 | `tests/unit/domain/tasks/test_parser.py` | `test_parse_task_has_spec_fields`, `test_parse_is_deterministic`, `test_parse_missing_optional_fields_default_empty`, `test_parse_missing_file_raises`, `test_parse_malformed_no_headers_raises`, `test_parse_done_status` | I-TS-1, I-TS-2, I-TS-3 |
| 6 | `tests/unit/context/test_build_context.py` | `test_coder_context_includes_task_row`, `test_coder_context_excludes_other_tasks`, `test_planner_context_includes_spec_and_plan`, `test_planner_context_excludes_task_rows`, `test_context_within_token_budget_all_depths`, `test_build_context_is_deterministic`, `test_context_hash_present_in_output`, `test_context_hash_changes_on_file_change`, `test_layer_order_is_ascending` | I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Guard pipeline (`phase_guard`, `task_guard`, `norm_guard`, `task_start`) | Phase 3 |
| Task scheduler (DAG, `depends_on`, parallel groups) | Phase 3 |
| Command handlers (`complete`, `validate`, `sdd_run`) | Phase 4 |
| `error_event_boundary` decorator — I-ERR-1 | Phase 4 |
| Command idempotency by `command_id` — I-CMD-1b | Phase 4 |
| `query_events.py` Python module | Phase 5 |
| `metrics_report.py` Python module | Phase 5 |
| CLI entry point (`cli.py`) | Phase 6 |
| `log_tool.py` / `log_bash.py` Python modules | Phase 6 |
| `build_context.py` CLI wiring (Python module only in Phase 2) | Phase 6 |
| `PhaseActivated` event + closing EventLog governance gap for phase_status | Phase 7 |
| v1↔v2 full replay compatibility test — I-EL-4 | Phase 7 |
| Thin adapter migration of `.sdd/tools/` | Phase 8 |
| Multi-process / concurrent writers | Out of scope until explicitly specced |
