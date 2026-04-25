# Validation Report — T-710

**Task:** T-710 — Phase validation: ValidationReport_T-710.md covering §PHASE-INV ×9  
**Phase:** 7  
**Spec ref:** Spec_v7_Hardening.md §5, §9  
**Date:** 2026-04-22  
**Overall result:** FAIL

---

## Summary

| Criterion | Status | Detail |
|-----------|--------|--------|
| 9 §PHASE-INV invariants PASS | **PASS** | All 32 invariant-covering tests pass |
| Full test suite (pytest exit 0) | **FAIL** | 7 failures in `tests/unit/hooks/test_log_tool.py` |
| No lint violations in T-710 outputs | **PASS** | `ValidationReport_T-710.md` is markdown — no lint applicable |
| Report covers each invariant with test evidence | **PASS** | See §PHASE-INV coverage below |

**Blocking issue:** `tests/unit/hooks/test_log_tool.py` has 7 failures caused by a T-708 regression — that task rewrote `src/sdd/hooks/log_tool.py` to the stdin-JSON protocol but did not update the pre-existing tests, which still invoke the hook with the old positional-arg interface.

---

## §PHASE-INV Coverage — All 9 PASS

### I-REDUCER-1 — PASS

**Definition:** `EventReducer.reduce()` MUST discard any event where `event_source ≠ "runtime"` OR `level ≠ "L1"` before the dispatch table is consulted. Meta events and L2/L3 events MUST NOT alter `SDDState`.

**Implementation:** `src/sdd/domain/state/reducer.py` — `_pre_filter()` called at top of `reduce()`. Named constants `_REDUCER_REQUIRES_SOURCE = "runtime"` and `_REDUCER_REQUIRES_LEVEL = "L1"` enforce the boundary explicitly.

**Test evidence** (`tests/unit/domain/state/test_reducer_hardening.py`):

| Test | Result |
|------|--------|
| `test_meta_events_filtered` | PASS |
| `test_l2_events_filtered` | PASS |
| `test_l3_events_filtered` | PASS |
| `test_only_runtime_l1_dispatched` | PASS |
| `test_pre_filter_constants_named` | PASS |
| `test_state_identical_with_without_meta` | PASS |

---

### I-REDUCER-WARN — PASS

**Definition:** If a known L1 event_type (∈ `V1_L1_EVENT_TYPES`) is filtered out by `_pre_filter` due to wrong `event_source` or `level`, `_pre_filter` MUST emit `logging.warning`. Diagnostic only — no exception, replay always completes.

**Implementation:** `src/sdd/domain/state/reducer.py` — `_pre_filter()` calls `logging.warning(...)` when a known L1 type is mis-classified.

**Test evidence** (`tests/unit/domain/state/test_reducer_hardening.py`):

| Test | Result |
|------|--------|
| `test_misclassified_l1_event_type_warns` | PASS |

---

### I-EL-12 — PASS

**Definition:** `batch_id TEXT` column exists in events table (nullable). `sdd_append_batch(events)` generates one `uuid4()` per call; `sdd_append(event)` sets `batch_id=NULL`. For any two events: `e1.batch_id == e2.batch_id and e1.batch_id is not None` iff written in the same `sdd_append_batch` call. `QueryFilters.batch_id` exact-matches; `QueryFilters.is_batched` filters IS NULL / IS NOT NULL.

**Implementation:** `src/sdd/infra/db.py` — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS batch_id TEXT`. `src/sdd/infra/event_log.py` — `sdd_append_batch` generates `uuid4()` per call. `src/sdd/infra/event_query.py` — `QueryFilters.batch_id` and `QueryFilters.is_batched` supported.

**Test evidence** (`tests/unit/infra/test_batch_id.py`):

| Test | Result |
|------|--------|
| `test_batch_id_column_exists` | PASS |
| `test_batch_id_set_on_batch_append` | PASS |
| `test_batch_id_null_on_single_append` | PASS |
| `test_batch_id_uuid_unique_per_call` | PASS |
| `test_batch_id_same_within_one_call` | PASS |
| `test_batch_id_filter_exact` | PASS |
| `test_is_batched_true_filter` | PASS |
| `test_is_batched_false_filter` | PASS |
| `test_is_batched_none_no_filter` | PASS |

---

### I-REG-1 — PASS

**Definition:** `register_l1_event_type(event_type, handler)` is the sole registration path for new L1 event types. Adds to `V1_L1_EVENT_TYPES` and to exactly one of `_EVENT_SCHEMA` or `_KNOWN_NO_HANDLER`. Calls `_check_c1_consistency()` internally. Raises `ValueError` on duplicate. C-1 holds after any successful registration.

**Implementation:** `src/sdd/core/events.py` — `register_l1_event_type()` function with full contract.

**Test evidence** (`tests/unit/core/test_event_registry.py`):

| Test | Result |
|------|--------|
| `test_register_with_handler` | PASS |
| `test_register_without_handler` | PASS |
| `test_register_duplicate_raises` | PASS |
| `test_c1_consistent_after_registration` | PASS |

---

### I-REG-STATIC-1 — PASS

**Definition:** `register_l1_event_type` MUST be called only at module import time. Calling after EventLog replay has started is FORBIDDEN. Convention enforced by code comment and test.

**Implementation:** `src/sdd/core/events.py` — docstring documents the static-only constraint.

**Test evidence** (`tests/unit/core/test_event_registry.py`):

| Test | Result |
|------|--------|
| `test_register_only_at_import_time_convention` | PASS |

---

### I-C1-MODE-1 — PASS

**Definition:** The C-1 consistency check is controlled by `SDD_C1_MODE` env var. `"strict"` → `AssertionError`. `"warn"` → `logging.warning` (production default). The bare `assert` at module level is replaced by `_check_c1_consistency()`.

**Implementation:** `src/sdd/core/events.py` — `_check_c1_consistency()` reads `SDD_C1_MODE`; module-level bare `assert` removed.

**Test evidence** (`tests/unit/core/test_event_registry.py`):

| Test | Result |
|------|--------|
| `test_c1_strict_mode_raises` | PASS |
| `test_c1_warn_mode_does_not_raise` | PASS |
| `test_existing_c1_assert_replaced` | PASS |
| `test_module_import_does_not_raise_in_warn_mode` | PASS |

---

### I-HOOK-WIRE-1 — PASS

**Definition:** `.sdd/tools/log_tool.py` contains NO event-building logic and NO `sdd_append` call. Its sole responsibility: resolve `src/` path, inject into `sys.path`, call `from sdd.hooks.log_tool import main; main()`.

**Implementation:** `.sdd/tools/log_tool.py` — thin wrapper confirmed by AST check (no `sdd_append` node in AST).

**Test evidence** (`tests/unit/hooks/test_log_tool_parity.py`):

| Test | Result |
|------|--------|
| `test_tools_hook_is_thin_wrapper` | PASS |

---

### I-HOOK-PATH-1 — PASS

**Definition:** The `src/` path in `.sdd/tools/log_tool.py` MUST be resolved via `Path(__file__).resolve().parents[2] / "src"` (not `Path(__file__).parent.parent.parent`). Using `.resolve()` avoids symlink ambiguity.

**Implementation:** `.sdd/tools/log_tool.py` — uses `Path(__file__).resolve().parents[2] / "src"`.

**Test evidence** (`tests/unit/hooks/test_log_tool_parity.py`):

| Test | Result |
|------|--------|
| `test_tools_hook_path_resolution` | PASS |

---

### I-HOOK-PARITY-1 — PASS

**Definition:** For the same stdin JSON fixture, `.sdd/tools/log_tool.py` and `src/sdd/hooks/log_tool.py` produce the same number of EventLog rows and rows that are identical on `event_type`, `event_source`, `level`, `tool_name`, and all payload fields except `timestamp_ms`.

**Implementation:** `.sdd/tools/log_tool.py` delegates to `src/sdd/hooks/log_tool.py`, so parity is structural.

**Test evidence** (`tests/unit/hooks/test_log_tool_parity.py`):

| Test | Result |
|------|--------|
| `test_parity_pre_bash` | PASS |
| `test_parity_post_bash` | PASS |
| `test_parity_pre_read` | PASS |
| `test_parity_pre_write` | PASS |
| `test_parity_failure_path` | PASS |

---

## Blocking Issue: T-708 Regression in test_log_tool.py

### Root cause

T-708 rewrote `src/sdd/hooks/log_tool.py` to read hook payloads from `stdin` as JSON (`json.load(sys.stdin)`), replacing the old positional-arg interface. T-708's Outputs field did not include `tests/unit/hooks/test_log_tool.py`, so the pre-existing tests were not updated.

`tests/unit/hooks/test_log_tool.py` calls the hook via:
```python
subprocess.run([sys.executable, str(script)] + ["pre", "TestTool"], ...)
```
With the new interface, the hook reads from stdin. With no stdin provided, `json.load(sys.stdin)` raises `JSONDecodeError`, the hook exits 0 without writing anything, and the `_query` helper then fails with `CatalogError: Table 'events' does not exist` (the DB was never initialized).

### Failing tests (7)

| Test | Invariant | Error |
|------|-----------|-------|
| `test_hook_uses_meta_source` | I-HOOK-1 | `CatalogError: Table 'events' does not exist` |
| `test_hook_event_level_l2` | I-HOOK-3 | `CatalogError: Table 'events' does not exist` |
| `test_hook_error_event_level_l3` | I-HOOK-3 | `assert 0 == 1` (no HookError row written) |
| `test_hook_pre_emits_tool_use_started` | I-HOOK-1/3 | `CatalogError: Table 'events' does not exist` |
| `test_hook_post_emits_tool_use_completed` | I-HOOK-1/3 | `CatalogError: Table 'events' does not exist` |
| `test_hook_emits_error_event_on_failure` | I-HOOK-4 | `assert 0 == 1` (no HookError row written) |
| `test_hook_logs_stderr_on_double_failure` | I-HOOK-4 | `assert 'double failure' in ''` |

### Required fix (outside T-710 scope)

Update `tests/unit/hooks/test_log_tool.py` to use the stdin-JSON interface. The `_run` helper must be updated to pass a JSON payload dict via `input=json.dumps(payload)` (matching the pattern established by `test_log_tool_parity.py`). Suggested task: T-711 (or amend T-708 scope).

Example fix for `_run`:
```python
def _run(script: Path, payload: dict, db_path: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SDD_DB_PATH"] = db_path
    env["PYTHONPATH"] = f"{_SRC}:{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )
```

---

## Additional Findings: Lint Violations in Phase 7 Source Files

The following lint violations exist in files from earlier Phase 7 tasks. They are not in T-710's task outputs but are reported here for completeness.

| File | Rule | Description | Fixable |
|------|------|-------------|---------|
| `src/sdd/core/events.py:8` | UP035 | `Callable` should be imported from `collections.abc` | Yes (`--fix`) |
| `src/sdd/domain/state/reducer.py:3` | I001 | Import block unsorted | Yes (`--fix`) |
| `src/sdd/domain/state/reducer.py:12` | F401 | `SDDError` imported but unused | Yes (`--fix`) |
| `src/sdd/infra/event_log.py:229` | UP017 | Use `datetime.UTC` alias | Yes (`--fix`) |

These should be addressed in the task that owns each file (T-701, T-706, T-703 respectively) or in a dedicated cleanup task.

---

## Test Suite Summary

```
339 passed, 7 failed in 25.99s

Passing: all tests except tests/unit/hooks/test_log_tool.py
Failing: tests/unit/hooks/test_log_tool.py (7 tests)
```

The 32 tests covering all 9 §PHASE-INV invariants all pass.

---

## Conclusion

**§PHASE-INV verdict: PASS** — all 9 invariants verified by passing tests.

**T-710 overall verdict: FAIL** — the "full test suite passes (pytest exit 0)" acceptance criterion is not met due to 7 pre-existing failures in `tests/unit/hooks/test_log_tool.py` (T-708 regression).

**Required action before Phase 7 can complete:**
1. Fix `tests/unit/hooks/test_log_tool.py` to use the stdin-JSON calling convention (I-HOOK-1/2/3/4 tests)
2. Optionally fix the 4 auto-fixable lint violations in Phase 7 source files
