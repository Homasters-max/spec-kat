# Plan: Rebuild SDD Framework Using SDD (sdd_v2)

## Context

Current SDD project is at Phase 6 (ACTIVE, 15/15 tasks DONE, invariants PASS). The `.sdd/tools/` directory contains 23 standalone Python scripts (~5500 LOC) — the SDD governance layer. There is no `src/` directory.

**Goal:** Archive current project to `/root/project/sdd_v1/`, then use SDD methodology to rebuild the SDD framework as a proper Python package in `src/sdd/`. Phase 8 completes the loop: governance itself migrates to `src/sdd/` as thin adapters.

---

## Resolved Design Decisions

### D-1: EventLog boundary — two sources, single DB, single seq

Both governance (meta) and runtime (application) events live in the same DuckDB:

```
event_source: "meta"    ← .sdd governance events
event_source: "runtime" ← src/sdd application events
```

**`I-EL-5: seq is globally monotonic across meta + runtime`** — single AUTOINCREMENT sequence, single writer path (`sdd_append`). No two events share the same seq regardless of source.

Meta layer does NOT import src/sdd. Runtime layer emits via `sdd_append(event_source="runtime")`.

### D-2: Reducer processes ONLY runtime events

```python
# reducer.py
def _reduce_events(events: List[EventRecord]) -> State:
    # ONLY processes event_source == "runtime"
    # meta events are filtered out before entering the reducer
```

Meta events do not affect application state. `sdd_replay(level=L1, source="runtime")` is the default replay path.

### D-3: Compatibility Spec (Spec_v0) — event-level, not just state-level

```
I-EL-4: v2.sdd_replay(v1_events, source="runtime", level=L1) produces same State as v1
I-EL-6: L1 event_type names and required fields are identical between v1 and v2
         (id, event_type, payload schema — field names and types must match)
```

Written before Phase 1. Defines: event schema, invariant equivalence, CLI contract, replay compatibility.

### D-4: TaskStartGuard — requires_invariants enforcement (not just declaration)

New tool: `sdd.guards.task_start.check_requires_invariants(task_id, required_ids)`.  
Checks that each listed invariant has status PASS in `.sdd/reports/ValidationReport_T-NNN.md` of the producing task.  
Wired into §R.6 protocol between steps 2 and 3.

### D-5: Command handler contract

All commands implement:
```python
class CommandHandler(Protocol):
    def handle(self, command: Command) -> List[DomainEvent]: ...
```

Defined in `core/types.py` in Phase 1. CLI routes to handlers. No CLI logic in command modules.

### D-6: Context builder moves to Phase 2

`build_context.py` (SEM-9) in Phase 2. Agents for Phases 3+ use it.

### D-7: ErrorEvent with lifecycle fields

```python
@dataclass(frozen=True)
class ErrorEvent(DomainEvent):
    error_type: str
    source: str          # module or command name
    recoverable: bool
    retry_count: int     # 0 on first occurrence; incremented on retry
    context: dict
```

`retry_count` prepares for retry/escalation tracking without requiring a full retry policy in Phase 1.

### D-8: L3 events — archive, never delete

```
Old: L3 → TTL 7 days → DELETE
New: L3 → TTL 7 days → ARCHIVE (set expired=true, never physically deleted)
```

**`I-EL-7: L3 events MUST be archived (expired=true), never deleted — reproducibility must be preserved`**

`sdd_replay(level=None, include_expired=True)` for full debug replay.

### D-9: Event classification as enforced contract

```
L1 (domain truth):    reducer works ONLY on L1 + source="runtime"
L2 (telemetry):       guards may read; 90-day retention
L3 (meta/governance): archive after TTL, never delete (I-EL-7)
```

### D-10: Metrics contract in Phase 1

```
I-M-1: every TaskCompleted event MUST be followed by ≥1 MetricRecorded event
        (task.lead_time minimum) within the same phase
```

`record_metric.py` is a mandatory Phase 1 component with this invariant enforced by `validate_invariants.py`.

### D-11: Spec→Code traceability

Every task declares:
```yaml
spec_refs: [Spec_vN §section, I-invariant-id, ...]
produces_invariants: [I-PK-1, ...]
requires_invariants: [I-PK-1, ...]   # checked by TaskStartGuard
```

### D-12: Phase-level aggregated invariants

Each phase spec ends with a `§PHASE-INV` section listing invariants that must ALL be PASS before phase can be COMPLETE. Example for Phase 1: `[I-PK-1..5, I-EL-1..2, I-EL-5, I-EL-7, I-M-1]`. Controls drift across ~152 tasks.

### D-14: I-EL-8 — causal link via execution context

Runtime events reference the meta event that triggered them:
```python
caused_by_meta_seq: Optional[int] = None   # in EventRecord schema
```

Set via context manager in governance scripts:
```python
with meta_context(meta_seq=governance_event.seq):
    # all sdd_append calls inside set caused_by_meta_seq=meta_seq
    command.handle(...)
```

If not inside a meta context: `caused_by_meta_seq=None` (valid — e.g. tests, direct API calls).

### D-15: I-EL-9 — single writer enforced by code analysis

All DuckDB writes MUST go through `sdd_append`. Enforced via:
1. `project_profile.yaml` `code_rules.forbidden_patterns`:
   ```yaml
   - pattern: "duckdb\\.connect"
     applies_to: "src/sdd/**/*.py"
     exclude: ["src/sdd/infra/db.py"]
     severity: hard
     message: "Direct duckdb.connect outside infra/db.py violates I-EL-9"
   ```
2. `validate_invariants.py` checks this pattern on Task Outputs (grep).

### D-16: I-CMD-1 — command idempotency by command_id

`Command` dataclass (Phase 1 schema) includes `command_id: str`.  
`CommandEvent` stored in event log contains `command_id`.  
In Phase 4, `handle()` checks:
```python
if event_log.exists_command(command_id=cmd.command_id):
    return []   # already processed — idempotent return
```

### D-17: I-ERR-1 — any exception → ErrorEvent (Phase 4 decorator)

```python
@error_event_boundary(source=__name__)
def handle(self, command: Command) -> List[DomainEvent]:
    ...
# On exception: emit ErrorEvent(retry_count=0, recoverable=...) → re-raise
```

`error_event_boundary` defined in `sdd.commands._base` (Phase 4). ErrorEvent schema defined in Phase 1.

### D-18: compatibility fixture from v1 DB

`tests/compatibility/fixtures/v1_events.json` — extracted from `sdd_v1/.sdd/state/sdd_events.duckdb` during bootstrap (Step 0.6). Sample of L1 events only. v1 events loaded with `event_source="runtime"` coercion (v1 predates the `event_source` field).

### D-19: transaction boundary for multi-event writes (I-EL-11)

```
I-EL-11: sdd_append_batch(events: List[Event]) → single DB transaction
         TaskCompleted + MetricRecorded always written via sdd_append_batch
```

Prevents I-M-1 violation on crash between the two events.

### D-13: Phase 8 — thin adapters, no sys.path hacks

```
Phase 8 approach:
  1. Install src/sdd as editable package: pip install -e .
  2. Each .sdd/tools/X.py becomes a thin adapter:
     #!/usr/bin/env python3
     from sdd.commands.X import main
     if __name__ == "__main__": main()
  3. No sys.path manipulation — uses proper package resolution
  4. Tests: adapter output == original script output (parity test)
```

### D-20: Scheduler — DAG-based task ordering with parallel groups (Phase 3)

```
domain/tasks/scheduler.py

TaskNode dataclass (frozen):
  task_id, depends_on: tuple[str,...], parallel_group: str | None

build_dag(tasks: list[Task]) → dict[str, TaskNode]:
  - Raises CyclicDependency if depends_on graph has a cycle
  - Raises MissingContext if depends_on references unknown task_id

topological_order(dag) → list[list[str]]:
  - Returns layers: each layer is a list of task_ids that can run in parallel
  - Layer N tasks have all their depends_on satisfied by layers 0..N-1
  - Tasks in same parallel_group are co-located in the same layer

Purity contract (same as reducer — I-ST-2 extension):
  - No I/O, no randomness, same dag → same topological_order always

Invariants produced:
  I-SCH-1: topological_order output has no cycles (verified by re-checking dag)
  I-SCH-2: every task appears exactly once across all layers
  I-SCH-3: build_dag / topological_order are pure functions
```

---

## Phase Overview

> ⚠️ Нумерация фаз обновлена. Актуальный план стабилизации ядра:
> `.sdd/docs/kernel_stabilization_roadmap.md`

| # | Title | Key D-* | Tasks | Status |
|---|-------|---------|-------|--------|
| 0  | Compatibility Spec (artifact, human gate)  | D-3, D-9                                              | —   | COMPLETE |
| 1  | Foundation                                 | D-1, D-2, D-5, D-7, D-8, D-9, D-10, D-12             | 22  | COMPLETE |
| 2  | State & Context                            | D-2 reducer filter, D-6 build_context                 | 15  | COMPLETE |
| 3  | Norm, Guards & Scheduler                   | D-4 TaskStartGuard, D-9 scheduler                     | 20  | COMPLETE |
| 4  | Commands Layer                             | D-5 handler contract, D-7 ErrorEvent lifecycle        | 27  | COMPLETE |
| 5  | Critical Fixes                             | I-ES-1 final, replay completeness, GuardContext dedup | 5   | COMPLETE |
| 6  | Query, Metrics & Reporting                 | D-10 I-M-1 enforcement, I-EL-6 check                  | 14  | COMPLETE |
| 7  | Hardening                                  | extension points, API polish, I-REDUCER-1             | 10  | COMPLETE |
| **8**  | **CLI + Kernel Stabilization**         | D-5 declarative CLI, kernel contracts freeze, §0.15   | 15  | **COMPLETE** |
| **9**  | **Command Envelope Refactor**          | BC-CMD-ENV registry + factory, fix all main(), I-CMD-ENV-1..6 | 10 | **COMPLETE** |
| **10** | **Kernel Hardening**                   | BC-EXEC execution contract, static enforcement, regression suite | 11 | **ACTIVE** |
| **11** | **Improvements & Integration** *(was 10)* | Risk #5, Risk #8, I-EL-4/6 compat tests           | ~20 | PLANNED |
| **12** | **Self-hosted Governance** *(was 11)*  | D-13 thin adapters, pip install -e                    | ~18 | PLANNED |

Total: ~140 tasks across phases 5–12 (avg ~20/phase).

---

## Step 0: Archive & Bootstrap ✓ COMPLETE

### 0.1 Draft Compatibility Spec (LLM first)

```
.sdd/specs_draft/Spec_v0_Compatibility.md
  §1  Event schema contract     — field names, types, required fields per event_type
  §2  event_source contract     — {"meta","runtime"} — I-EL-1
  §3  Invariant equivalence     — v2 must satisfy I-SDD-1..19 + I-EL-4, I-EL-6
  §4  Replay compatibility      — I-EL-4 (state), I-EL-6 (L1 event-level)
  §5  CLI contract              — complete/validate/query/metrics/error subset
  §6  Out of scope              — .sdd/tools/ CLI flags, L2/L3 events
```

Human approves → `.sdd/specs/Spec_v0_Compatibility.md`

### 0.2 Archive

```bash
mkdir -p /root/project/sdd_v1
rsync -a /root/project/ /root/project/sdd_v1/ --exclude sdd_v1/
```

### 0.3 Bootstrap

```
Copy from sdd_v1:
  .sdd/tools/      (governance — unchanged until Phase 8)
  .sdd/norms/
  .sdd/templates/  (update TaskSet_template: add spec_refs, produces_invariants, requires_invariants)
  .sdd/docs/
  CLAUDE.md

Create fresh:
  .sdd/{specs,specs_draft,plans,tasks,reports,state,runtime,config}/
  src/sdd/{core,infra,domain,guards,commands,hooks,context}/
  tests/{unit/{infra,domain,guards,commands},compatibility,integration}/
  tests/conftest.py
```

### 0.4 Phases_index.md

```markdown
| ID | Title | Spec | Status |
|----|-------|------|--------|
| 0  | Compatibility Contract | .sdd/specs/Spec_v0_Compatibility.md | COMPLETE |
| 1  | Foundation | .sdd/specs/Spec_v1_Foundation.md | PLANNED |
| 2  | State & Context | .sdd/specs/Spec_v2_State.md | PLANNED |
| 3  | Norm, Guards & Scheduler | .sdd/specs/Spec_v3_Guards.md | PLANNED |
| 4  | Commands Layer | .sdd/specs/Spec_v4_Commands.md | PLANNED |
| 5  | Query, Metrics & Reporting | .sdd/specs/Spec_v5_QueryMetrics.md | PLANNED |
| 6  | CLI + Hooks | .sdd/specs/Spec_v6_CLI.md | PLANNED |
| 7  | Improvements & Integration | .sdd/specs/Spec_v7_Improvements.md | PLANNED |
| 8  | Self-hosted Governance | .sdd/specs/Spec_v8_SelfHosted.md | PLANNED |
```

### 0.6 Extract v1 compatibility fixture

```bash
python3 -c "
import duckdb, json
con = duckdb.connect('sdd_v1/.sdd/state/sdd_events.duckdb', read_only=True)
rows = con.execute(\"SELECT * FROM events WHERE level='L1' LIMIT 200\").fetchall()
cols = [d[0] for d in con.description]
events = [dict(zip(cols, r)) for r in rows]
# coerce: add event_source='runtime' (v1 predates this field)
for e in events: e['event_source'] = 'runtime'
json.dump(events, open('tests/compatibility/fixtures/v1_events.json','w'), default=str)
"
```

This fixture is used by `tests/compatibility/test_v1_schema.py` (T-120).

### 0.5 Config files

**`.sdd/config/project_profile.yaml`:**
```yaml
stack:
  language: python
  version: "3.12"
  lint: ruff
  typecheck: mypy
build:
  commands:
    lint:      ruff check src/
    typecheck: mypy src/sdd/
    test:      pytest tests/ -q
testing:
  coverage_threshold: 80
scope:
  source_root: src/sdd/
  forbidden_dirs: [sdd_v1/, .sdd/state/]
code_rules:
  forbidden_patterns:
    - pattern: "duckdb\\.connect"
      applies_to: "src/sdd/**/*.py"
      exclude: ["src/sdd/infra/db.py"]
      severity: hard
      message: "Direct duckdb.connect violates I-EL-9 — use sdd_append/sdd_append_batch"
event_log:
  path: .sdd/state/sdd_events.duckdb
  meta_source: meta
  runtime_source: runtime
```

---

## Target Package Structure

```
src/sdd/
├── core/
│   ├── errors.py        ← SDDError hierarchy
│   ├── events.py        ← DomainEvent, ErrorEvent(+retry_count), CommandEvent, L1/L2/L3 contract
│   └── types.py         ← frozen dataclasses + CommandHandler Protocol
├── infra/
│   ├── db.py            ← sdd_db.py + event_source + expired columns; single AUTOINCREMENT seq
│   ├── event_log.py     ← sdd_append(event_source=), sdd_replay(level, source, include_expired)
│   ├── audit.py         ← senar_audit.py
│   ├── config_loader.py ← 3-level YAML override
│   └── metrics.py       ← record_metric.py (mandatory Phase 1, I-M-1 enforcement)
├── domain/
│   ├── norms/catalog.py
│   ├── state/
│   │   ├── yaml_state.py
│   │   ├── sync.py
│   │   ├── reducer.py   ← ONLY source="runtime", level=L1 events processed
│   │   └── init_state.py
│   ├── tasks/
│   │   ├── parser.py    ← +spec_refs, produces_invariants, requires_invariants fields
│   │   └── scheduler.py ← Phase 3: DAG, depends_on, parallel groups
│   └── validation/
│       └── invariants.py ← +phase-level aggregated invariant sets per phase
├── guards/
│   ├── scope.py
│   ├── phase.py
│   ├── task.py
│   ├── task_start.py    ← NEW: check_requires_invariants (D-4)
│   ├── norm.py
│   └── runner.py        ← +task_start guard in pipeline
├── commands/
│   ├── update_state.py
│   ├── validate_invariants.py
│   ├── validate_config.py
│   ├── record_decision.py
│   ├── report_error.py  ← emits ErrorEvent(retry_count=0)
│   ├── query_events.py  ← +event_source filter, +include_expired
│   ├── metrics_report.py
│   └── sdd_run.py       ← Command → handle() → List[DomainEvent]
├── hooks/
│   ├── log_tool.py      ← event_source="meta", L2; L3 archived not deleted
│   └── log_bash.py      ← legacy stub
├── context/
│   └── build_context.py ← Phase 2
└── cli.py               ← Click router, declarative, no logic
```

**EventLog invariants:**
```
I-EL-1:  event_source ∈ {"meta", "runtime"}
I-EL-2:  sdd_replay(level=L1, source="runtime") returns ONLY L1 runtime events
I-EL-3:  meta events do NOT cause state changes (reducer filters them out)
I-EL-4:  v2.sdd_replay(v1_events, ...) produces same State as v1
I-EL-5:  seq globally monotonic across meta + runtime (single AUTOINCREMENT)
I-EL-6:  L1 event_type names and required field names identical between v1 and v2
I-EL-7:  L3 events MUST be archived (expired=true), never physically deleted
I-EL-8:  runtime events have caused_by_meta_seq referencing triggering meta event (or null)
I-EL-9:  all DB writes go through sdd_append — no direct duckdb.connect outside infra/db.py
I-EL-10: sdd_replay() default params = level=L1, source="runtime"
I-EL-11: TaskCompleted + MetricRecorded written via sdd_append_batch (single transaction)

Command invariants:
I-CMD-1: handle(command) is idempotent by command_id — re-processing returns []
I-ERR-1: any exception in handle() emits ErrorEvent before propagating

Metrics invariants:
I-M-1:   TaskCompleted → ≥1 MetricRecorded (task.lead_time) in same transaction (I-EL-11)
```

---

## Phase 1 Detail: Foundation

**Spec:** `.sdd/specs/Spec_v1_Foundation.md`  
**Phase-level invariants (§PHASE-INV):** `[I-PK-1..5, I-EL-1, I-EL-2, I-EL-5, I-EL-7, I-M-1]`

| ID | Invariant |
|----|-----------|
| I-PK-1 | `open_sdd_connection` idempotent: N calls → same schema |
| I-PK-2 | `sdd_append` idempotent: duplicate event_id → ON CONFLICT DO NOTHING |
| I-PK-3 | `sdd_replay` returns events ordered strictly by seq ASC |
| I-PK-4 | `classify_event_level` is a pure total function |
| I-PK-5 | `atomic_write` uses tmp+os.replace |
| I-EL-1 | `event_source ∈ {"meta", "runtime"}` |
| I-EL-2 | `sdd_replay(level=L1, source="runtime")` returns ONLY L1 runtime events |
| I-EL-5 | seq globally monotonic across all sources |
| I-EL-7 | L3 events archived (expired=true), never deleted |
| I-EL-8 | runtime events have `caused_by_meta_seq` (Optional[int]) in schema |
| I-EL-9 | no direct `duckdb.connect` outside `infra/db.py` (enforced by code_rules) |
| I-EL-10 | `sdd_replay()` default = `level=L1, source="runtime"` |
| I-EL-11 | TaskCompleted + MetricRecorded written via `sdd_append_batch` (single txn) |
| I-CMD-1 | `handle(cmd)` idempotent by `command_id` |
| I-M-1  | TaskCompleted → ≥1 MetricRecorded in same batch (I-EL-11) |

**22 tasks:**

| Task | Output | produces_inv | requires_inv |
|------|--------|-------------|--------------|
| T-101 | pyproject.toml, src/sdd/__init__.py, src/sdd/py.typed | I-PK-1 | — |
| T-102 | core/errors.py (SDDError hierarchy) | I-PK-4 | I-PK-1 |
| T-103 | core/events.py (DomainEvent+caused_by_meta_seq, ErrorEvent+retry_count, CommandEvent+command_id schema, L1/L2/L3) | I-PK-4, I-EL-2, I-EL-8 | I-PK-1 |
| T-104 | core/types.py (frozen dataclasses + CommandHandler Protocol with command_id) | I-PK-4, I-CMD-1 | I-PK-1 |
| T-105 | infra/db.py (schema: event_source + expired + caused_by_meta_seq cols, single AUTOINCREMENT) | I-PK-1, I-EL-1, I-EL-5, I-EL-8 | I-PK-4 |
| T-106 | tests/unit/infra/test_db.py | — | I-PK-1, I-EL-1, I-EL-5 |
| T-107 | infra/event_log.py (sdd_append+event_source+caused_by_meta_seq, sdd_append_batch txn, sdd_replay defaults level=L1 source="runtime", meta_context()) | I-PK-2, I-PK-3, I-EL-2, I-EL-7, I-EL-9, I-EL-10, I-EL-11 | I-PK-1, I-EL-1, I-EL-8 |
| T-108 | tests/unit/infra/test_event_log.py (idempotency, replay order, L3 archive, batch txn, I-EL-9 grep check) | — | I-PK-2, I-PK-3, I-EL-7, I-EL-11 |
| T-109 | infra/audit.py (log_action, AuditEntry, make_entry_id deterministic) | I-PK-5 | I-PK-4 |
| T-110 | tests/unit/infra/test_audit.py | — | I-PK-5 |
| T-111 | infra/config_loader.py (3-level override) | I-PK-4 | I-PK-1 |
| T-112 | tests/unit/infra/test_config_loader.py | — | I-PK-4 |
| T-113 | tests/conftest.py, __init__ stubs, tmp_db_path + tmp_state_dir fixtures | I-PK-1 | I-PK-1 |
| T-114 | infra/__init__.py (public re-exports) | I-PK-1 | I-PK-1..5 |
| T-115 | core/__init__.py (public re-exports) | I-PK-4 | I-PK-4 |
| T-116 | infra/db.py: SDD_SEQ_CHECKPOINT=1 + SDD-SEQ-1 comment | I-PK-1 | I-PK-1 |
| T-117 | pyproject.toml [tool.pytest/ruff/mypy/coverage sections] | I-PK-1 | I-PK-1 |
| T-118 | infra/metrics.py (record_metric, sdd_append_batch used for TaskCompleted+MetricRecorded) | I-PK-2, I-M-1, I-EL-11 | I-PK-2, I-PK-3, I-EL-11 |
| T-119 | tests/unit/infra/test_metrics.py (I-M-1 enforcement test) | — | I-M-1 |
| T-120 | tests/compatibility/test_v1_schema.py (L1 field names vs Spec_v0 §1 — I-EL-6) | I-EL-6 | I-PK-2, I-PK-3 |
| T-121 | .sdd/reports/ValidationReport_T-121.md (phase-level invariant pass: all I-PK-*, I-EL-1/2/5/7, I-M-1) | — | all above |
| T-122 | .sdd/reports/Phase1_Summary.md + Metrics_Phase1.md | — | T-121 |

---

## Phase 8: Self-hosted Governance (thin adapters)

```
1. pip install -e .    (editable install of src/sdd — no sys.path hacks)
2. Each .sdd/tools/X.py → thin adapter:
   #!/usr/bin/env python3
   from sdd.commands.X import main
   if __name__ == "__main__": main()
3. Parity tests: .sdd/tools/X.py output == sdd CLI output (same args, same fixture)
4. governance events continue with event_source="meta"
5. Phase-level invariant: all .sdd/tools/ adapters pass parity tests
```

This closes the self-referential loop without any path manipulation.

---

## Phase 2 Detail: State & Context

**Spec:** `.sdd/specs/Spec_v2_State.md`  
**Status:** COMPLETE — 15/15 tasks DONE, invariants PASS, coverage 90.46%  
**Phase-level invariants (§PHASE-INV):** `[I-TS-1..3, I-EL-3, I-EL-9, I-EL-13, I-ST-1..11, I-CTX-1..6]`

| Task | Output | produces_inv | requires_inv |
|------|--------|-------------|--------------|
| T-201 | domain/tasks/parser.py (Task dataclass + parse_taskset) | I-TS-1, I-TS-2, I-TS-3 | — |
| T-202 | domain/tasks/__init__.py, tests/.../test_parser.py (6 tests) | — | I-TS-1..3 |
| T-203 | domain/state/reducer.py (SDDState, ReducerDiagnostics, EventReducer) | I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10, I-ST-11, I-EL-3, I-EL-13 | — |
| T-204 | tests/.../test_reducer.py (16 tests) | — | I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10, I-EL-3, I-EL-13 |
| T-205 | core/events.py: PhaseInitializedEvent, StateDerivationCompletedEvent | — | — |
| T-206 | domain/state/yaml_state.py (read_state + write_state) | I-ST-3, I-ST-8, I-ST-11 | I-ST-11 |
| T-207 | tests/.../test_yaml_state.py (8 tests) | — | I-ST-3, I-ST-8, I-ST-11 |
| T-208 | domain/state/sync.py (sync_state algorithm) | I-ST-4, I-ST-6, I-EL-9 | I-ST-3, I-TS-1, I-TS-2 |
| T-209 | tests/.../test_sync.py (7 tests) | — | I-ST-4, I-ST-6, I-EL-9 |
| T-210 | domain/state/init_state.py (init_state algorithm) | I-ST-5 | I-TS-1, I-ST-3 |
| T-211 | tests/.../test_init_state.py (5 tests) + domain/state/__init__.py | — | I-ST-5, I-EL-9 |
| T-212 | context/build_context.py (staged context builder) | I-CTX-1..6 | I-ST-3, I-TS-1 |
| T-213 | context/__init__.py + tests/.../test_build_context.py (12 tests) | — | I-CTX-1..6 |
| T-214 | domain/__init__.py (BC boundary + integration smoke) | — | I-TS-1..3, I-ST-1..2, I-CTX-1 |
| T-215 | .sdd/reports/ValidationReport_T-215.md (§PHASE-INV coverage report) | I-EL-3, I-EL-13, I-ST-1..11, I-TS-1..3, I-CTX-1..6 | all above |

---

## Phase 3 Constraints (known before Spec_v3 is written)

### C-1: I-ST-10 — assert при импорте (BLOCKING)

`EventReducer` в [src/sdd/domain/state/reducer.py](src/sdd/domain/state/reducer.py) содержит **assert на уровне класса** (выполняется при каждом импорте модуля):

```python
assert _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
```

**Правило для Phase 3:** любой новый L1 event type (например `NormViolated`, `TaskStartGuardRejected`, `TaskScheduled`) ДОЛЖЕН быть добавлен в `V1_L1_EVENT_TYPES` ([src/sdd/core/events.py](src/sdd/core/events.py)) **одновременно** с регистрацией в одном из двух мест:
- `_EVENT_SCHEMA` — если reducer должен его обрабатывать
- `_KNOWN_NO_HANDLER` — если reducer игнорирует (governance/observability events)

Нарушение → `AssertionError` при импорте → весь процесс не запускается.

### C-2: Зависимости Phase 3 от Phase 2

| requires_inv | Источник | Кто использует в Phase 3 |
|---|---|---|
| I-TS-1 | T-201 | TaskStartGuard читает `task.requires_invariants` |
| I-TS-2 | T-201 | Scheduler кэширует результат `parse_taskset()` |
| I-ST-4 | T-208 | `phase_guard` должен обрабатывать `Inconsistency` из `sync_state` |
| I-CTX-6 | T-212 | Новые контекстные слои Phase 3 должны вписаться в порядок 0→8 |
| I-EL-9 | T-107/T-208 | Guards не делают `duckdb.connect` напрямую |

---

## SDD Workflow Per Phase

```
1. LLM: Draft Spec_vN        → .sdd/specs_draft/Spec_vN_*.md (includes §PHASE-INV)
2. Human: Approve             → .sdd/specs/Spec_vN_*.md  (NORM-GATE-001)
3. LLM: Plan Phase N          → .sdd/plans/Plan_vN.md  DRAFT
4. Human: Activate plan       → plan.status → ACTIVE  (NORM-GATE-002)
5. LLM: Decompose Phase N     → .sdd/tasks/TaskSet_vN.md (all TODO; spec_refs + inv fields)
6. LLM: Init State N          → .sdd/runtime/State_index.yaml
7. LLM: Implement T-NNN
     a. phase_guard.py check
     b. task_guard.py check
     c. task_start.py check_requires_invariants    ← NEW (D-4)
     d. check_scope.py read inputs
     e. Implement outputs
     f. update_state.py complete T-NNN → emits TaskCompleted + MetricRecorded (I-M-1)
8. LLM: Validate T-NNN
     a. validate_invariants.py --task T-NNN (checks produces_invariants)
     b. update_state.py validate T-NNN --result PASS|FAIL
9. After all tasks: validate §PHASE-INV set → all must PASS
10. Summarize + Metrics + EventLog snapshot
11. Human gate                → phase COMPLETE  (NORM-GATE-003)
```

---

## Critical Files

| File | Role |
|------|------|
| `sdd_v1/.sdd/tools/` | Reference implementation for all rebuilt modules |
| `.sdd/specs/Spec_v0_Compatibility.md` | v1↔v2 formal contract (I-EL-4, I-EL-6) |
| `.sdd/tools/update_state.py` | Sole mutation path (governance) |
| `.sdd/tools/validate_invariants.py` | Invariant checker (governance) |
| `CLAUDE.md` | Master protocol |
| `.sdd/plans/Phases_index.md` | Phase registry |
| `.sdd/config/project_profile.yaml` | Stack + build + event_log config |

---

## Verification (after Phase 8)

```bash
pip install -e .
python -c "import sdd; print(sdd.__version__)"
pytest tests/ -q --tb=short
mypy src/sdd/
ruff check src/

# v1 compatibility
pytest tests/compatibility/ -q

# I-M-1: every TaskCompleted has ≥1 metric
python3 .sdd/tools/validate_invariants.py --check I-M-1 --phase 8

# governance via thin adapters
python3 .sdd/tools/update_state.py complete T-801

# full event audit with both sources
python3 .sdd/tools/query_events.py --phase 8 --include-bash --json
```
