# TaskSet_v45 — Phase 45: Enforce PostgreSQL (BREAKING)

Spec: specs/Spec_v45_EnforcePostgres.md
Plan: plans/Plan_v45.md

BC order: BC-45-G → BC-45-E → BC-45-C → BC-45-D → BC-45-B → BC-45-A → BC-45-F

Audit (§8): test_paths.py::test_event_store_url_duckdb_fallback и test_is_production_event_store_duckdb
ожидают DuckDB fallback — нужно заменить на EnvironmentError до BC-45-A.
test_log_tool.py::test_log_tool_uses_event_store_url_fallback "Check 2" — убрать.
Pre-existing (не в scope): test_cli_is_pure_router, test_done_task_output_exists[T-4413], fuzz/property.

---

T-4501: BC-45-G — Fix tests expecting DuckDB fallback before BREAKING CHANGE

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-G, §8 Pre-requisites
Invariants:           I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v45 §2 BC-45-G, §8]
produces_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  []
Inputs:               tests/unit/infra/test_paths.py, tests/unit/hooks/test_log_tool.py
Outputs:              tests/unit/infra/test_paths.py, tests/unit/hooks/test_log_tool.py
Acceptance:           pytest tests/unit/infra/test_paths.py tests/unit/hooks/test_log_tool.py -v → PASS
Depends on:           —

---

T-4502: BC-45-E — Update _isolate_sdd_home fixture: passthrough SDD_DATABASE_URL

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-E
Invariants:           I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v45 §2 BC-45-E]
produces_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  []
Inputs:               tests/conftest.py
Outputs:              tests/conftest.py
Acceptance:           pytest tests/unit/ -m "not pg" --tb=short -q → no new failures
Depends on:           T-4501

---

T-4503: BC-45-C — Add _ALWAYS_PASSTHROUGH constant + subprocess env in validate_invariants.py + test 5

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-C, §4, §10 test 5
Invariants:           I-SUBPROCESS-ENV-1
spec_refs:            [Spec_v45 §2 BC-45-C, I-SUBPROCESS-ENV-1]
produces_invariants:  [I-SUBPROCESS-ENV-1]
requires_invariants:  []
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              src/sdd/commands/validate_invariants.py, tests/unit/commands/test_validate_invariants_v45.py
Acceptance:           pytest tests/unit/commands/ -v -k "validate" → test 5 PASS; _ALWAYS_PASSTHROUGH is frozenset constant
Depends on:           T-4502

---

T-4504: BC-45-D — Implement _pg_max_seq() + staleness guard in get_current_state() + tests 6-9

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-D, §4, §6 BC-45-D, §7 UC-45-3/UC-45-4, §10 tests 6-9
Invariants:           I-STATE-READ-1
spec_refs:            [Spec_v45 §2 BC-45-D, I-STATE-READ-1]
produces_invariants:  [I-STATE-READ-1]
requires_invariants:  []
Inputs:               src/sdd/infra/projections.py
Outputs:              src/sdd/infra/projections.py, tests/unit/infra/test_projections_v45.py
Acceptance:           pytest tests/unit/ -v -k "get_current_state" → tests 6-9 PASS; YAML-first O(1) path confirmed
Depends on:           T-4503

---

T-4505: BC-45-B — Update is_production_event_store(): remove DuckDB branch + tests 3-4

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-B, §4, §6 BC-45-B, §10 tests 3-4
Invariants:           I-PROD-GUARD-1
spec_refs:            [Spec_v45 §2 BC-45-B, I-PROD-GUARD-1]
produces_invariants:  [I-PROD-GUARD-1]
requires_invariants:  [I-DB-URL-REQUIRED-1]
Inputs:               src/sdd/infra/paths.py (is_production_event_store, lines ~38-46)
Outputs:              src/sdd/infra/paths.py, tests/unit/infra/test_paths.py
Acceptance:           pytest tests/unit/infra/test_paths.py -v → tests 3-4 PASS; no event_store_file() call inside function
Depends on:           T-4504

---

T-4506: BC-45-A — Remove DuckDB fallback from event_store_url() (BREAKING) + tests 1-2 + smoke

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-A, §4, §5 I-DB-URL-REQUIRED-1, §6 BC-45-A, §7 UC-45-1, §10 tests 1-2
Invariants:           I-DB-URL-REQUIRED-1, I-EVENT-STORE-URL-1
spec_refs:            [Spec_v45 §2 BC-45-A, I-DB-URL-REQUIRED-1, I-EVENT-STORE-URL-1]
produces_invariants:  [I-DB-URL-REQUIRED-1, I-EVENT-STORE-URL-1]
requires_invariants:  [I-PROD-GUARD-1, I-DB-TEST-1, I-SUBPROCESS-ENV-1]
Inputs:               src/sdd/infra/paths.py (event_store_url, lines ~27-35)
Outputs:              src/sdd/infra/paths.py, tests/unit/infra/test_paths.py
Acceptance:           pytest tests/unit/infra/test_paths.py -v → tests 1-2 PASS; smoke: unset SDD_DATABASE_URL && sdd show-state 2>&1 | grep "SDD_DATABASE_URL" → message found
Depends on:           T-4505

---

T-4507: BC-45-F — show_path.py password masking in PG mode + test 10

Status:               DONE
Spec ref:             Spec_v45 §2 BC-45-F, §10 test 10
Invariants:           —
spec_refs:            [Spec_v45 §2 BC-45-F]
produces_invariants:  []
requires_invariants:  [I-DB-URL-REQUIRED-1]
Inputs:               src/sdd/commands/show_path.py
Outputs:              src/sdd/commands/show_path.py, tests/unit/commands/test_show_path_v45.py
Acceptance:           pytest tests/unit/ -v -k "show_path" → test 10 PASS; unset SDD_DATABASE_URL && pytest -m "not pg" --cov=sdd → 0 FAILED (кроме pre-existing)
Depends on:           T-4506
