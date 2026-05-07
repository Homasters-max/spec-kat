# Spec_v6_QueryMetrics — Phase 6: Query, Metrics & Reporting

Status: Draft
Baseline: Spec_v5_CriticalFixes.md (BC-CORE, BC-INFRA, BC-STATE, BC-GUARDS, BC-COMMANDS)

---

## 0. Goal

Add the query, metrics aggregation, and observability infrastructure to `src/sdd/`.
After this phase:

- `EventLogQuerier` + `QueryEventsHandler` provide a programmatic API for querying the
  EventLog with filters (phase, event_type, event_source, include_expired);
  `QueryEventsHandler` uses a dedicated `QueryHandler` Protocol — it is NOT routed through
  `CommandRunner` and returns `QueryEventsResult` directly (no side-channel state)
- `MetricsAggregator` + `MetricsReportHandler` aggregate `MetricRecorded` events per phase
  and generate human-readable Markdown reports; `MetricsReportHandler` calls `EventLogQuerier`
  directly — never another `CommandHandler` (I-CHAIN-1)
- `validate_invariants` enforces **I-M-1**: any `TaskCompleted` event without a corresponding
  `MetricRecorded` with matching `task_id` in payload is flagged as a violation
- `hooks/log_tool.py` implements the Claude Code `PreToolUse` / `PostToolUse` hook:
  it logs `ToolUseStarted` / `ToolUseCompleted` as `event_source="meta"` L2 events;
  on write failure it emits `HookErrorEvent` (L3) before exiting 0 — so diagnostics
  are preserved without ever blocking execution (I-HOOK-2, I-HOOK-4)
- `hooks/log_bash.py` is a legacy stub that delegates to `log_tool.py`
- All projections satisfy the **Projection Layer Contract** (I-PROJ-CONST-1..3):
  deterministic over EventLog snapshot, no shared handler state, no hidden caching

This phase does **NOT** introduce CLI entry points, trend analysis, anomaly detection,
or the metrics dashboard. Those are Phase 8/9 scope.

---

## 1. Scope

### In-Scope

- BC-QUERY: `infra/event_query.py` + `commands/query_events.py`
- BC-METRICS: `domain/metrics/` + `commands/metrics_report.py`
- BC-HOOKS: `hooks/log_tool.py` + `hooks/log_bash.py`
- BC-VALIDATION extension: `commands/validate_invariants.py` — add I-M-1 enforcement check
- `core/events.py` + `domain/state/reducer.py` — register `ToolUseStarted`, `ToolUseCompleted`
  in `_KNOWN_NO_HANDLER` + `V1_L1_EVENT_TYPES` (C-1 compliance)
- Invariants: I-CHAIN-1, I-QE-1..4, I-MR-1..2, I-M-1-CHECK, I-HOOK-1..4,
  I-HOOKS-ISO, I-PROJ-CONST-1..3
- Tests for all above

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### §2.1 Layer Model (enforced by I-CHAIN-1)

Three distinct layers with one-directional dependency:

```
(C) Command / Orchestration layer
    MetricsReportHandler
    validate_invariants.check_im1_invariant
    ↓  (allowed: call Query layer and Domain pure functions)
    ↓  (FORBIDDEN: call another CommandHandler — I-CHAIN-1)

(B) Domain / Aggregation layer
    MetricsAggregator         ← pure function, no I/O
    ↓

(A) Query layer
    EventLogQuerier           ← read-only SQL, no side effects
```

`QueryEventsHandler` is a **read-side handler** — it uses `QueryHandler` Protocol
(not `CommandHandler`) and is called directly by callers; it is NOT routed through
`CommandRunner`.

### §2.2 BC-QUERY

```
src/sdd/infra/event_query.py      ← QueryFilters, EventLogQuerier (SQL builder + DuckDB read)
src/sdd/commands/query_events.py  ← QueryEventsCommand, QueryEventsResult, QueryEventsHandler
```

`EventLogQuerier` is a pure read path — it reads but never writes (I-PROJ-CONST-1).
`QueryEventsHandler` conforms to `QueryHandler` Protocol (returns `QueryEventsResult`,
NOT `list[DomainEvent]`); it is NOT registered with `CommandRunner`.

### §2.3 BC-METRICS

```
src/sdd/domain/metrics/__init__.py
src/sdd/domain/metrics/aggregator.py  ← MetricRecord, MetricsSummary, MetricsAggregator
src/sdd/commands/metrics_report.py    ← MetricsReportCommand, MetricsReportHandler
```

`MetricsAggregator` is a pure function of its inputs — no I/O (I-MR-2, I-PROJ-CONST-1).
`MetricsReportHandler` calls `EventLogQuerier` directly. It MUST NOT call
`QueryEventsHandler` or any other `CommandHandler` (I-CHAIN-1).

### §2.4 BC-HOOKS

```
src/sdd/hooks/log_tool.py  ← PreToolUse / PostToolUse hook (always exit 0; HookErrorEvent on failure)
src/sdd/hooks/log_bash.py  ← legacy stub; delegates to log_tool.py
```

Hooks are invoked as subprocess commands by Claude Code — they are **NOT imported** by any
module in `src/sdd/` (I-HOOKS-ISO). They use `sdd_append` from `infra/event_log.py`
(I-EL-9: no direct `duckdb.connect`).

**BC-HOOKS Isolation Rule (I-HOOKS-ISO):**
```
MUST NOT:  import hooks.* from any domain / commands / infra module
MUST NOT:  import hooks.* in tests directly (tests use subprocess.run only)
ALLOWED:   hooks import from infra/event_log.py and core/events.py only
```

### §2.5 Dependencies

```
BC-QUERY    → infra/db.py (DuckDB read connection)
BC-METRICS  → infra/event_query.py (EventLogQuerier — Layer A)
BC-METRICS  → domain/metrics/aggregator.py (MetricsAggregator — Layer B)
BC-HOOKS    → infra/event_log.py (sdd_append, event_source="meta")
BC-HOOKS    → core/events.py (ToolUseStarted/ToolUseCompleted/HookErrorEvent dataclasses)
BC-VALIDATION-EXT → infra/event_query.py + domain/metrics/aggregator.py
C-1 compliance    → core/events.py + domain/state/reducer.py
```

**FORBIDDEN cross-layer calls:**
```
MetricsReportHandler  →  QueryEventsHandler     ← FORBIDDEN (I-CHAIN-1)
validate_invariants   →  MetricsReportHandler   ← FORBIDDEN (I-CHAIN-1)
hooks/**              →  commands/**            ← FORBIDDEN (I-HOOKS-ISO)
hooks/**              →  domain/**              ← FORBIDDEN (I-HOOKS-ISO)
```

---

## 3. Domain Events

### ToolUseStarted (L2 Operational — meta)

Emitted by `hooks/log_tool.py` at `PreToolUse`. Not processed by reducer (L2, `_KNOWN_NO_HANDLER`).

```python
@dataclass(frozen=True)
class ToolUseStartedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "ToolUseStarted"
    tool_name:    str
    extra:        tuple[tuple[str, str], ...]  # key-value pairs per CLAUDE.md §0.12 taxonomy
    timestamp_ms: int                          # Unix ms
```

### ToolUseCompleted (L2 Operational — meta)

Emitted by `hooks/log_tool.py` at `PostToolUse`.

```python
@dataclass(frozen=True)
class ToolUseCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "ToolUseCompleted"
    tool_name:     str
    output_len:    int
    interrupted:   bool
    error_snippet: str    # "" if no error; first 200 chars otherwise
    timestamp_ms:  int
```

### HookErrorEvent (L3 Debug — meta)

Emitted by `hooks/log_tool.py` when `sdd_append` fails. Written with `expired=false`
initially; archived (TTL → `expired=true`) per retention policy — never deleted (I-EL-7).
This preserves failure diagnostics without blocking Claude Code execution (I-HOOK-2).

```python
@dataclass(frozen=True)
class HookErrorEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "HookError"
    hook_name:    str    # "log_tool"
    error_type:   str    # exception class name
    error_msg:    str    # first 300 chars of str(exc)
    timestamp_ms: int
```

**Fallback:** If `sdd_append(HookErrorEvent, ...)` itself fails, log full traceback to
`stderr` via `logging.error`. Exit 0 in all cases (I-HOOK-2). Root cause is never silently
lost.

### Event Catalog

| Event | Source | Level | Emitter | Description |
|-------|--------|-------|---------|-------------|
| `ToolUseStarted` | meta | L2 | `hooks/log_tool.py` | Tool call begins |
| `ToolUseCompleted` | meta | L2 | `hooks/log_tool.py` | Tool call ends |
| `HookError` | meta | L3 | `hooks/log_tool.py` | Hook write failure; diagnostic only |

### C-1 Compliance (Phase 6 — BLOCKING)

`ToolUseStarted`, `ToolUseCompleted`, and `HookError` are new event_type strings. They are
**L2/L3 / meta** — the reducer must NOT process them as state changes. They MUST be added
to `_KNOWN_NO_HANDLER` and `V1_L1_EVENT_TYPES` in a single task (T-611):

```python
assert _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
```

Violation → `AssertionError` on import → whole process fails.

---

## 4. Types & Interfaces

### 4.1 QueryFilters (`infra/event_query.py`)

```python
@dataclass(frozen=True)
class QueryFilters:
    phase_id:        int | None = None   # filter payload.phase_id == N
    event_type:      str | None = None   # exact match on event_type column
    event_source:    str | None = None   # "meta" | "runtime" | None (all)
    include_expired: bool = False        # if True, include expired=true rows (L3 archived)
    limit:           int | None = None   # None = no limit
    order:           str = "ASC"         # "ASC" | "DESC" by seq
```

### 4.2 EventLogQuerier (`infra/event_query.py`)

```python
class EventLogQuerier:
    """Read-only query path. Never calls sdd_append or modifies DB.
    I-PROJ-CONST-1: same db_path + same filters → same result (deterministic).
    I-PROJ-CONST-2: no shared state between calls; no hidden caching.
    """

    def __init__(self, db_path: str) -> None: ...

    def query(self, filters: QueryFilters) -> tuple[EventRecord, ...]:
        """
        I-QE-1: ordered by seq ASC/DESC per filters.order
        I-QE-2: event_source filter is exact — no partial matches
        I-QE-3: expired=true rows excluded when include_expired=False (default)
        I-QE-4: phase_id filter matches JSON_EXTRACT(payload, '$.phase_id')
        """
        ...
```

### 4.3 QueryHandler Protocol + QueryEventsHandler (`commands/query_events.py`)

`QueryEventsHandler` is a **read-side handler** — it returns `QueryEventsResult` directly.
It does NOT conform to `CommandHandler` Protocol and is NOT routed through `CommandRunner`.
This eliminates the `self.last_result` side-channel anti-pattern.

```python
class QueryHandler(Protocol):
    """Read-side handler protocol. Distinct from CommandHandler (write-side)."""
    def execute(self, query: QueryEventsCommand) -> QueryEventsResult: ...

@dataclass(frozen=True)
class QueryEventsCommand:
    filters: QueryFilters

@dataclass(frozen=True)
class QueryEventsResult:
    events: tuple[EventRecord, ...]
    total:  int

class QueryEventsHandler:
    """
    Thin wrapper over EventLogQuerier. Conforms to QueryHandler Protocol.
    No state between calls (I-PROJ-CONST-2).
    No DB writes (I-PROJ-CONST-1).
    """
    def __init__(self, db_path: str) -> None: ...

    def execute(self, query: QueryEventsCommand) -> QueryEventsResult:
        """
        Calls EventLogQuerier.query(query.filters) → returns QueryEventsResult.
        Never calls CommandRunner or any other CommandHandler (I-CHAIN-1).
        """
        ...
```

### 4.4 MetricRecord (`domain/metrics/aggregator.py`)

```python
@dataclass(frozen=True)
class MetricRecord:
    seq:         int
    metric_id:   str    # e.g. "task.lead_time"
    value:       float
    task_id:     str | None
    phase_id:    int | None
    context:     tuple[tuple[str, str], ...]  # serialized key-value pairs
    recorded_at: str    # ISO8601
```

### 4.5 MetricsSummary (`domain/metrics/aggregator.py`)

```python
@dataclass(frozen=True)
class MetricsSummary:
    phase_id:          int
    task_count:        int                       # count of TaskCompleted events
    metric_count:      int                       # count of MetricRecorded events
    metrics:           tuple[MetricRecord, ...]  # all metrics for phase_id
    im1_violations:    tuple[str, ...]           # task_ids missing MetricRecorded
    has_im1_violation: bool                      # True if im1_violations non-empty
```

### 4.6 MetricsAggregator (`domain/metrics/aggregator.py`)

```python
class MetricsAggregator:
    """
    Pure aggregation over queried events. No I/O — accepts pre-fetched event tuples.
    I-MR-2: same inputs → same MetricsSummary (pure function).
    I-PROJ-CONST-1: deterministic; no randomness, no I/O.
    I-PROJ-CONST-2: no instance state between calls.
    """

    def aggregate(
        self,
        task_completed_events: tuple[EventRecord, ...],
        metric_recorded_events: tuple[EventRecord, ...],
        phase_id: int,
    ) -> MetricsSummary:
        """
        I-MR-1 check (task_id correlation):
          For each TaskCompleted event with payload.task_id == T:
            look for any MetricRecorded event with payload.task_id == T
            and payload.metric_id == "task.lead_time".
          If none found → add T to im1_violations.

        No batch_id required. No seq-proximity heuristic.
        Correlation is solely by matching task_id in payload.
        """
        ...
```

### 4.7 MetricsReportCommand / MetricsReportHandler (`commands/metrics_report.py`)

```python
@dataclass(frozen=True)
class MetricsReportCommand(Command):
    phase_id:    int
    output_path: str | None = None  # if None, returns Markdown string only

class MetricsReportHandler:
    """
    Orchestrates Layer A → Layer B pipeline. No other CommandHandlers called (I-CHAIN-1).
    I-PROJ-CONST-3: no handler-level caching; each handle() call reads from EventLog fresh.
    """

    def __init__(self, db_path: str) -> None: ...

    def handle(self, command: MetricsReportCommand) -> list[DomainEvent]:
        """
        Steps:
          1. self._querier.query(QueryFilters(phase_id=N, event_type="TaskCompleted"))
             — calls EventLogQuerier directly, NOT QueryEventsHandler (I-CHAIN-1)
          2. self._querier.query(QueryFilters(phase_id=N, event_type="MetricRecorded"))
          3. MetricsAggregator().aggregate(...) → MetricsSummary
          4. Render Markdown; write to output_path if set
          5. Return []  — no events emitted; I-ES-6 upheld

        I-MR-2: same db_path + same phase_id → same Markdown output
        """
        ...
```

### 4.8 I-M-1 check in `validate_invariants.py`

```python
def check_im1_invariant(db_path: str, phase_id: int) -> InvariantCheckResult:
    """
    Uses EventLogQuerier (Layer A) + MetricsAggregator (Layer B) directly.
    Does NOT call MetricsReportHandler or any CommandHandler (I-CHAIN-1).

    Returns PASS if MetricsSummary.has_im1_violation == False.
    Returns FAIL with im1_violations task_ids if any violation exists.
    """
    ...
```

### 4.9 `hooks/log_tool.py`

```
Invocation (Claude Code hook — NOT importable, always subprocess):
  PreToolUse:   python3 src/sdd/hooks/log_tool.py pre  <tool_name> [extra_json]
  PostToolUse:  python3 src/sdd/hooks/log_tool.py post <tool_name> [extra_json]

Normal path:
  1. DB_PATH = os.environ.get("SDD_DB_PATH", ".sdd/state/sdd_events.duckdb")
  2. Build ToolUseStarted / ToolUseCompleted event dict
  3. sdd_append(event_type, payload, db_path=DB_PATH, event_source="meta", level="L2")
  4. sys.exit(0)

Failure path (sdd_append raises):
  1. Build HookErrorEvent(hook_name="log_tool", error_type=..., error_msg=..., timestamp_ms=...)
  2. Attempt sdd_append("HookError", hook_error_payload, event_source="meta", level="L3")
     — if this also raises: log full traceback to stderr via logging.error()
  3. sys.exit(0)  ← ALWAYS; never block Claude Code execution (I-HOOK-2)

I-HOOKS-ISO enforced:
  - hooks/log_tool.py imports ONLY from: infra.event_log, core.events, stdlib
  - NO imports from commands.*, domain.*, guards.*
```

---

## 5. Invariants

### New Invariants (Phase 6)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-CHAIN-1 | `CommandHandler.handle()` MUST NOT call another `CommandHandler.handle()`. It MAY call `EventLogQuerier.query()` (Layer A) and domain pure functions (Layer B). Violation creates command-chain coupling that breaks testability and future caching/async. | `tests/unit/commands/test_metrics_report.py` — `test_no_query_handler_in_report`; `tests/unit/commands/test_validate_invariants.py` — `test_no_command_handler_in_im1_check`; code review via `project_profile.yaml` `code_rules` grep |
| I-QE-1 | `EventLogQuerier.query(filters)` result ordered by `seq ASC` when `filters.order=="ASC"` (and `DESC` otherwise) | `tests/unit/infra/test_event_query.py` — `test_query_order_asc`, `test_query_order_desc` |
| I-QE-2 | `filters.event_source` is an exact match — `"meta"` returns ONLY meta events; `"runtime"` returns ONLY runtime events; `None` returns all | `tests/unit/infra/test_event_query.py` — `test_query_source_filter_meta`, `test_query_source_filter_runtime`, `test_query_source_filter_none` |
| I-QE-3 | `filters.include_expired=False` (default) excludes `expired=true` rows; `True` includes them | `tests/unit/infra/test_event_query.py` — `test_query_excludes_expired_by_default`, `test_query_includes_expired_when_flag_set` |
| I-QE-4 | `filters.phase_id=N` matches events where `JSON_EXTRACT(payload, '$.phase_id') = N` | `tests/unit/infra/test_event_query.py` — `test_query_phase_id_filter` |
| I-MR-1 | `MetricsSummary.has_im1_violation` is `True` iff any `TaskCompleted` event (by `task_id`) in the phase has no corresponding `MetricRecorded` event with matching `task_id` and `metric_id=="task.lead_time"` in payload. No seq-proximity or batch_id required — correlation is solely by `task_id`. | `tests/unit/domain/metrics/test_aggregator.py` — `test_im1_violation_detected`, `test_no_im1_violation_when_metric_present`, `test_im1_correlation_by_task_id_only` |
| I-MR-2 | `MetricsAggregator.aggregate()` is a pure function — same inputs → same `MetricsSummary`; no I/O, no randomness, no instance state | `tests/unit/domain/metrics/test_aggregator.py` — `test_aggregator_deterministic` |
| I-M-1-CHECK | `validate_invariants.check_im1_invariant(db_path, phase_id)` returns `FAIL` when any `TaskCompleted` event lacks a paired `MetricRecorded`; returns `PASS` otherwise. Uses EventLogQuerier + MetricsAggregator directly (I-CHAIN-1). | `tests/unit/commands/test_validate_invariants.py` — `test_check_im1_pass`, `test_check_im1_fail_missing_metric` |
| I-HOOK-1 | `hooks/log_tool.py` calls `sdd_append(..., event_source="meta")` exclusively — never `"runtime"` | `tests/unit/hooks/test_log_tool.py` — `test_hook_uses_meta_source` |
| I-HOOK-2 | `hooks/log_tool.py` exits with code `0` unconditionally — on success and on any exception (including HookErrorEvent write failure) | `tests/unit/hooks/test_log_tool.py` — `test_hook_exits_zero_on_success`, `test_hook_exits_zero_on_exception`, `test_hook_exits_zero_on_double_failure` |
| I-HOOK-3 | `ToolUseStarted` / `ToolUseCompleted` events written with `level="L2"`; `HookError` events written with `level="L3"`, `expired=false` initially (archived by TTL, never deleted — I-EL-7) | `tests/unit/hooks/test_log_tool.py` — `test_hook_event_level_l2`, `test_hook_error_event_level_l3` |
| I-HOOK-4 | On `sdd_append` failure, `hooks/log_tool.py` MUST attempt to write `HookError` (L3) before exiting. If `HookError` write also fails, full traceback logged to `stderr`. Diagnostic is never silently lost. | `tests/unit/hooks/test_log_tool.py` — `test_hook_emits_error_event_on_failure`, `test_hook_logs_stderr_on_double_failure` |
| I-HOOKS-ISO | `hooks/` modules MUST NOT be imported by any module in `src/sdd/{commands,domain,guards,infra}/`. Tests for hooks MUST use `subprocess.run` — no direct import in test code. | `tests/unit/hooks/test_log_tool.py` (subprocess only); `project_profile.yaml` grep rule on hooks imports |
| I-PROJ-CONST-1 | All projections (`EventLogQuerier`, `MetricsAggregator`) MUST be deterministic over a fixed EventLog snapshot: same inputs → same output, always. No I/O, no randomness inside aggregate/query logic. | `test_aggregator_deterministic`, `test_query_deterministic` |
| I-PROJ-CONST-2 | No cross-call shared state in projection objects. Each `query()` / `aggregate()` call is independent. No hidden caching unless invalidation is explicit and tested. Phase 6 introduces no caching. | `test_aggregator_pure_no_io`, `test_querier_no_shared_state` |
| I-PROJ-CONST-3 | Each `CommandHandler.handle()` call reads from EventLog fresh — no handler-level result caching between invocations. | `tests/unit/commands/test_metrics_report.py` — `test_report_no_handler_cache` |

### C-1 Compliance (Phase 6 — BLOCKING)

| New event type | `_KNOWN_NO_HANDLER` | `V1_L1_EVENT_TYPES` | Task |
|---|---|---|---|
| `ToolUseStarted` | ✓ | ✓ | T-611 |
| `ToolUseCompleted` | ✓ | ✓ | T-611 |
| `HookError` | ✓ | ✓ | T-611 |

Import-time assertion still passes after T-611 — verified by existing `test_c1_assert_phase5_import`.

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-M-1 | `TaskCompleted` → ≥1 `MetricRecorded(task.lead_time)` in same `sdd_append_batch` (I-EL-11) |
| I-EL-7 | L3 events archived (`expired=true`), never physically deleted |
| I-EL-9 | All DB writes via `sdd_append` — no direct `duckdb.connect` outside `infra/db.py` |
| I-EL-11 | `TaskCompleted` + `MetricRecorded` written via `sdd_append_batch` (single txn) |
| I-ES-6 | `CommandHandler.handle()` returns `[]` → `CommandRunner` skips `append` |
| C-1 | New event types registered atomically in `V1_L1_EVENT_TYPES` + handler location |

### §PHASE-INV (must ALL be PASS before Phase 6 can be COMPLETE)

```
[I-CHAIN-1,
 I-QE-1, I-QE-2, I-QE-3, I-QE-4,
 I-MR-1, I-MR-2, I-M-1-CHECK,
 I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO,
 I-PROJ-CONST-1, I-PROJ-CONST-2, I-PROJ-CONST-3,
 C-1 (ToolUseStarted/ToolUseCompleted/HookError registered)]
```

---

## 6. Pre/Post Conditions

### EventLogQuerier.query(filters: QueryFilters)

**Pre:**
- `db_path` is a valid readable DuckDB path
- `filters.event_source ∈ {"meta", "runtime", None}`
- `filters.order ∈ {"ASC", "DESC"}`

**Post:**
- Returns `tuple[EventRecord, ...]` ordered by `seq` per `filters.order`
- `expired=true` rows excluded unless `filters.include_expired=True`
- No writes to DB; no side effects (I-PROJ-CONST-1, I-PROJ-CONST-2)

### MetricsAggregator.aggregate(task_completed, metric_recorded, phase_id)

**Pre:**
- Both input tuples contain `EventRecord` objects (pre-fetched; no DB calls inside)
- `MetricRecord` payloads have `task_id` and `metric_id` fields

**Post:**
- Returns `MetricsSummary` — deterministic for given inputs (I-MR-2)
- `im1_violations` contains `task_id` strings from `TaskCompleted` events with no matching
  `MetricRecorded` by `task_id` — no seq-proximity check required (I-MR-1)

### hooks/log_tool.py (invoked as subprocess)

**Pre:** Called by Claude Code `PreToolUse` or `PostToolUse`

**Post (success):**
- `ToolUseStarted` or `ToolUseCompleted` (L2, `event_source="meta"`) appended to EventLog
- Exit code 0

**Post (sdd_append failure):**
- Attempt to write `HookError` (L3, `event_source="meta"`) — best-effort (I-HOOK-4)
- If `HookError` write also fails: full traceback logged to `stderr`
- Exit code 0 always (I-HOOK-2) — Claude Code is never blocked

---

## 7. Use Cases

### UC-6-1: Query all TaskImplemented events for Phase 6

**Actor:** LLM or operator
**Trigger:** `QueryEventsHandler.execute(QueryEventsCommand(QueryFilters(phase_id=6, event_type="TaskImplemented")))`
**Pre:** EventLog populated with Phase 6 events
**Steps:**
1. Build `QueryFilters(phase_id=6, event_type="TaskImplemented", include_expired=False)`
2. `EventLogQuerier.query(filters)` → SQL `WHERE ... ORDER BY seq ASC`
3. Return `QueryEventsResult(events=(...), total=N)`
**Post:** Results ordered by seq ASC; only non-archived events; I-QE-1..4 upheld; no side-channel state

### UC-6-2: Generate metrics report for Phase 6

**Actor:** LLM (post-phase summary step)
**Trigger:** `MetricsReportHandler.handle(MetricsReportCommand(phase_id=6, output_path=".sdd/reports/Metrics_Phase6.md"))`
**Pre:** EventLog contains `TaskCompleted` + `MetricRecorded` events for phase 6
**Steps:**
1. `self._querier.query(QueryFilters(phase_id=6, event_type="TaskCompleted"))` — direct, not via QueryEventsHandler
2. `self._querier.query(QueryFilters(phase_id=6, event_type="MetricRecorded"))` — direct
3. `MetricsAggregator().aggregate(tc_events, mr_events, phase_id=6)` → `MetricsSummary`
4. Render Markdown → write to output_path
5. Return `[]`
**Post:** `Metrics_Phase6.md` written; I-CHAIN-1 upheld (no CommandHandler called inside handler)

### UC-6-3: Claude Code hook logs a Bash tool call

**Actor:** Claude Code runtime (automatic, subprocess)
**Trigger:** Claude Code fires `PreToolUse` → `python3 src/sdd/hooks/log_tool.py pre Bash ...`
**Pre:** Hook wired in `~/.claude/settings.json`; `SDD_DB_PATH` set
**Steps (normal):**
1. Build `ToolUseStartedEvent(tool_name="Bash", extra=..., timestamp_ms=...)`
2. `sdd_append("ToolUseStarted", payload, event_source="meta", level="L2")` → EventLog
3. `sys.exit(0)`
**Steps (write failure):**
1. `sdd_append(ToolUseStarted...)` raises
2. Build `HookError` payload; attempt `sdd_append("HookError", ..., level="L3")`
3. If that also fails: `logging.error(traceback)` to stderr
4. `sys.exit(0)`
**Post:** L2 meta event in EventLog (or L3 HookError); Claude Code unblocked; no silent loss (I-HOOK-4)

### UC-6-4: validate_invariants detects I-M-1 violation

**Actor:** Validate T-NNN protocol (§R.7)
**Trigger:** `check_im1_invariant(db_path, phase_id=6)`
**Pre:** EventLog has `TaskCompleted(task_id="T-601")` with NO `MetricRecorded(task_id="T-601")`
**Steps:**
1. `EventLogQuerier.query(...)` fetches TaskCompleted + MetricRecorded events — direct call (I-CHAIN-1)
2. `MetricsAggregator().aggregate(...)` → `MetricsSummary(im1_violations=("T-601",), has_im1_violation=True)`
3. `check_im1_invariant` returns `InvariantCheckResult(status=FAIL, details=["T-601 missing MetricRecorded"])`
**Post:** Validation fails; no command handler was called inside the check (I-CHAIN-1 upheld)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-INFRA (`infra/db.py`) | BC-QUERY → | DuckDB read connection |
| BC-INFRA (`infra/event_log.py`) | BC-HOOKS → | `sdd_append` for meta events (I-EL-9) |
| BC-CORE (`core/events.py`) | BC-HOOKS → | `ToolUseStartedEvent`, `ToolUseCompletedEvent`, `HookErrorEvent` |
| BC-STATE (`domain/state/reducer.py`) | C-1 → | `_KNOWN_NO_HANDLER` registration for all three hook event types |
| BC-COMMANDS (`commands/validate_invariants.py`) | self | `check_im1_invariant` added; calls Layer A + B directly |

### Read-Only Boundary

`EventLogQuerier` and `MetricsAggregator` are **read-only projections**.
They MUST NOT call `sdd_append`, `sdd_append_batch`, or any write path.
Verified by `project_profile.yaml` `code_rules` grep check on Task Outputs:

```yaml
- pattern: "sdd_append"
  applies_to: "src/sdd/infra/event_query.py"
  severity: hard
  message: "EventLogQuerier is read-only — no sdd_append calls (I-PROJ-CONST-1)"
- pattern: "sdd_append"
  applies_to: "src/sdd/domain/metrics/aggregator.py"
  severity: hard
  message: "MetricsAggregator is pure — no sdd_append calls (I-PROJ-CONST-1)"
```

### Projection Layer Contract

All projection components in Phase 6 satisfy (I-PROJ-CONST-1..3):

```
Deterministic:    same EventLog snapshot → same output (no randomness, no I/O inside logic)
No shared state:  each query() / aggregate() call is independent; no object-level caching
No cross-handler: MetricsReportHandler calls EventLogQuerier, never QueryEventsHandler
```

These rules are the minimal set needed to enable reliable testing, future caching
(with explicit invalidation), and async execution without race conditions.

### BC-HOOKS Isolation

`hooks/log_tool.py` is invoked as a subprocess by Claude Code — never imported. This
boundary is enforced by I-HOOKS-ISO. Tests invoke hooks exclusively via `subprocess.run`
with controlled `SDD_DB_PATH` env var. The boundary also applies in reverse: hook code
imports ONLY from `infra/event_log.py`, `core/events.py`, and stdlib.

---

## 9. Verification

| # | Test File | Key Tests | Invariant(s) |
|---|-----------|-----------|--------------|
| 1 | `tests/unit/infra/test_event_query.py` | `test_query_order_asc`, `test_query_order_desc`, `test_query_source_filter_meta`, `test_query_source_filter_runtime`, `test_query_source_filter_none`, `test_query_phase_id_filter`, `test_query_excludes_expired_by_default`, `test_query_includes_expired_when_flag_set`, `test_query_limit`, `test_query_deterministic`, `test_querier_no_shared_state` | I-QE-1..4, I-PROJ-CONST-1..2 |
| 2 | `tests/unit/commands/test_query_events.py` | `test_execute_returns_result`, `test_no_db_write_on_query`, `test_handler_conforms_to_query_handler_protocol` | I-QE-1..4, I-PROJ-CONST-2 |
| 3 | `tests/unit/domain/metrics/test_aggregator.py` | `test_aggregator_deterministic`, `test_im1_violation_detected`, `test_no_im1_violation_when_metric_present`, `test_im1_correlation_by_task_id_only`, `test_summary_counts_correct`, `test_aggregator_pure_no_io` | I-MR-1, I-MR-2, I-PROJ-CONST-1..2 |
| 4 | `tests/unit/commands/test_metrics_report.py` | `test_report_renders_markdown`, `test_report_returns_empty_events`, `test_report_deterministic`, `test_report_writes_file_when_output_path_set`, `test_no_query_handler_in_report`, `test_report_no_handler_cache` | I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3 |
| 5 | `tests/unit/commands/test_validate_invariants.py` | `test_check_im1_pass`, `test_check_im1_fail_missing_metric`, `test_check_im1_fail_reports_task_ids`, `test_no_command_handler_in_im1_check` | I-M-1-CHECK, I-CHAIN-1 |
| 6 | `tests/unit/hooks/test_log_tool.py` | `test_hook_exits_zero_on_success`, `test_hook_exits_zero_on_exception`, `test_hook_exits_zero_on_double_failure`, `test_hook_uses_meta_source`, `test_hook_event_level_l2`, `test_hook_error_event_level_l3`, `test_hook_pre_emits_tool_use_started`, `test_hook_post_emits_tool_use_completed`, `test_hook_emits_error_event_on_failure`, `test_hook_logs_stderr_on_double_failure` | I-HOOK-1..4, I-HOOKS-ISO |
| 7 | `tests/unit/hooks/__init__.py` | (module stub) | — |
| 8 | existing `tests/unit/core/test_events_phase5.py` | `test_c1_assert_phase5_import` must still pass with 3 new types added | C-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| CLI entry points for `query-events`, `metrics-report` | Phase 8 |
| Trend analysis (`--trend`) and anomaly detection (`--anomalies`) | Phase 8/9 |
| Metrics dashboard / visualization | Phase 9 |
| Real-time streaming / subscription API | Phase 9 |
| `batch_id` field on EventRecord for txn-level I-EL-11 pairing | Phase 7 (Hardening) |
| `register_l1_event_type` extension point | Phase 7 |
| C-1 import-time assertion: test-strict / production-warning split | Phase 7 (changes Phase 5 architecture; out of scope here) |
| Migration seeding of existing EventLogs | Phase 8 |
| Hooks wiring in `settings.json` (actual Claude Code configuration) | Phase 8 |
| `log_bash.py` full implementation | Phase 8 (currently: legacy stub only) |
| Explicit cache invalidation strategy for projections | Phase 7/9 |

---

## Appendix: Task Breakdown (14 tasks)

| Task | Outputs | Produces Invariants | Requires Invariants |
|------|---------|---------------------|---------------------|
| T-601 | `src/sdd/infra/event_query.py` (`QueryFilters`, `EventLogQuerier`) | I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2 | I-EL-9, I-PK-1 |
| T-602 | `tests/unit/infra/test_event_query.py` | — | I-QE-1..4, I-PROJ-CONST-1..2 |
| T-603 | `src/sdd/commands/query_events.py` (`QueryHandler` Protocol, `QueryEventsCommand`, `QueryEventsResult`, `QueryEventsHandler.execute()`) | I-QE-1..4, I-PROJ-CONST-2 | I-QE-1..4 |
| T-604 | `tests/unit/commands/test_query_events.py` | — | I-QE-1..4, I-PROJ-CONST-2 |
| T-605 | `src/sdd/domain/metrics/__init__.py`, `src/sdd/domain/metrics/aggregator.py` (`MetricRecord`, `MetricsSummary`, `MetricsAggregator`) | I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2 | I-QE-1..4 |
| T-606 | `tests/unit/domain/metrics/__init__.py`, `tests/unit/domain/metrics/test_aggregator.py` | — | I-MR-1, I-MR-2, I-PROJ-CONST-1..2 |
| T-607 | `src/sdd/commands/metrics_report.py` (`MetricsReportCommand`, `MetricsReportHandler`) — calls EventLogQuerier directly (I-CHAIN-1) | I-MR-1, I-MR-2, I-CHAIN-1, I-PROJ-CONST-3 | I-MR-1, I-MR-2, I-ES-6, I-QE-1..4 |
| T-608 | `tests/unit/commands/test_metrics_report.py` | — | I-MR-1, I-MR-2, I-CHAIN-1, I-PROJ-CONST-3 |
| T-609 | `src/sdd/commands/validate_invariants.py` (+`check_im1_invariant` — calls EventLogQuerier + MetricsAggregator directly) | I-M-1-CHECK, I-CHAIN-1 | I-MR-1, I-QE-1..4 |
| T-610 | `tests/unit/commands/test_validate_invariants.py` (+`test_check_im1_*` tests) | — | I-M-1-CHECK, I-CHAIN-1 |
| T-611 | `src/sdd/hooks/log_tool.py` (normal + failure path with HookErrorEvent); `src/sdd/core/events.py` (+`ToolUseStartedEvent`, +`ToolUseCompletedEvent`, +`HookErrorEvent`, +`V1_L1_EVENT_TYPES` entries for all three); `src/sdd/domain/state/reducer.py` (+`_KNOWN_NO_HANDLER` for all three); `project_profile.yaml` (+`hooks` import grep rule for I-HOOKS-ISO) | I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, C-1 | I-EL-7, I-EL-9, I-PK-1 |
| T-612 | `src/sdd/hooks/log_bash.py` (legacy stub: delegates to `log_tool.py`; exits 0) | — | I-HOOK-2 |
| T-613 | `tests/unit/hooks/__init__.py`, `tests/unit/hooks/test_log_tool.py` (subprocess invocation only — I-HOOKS-ISO) | — | I-HOOK-1..4, I-HOOKS-ISO |
| T-614 | `.sdd/reports/ValidationReport_T-614.md` (§PHASE-INV coverage: all I-CHAIN-1, I-QE-*, I-MR-*, I-M-1-CHECK, I-HOOK-*, I-HOOKS-ISO, I-PROJ-CONST-*) | — | all T-601..T-613 |
