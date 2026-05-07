# Plan_v2 — Phase 2: State & Context

Status: ACTIVE
Spec: .sdd/specs/Spec_v2_State.md

---

## Milestones

### M1: BC-TASKS — Task dataclass + TaskSet parser

```text
Spec:       §4.7, §2 BC-TASKS, §5 I-TS-1..3
BCs:        BC-TASKS
Invariants: I-TS-1, I-TS-2, I-TS-3
Depends:    BC-CORE (SDDError, MissingContext from Phase 1)
Risks:      None — pure stdlib; no infra deps
```

#### Outputs

**`src/sdd/domain/tasks/parser.py`**

Task dataclass (frozen):
```
task_id, title, status, spec_section,
inputs: tuple[str,...], outputs: tuple[str,...], checks: tuple[str,...],
spec_refs: tuple[str,...],          # default ()  — I-TS-1
produces_invariants: tuple[str,...], # default ()
requires_invariants: tuple[str,...]  # default ()
```

`parse_taskset(path: str) → list[Task]` algorithm:
1. Raise `MissingContext` if `path` absent (I-TS-3 precondition)
2. Read file; split into sections on `## T-` boundary
3. Raise `MissingContext` if no `## T-NNN` headers found (I-TS-3 — no silent empty list)
4. For each section: parse key-value pairs (`Status:`, `Inputs:`, `Outputs:` etc.)
5. Missing optional fields → `()` (I-TS-1)
6. Return `list[Task]` ordered by document appearance
7. Called twice on same unchanged file → identical result (I-TS-2 determinism)

**`src/sdd/domain/tasks/__init__.py`** — re-exports `Task`, `parse_taskset`

**`tests/unit/domain/tasks/test_parser.py`**

| Test | Invariant |
|------|-----------|
| `test_parse_task_has_spec_fields` | I-TS-1 |
| `test_parse_missing_optional_fields_default_empty` | I-TS-1 |
| `test_parse_is_deterministic` | I-TS-2 |
| `test_parse_missing_file_raises` | I-TS-3 |
| `test_parse_malformed_no_headers_raises` | I-TS-3 |
| `test_parse_done_status` | I-TS-1 |

---

### M2: BC-STATE core — SDDState, ReducerDiagnostics, EventReducer

```text
Spec:       §4.1, §4.2, §4.3, §5 I-EL-3/I-EL-13/I-ST-1..2/I-ST-7..11
BCs:        BC-STATE (reducer.py only)
Invariants: I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11
Depends:    BC-CORE (SDDError, DomainEvent, V1_L1_EVENT_TYPES)
Risks:      ClassVar excluded from asdict() — REDUCER_VERSION must be injected explicitly
            into hash dict; _HUMAN_FIELDS also ClassVar — same rule applies
```

#### Purity contract (I-ST-2)

`reduce()`, `reduce_with_diagnostics()`, `reduce_incremental()`, `compute_state_hash()`:
- **No I/O** — no file reads, no DB calls, no network access
- **No randomness** — no `random`, no `uuid`, no `datetime.now()`
- **No global mutation** — no module-level side effects; EMPTY_STATE is a constant
- Same `events` argument → identical `SDDState` result, always

Verification: any mock/stub that injects I/O into these functions is a test design error.

#### SDDState field contract

Derived fields (EventLog authoritative — included in `state_hash`):
```
phase_current, plan_version, tasks_version, tasks_total,
tasks_completed, tasks_done_ids, invariants_status, tests_status,
last_updated, schema_version, snapshot_event_id
```

Human-managed fields (YAML-only — excluded from `state_hash`, I-ST-11):
```
phase_status, plan_status
```

`state_hash` computation (I-ST-8, I-ST-11):
```python
_HUMAN_FIELDS = frozenset({"phase_status", "plan_status", "state_hash"})
data = {k: v for k, v in asdict(self).items() if k not in _HUMAN_FIELDS}
data["reducer_version"] = SDDState.REDUCER_VERSION   # ClassVar — not in asdict()
hash = SHA-256(json.dumps(data, sort_keys=True, default=str))
```

#### _EVENT_SCHEMA + strict payload validation

`EventReducer._EVENT_SCHEMA: dict[str, frozenset[str]]` — required payload fields per handled type:
```python
{
    "PhaseInitialized": frozenset({"phase_id", "tasks_total", "plan_version", "actor", "timestamp"}),
    "TaskImplemented":  frozenset({"task_id", "phase_id"}),
    "TaskValidated":    frozenset({"task_id", "phase_id", "result"}),
    "PhaseCompleted":   frozenset({"phase_id"}),
}
```

Validation in `_fold()`: before calling a handler, assert `_EVENT_SCHEMA[event_type] ⊆ payload.keys()`.
- `strict_mode=False`: missing field → count in diagnostics as `events_unknown_type`; skip handler
- `strict_mode=True`: missing field → raise `UnknownEventType` (I-ST-7 extension to schema errors)

#### _KNOWN_NO_HANDLER completeness (I-ST-10)

Algorithm for `test_all_l1_events_classified`:
```python
from sdd.core.events import V1_L1_EVENT_TYPES          # frozenset from Phase 1
handlers  = frozenset(EventReducer._EVENT_SCHEMA.keys())
no_handle = EventReducer._KNOWN_NO_HANDLER
all_classified = V1_L1_EVENT_TYPES == (handlers | no_handle)
assert all_classified, f"Unclassified: {V1_L1_EVENT_TYPES - handlers - no_handle}"
```

Every L1 type must appear in exactly one of the two sets. This test catches omissions statically.

#### Event ordering (I-EL-13)

`reduce()` precondition: events sorted by `seq` ASC. No auto-sort (would hide caller bugs).
`sdd_replay()` guarantees this via I-PK-3. Test `test_reduce_assumes_sorted_input` verifies that
two events applied in reversed order produce a different (wrong) state — documenting the
invariant as an observable property.

#### Outputs

**`src/sdd/domain/state/reducer.py`**

**`tests/unit/domain/state/test_reducer.py`**

| Test | Invariant |
|------|-----------|
| `test_reduce_empty_returns_empty_state` | I-ST-1 |
| `test_reduce_filters_meta_events` | I-EL-3 |
| `test_reduce_filters_non_l1` | I-EL-3 |
| `test_reduce_state_derivation_has_no_handler` | I-EL-3, I-ST-10 |
| `test_reduce_task_implemented_deduplicates` | I-ST-2 |
| `test_reduce_task_implemented_increments_count` | I-ST-1 |
| `test_reduce_phase_completed_sets_status` | I-ST-1 |
| `test_reduce_is_deterministic` | I-ST-2 |
| `test_reduce_unknown_type_counted_in_diagnostics` | I-ST-7 |
| `test_reduce_strict_mode_raises_on_unknown` | I-ST-7 |
| `test_reduce_strict_mode_raises_on_missing_schema_field` | I-ST-7 (schema extension) |
| `test_reduce_incremental_equivalent_to_full` | I-ST-9 |
| `test_all_l1_events_classified` | I-ST-10 |
| `test_reduce_assumes_sorted_input` | I-EL-13 |
| `test_state_hash_excludes_human_fields` | I-ST-11 |
| `test_state_hash_includes_reducer_version` | I-ST-11 |

---

### M3: BC-STATE persistence — yaml_state, sync, init_state

```text
Spec:       §3, §4.4, §4.5, §4.6, §5 I-ST-3..6, §8
BCs:        BC-STATE (yaml_state.py, sync.py, init_state.py, __init__.py)
Invariants: I-ST-3, I-ST-4, I-ST-5, I-ST-6, I-EL-9
Depends:    M2 (SDDState, reduce, compute_state_hash),
            M1 (parse_taskset),
            BC-INFRA (atomic_write, sdd_replay, sdd_append, sdd_append_batch)
Risks:      sync_state must read existing YAML before building new_state to preserve
            human_fields; if YAML absent treat phase_status/plan_status as UNKNOWN/PLANNED
            sdd_replay() returns sorted events (I-PK-3) — replay_fn contract must state this
```

#### sync_state algorithm (precise — I-ST-4, I-ST-6)

```
sync_state(taskset_path, state_path, emit, replay_fn=sdd_replay):

1. events = replay_fn()                         # I-EL-9: no direct duckdb.connect
2. authoritative = reduce(events)               # I-EL-13: replay_fn returns seq-sorted events
   → authoritative.tasks_completed, tasks_done_ids are SSOT

3. tasks = parse_taskset(taskset_path)          # for tasks_total + cross-validation
   taskset_done = count(t for t in tasks if t.status == "DONE")  # display count only

4. if taskset_done != authoritative.tasks_completed:
       raise Inconsistency(...)                 # I-ST-4: reactive split-brain detection

5. try:
       existing = read_state(state_path)        # may be absent on first sync
       phase_status = existing.phase_status     # preserve human_fields
       plan_status  = existing.plan_status
   except MissingState:
       phase_status = authoritative.phase_status   # or "PLANNED" as safe default
       plan_status  = authoritative.plan_status

6. new_state = SDDState(
       # derived fields from EventLog
       phase_current   = authoritative.phase_current,
       plan_version    = authoritative.plan_version,
       tasks_version   = authoritative.tasks_version,
       tasks_total     = len(tasks),            # from TaskSet (planning record)
       tasks_completed = authoritative.tasks_completed,
       tasks_done_ids  = authoritative.tasks_done_ids,
       invariants_status = authoritative.invariants_status,
       tests_status    = authoritative.tests_status,
       snapshot_event_id = authoritative.snapshot_event_id,
       last_updated    = now_iso8601(),
       schema_version  = 1,
       # human_fields preserved
       phase_status    = phase_status,
       plan_status     = plan_status,
   )

7. write_state(new_state, state_path)           # atomic (I-PK-5)
8. emit(StateDerivationCompletedEvent(
       phase_id       = str(authoritative.phase_current),
       tasks_total    = len(tasks),
       tasks_completed= authoritative.tasks_completed,
       derived_from   = "eventlog",
       timestamp      = now_iso8601(),
   ))
```

#### init_state algorithm (precise — I-ST-5)

```
init_state(phase_id, taskset_path, state_path, emit):

1. if state_path exists: raise InvalidState(...)   # must be absent — clean slate only

2. tasks = parse_taskset(taskset_path)
   tasks_total    = len(tasks)
   done_ids       = sorted(t.task_id for t in tasks if t.status == "DONE")
   tasks_completed= len(done_ids)               # normally 0 at phase start

3. state = SDDState(
       phase_current    = phase_id,
       plan_version     = phase_id,
       tasks_version    = phase_id,
       tasks_total      = tasks_total,
       tasks_completed  = tasks_completed,
       tasks_done_ids   = tuple(done_ids),
       invariants_status= "UNKNOWN",
       tests_status     = "UNKNOWN",
       snapshot_event_id= None,
       last_updated     = now_iso8601(),
       schema_version   = 1,
       phase_status     = "ACTIVE",             # init always starts ACTIVE
       plan_status      = "ACTIVE",
   )

4. write_state(state, state_path)               # atomic (I-PK-5)

5. emit(PhaseInitializedEvent(
       phase_id    = str(phase_id),
       tasks_total = tasks_total,
       plan_version= phase_id,
       actor       = "llm",
       timestamp   = now_iso8601(),
   ))
6. emit(StateDerivationCompletedEvent(
       phase_id        = str(phase_id),
       tasks_total     = tasks_total,
       tasks_completed = tasks_completed,
       derived_from    = "initial",
       timestamp       = now_iso8601(),
   ))

Note: does NOT call replay_fn — EventLog empty for a new phase.
```

#### I-EL-9 enforcement: replay_fn injection

`sync_state` MUST accept `replay_fn: Callable[[], list[dict]] = sdd_replay`.
Default binding to `sdd_replay` at module level is the ONLY production use of infra.
Tests pass a stub: `replay_fn=lambda: [...]` — no DB required.

`init_state` MUST NOT call `sdd_replay` at all — verified by `test_init_state_no_db_calls`
(monkeypatch `sdd_replay` to raise, assert no exception).

#### Outputs

**`src/sdd/domain/state/yaml_state.py`**

`read_state(path)` — parse YAML → SDDState; recompute + verify `state_hash`; raise `Inconsistency`
on mismatch; `tasks_done_ids`: YAML list → `tuple[str,...]`.

`write_state(state, path)` — atomic via `atomic_write` (I-PK-5); `state_hash` written as YAML
comment; human_fields written normally; `tasks_done_ids` as YAML list.

**`src/sdd/domain/state/sync.py`** — implements sync_state algorithm above

**`src/sdd/domain/state/init_state.py`** — implements init_state algorithm above

**`src/sdd/domain/state/__init__.py`** — re-exports all public symbols + `StateDerivationCompletedEvent`

**`tests/unit/domain/state/test_yaml_state.py`**

| Test | Invariant |
|------|-----------|
| `test_read_write_roundtrip` | I-ST-3 |
| `test_read_missing_raises_missing_state` | I-ST-3 pre |
| `test_write_uses_atomic_write` | I-PK-5 |
| `test_state_hash_verified_on_read` | I-ST-8 |
| `test_state_hash_mismatch_raises_inconsistency` | I-ST-8 |
| `test_state_hash_excludes_human_fields` | I-ST-11 |
| `test_state_hash_includes_reducer_version` | I-ST-11 |
| `test_human_fields_preserved_in_roundtrip` | I-ST-11 (human_fields survive write→read) |

**`tests/unit/domain/state/test_sync.py`**

| Test | Invariant |
|------|-----------|
| `test_sync_uses_eventlog_for_task_counts` | I-ST-4, I-ST-6 |
| `test_sync_raises_inconsistency_on_divergence` | I-ST-4 |
| `test_sync_preserves_phase_fields` | I-ST-6 (human_fields survive sync) |
| `test_sync_emits_state_derivation_event` | §3 event catalog |
| `test_sync_no_direct_db_calls` | I-EL-9 |
| `test_sync_replay_fn_injectable` | I-EL-9 (stub replay_fn, no DB required) |
| `test_sync_absent_yaml_uses_reducer_defaults` | I-ST-4 (first sync path) |

**`tests/unit/domain/state/test_init_state.py`**

| Test | Invariant |
|------|-----------|
| `test_init_state_creates_yaml` | I-ST-5 |
| `test_init_state_raises_if_exists` | I-ST-5 pre |
| `test_init_state_counts_match_taskset` | I-ST-5 |
| `test_init_state_emits_phase_initialized_then_derivation` | §3 event order |
| `test_init_state_no_db_calls` | I-EL-9 (sdd_replay never called by init) |

---

### M4: BC-CONTEXT — staged context builder

```text
Spec:       §4.8, §5 I-CTX-1..6, §7 UC-2-5/UC-2-6
BCs:        BC-CONTEXT (context/build_context.py)
Invariants: I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6
Depends:    M2 (read_state), M1 (parse_taskset), BC-INFRA (load_config)
Risks:      Budget truncation must cut at last double-newline before limit — not mid-word
            context_hash: sorted file paths critical — dict insertion order not guaranteed
            Coder: must exclude ALL tasks except task_id (I-CTX-3) — not just filter by status
            Planner: must exclude ALL task implementation rows (I-CTX-4) — Spec/Plan included
```

#### Purity contract (I-CTX-1)

`build_context()` is a **pure function w.r.t. file contents**:
- **All I/O is read-only**: reads files listed in §K.6 canonical order; no writes, no DB calls
- **No randomness**, no `datetime.now()`, no environment-dependent values
- Same file contents + same arguments → identical markdown output including `context_hash`
- Violation: any call to `write_state`, `sdd_append`, or mutable globals is a spec violation

#### context_hash formula (I-CTX-5)

```python
context_hash = SHA-256(
    json.dumps({
        "agent_type": agent_type,        # "coder" | "planner"
        "task_id":    task_id,           # str | None
        "depth":      depth,             # ContextDepth constant
        "files": {
            path: sha256(content)        # key = absolute path, sorted ascending
            for path in sorted(loaded_file_paths)
        }
    }, sort_keys=True)
).hexdigest()
```

**Determinism rules:**
- `loaded_file_paths` = all files actually read in this call, sorted lexicographically
- `sha256(content)` = hex digest of raw file bytes before decoding
- `sort_keys=True` in outer `json.dumps` ensures field order is stable across Python versions
- Output line 1: `<!-- context_hash: {hexdigest} -->`
- Any file content change → different hash → cache invalidation (I-CTX-5)

#### Budget enforcement (I-CTX-2)

```python
EFFECTIVE_BUDGET = {depth: int(TOKEN_BUDGET[depth] * 0.75) for depth in TOKEN_BUDGET}
# COMPACT: 1500 words | STANDARD: 4500 | VERBOSE: 9000
```

Word count = `len(output.split())` (whitespace-split, I-CTX-2a).
Truncation: if adding a layer would exceed budget, truncate at the last `\n\n` boundary before
the limit. Never truncate mid-sentence. Header comment lines do NOT count toward budget.

#### Layer isolation guarantees

**Coder (I-CTX-3):** layers 0–3 always included. Layer 3 = single task row for `task_id` only.
Layers 4–5 = spec section + plan milestone for that task only. No other task IDs in output.
Test: assert no `T-NNN` strings in output except the requested `task_id`.

**Planner (I-CTX-4):** layers 0–2 + 4+ (Spec, Plan). Layer 3 (individual task rows) NEVER
included for planner. Test: assert output contains no `## T-` section headers.

#### Outputs

**`src/sdd/context/build_context.py`**

**`src/sdd/context/__init__.py`** — re-exports `build_context`, `ContextDepth`, `TOKEN_BUDGET`,
`EFFECTIVE_BUDGET`

**`tests/unit/context/test_build_context.py`**

| Test | Invariant |
|------|-----------|
| `test_build_context_is_deterministic` | I-CTX-1 |
| `test_build_context_pure_no_io_writes` | I-CTX-1 (monkeypatch writes → assert not called) |
| `test_context_within_token_budget_all_depths` | I-CTX-2 (parametrised COMPACT/STANDARD/VERBOSE) |
| `test_coder_context_includes_task_row` | I-CTX-3 |
| `test_coder_context_excludes_other_tasks` | I-CTX-3 (assert no other T-NNN present) |
| `test_planner_context_includes_spec_and_plan` | I-CTX-4 |
| `test_planner_context_excludes_task_rows` | I-CTX-4 (assert no `## T-` headers) |
| `test_context_hash_present_in_output` | I-CTX-5 |
| `test_context_hash_changes_on_file_change` | I-CTX-5 (mutate one file → different hash) |
| `test_context_hash_sorted_file_paths` | I-CTX-5 (path order determinism) |
| `test_layer_order_is_ascending` | I-CTX-6 |
| `test_truncation_at_paragraph_boundary` | I-CTX-2 (no mid-sentence cut) |

---

### M5: Module wiring + §PHASE-INV verification

```text
Spec:       §1 (80%+ coverage), §5 §PHASE-INV, §9 Verification
BCs:        all Phase 2 BCs
Invariants: all §PHASE-INV (see list below)
Depends:    M1, M2, M3, M4 all DONE
Risks:      Coverage gaps most likely in: Inconsistency branch of sync_state,
            strict_mode=True path of reducer, MissingState on absent YAML
```

#### §PHASE-INV checklist

All must be PASS before Phase 2 can be COMPLETE:

```
BC-TASKS:
  ☐ I-TS-1   Task has spec_refs/produces/requires fields; defaults ()
  ☐ I-TS-2   parse_taskset() is deterministic
  ☐ I-TS-3   parse_taskset() raises on no T-NNN headers

BC-STATE reducer:
  ☐ I-EL-3   reduce() filters source != "runtime" AND level != "L1"
  ☐ I-EL-13  reduce() assumes events sorted by seq ASC
  ☐ I-ST-1   SDDState fully reconstructable from reduce(sdd_replay())
  ☐ I-ST-2   reduce() is pure: no I/O, no randomness, same input → same output
  ☐ I-ST-7   Unknown event_type → diagnostics.events_unknown_type; strict_mode → raises
  ☐ I-ST-9   reduce(all) == reduce_incremental(EMPTY_STATE, all)
  ☐ I-ST-10  All V1_L1_EVENT_TYPES classified (handler OR _KNOWN_NO_HANDLER)
  ☐ I-ST-11  state_hash covers derived+REDUCER_VERSION; excludes human_fields

BC-STATE persistence:
  ☐ I-ST-3   read→write→read roundtrip preserves SDDState
  ☐ I-ST-4   sync_state derives counts from EventLog; raises Inconsistency on divergence
  ☐ I-ST-5   init_state produces correct YAML; raises InvalidState if exists
  ☐ I-ST-6   EventLog is SSOT; TaskSet.status is display annotation only
  ☐ I-ST-8   state_hash verified on read; Inconsistency on mismatch
  ☐ I-EL-9   No direct duckdb.connect in sync.py or init_state.py

BC-CONTEXT:
  ☐ I-CTX-1  build_context() is pure w.r.t. file contents
  ☐ I-CTX-2  output word-count ≤ EFFECTIVE_BUDGET[depth]
  ☐ I-CTX-3  coder: task_id row included; other task rows excluded
  ☐ I-CTX-4  planner: Spec+Plan included; task rows excluded
  ☐ I-CTX-5  output starts with context_hash comment; hash is deterministic
  ☐ I-CTX-6  layers appended in strict ascending order 0→8
```

#### Outputs

- `src/sdd/domain/__init__.py` — package marker (if absent)
- `.sdd/reports/ValidationReport_T-2NN.md` — §PHASE-INV pass report: all invariants PASS
  + `pytest --cov=src/sdd --cov-report=term-missing` coverage ≥ 80% for M1..M4 modules

---

## Risk Notes

- R-1: **ClassVar excluded from asdict()** — `REDUCER_VERSION` and `_HUMAN_FIELDS` are ClassVars;
  `dataclasses.asdict()` skips them. `__post_init__` must add `reducer_version` manually to the
  hash dict. Mitigation: `test_state_hash_includes_reducer_version` asserts hash changes when
  `REDUCER_VERSION` is temporarily mutated.

- R-2: **human_fields preservation across sync** — `phase_status`/`plan_status` must survive
  `sync_state`. Algorithm step 5 reads existing YAML first. If YAML absent: safe default
  (`"PLANNED"`). Mitigation: `test_sync_preserves_phase_fields` and
  `test_sync_absent_yaml_uses_reducer_defaults`.

- R-3: **_KNOWN_NO_HANDLER staleness** — any new L1 event type added in Phase 2+ without a
  handler must be added to `_KNOWN_NO_HANDLER`. `test_all_l1_events_classified` catches this
  statically by diffing `V1_L1_EVENT_TYPES` against both sets (I-ST-10).

- R-4: **EFFECTIVE_BUDGET not TOKEN_BUDGET** — `build_context` must enforce `EFFECTIVE_BUDGET`
  (= TOKEN_BUDGET × 0.75). Tests parametrised over all three depths assert against effective
  values (1500/4500/9000). Using raw TOKEN_BUDGET values in tests would give false passes.

- R-5: **context_hash path ordering** — hash must use `sorted(loaded_file_paths)`. Any
  nondeterminism in path collection (e.g., `glob`, `os.listdir`) breaks I-CTX-1 and I-CTX-5.
  Mitigation: `test_context_hash_sorted_file_paths` reorders file load and asserts same hash.

- R-6: **replay_fn injection in sync_state** — production code uses `sdd_replay` as default.
  Tests MUST pass a stub `replay_fn` — never hit the real DB. `test_sync_no_direct_db_calls`
  monkeypatches `duckdb.connect` to raise and asserts no exception during sync (I-EL-9).
