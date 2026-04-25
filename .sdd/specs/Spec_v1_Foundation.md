# Spec_v1_Foundation — Phase 1: Foundation

Status: Draft
Baseline: Spec_v0_Compatibility.md (event schema contract, I-EL-* invariants)
Reference implementation: sdd_v1/.sdd/tools/sdd_db.py, sdd_event_log.py

---

## 0. Goal

Establish the foundational Python package `src/sdd/` with:
- Typed domain model (`core/`)
- Persistence layer with dual-source event log (`infra/`)
- Full invariant set I-PK-1..5, I-EL-1/2/5a/5b/7/8/8a/9/10/11/12, I-CMD-1a, I-M-1
- 80%+ test coverage for all infra modules
- pyproject.toml configured for ruff, mypy, pytest, coverage

This phase produces no business-logic commands. It is the substrate that all
subsequent phases build on.

---

## 1. Scope

### In-Scope

- BC-CORE: frozen dataclasses, error hierarchy, event classification, CommandHandler protocol
- BC-INFRA: DuckDB schema with v2 columns, sdd_append/sdd_replay, audit, config loader, metrics

### Concurrency Model (Phase 1–6)

Single-process, single-writer. No concurrent access to DuckDB from multiple processes.
Consequences:
- I-EL-5a (single writer) is trivially satisfied — no locking needed in Phase 1
- `ContextVar`-based `meta_context()` is safe (no threading in Phase 1)
- Future multi-writer support is out of scope until explicitly added to a future spec

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-CORE: `src/sdd/core/`

```
src/sdd/core/
  __init__.py      ← re-exports: SDDError, DomainEvent, ErrorEvent, CommandEvent,
                     EventLevel, CommandHandler, classify_event_level
  errors.py        ← SDDError hierarchy
  events.py        ← DomainEvent, ErrorEvent(+retry_count), CommandEvent(+command_id),
                     L1/L2/L3 classification, V1_L1_EVENT_TYPES
  types.py         ← frozen dataclasses + CommandHandler Protocol
```

### BC-INFRA: `src/sdd/infra/`

```
src/sdd/infra/
  __init__.py      ← re-exports: open_sdd_connection, sdd_append, sdd_append_batch,
                     sdd_replay, meta_context, record_metric, log_action, load_config
  db.py            ← DuckDB schema (v2 columns), SDD_SEQ_CHECKPOINT, open_sdd_connection,
                     ensure_sdd_schema, SDD_MIGRATION_REGISTRY
  event_log.py     ← sdd_append(event_source), sdd_append_batch (single txn), sdd_replay,
                     meta_context(), classify_event_level, _make_event_id
  audit.py         ← log_action, AuditEntry, make_entry_id (deterministic SHA-256)
  config_loader.py ← 3-level YAML override: base defaults → project_profile.yaml → phase_N.yaml
  metrics.py       ← record_metric(metric_id, value, task, phase, context),
                     MetricEvent, batch write with TaskCompleted (I-M-1)
```

### Dependencies

```text
BC-INFRA → BC-CORE : imports DomainEvent, EventLevel, SDDError
BC-CORE  → stdlib  : dataclasses, hashlib, typing (no external deps)
BC-INFRA → duckdb  : single external dep for persistence
BC-INFRA → PyYAML  : config loading only
```

---

## 3. Domain Events

All events are frozen dataclasses inheriting `DomainEvent`.

```python
@dataclass(frozen=True)
class DomainEvent:
    # event_type MUST equal the class name (or the class-level EVENT_TYPE constant).
    # Enforced in __init_subclass__: subclass without EVENT_TYPE raises TypeError at definition time.
    event_type: str
    event_id: str                         # SHA-256 deterministic — I-EL-12
    appended_at: int                      # Unix ms
    level: str                            # "L1" | "L2" | "L3"
    event_source: str                     # "meta" | "runtime" — I-EL-1
    caused_by_meta_seq: Optional[int]     # I-EL-8; MUST be set inside meta_context (I-EL-8a)

@dataclass(frozen=True)
class ErrorEvent(DomainEvent):
    error_type: str
    source: str                           # module or command name
    recoverable: bool
    retry_count: int                      # 0 on first occurrence
    context: tuple[tuple[str, Any], ...]  # tuple-of-pairs for hashability (no mutable dict)

@dataclass(frozen=True)
class CommandEvent(DomainEvent):
    command_id: str         # idempotency key (I-CMD-1)
    command_type: str
```

### Event Catalog (Phase 1 infrastructure events — L2)

| Event | Emitter | Level | Description |
|-------|---------|-------|-------------|
| `MetricRecorded` | `infra/metrics.py` | L2 | metric value written to DB |
| `AuditEntry` | `infra/audit.py` | L2 | SENAR audit log entry — NOT L1, NOT part of domain replay |

**AuditEntry** is governance metadata only. It MUST NOT appear in `sdd_replay(level="L1")` results
and MUST NOT be processed by the domain reducer (Phase 2).

---

## 4. Types & Interfaces

### 4.1 SDDError Hierarchy (`core/errors.py`)

```python
class SDDError(Exception): ...
class ScopeViolation(SDDError): ...
class PhaseGuardError(SDDError): ...
class MissingContext(SDDError): ...
class Inconsistency(SDDError): ...
class VersionMismatch(SDDError): ...
class MissingState(SDDError): ...
class InvalidState(SDDError): ...
class NormViolation(SDDError): ...
```

### 4.2 CommandHandler Protocol (`core/types.py`)

```python
from typing import Protocol, List

class CommandHandler(Protocol):
    def handle(self, command: "Command") -> List[DomainEvent]: ...

@dataclass(frozen=True)
class Command:
    command_id: str                   # idempotency key — I-CMD-1a
    command_type: str                 # e.g. "complete_task", "validate_task"
    payload: Mapping[str, Any]        # immutable view; use types.MappingProxyType at construction
```

### 4.3 EventLevel Enum + classify_event_level mapping (`core/events.py`)

```python
class EventLevel:
    L1 = "L1"   # domain truth — replay forever
    L2 = "L2"   # operational — 90 days
    L3 = "L3"   # debug — archive after TTL (never delete)

# Canonical L1 event types — shared between v1 and v2 (I-EL-6)
V1_L1_EVENT_TYPES: frozenset[str] = frozenset({
    "TaskImplemented", "TaskValidated", "PhaseCompleted", "TestRunCompleted",
    "StateDerivationCompleted", "ExecutionWrapperAccepted", "ExecutionWrapperRejected",
    "SDDEventRejected", "DecisionRecorded", "SpecApproved", "PlanActivated",
    "PhaseInitialized", "TaskFailed", "TaskRetryScheduled",
})
V2_L1_EVENT_TYPES: frozenset[str] = V1_L1_EVENT_TYPES  # must be identical (I-EL-6)

_L3_EVENT_TYPES: frozenset[str] = frozenset({
    "ToolUseStarted", "ToolUseCompleted",
    "BashCommandStarted", "BashCommandCompleted",
})

def classify_event_level(event_type: str) -> str:
    """Pure total function (I-PK-4): L1 | L2 | L3, no side effects."""
    if event_type in V2_L1_EVENT_TYPES:
        return EventLevel.L1
    if event_type in _L3_EVENT_TYPES:
        return EventLevel.L3
    return EventLevel.L2
```

### 4.4 sdd_append signature (`infra/event_log.py`)

```python
def sdd_append(
    event_type: str,
    payload: dict,
    db_path: str = SDD_EVENTS_DB,
    level: str | None = None,         # auto-classified if None
    event_source: str = "runtime",    # "meta" | "runtime" — I-EL-1
    caused_by_meta_seq: int | None = None,  # I-EL-8
) -> None: ...
```

### 4.5 EventInput + sdd_append_batch signature (`infra/event_log.py`)

```python
@dataclass(frozen=True)
class EventInput:
    """Typed input for sdd_append_batch. All fields explicit — no silent defaults."""
    event_type: str
    payload: Mapping[str, Any]
    event_source: str = "runtime"       # "meta" | "runtime"
    level: str | None = None            # auto-classified if None
    caused_by_meta_seq: int | None = None

def sdd_append_batch(
    events: List[EventInput],
    db_path: str = SDD_EVENTS_DB,
) -> None: ...
# All events written in single DB transaction — I-EL-11
# Each EventInput must have same or compatible event_source
```

### 4.6 sdd_replay signature (`infra/event_log.py`)

```python
def sdd_replay(
    after_seq: int | None = None,
    db_path: str = SDD_EVENTS_DB,
    level: str = "L1",                # default L1 — I-EL-10
    source: str = "runtime",          # default runtime — I-EL-10
    include_expired: bool = False,    # include archived L3 events
) -> list[dict]: ...
```

### 4.7 meta_context (`infra/event_log.py`)

```python
from contextlib import contextmanager

@contextmanager
def meta_context(meta_seq: int):
    """All sdd_append calls inside set caused_by_meta_seq=meta_seq."""
    ...

# Usage:
with meta_context(meta_seq=governance_event.seq):
    sdd_append("SomeRuntimeEvent", payload)  # caused_by_meta_seq = governance_event.seq
```

### 4.8 record_metric (`infra/metrics.py`)

```python
def record_metric(
    metric_id: str,
    value: float | int,
    task_id: str | None = None,
    phase_id: int | None = None,
    context: dict | None = None,
    db_path: str = SDD_EVENTS_DB,
) -> None: ...
```

---

## 5. Invariants

### New Invariants (Phase 1)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-PK-1 | `open_sdd_connection` idempotent: N calls → same schema, no errors | `tests/unit/infra/test_db.py` |
| I-PK-2 | `sdd_append` idempotent: duplicate `event_id` → `ON CONFLICT DO NOTHING`, no exception | `tests/unit/infra/test_event_log.py` |
| I-PK-3 | `sdd_replay` returns events ordered strictly by `seq ASC` (verified by asserting monotone increasing seq) | `tests/unit/infra/test_event_log.py` |
| I-PK-4 | `classify_event_level` is a pure total function: same input → same output, no side effects, no IO | `tests/unit/infra/test_event_log.py` |
| I-PK-5 | `atomic_write(path, content)` uses `tmp_path + os.replace` — no partial writes visible on disk | `tests/unit/infra/test_audit.py` |
| I-EL-1 | `sdd_append` rejects `event_source ∉ {"meta","runtime"}` with `ValueError` | `tests/unit/infra/test_event_log.py` |
| I-EL-2 | `sdd_replay(level="L1", source="runtime")` returns ONLY events where level="L1" AND event_source="runtime" | `tests/unit/infra/test_event_log.py` |
| I-EL-5a | All DB writes go through a single logical writer (`sdd_append` / `sdd_append_batch`); no concurrent writers in Phase 1–6 | `code_rules` + I-EL-9 |
| I-EL-5b | `seq` defines total order of events for replay: `sdd_replay` result list is strictly ordered by `seq ASC`; a later `sdd_append` call always produces a higher `seq` than any prior call within the same process | `tests/unit/infra/test_db.py` |
| I-EL-7 | `sdd_append` with L3 event: after TTL expiry, sets `expired=true` via `archive_expired_l3()`; no DELETE ever issued | `tests/unit/infra/test_event_log.py` |
| I-EL-8 | DB schema has `caused_by_meta_seq BIGINT` column; `sdd_append` accepts and stores this value | `tests/unit/infra/test_db.py` |
| I-EL-8a | If `event_source="runtime"` AND the call originates inside `meta_context(meta_seq=N)`, then `caused_by_meta_seq` MUST be `N` (not NULL) — causal chain must not be silently lost | `tests/unit/infra/test_event_log.py` |
| I-EL-9 | `grep -r "duckdb.connect" src/sdd/` returns no matches outside `src/sdd/infra/db.py` | `tests/unit/infra/test_event_log.py` (subprocess grep) |
| I-EL-10 | `sdd_replay()` with no args → equivalent to `sdd_replay(level="L1", source="runtime")` | `tests/unit/infra/test_event_log.py` |
| I-EL-11 | `sdd_append_batch(events)` writes all events in single DB transaction — verified by injecting error mid-batch | `tests/unit/infra/test_event_log.py` |
| I-EL-12 | `event_id = SHA-256(event_type + canonical_payload + str(timestamp_ms))` — deterministic: same `(event_type, payload_dict, timestamp_ms)` → same `event_id`; `canonical_payload = json.dumps(payload, sort_keys=True)` | `tests/unit/infra/test_event_log.py` |
| I-CMD-1a | `Command` dataclass has `command_id: str` field; `CommandHandler` Protocol declares `handle(command) -> List[DomainEvent]` — structural contract established | `tests/unit/domain/test_types.py` |
| I-CMD-1b | `handle(command)` is idempotent by `command_id`: re-processing same `command_id` returns `[]` — **Phase 4 only** | Phase 4 |
| I-M-1 | `TaskCompleted` MUST be written in the same `sdd_append_batch` call as ≥1 `MetricRecorded` event — both written atomically or neither written | `tests/unit/infra/test_metrics.py` |

### §PHASE-INV (must ALL be PASS before Phase 1 can be COMPLETE)

```
[I-PK-1, I-PK-2, I-PK-3, I-PK-4, I-PK-5,
 I-EL-1, I-EL-2, I-EL-5a, I-EL-5b, I-EL-7, I-EL-8, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12,
 I-CMD-1a, I-M-1]
```

*I-CMD-1b (idempotency at runtime) and I-EL-3 (reducer meta filter) are Phase 4 and Phase 2 respectively.*

---

## 6. Pre/Post Conditions

### open_sdd_connection(db_path)

**Pre:**
- `db_path` parent directory exists (or `db_path` is an in-memory path)

**Post:**
- Returns open `DuckDBPyConnection`
- `events` table exists with all v2 columns (including `event_source`, `caused_by_meta_seq`, `expired`, `level`)
- `sdd_event_seq` AUTOINCREMENT sequence exists, next value ≥ `SDD_SEQ_CHECKPOINT`

### sdd_append(event_type, payload, ..., event_source)

**Pre:**
- `event_source ∈ {"meta", "runtime"}` (else `ValueError`)
- DB reachable

**Post:**
- Event stored with unique `event_id` (idempotent on collision)
- `level` auto-classified if not provided
- `seq` strictly greater than all prior seq values
- `caused_by_meta_seq` stored (may be NULL)

### sdd_append_batch(events, ...)

**Pre:**
- `events` is non-empty list
- All events have same `event_source`

**Post:**
- All events stored atomically (all-or-nothing)
- I-M-1: TaskCompleted + MetricRecorded are always batched together

### sdd_replay(level, source)

**Pre:** DB reachable

**Post:**
- Returns list[dict] ordered strictly by `seq ASC`
- Filters by `level` and `event_source` if provided
- `expired=True` events excluded unless `include_expired=True`

---

## 7. Use Cases

### UC-1: Write governance event from .sdd/tools/ hook

**Actor:** Claude Code hook (log_tool.py)
**Trigger:** Tool use event detected
**Pre:** DB initialized
**Steps:**
1. `meta_context(meta_seq=N)` not needed for L3 hooks
2. `sdd_append("ToolUseStarted", payload, event_source="meta", level="L3")`
**Post:** Event stored with `event_source="meta"`, `level="L3"`, `expired=False`

### UC-2: Record task completion with metric

**Actor:** `update_state.py complete T-NNN`
**Trigger:** Task implementation complete
**Steps:**
1. `sdd_append_batch([("TaskCompleted", tc_payload), ("MetricRecorded", mr_payload)])`
**Post:** Both events atomic; I-M-1 satisfied; I-EL-11 satisfied

### UC-3: Replay application state

**Actor:** Domain state reducer (Phase 2)
**Trigger:** State query
**Steps:**
1. `sdd_replay()` — defaults to `level="L1", source="runtime"`
2. Reducer processes events (meta events already excluded by source filter)
**Post:** Pure deterministic state — I-EL-10, I-EL-3

---

## 8. Integration

### Dependencies on other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| sdd_v1/.sdd/tools/ | reference only | Algorithm parity for sdd_db.py, sdd_event_log.py |
| tests/compatibility/fixtures/ | test input | v1_events.json for T-120 |

### Migration from v1

v2 `infra/db.py` `SDD_MIGRATION_REGISTRY` adds:
```python
(3, "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_source VARCHAR DEFAULT 'runtime'"),
(3, "ALTER TABLE events ADD COLUMN IF NOT EXISTS caused_by_meta_seq BIGINT DEFAULT NULL"),
```
`DEFAULT 'runtime'` coerces existing v1 events (I-EL-4 compatible).

---

## 9. Verification

| # | Test File | Tests | Invariant(s) |
|---|-----------|-------|--------------|
| 1 | `tests/unit/infra/test_db.py` | `test_open_connection_idempotent`, `test_schema_has_v2_columns`, `test_seq_monotonic` | I-PK-1, I-EL-5, I-EL-8 |
| 2 | `tests/unit/infra/test_event_log.py` | `test_sdd_append_idempotent`, `test_replay_ordered_by_seq`, `test_replay_filters_level_source`, `test_l3_archived_not_deleted`, `test_batch_atomic`, `test_i_el_9_no_direct_connect`, `test_replay_defaults` | I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-9, I-EL-10, I-EL-11 |
| 3 | `tests/unit/infra/test_audit.py` | `test_atomic_write_no_partial`, `test_log_action_deterministic_id` | I-PK-5 |
| 4 | `tests/unit/infra/test_config_loader.py` | `test_3level_override`, `test_missing_phase_config_falls_back` | I-PK-4 |
| 5 | `tests/unit/infra/test_metrics.py` | `test_record_metric_batch_with_task_completed`, `test_i_m_1_enforced` | I-M-1, I-EL-11 |
| 6 | `tests/compatibility/test_v1_schema.py` | `test_v1_l1_events_have_required_fields` | I-EL-6 (partial; full in Phase 7) |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Domain state reducer (`reduce_events`) | Phase 2 |
| `build_context.py` (SEM-9) | Phase 2 |
| Norm catalog reader | Phase 3 |
| Guard pipeline | Phase 3 |
| Task scheduler (DAG) | Phase 3 |
| Command handlers (complete, validate) | Phase 4 |
| CLI entry point (`cli.py`) | Phase 6 |
| Thin adapter migration of .sdd/tools/ | Phase 8 |
| I-EL-3 (reducer meta filter) | Phase 2 |
| I-EL-4 (full replay compatibility test) | Phase 7 |
| I-ERR-1 (error_event_boundary decorator) | Phase 4 |
