# Spec_v7_Hardening — Phase 7: Hardening

Status: Draft
Baseline: Spec_v6_QueryMetrics.md (BC-CORE, BC-INFRA, BC-STATE, BC-GUARDS, BC-COMMANDS,
          BC-QUERY, BC-METRICS, BC-HOOKS)

---

## 0. Goal

Harden the `src/sdd/` package by closing five gaps identified during and after Phase 6:

1. **I-REDUCER-1** (D-2 formal contract): the EventReducer's source+level filter is already
   applied in practice but has no formal invariant, no named constant, and no dedicated test.
   Phase 7 formalises the filter, adds `_REDUCER_REQUIRES_SOURCE` / `_REDUCER_REQUIRES_LEVEL`
   module constants, and verifies that meta events can never reach the dispatch table.

2. **I-EL-12 — batch_id** (Spec_v6 §10 deferral): `sdd_append_batch` writes multiple events
   as a single DB transaction (I-EL-11) but the events share no queryable marker. Phase 7
   adds a `batch_id TEXT` column to the events table; `sdd_append_batch` stamps a UUID on
   every event in the batch so that I-EL-11 pairing can be verified by query, not just by
   inspecting DuckDB transaction logs.

3. **I-REG-1 — register_l1_event_type** (Spec_v6 §10 deferral): new L1 event types require
   manual edits to three locations (`V1_L1_EVENT_TYPES`, `_EVENT_SCHEMA` or
   `_KNOWN_NO_HANDLER`, and the C-1 assert test). Phase 7 introduces a single registration
   function that keeps all three locations consistent atomically.

4. **I-C1-MODE-1 — C-1 strict / warn split** (Spec_v6 §10 deferral): the import-time
   `assert` that enforces C-1 is too blunt for production use. Phase 7 replaces it with a
   two-mode check: "strict" (raises AssertionError — test default) and "warn" (emits
   `logging.warning` — production default), controlled by the `SDD_C1_MODE` env var.

5. **I-HOOK-WIRE-1 + I-HOOK-PARITY-1 — hook delegation contract**: `.sdd/tools/log_tool.py`
   (the actual Claude Code hook) and `src/sdd/hooks/log_tool.py` (the reference
   implementation built in Phase 6) have diverged: different invocation protocols, different
   input-extraction logic, and independent failure paths. Phase 7 canonicalises
   `src/sdd/hooks/log_tool.py` as the single source of truth, makes `.sdd/tools/log_tool.py`
   a thin delegation wrapper, and adds a parity test that confirms identical EventLog output.

After this phase `src/sdd/` satisfies all five contracts and is ready for the Phase 8 CLI
and kernel-stabilisation work.

---

## 1. Scope

### In-Scope

- **BC-STATE extension**: `domain/state/reducer.py` — add named filter constants and
  the I-REDUCER-1 pre-filter guard; new tests in `tests/unit/domain/state/`
- **BC-INFRA extension**: `infra/db.py` + `infra/event_log.py` — add `batch_id` column,
  update `sdd_append` / `sdd_append_batch`; `infra/event_query.py` + `core/types.py`
  (`QueryFilters`) — add `batch_id` filter
- **BC-CORE extension**: `core/events.py` — add `register_l1_event_type()` and C-1
  mode split; new tests in `tests/unit/core/`
- **BC-HOOKS hardening**: `src/sdd/hooks/log_tool.py` — align to stdin JSON protocol,
  add full `_extract_inputs` / `_extract_output` logic; `.sdd/tools/log_tool.py` — thin
  delegation wrapper; parity test in `tests/unit/hooks/`
- Invariants: I-REDUCER-1, I-REDUCER-WARN, I-EL-12, I-REG-1, I-REG-STATIC-1, I-C1-MODE-1,
  I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### §2.1 BC-STATE Extension (I-REDUCER-1)

```
src/sdd/domain/state/reducer.py   ← add _REDUCER_REQUIRES_SOURCE, _REDUCER_REQUIRES_LEVEL
                                    add _pre_filter() → filters before dispatch
```

`EventReducer.reduce(events)` must apply the pre-filter before any dispatch:

```python
_REDUCER_REQUIRES_SOURCE: Final[str]  = "runtime"
_REDUCER_REQUIRES_LEVEL:  Final[str]  = "L1"

def _pre_filter(events: Sequence[EventRecord]) -> tuple[EventRecord, ...]:
    accepted = []
    for e in events:
        if e.event_source == _REDUCER_REQUIRES_SOURCE and e.level == _REDUCER_REQUIRES_LEVEL:
            accepted.append(e)
        elif e.event_type in V1_L1_EVENT_TYPES:
            # Soft-check: a known L1 event_type arrived with wrong source/level.
            # This indicates a classification bug (e.g. runtime event stamped L2).
            # Log a warning — do NOT raise, to preserve replay safety.
            logging.warning(
                "I-REDUCER-1: known L1 event_type %r filtered out "
                "(source=%r level=%r); expected source=%r level=%r",
                e.event_type, e.event_source, e.level,
                _REDUCER_REQUIRES_SOURCE, _REDUCER_REQUIRES_LEVEL,
            )
    return tuple(accepted)
```

This is a **new named guard** — the filter already happens implicitly through the event
dispatch table, but I-REDUCER-1 requires an explicit, tested boundary so that any future
addition of meta / L2 events to `_EVENT_SCHEMA` cannot accidentally affect `SDDState`.

The **soft-check warning** (I-REDUCER-WARN) catches the silent-loss failure mode: if a
runtime event is mistakenly stamped with `level="L2"` it would disappear from `SDDState`
without error. The warning surfaces this without breaking replay (no exception — replay
must always complete).

### §2.2 BC-INFRA Extension (I-EL-12)

```
src/sdd/infra/db.py              ← add batch_id TEXT column (nullable) to events table
src/sdd/infra/event_log.py       ← sdd_append: batch_id=None; sdd_append_batch: batch_id=uuid4
src/sdd/infra/event_query.py     ← QueryFilters: add batch_id field; EventLogQuerier: WHERE clause
```

Schema change:
```sql
ALTER TABLE events ADD COLUMN IF NOT EXISTS batch_id TEXT DEFAULT NULL;
```

`sdd_append_batch` generates one `uuid4()` per call and sets `batch_id` on every event in
the batch. `sdd_append` sets `batch_id=NULL` (single-event writes are not batched).

No migration is required for existing rows — the column defaults to NULL.

**SQL NULL semantics note:** `NULL != NULL` in SQL, so a `WHERE batch_id = ?` clause cannot
find singleton events. `QueryFilters` uses an explicit `is_batched` flag to filter on
nullability, and `batch_id` (string) for exact-value lookup:

```
QueryFilters(batch_id="abc-123")  → WHERE batch_id = 'abc-123'  (specific batch)
QueryFilters(is_batched=True)     → WHERE batch_id IS NOT NULL   (all batched events)
QueryFilters(is_batched=False)    → WHERE batch_id IS NULL       (all singleton events)
QueryFilters(is_batched=None)     → (no filter)                  (all events — default)
QueryFilters(batch_id=None)       → (no filter on batch_id)
```

`batch_id` and `is_batched` are independent filters; both may be set simultaneously
(though `batch_id="..."` + `is_batched=False` always returns empty).

### §2.3 BC-CORE Extension (I-REG-1 + I-C1-MODE-1)

```
src/sdd/core/events.py           ← register_l1_event_type(), _check_c1_consistency(), SDD_C1_MODE
```

`register_l1_event_type(event_type, handler=None)` is the **sole path** for adding a new
L1 event type after Phase 7. It atomically:

1. Adds `event_type` to `V1_L1_EVENT_TYPES`
2. Adds `handler` to `_EVENT_SCHEMA` **or** adds `event_type` to `_KNOWN_NO_HANDLER`
3. Calls `_check_c1_consistency()` to verify the invariant still holds

**Static-only constraint (I-REG-STATIC-1):** `register_l1_event_type` MUST be called
only at **module import time** — i.e. at module top-level or inside `__init_subclass__`
/ decorator evaluation. Calling it after EventLog replay has started is undefined behaviour:
the registry is global state that lives outside the EventLog and is not restored by replay.
Phase 7 does not enforce this at runtime (no replay-start sentinel exists yet); it is
enforced by code convention and documented as a hard rule for implementors.

> **Why:** The EventLog is the SSOT. The event-type registry is global mutable state that
> cannot be reconstructed by `sdd_replay()`. If registration happens at runtime
> post-replay the registry and the events in the log can diverge, making future replays
> non-deterministic. Static-only registration keeps the registry equivalent to a
> compile-time constant.

`_check_c1_consistency()` is the replacement for the bare `assert` statement. Its behavior
depends on `SDD_C1_MODE`:

```python
def _check_c1_consistency() -> None:
    ok = _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
    if ok:
        return
    msg = "C-1 violation: V1_L1_EVENT_TYPES is out of sync with handler registrations"
    mode = os.environ.get("SDD_C1_MODE", "warn")   # "strict" | "warn"
    if mode == "strict":
        raise AssertionError(msg)
    logging.warning(msg)
```

The existing import-time `assert` is replaced by a call to `_check_c1_consistency()` at
module level. Tests set `SDD_C1_MODE=strict` (via env or conftest.py fixture).

### §2.4 BC-HOOKS Hardening (I-HOOK-WIRE-1 + I-HOOK-PARITY-1)

**Root cause of divergence (Phase 6):**

`src/sdd/hooks/log_tool.py` (Spec_v6 §4.9) was specified with an argv-based invocation:
```
python3 src/sdd/hooks/log_tool.py pre <tool_name> [extra_json]
```

But the actual Claude Code hook protocol delivers a JSON object on **stdin**, not as
argv arguments. `.sdd/tools/log_tool.py` correctly reads `json.load(sys.stdin)` and
also contains full per-tool `_extract_inputs()` / `_extract_output()` logic.

**Phase 7 resolution:**

`src/sdd/hooks/log_tool.py` is updated to:
1. Read from stdin (same protocol as the real hook)
2. Contain the canonical `_extract_inputs()` / `_extract_output()` logic
3. Retain proper `HookErrorEvent` handling (I-HOOK-4)

`.sdd/tools/log_tool.py` becomes a thin delegation wrapper:

```python
#!/usr/bin/env python3
"""Thin delegation wrapper — logic lives in src/sdd/hooks/log_tool.py.

sys.path injection: documented Phase 8 deferral (D-13).
Path contract (I-HOOK-PATH-1): project_root/src = resolve().parents[2]/src.
Changing .sdd/tools/ location or src/ location requires updating parents[2].
"""
from __future__ import annotations
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[2] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from sdd.hooks.log_tool import main   # noqa: E402
if __name__ == "__main__":
    main()
```

The `sys.path` injection is **documented and intentional** — it will be replaced by
`pip install -e .` in Phase 8 (D-13). Until then it is the only viable mechanism given
`.sdd/tools/` runs outside the package install path.

`.resolve()` is required (I-HOOK-PATH-1) — it eliminates symlink ambiguity that
`Path(__file__).parent.parent.parent` would not handle correctly if the file is
accessed via a symlink.

**I-HOOK-WIRE-1:** `.sdd/tools/log_tool.py` contains NO event-building logic. All logic
lives in `src/sdd/hooks/log_tool.py`. The delegation is via direct `main()` call (not
subprocess) to avoid double sys.path injection costs.

**I-HOOK-PARITY-1:** A parity test in `tests/unit/hooks/test_log_tool_parity.py` invokes
both entry points as subprocesses with the same stdin JSON fixture and asserts that the
EventLog entries they produce are identical on: `event_type`, `event_source`, `level`,
`tool_name`, and all payload fields except `timestamp_ms`.

```
src/sdd/hooks/log_tool.py        ← canonical implementation (stdin JSON, _extract_inputs)
.sdd/tools/log_tool.py           ← thin wrapper: sys.path inject → from sdd.hooks.log_tool import main
tests/unit/hooks/test_log_tool_parity.py  ← parity test (subprocess both; compare EventLog rows)
```

### §2.5 Dependencies

```
BC-STATE-EXT  → infra/event_log.py  (reads EventRecord.event_source, .level)
BC-INFRA-EXT  → infra/db.py         (schema DDL)
BC-CORE-EXT   → core/events.py      (V1_L1_EVENT_TYPES, _EVENT_SCHEMA, _KNOWN_NO_HANDLER)
BC-HOOKS-HARD → infra/event_log.py  (sdd_append — I-EL-9)
BC-HOOKS-HARD → core/events.py      (ToolUseStartedEvent, ToolUseCompletedEvent, HookErrorEvent)
```

---

## 3. Domain Events

No new domain events are introduced in Phase 7.

`batch_id` is added to the **EventRecord schema** (infra/db.py column + EventRecord dataclass
field), not a new event type.

### C-1 Compliance (Phase 7)

No new event_type strings are introduced. The C-1 `_check_c1_consistency()` mechanism
itself is the subject of I-C1-MODE-1. All existing entries in `V1_L1_EVENT_TYPES` remain
unchanged.

---

## 4. Types & Interfaces

### 4.1 EventRecord update (`infra/db.py`)

```python
@dataclass(frozen=True)
class EventRecord:
    seq:               int
    event_id:          str
    event_type:        str
    event_source:      str        # "meta" | "runtime"
    level:             str        # "L1" | "L2" | "L3"
    payload:           dict
    batch_id:          str | None  # NEW — set by sdd_append_batch; None for singleton appends
    expired:           bool
    caused_by_meta_seq: int | None
    recorded_at:       str        # ISO8601
```

The `batch_id` field is nullable. Existing rows with `batch_id IS NULL` are valid —
they represent events written by `sdd_append` (singleton path).

### 4.2 sdd_append_batch update (`infra/event_log.py`)

```python
def sdd_append_batch(events: list[dict], db_path: str = ...) -> None:
    """
    I-EL-11: single DB transaction.
    I-EL-12: all events in this call share the same batch_id (uuid4).

    batch_id is generated once per call:
        batch_id = str(uuid.uuid4())
    Then injected into each event dict before insertion.
    """
    ...
```

`sdd_append` signature is unchanged; it inserts with `batch_id=NULL`.

### 4.3 QueryFilters update (`infra/event_query.py`)

```python
@dataclass(frozen=True)
class QueryFilters:
    phase_id:        int | None  = None
    event_type:      str | None  = None
    event_source:    str | None  = None
    include_expired: bool        = False
    limit:           int | None  = None
    order:           str         = "ASC"
    batch_id:        str | None  = None   # NEW — exact match on batch_id value; None = no filter
    is_batched:      bool | None = None   # NEW — True: IS NOT NULL; False: IS NULL; None: no filter
```

`EventLogQuerier.query(filters)` SQL generation (batch_id clauses appended after
existing filters; both are independent):

```python
if filters.batch_id is not None:
    clauses.append("batch_id = ?")
    params.append(filters.batch_id)
if filters.is_batched is True:
    clauses.append("batch_id IS NOT NULL")
elif filters.is_batched is False:
    clauses.append("batch_id IS NULL")
```

`batch_id=None` and `is_batched=None` both mean "no filter on batch_id".
Combining `batch_id="..."` with `is_batched=False` is logically contradictory — no row
can satisfy both — but it is not an error; the query returns empty (consistent with SQL
semantics). See §2.2 for the full filter table.

### 4.4 register_l1_event_type (`core/events.py`)

```python
def register_l1_event_type(
    event_type: str,
    handler: Callable[[PartitionState, DomainEvent], None] | None = None,
) -> None:
    """
    I-REG-1 / I-REG-STATIC-1: sole registration path for new L1 event types.

    MUST be called only at module import time (top-level or decorator evaluation).
    Calling after EventLog replay start is FORBIDDEN — registry is global state
    outside the EventLog and cannot be reconstructed by sdd_replay().

    Atomically:
      1. Adds event_type to V1_L1_EVENT_TYPES
      2. Adds handler to _EVENT_SCHEMA  OR  adds event_type to _KNOWN_NO_HANDLER
      3. Calls _check_c1_consistency()

    handler=None  → event_type goes into _KNOWN_NO_HANDLER (reducer ignores)
    handler=fn    → event_type goes into _EVENT_SCHEMA (reducer processes)

    Raises ValueError if event_type already registered (call once only).
    """
    ...
```

### 4.5 _check_c1_consistency (`core/events.py`)

```python
def _check_c1_consistency() -> None:
    """
    I-C1-MODE-1: replaces bare import-time assert.
    Mode from SDD_C1_MODE env var: "strict" (AssertionError) | "warn" (logging.warning).
    Default: "warn" (production-safe).
    Tests set SDD_C1_MODE=strict via conftest fixture or pytest.ini.
    """
    ...
```

### 4.6 reducer pre-filter (`domain/state/reducer.py`)

```python
_REDUCER_REQUIRES_SOURCE: Final[str] = "runtime"
_REDUCER_REQUIRES_LEVEL:  Final[str] = "L1"

def _pre_filter(events: Sequence[EventRecord]) -> tuple[EventRecord, ...]:
    """
    I-REDUCER-1: discard any event that does not have
      event_source == "runtime" AND level == "L1".
    Called at the top of EventReducer.reduce() before dispatch.

    I-REDUCER-WARN: if a known L1 event_type arrives with wrong source/level,
    emit logging.warning (classification bug detector). Never raise — replay
    must always complete.
    """
    accepted = []
    for e in events:
        if e.event_source == _REDUCER_REQUIRES_SOURCE and e.level == _REDUCER_REQUIRES_LEVEL:
            accepted.append(e)
        elif e.event_type in V1_L1_EVENT_TYPES:
            logging.warning(
                "I-REDUCER-1: known L1 event_type %r filtered out "
                "(source=%r level=%r); expected source=%r level=%r",
                e.event_type, e.event_source, e.level,
                _REDUCER_REQUIRES_SOURCE, _REDUCER_REQUIRES_LEVEL,
            )
    return tuple(accepted)
```

---

## 5. Invariants

### New Invariants (Phase 7)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-REDUCER-1 | `EventReducer.reduce()` MUST discard any event where `event_source ≠ "runtime"` OR `level ≠ "L1"` **before** the dispatch table is consulted. A meta event or L2/L3 event passed to `reduce()` MUST NOT alter `SDDState`. | `tests/unit/domain/state/test_reducer_hardening.py` — `test_meta_events_filtered`, `test_l2_events_filtered`, `test_l3_events_filtered`, `test_only_runtime_l1_dispatched`, `test_pre_filter_constants_named`, `test_state_identical_with_without_meta`; named constants `_REDUCER_REQUIRES_SOURCE / _REDUCER_REQUIRES_LEVEL` |
| I-REDUCER-WARN | If a known L1 event_type (i.e. `event_type ∈ V1_L1_EVENT_TYPES`) is filtered out by `_pre_filter` due to wrong `event_source` or `level`, `_pre_filter` MUST emit `logging.warning`. The warning is diagnostic-only — no exception raised, replay always completes. | `tests/unit/domain/state/test_reducer_hardening.py` — `test_misclassified_l1_event_type_warns` |
| I-EL-12 | `batch_id TEXT` column exists in events table (nullable). `sdd_append_batch(events)` generates one `uuid4()` per call and sets `batch_id` on all events in that batch. `sdd_append(event)` sets `batch_id=NULL`. For any two events `e1`, `e2`: `e1.batch_id == e2.batch_id and e1.batch_id is not None` iff they were written in the same `sdd_append_batch` call. `QueryFilters.batch_id` exact-matches; `QueryFilters.is_batched` filters IS NULL / IS NOT NULL (SQL NULL semantics — `batch_id = NULL` is never valid). | `tests/unit/infra/test_batch_id.py` — `test_batch_id_set_on_batch_append`, `test_batch_id_null_on_single_append`, `test_batch_id_uuid_unique_per_call`, `test_batch_id_filter_exact`, `test_is_batched_true_filter`, `test_is_batched_false_filter`, `test_is_batched_none_no_filter` |
| I-REG-1 | `register_l1_event_type(event_type, handler)` is the sole path for registering new L1 event types. It adds `event_type` to `V1_L1_EVENT_TYPES` and to exactly one of `_EVENT_SCHEMA` (if handler provided) or `_KNOWN_NO_HANDLER` (if handler=None). `_check_c1_consistency()` is called inside every registration. Raises `ValueError` on duplicate registration. After any successful registration the C-1 consistency invariant still holds. | `tests/unit/core/test_event_registry.py` — `test_register_with_handler`, `test_register_without_handler`, `test_register_duplicate_raises`, `test_c1_consistent_after_registration` |
| I-REG-STATIC-1 | `register_l1_event_type` MUST be called only at module import time (module top-level or inside `__init_subclass__` / decorator evaluation). Calling it after EventLog replay has started is FORBIDDEN. The registry is global mutable state outside the EventLog; it is not reconstructed by `sdd_replay()`. Dynamic registration is NOT supported in Phase 7. | Code convention; enforced by `tests/unit/core/test_event_registry.py` — `test_register_only_at_import_time_convention` (documents the rule via a docstring check / code comment grep; runtime enforcement deferred to Phase 9) |
| I-C1-MODE-1 | The C-1 consistency check is controlled by `SDD_C1_MODE` env var. `"strict"` → `AssertionError` (used in tests). `"warn"` → `logging.warning` (production default — import never fails). The bare `assert` at module level in `core/events.py` is replaced by a call to `_check_c1_consistency()`. | `tests/unit/core/test_event_registry.py` — `test_c1_strict_mode_raises`, `test_c1_warn_mode_does_not_raise` |
| I-HOOK-WIRE-1 | `.sdd/tools/log_tool.py` contains NO event-building logic and NO `sdd_append` call of its own. Its sole responsibility is: (1) resolve `src/` path via `Path(__file__).resolve().parents[2] / "src"`; (2) inject into `sys.path`; (3) call `from sdd.hooks.log_tool import main; main()`. All hook logic lives in `src/sdd/hooks/log_tool.py`. The `sys.path` injection is documented as a Phase 8 deferral (D-13). | `tests/unit/hooks/test_log_tool_parity.py` — `test_tools_hook_is_thin_wrapper` (AST check: no `sdd_append` call in `.sdd/tools/log_tool.py`) |
| I-HOOK-PATH-1 | The `src/` path in `.sdd/tools/log_tool.py` MUST be resolved relative to the project root using `Path(__file__).resolve().parents[2] / "src"` (not `Path(__file__).parent.parent.parent`). Using `.resolve()` avoids symlink-traversal ambiguity. Changing the project directory layout (e.g. moving `.sdd/tools/` or `src/`) requires updating this path. The path contract is: `project_root/src` = `Path(".sdd/tools/log_tool.py").resolve().parents[2] / "src"`. | `tests/unit/hooks/test_log_tool_parity.py` — `test_tools_hook_path_resolution` (verifies the resolved path exists and contains `sdd/__init__.py`) |
| I-HOOK-PARITY-1 | For the same stdin JSON fixture, `.sdd/tools/log_tool.py` and `src/sdd/hooks/log_tool.py` produce **the same number** of EventLog rows and rows that are identical on: `event_type`, `event_source`, `level`, `tool_name` (from payload), and all other payload fields except `timestamp_ms`. `assert len(rows_tools) == len(rows_src)` is a required assertion in the parity test. | `tests/unit/hooks/test_log_tool_parity.py` — `test_parity_pre_bash`, `test_parity_post_bash`, `test_parity_pre_read`, `test_parity_pre_write`, `test_parity_failure_path` (each asserts equal row count before field comparison) |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-EL-9 | All DB writes go through `sdd_append` — no direct `duckdb.connect` outside `infra/db.py` |
| I-EL-11 | `TaskCompleted` + `MetricRecorded` written via `sdd_append_batch` (single transaction) |
| I-HOOK-1 | `hooks/log_tool.py` uses `event_source="meta"` exclusively |
| I-HOOK-2 | `hooks/log_tool.py` exits 0 unconditionally |
| I-HOOK-3 | `ToolUseStarted` / `ToolUseCompleted` at L2; `HookError` at L3 |
| I-HOOK-4 | On failure: attempt HookError write; on double failure: log to stderr |
| I-HOOKS-ISO | hooks not imported by commands/domain/infra; tests use subprocess only |
| I-QE-1..4 | EventLogQuerier query contracts (order, source filter, expired filter, phase filter) |
| C-1 | New event types registered atomically (now via `register_l1_event_type`) |

### §PHASE-INV (must ALL be PASS before Phase 7 can be COMPLETE)

```
[I-REDUCER-1,
 I-REDUCER-WARN,
 I-EL-12,
 I-REG-1,
 I-REG-STATIC-1,
 I-C1-MODE-1,
 I-HOOK-WIRE-1,
 I-HOOK-PATH-1,
 I-HOOK-PARITY-1]
```

---

## 6. Pre/Post Conditions

### EventReducer.reduce(events)

**Pre:**
- `events` is a sequence of `EventRecord` objects (may contain any `event_source` / `level`)

**Post:**
- Only events with `event_source == "runtime"` AND `level == "L1"` enter the dispatch table
- `SDDState` is identical whether meta / L2 / L3 events are present or absent (I-REDUCER-1)
- Pre-filter is applied before any dispatch; no dispatch-time check needed

### sdd_append_batch(events)

**Pre:**
- `events` is a non-empty list of event dicts
- Each event dict has required fields: `event_id`, `event_type`, `payload`, ...

**Post:**
- All events written in a single DB transaction (I-EL-11)
- All events in this call have the same `batch_id` (uuid4) (I-EL-12)
- `batch_id` is queryable via `QueryFilters(batch_id=...)` (I-EL-12)

### register_l1_event_type(event_type, handler)

**Pre:**
- `event_type` not already in `V1_L1_EVENT_TYPES` (otherwise `ValueError`)
- Called at module import time — not during or after EventLog replay (I-REG-STATIC-1)

**Post:**
- `event_type ∈ V1_L1_EVENT_TYPES`
- `event_type ∈ _EVENT_SCHEMA` XOR `event_type ∈ _KNOWN_NO_HANDLER`
- `_check_c1_consistency()` called; C-1 holds after registration (I-REG-1)
- Registry state is stable for the lifetime of the process (I-REG-STATIC-1)

### .sdd/tools/log_tool.py (wired Claude Code hook)

**Pre:** Called by Claude Code for any tool invocation; `stdin` contains Claude Code hook JSON

**Post:**
- `main()` from `src/sdd/hooks/log_tool.py` handles the full lifecycle
- EventLog entry produced is identical to what `src/sdd/hooks/log_tool.py` would produce
  if called directly with the same stdin (I-HOOK-PARITY-1)
- `.sdd/tools/log_tool.py` itself has no `sdd_append` call (I-HOOK-WIRE-1)
- Exit code 0 always (I-HOOK-2)

---

## 7. Use Cases

### UC-7-1: Register a new L1 event type (Phase 8+ workflow)

**Actor:** LLM implementing a future task  
**Trigger:** New domain event must be L1 (affects SDDState via reducer)  
**Pre:** `event_type` not in `V1_L1_EVENT_TYPES`; `SDD_C1_MODE` set appropriately  
**Steps:**
1. Call `register_l1_event_type("TaskScheduled", handler=_handle_task_scheduled)`
2. `V1_L1_EVENT_TYPES` updated; `_EVENT_SCHEMA["TaskScheduled"] = handler`
3. `_check_c1_consistency()` called — PASS in strict mode, no error
**Post:** `TaskScheduled` events are processed by the reducer; C-1 still holds

### UC-7-2: Register a new observability event (L2/L3, no handler)

**Actor:** LLM implementing Phase 8 CLI events  
**Trigger:** New meta event must be registered but must NOT affect SDDState  
**Pre:** `event_type` not in `V1_L1_EVENT_TYPES`  
**Steps:**
1. Call `register_l1_event_type("CLICommandStarted", handler=None)`
2. `V1_L1_EVENT_TYPES` updated; `_KNOWN_NO_HANDLER` updated
3. `_check_c1_consistency()` — PASS
**Post:** Import does not raise; reducer ignores `CLICommandStarted`; C-1 holds (I-REG-1)

### UC-7-3: Verify batch I-EL-11 pairing post-hoc

**Actor:** `validate_invariants.check_im1_invariant` or operator  
**Trigger:** Need to confirm `TaskCompleted` and `MetricRecorded` were in the same txn  
**Pre:** EventLog populated with at least one `sdd_append_batch([TaskCompleted, MetricRecorded])`  
**Steps:**
1. `EventLogQuerier.query(QueryFilters(event_type="TaskCompleted", phase_id=N))`
   — retrieves `TaskCompleted` event with `batch_id="abc-123"`
2. `EventLogQuerier.query(QueryFilters(batch_id="abc-123"))`
   — retrieves ALL events in that batch
3. Confirm `MetricRecorded` is in the result set
**Post:** I-EL-11 + I-EL-12 both confirmed by query alone (no txn log inspection needed)

### UC-7-4: Claude Code hook delegates to src/ implementation

**Actor:** Claude Code runtime (automatic, subprocess)  
**Trigger:** Claude Code fires `PreToolUse` → executes `.sdd/tools/log_tool.py pre`; stdin = JSON  
**Pre:** `.sdd/tools/log_tool.py` wired in `~/.claude/settings.json`  
**Steps:**
1. `.sdd/tools/log_tool.py` injects `src/` into `sys.path` (documented deferral)
2. `from sdd.hooks.log_tool import main; main()`
3. `src/sdd/hooks/log_tool.py` reads `json.load(sys.stdin)`, extracts `tool_name`, calls
   `_extract_inputs(tool_name, tool_input)`, calls `sdd_append("ToolUseStarted", ...)`
4. `sys.exit(0)`
**Post:** EventLog entry identical to one produced by direct invocation of `src/sdd/hooks/log_tool.py`
(I-HOOK-WIRE-1, I-HOOK-PARITY-1)

### UC-7-5: meta / L2 events do not corrupt SDDState

**Actor:** `EventReducer.reduce()` called during replay  
**Trigger:** EventLog contains a mix of `source="meta"` L2 `ToolUseStarted` events
  and `source="runtime"` L1 `TaskImplemented` events  
**Pre:** EventLog populated with both types  
**Steps:**
1. `sdd_replay(level=None, source=None)` returns all events (meta + runtime)
2. `EventReducer.reduce(all_events)` called
3. `_pre_filter()` drops all events where `source ≠ "runtime"` or `level ≠ "L1"`
4. Dispatcher sees only runtime L1 events
**Post:** `SDDState` identical to `EventReducer.reduce(runtime_l1_only_events)` (I-REDUCER-1)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-INFRA (`infra/db.py`) | BC-INFRA-EXT → | DDL for `batch_id` column |
| BC-INFRA (`infra/event_log.py`) | BC-INFRA-EXT → | `sdd_append_batch` uuid injection; `sdd_append` null batch_id |
| BC-INFRA (`infra/event_query.py`) | BC-INFRA-EXT → | `batch_id` filter in SQL |
| BC-CORE (`core/events.py`) | BC-CORE-EXT → | `register_l1_event_type`, `_check_c1_consistency` |
| BC-STATE (`domain/state/reducer.py`) | BC-STATE-EXT → | `_pre_filter`, named constants |
| BC-HOOKS (`hooks/log_tool.py`) | BC-HOOKS-HARD → | stdin JSON protocol; `_extract_inputs` canonical |

### Schema Migration Notes

`infra/db.py` `open_sdd_connection()` already uses `CREATE TABLE IF NOT EXISTS`. The
`batch_id` column is added via `ALTER TABLE events ADD COLUMN IF NOT EXISTS batch_id TEXT`.
This is idempotent — existing DBs are migrated on first `open_sdd_connection()` call.
Existing rows get `batch_id = NULL` (which is correct; they were written by `sdd_append`).

### Forbidden Patterns (additions to `project_profile.yaml`)

```yaml
# I-HOOK-WIRE-1: governance hook must not call sdd_append directly
- pattern: "sdd_append"
  applies_to: ".sdd/tools/log_tool.py"
  severity: hard
  message: "Delegation wrapper must not call sdd_append — logic lives in src/sdd/hooks/log_tool.py"

# I-REDUCER-1: reducer dispatch table must not be consulted for non-runtime events
- pattern: "_EVENT_SCHEMA\[.*\]\("
  applies_to: "src/sdd/domain/state/reducer.py"
  severity: soft
  message: "Dispatch must be called only after _pre_filter; verify I-REDUCER-1 pre-filter order"
```

### Backward Compatibility

- `sdd_append(...)` signature unchanged — `batch_id` column is populated internally
- `EventRecord` gains a `batch_id` field: existing callers that unpack by name are unaffected;
  callers that unpack by position (not permitted per I-PK-4 / frozen dataclass convention)
  would break — but no such callers exist in the codebase after Phase 6
- `QueryFilters` gains `batch_id: str | None = None` — default None means no change in behavior
  for existing queries
- `_check_c1_consistency()` replaces the bare `assert` — default mode is "warn" so production
  imports are silent on inconsistency; tests explicitly set `SDD_C1_MODE=strict`

---

## 9. Verification

| # | Test File | Key Tests | Invariant(s) |
|---|-----------|-----------|--------------|
| 1 | `tests/unit/domain/state/test_reducer_hardening.py` | `test_meta_events_filtered`, `test_l2_events_filtered`, `test_l3_events_filtered`, `test_only_runtime_l1_dispatched`, `test_pre_filter_constants_named`, `test_state_identical_with_without_meta`, `test_misclassified_l1_event_type_warns` | I-REDUCER-1, I-REDUCER-WARN |
| 2 | `tests/unit/infra/test_batch_id.py` | `test_batch_id_column_exists`, `test_batch_id_set_on_batch_append`, `test_batch_id_null_on_single_append`, `test_batch_id_uuid_unique_per_call`, `test_batch_id_same_within_one_call`, `test_batch_id_filter_exact`, `test_is_batched_true_filter`, `test_is_batched_false_filter`, `test_is_batched_none_no_filter` | I-EL-12 |
| 3 | `tests/unit/core/test_event_registry.py` | `test_register_with_handler`, `test_register_without_handler`, `test_register_duplicate_raises`, `test_c1_consistent_after_registration`, `test_c1_strict_mode_raises`, `test_c1_warn_mode_does_not_raise`, `test_existing_c1_assert_replaced`, `test_module_import_does_not_raise_in_warn_mode`, `test_register_only_at_import_time_convention` | I-REG-1, I-REG-STATIC-1, I-C1-MODE-1 |
| 4 | `tests/unit/hooks/test_log_tool_parity.py` | `test_tools_hook_is_thin_wrapper` (AST: no `sdd_append` in `.sdd/tools/log_tool.py`), `test_tools_hook_path_resolution` (resolved path contains `sdd/__init__.py`), `test_parity_pre_bash` (row count + fields), `test_parity_post_bash`, `test_parity_pre_read`, `test_parity_pre_write`, `test_parity_failure_path` | I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `pip install -e .` — full package install replacing `sys.path` hack | Phase 8 (D-13) |
| `.sdd/tools/log_tool.py` → true thin adapter (one-liner) post `pip install` | Phase 8 |
| `log_bash.py` full implementation (currently legacy stub) | Phase 8 |
| CLI entry points (`sdd query-events`, `sdd metrics-report`) | Phase 8 |
| Trend analysis (`--trend`) and anomaly detection (`--anomalies`) | Phase 8/9 |
| Explicit cache invalidation strategy for projections | Phase 9 |
| Projection caching with invalidation | Phase 9 |
| Migration seeding of existing EventLogs | Phase 8 |
| Hooks wiring in `settings.json` (actual Claude Code configuration change) | Phase 8 |
| `sdd_replay(level=None, include_expired=True)` full debug replay path | Phase 9 |
| I-EL-8 `caused_by_meta_seq` enforcement beyond schema presence | Phase 9 |

---

## Appendix: Task Breakdown (~10 tasks)

| Task | Outputs | Produces Invariants | Requires Invariants |
|------|---------|---------------------|---------------------|
| T-701 | `src/sdd/domain/state/reducer.py` (+`_REDUCER_REQUIRES_SOURCE`, +`_REDUCER_REQUIRES_LEVEL`, +`_pre_filter()` with soft-check warning for misclassified L1 types, called at top of `reduce()`) | I-REDUCER-1, I-REDUCER-WARN | I-ST-2, I-EL-3 |
| T-702 | `tests/unit/domain/state/test_reducer_hardening.py` (7 tests: meta filtered, L2 filtered, L3 filtered, only runtime-L1 dispatched, constants named, state identical with/without meta, misclassified L1 type warns) | — | I-REDUCER-1, I-REDUCER-WARN |
| T-703 | `src/sdd/infra/db.py` (+`batch_id TEXT` column via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`); `src/sdd/infra/event_log.py` (`sdd_append`: `batch_id=NULL`; `sdd_append_batch`: generates `uuid4()`, injects into all events) | I-EL-12 | I-EL-9, I-EL-11, I-PK-1 |
| T-704 | `src/sdd/infra/event_query.py` (`QueryFilters`: +`batch_id: str \| None = None`, +`is_batched: bool \| None = None`; `EventLogQuerier.query()`: `AND batch_id = ?` for exact; `AND batch_id IS NOT NULL` / `IS NULL` for is_batched) | I-EL-12 (query side) | I-QE-1..4, I-EL-12 |
| T-705 | `tests/unit/infra/test_batch_id.py` (9 tests: column exists, batch_id set on batch, null on single, unique uuid per call, same within call, filter exact, is_batched=True, is_batched=False, is_batched=None no filter) | — | I-EL-12 |
| T-706 | `src/sdd/core/events.py` (+`register_l1_event_type()` with I-REG-STATIC-1 docstring, +`_check_c1_consistency()` replacing bare `assert`, `SDD_C1_MODE` env var) | I-REG-1, I-REG-STATIC-1, I-C1-MODE-1 | C-1 (existing ToolUseStarted/Completed/HookError registrations preserved) |
| T-707 | `tests/unit/core/test_event_registry.py` (9 tests: I-REG-1 ×4, I-REG-STATIC-1 convention ×1, I-C1-MODE-1 ×3, import-safe ×1) | — | I-REG-1, I-REG-STATIC-1, I-C1-MODE-1 |
| T-708 | `src/sdd/hooks/log_tool.py` (rewrite: stdin JSON protocol; canonical `_extract_inputs()`, `_extract_output()`; proper HookErrorEvent; I-HOOK-1..4, I-HOOKS-ISO) | I-HOOK-WIRE-1 (src side), I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4 | I-HOOKS-ISO, I-EL-9 |
| T-709 | `.sdd/tools/log_tool.py` (thin wrapper: `Path(__file__).resolve().parents[2] / "src"` inject → `from sdd.hooks.log_tool import main; main()`); `tests/unit/hooks/test_log_tool_parity.py` (7 tests: AST no-sdd_append, path resolution, 5 parity fixtures each asserting `len(rows_tools) == len(rows_src)`) | I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1 | I-HOOK-WIRE-1 (src side), I-HOOK-2 |
| T-710 | `.sdd/reports/ValidationReport_T-710.md` (§PHASE-INV coverage: all 9 invariants PASS) | — | all T-701..T-709 |
