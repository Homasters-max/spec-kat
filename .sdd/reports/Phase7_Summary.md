# Phase 7 Summary — Hardening

**Status:** COMPLETE  
**Spec:** Spec_v7_Hardening.md  
**Metrics:** [Metrics_Phase7.md](Metrics_Phase7.md)  
**Date:** 2026-04-22

---

## Tasks

| Task | Description | Status |
|------|-------------|--------|
| T-701 | Reducer pre-filter — `_REDUCER_REQUIRES_SOURCE/LEVEL` + `_pre_filter()` | DONE |
| T-702 | Tests — `test_reducer_hardening.py` (7 tests) | DONE |
| T-703 | BC-INFRA — `batch_id` column + `sdd_append_batch` uuid injection | DONE |
| T-704 | BC-INFRA — `QueryFilters.batch_id` + `is_batched` + SQL WHERE | DONE |
| T-705 | Tests — `test_batch_id.py` (9 tests) | DONE |
| T-706 | BC-CORE — `register_l1_event_type` + `_check_c1_consistency` + `SDD_C1_MODE` | DONE |
| T-707 | Tests — `test_event_registry.py` (9 tests) | DONE |
| T-708 | BC-HOOKS — `src/sdd/hooks/log_tool.py` canonical stdin-JSON rewrite | DONE |
| T-709 | BC-HOOKS — `.sdd/tools/log_tool.py` thin wrapper + `test_log_tool_parity.py` (7 tests) | DONE |
| T-710 | Phase validation — `ValidationReport_T-710.md` covering §PHASE-INV ×9 | DONE |
| T-711 | Fix `test_log_tool.py` — sync to stdin JSON contract + I-HOOK-API-1 | DONE |
| T-712 | Lint fix — 4 auto-fixable violations in Phase 7 source files | DONE |

**12/12 DONE.**

---

## Invariant Coverage

| Invariant | Description | Status |
|-----------|-------------|--------|
| I-REDUCER-1 | `EventReducer.reduce()` discards non-runtime / non-L1 events before dispatch | PASS |
| I-REDUCER-WARN | `_pre_filter` warns on mis-classified known L1 type | PASS |
| I-EL-12 | `batch_id` column; `sdd_append_batch` stamps uuid4; `QueryFilters.batch_id/is_batched` | PASS |
| I-REG-1 | `register_l1_event_type` is sole registration path; C-1 holds after registration | PASS |
| I-REG-STATIC-1 | Registration only at module import time — convention enforced by test | PASS |
| I-C1-MODE-1 | `SDD_C1_MODE` controls strict/warn; bare `assert` replaced by `_check_c1_consistency()` | PASS |
| I-HOOK-WIRE-1 | `.sdd/tools/log_tool.py` contains no `sdd_append` call (AST-verified) | PASS |
| I-HOOK-PATH-1 | Path resolved via `Path(__file__).resolve().parents[2] / "src"` | PASS |
| I-HOOK-PARITY-1 | Both hooks produce identical rows for same stdin fixture | PASS |
| I-HOOK-API-1 | Hook ignores positional argv; only stdin JSON is the valid protocol | PASS |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §2.1 BC-STATE Extension (I-REDUCER-1, I-REDUCER-WARN) | Full |
| §2.2 BC-INFRA Extension (I-EL-12) | Full |
| §2.3 BC-CORE Extension (I-REG-1, I-REG-STATIC-1, I-C1-MODE-1) | Full |
| §2.4 BC-HOOKS Hardening (I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1) | Full |
| §5 PHASE-INV — all 9 invariants | Full |
| §9 Verification table — all 4 test files | Full |
| §10 Out-of-scope items | Deferred to Phase 8/9 per spec |

---

## Tests

| Test file | Tests | Status |
|-----------|-------|--------|
| `tests/unit/domain/state/test_reducer_hardening.py` | 7 | PASS |
| `tests/unit/infra/test_batch_id.py` | 9 | PASS |
| `tests/unit/core/test_event_registry.py` | 9 | PASS |
| `tests/unit/hooks/test_log_tool_parity.py` | 7 | PASS |
| `tests/unit/hooks/test_log_tool.py` | 11 | PASS |
| All other unit tests | 304 | PASS |
| **Total** | **347** | **PASS** |

---

## Issues Found & Resolved

**T-708 regression (resolved in T-711):** T-708 rewrote `src/sdd/hooks/log_tool.py` to stdin-JSON protocol but left `test_log_tool.py` using the old positional-arg interface. T-711 synchronized the tests and hardened the contract with I-HOOK-API-1.

**4 lint violations (resolved in T-712):** Auto-fixable ruff violations in T-708/T-701/T-703 outputs were deferred to T-712. Fixed: UP035 (`Callable` from `collections.abc`), I001 (import order ×2), UP017 (`datetime.UTC` alias).

**Improvement hypothesis from both findings:** Task acceptance criteria should include `ruff check` and `pytest` over the full suite — not just over task-specific files. This prevents deferred lint and interface drift being discovered only at phase validation.

---

## Risks

- R-1: `sys.path` injection in `.sdd/tools/log_tool.py` remains a known deferred item (D-13). Addressed in Phase 8 via `pip install -e .`.
- R-2: `I-REG-STATIC-1` runtime enforcement is deferred to Phase 9. Current enforcement is convention + test only.

---

## Decision

**READY — Phase 7 COMPLETE.**

All 12 tasks DONE. All 9 §PHASE-INV invariants PASS. 347/347 tests pass. 0 lint violations. DoD verified by `update_state.py validate --check-dod`.
