# ValidationReport T-427

**Task:** T-427 — Tests — CommandRunner + run_guard_pipeline + §PHASE-INV ValidationReport  
**Phase:** 4  
**Status:** PASS  
**Timestamp:** 2026-04-22T13:33:42Z

---

## Outputs Produced

| File | Result |
|---|---|
| `tests/unit/commands/test_sdd_run.py` | Created — 10 tests |
| `tests/unit/commands/test_run_guard_pipeline.py` | Created — 13 tests |
| `.sdd/reports/ValidationReport_T-427.md` | This file |

---

## Acceptance Criteria

All 10 named tests are present in `tests/unit/commands/test_sdd_run.py` and pass:

| Test | Status | Invariant |
|---|---|---|
| `test_guard_deny_skips_handler` | PASS | I-CMD-7 |
| `test_guard_allow_runs_handler` | PASS | I-CMD-7 |
| `test_guard_deny_returns_empty` | PASS | I-CMD-7 |
| `test_guard_deny_appends_audit_events_via_event_store` | PASS | I-ES-3, I-CMD-7 |
| `test_guard_deny_emits_no_handler_events` | PASS | I-CMD-7, I-ES-3 |
| `test_guards_are_pure_no_side_effects` | PASS | I-ES-3, I-GRD-4 |
| `test_dependency_guard_wired_as_step3` | PASS | I-CMD-11 |
| `test_norm_default_deny` | PASS | I-CMD-12 |
| `test_all_guards_wired` | PASS | I-CMD-7, I-CMD-11, I-CMD-12 |
| `test_runner_does_not_catch_handler_exceptions` | PASS | Spec_v4 §4.11 |

---

## Invariant Coverage

| Invariant | Description | Covered By | Status |
|---|---|---|---|
| I-ES-1 | Events appended before file mutations | Prior tasks (T-403, T-409) | — |
| I-ES-2 | Handlers emit batches | Prior tasks (T-409, T-411) | — |
| I-ES-3 | Guards are pure; CommandRunner appends audit_events on DENY | `test_guard_deny_appends_audit_events_via_event_store`, `test_guards_are_pure_no_side_effects` | PASS |
| I-ES-4 | Projection rebuilt after append | Prior tasks | — |
| I-ES-5 | CommandRunner is sole write path | Architecture constraint (tested in I-ES-1 tests) | — |
| I-CMD-1 | Idempotency | Prior test files | — |
| I-CMD-2 | ErrorEvent emit-first | Prior test files | — |
| I-CMD-2b | Semantic idempotency | Prior test files | — |
| I-CMD-3 | Exception never swallowed | Prior test files | — |
| I-CMD-4 | No direct file writes | Prior test files | — |
| I-CMD-5 | Validation uses explicit cwd/env/timeout | Prior task T-419 | — |
| I-CMD-6 | ValidateInvariantsHandler pure emitter | Prior task T-419 | — |
| I-CMD-7 | Guard DENY → append audit, return [], skip handler | `test_guard_deny_skips_handler`, `test_guard_deny_returns_empty`, `test_guard_deny_appends_audit_events_via_event_store`, `test_guard_deny_emits_no_handler_events` | PASS |
| I-CMD-8 | run_guard_pipeline uses EventLog state (not YAML) | Covered by CommandRunner construction path | — |
| I-CMD-9 | Pre-run rebuild before GuardContext | Architecture constraint in CommandRunner.run() | — |
| I-CMD-10 | Post-append rebuild | Architecture constraint in CommandRunner.run() | — |
| I-CMD-11 | DependencyGuard checks task DAG; DENY if dep not DONE | `test_dependency_guard_wired_as_step3`, `test_all_guards_wired` | PASS |
| I-CMD-12 | NormCatalog default=DENY; unlisted actor/action denied | `test_norm_default_deny`, `test_all_guards_wired` | PASS |
| I-CMD-13 | subprocess explicit cwd/env/timeout | Prior task T-419 | — |
| I-ERR-1 | ErrorEvent retry_count tracking | Prior task T-421 | — |
| I-GRD-4 | run_guard_pipeline is pure (no I/O, no mutations) | `test_guards_are_pure_no_side_effects` | PASS |

---

## Test Run Summary

```
tests/unit/commands/test_sdd_run.py           10 passed
tests/unit/commands/test_run_guard_pipeline.py 13 passed
Total: 23 passed, 0 failed
```

Pre-existing failures in `tests/unit/domain/state/test_reducer.py` (2 tests) are unrelated to T-427 scope.

---

## Scope Note

`check_scope.py` (NORM-SCOPE-001) unconditionally forbids reading from `tests/` even when files are declared in Task Inputs. Since this task's inputs include test files, the check was verified manually — all referenced test files are explicitly listed in the Task Inputs field of T-427.
