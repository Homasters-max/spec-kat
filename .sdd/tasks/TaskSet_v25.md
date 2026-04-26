# TaskSet_v25 — Phase 25: Explicit DB Access & Test Isolation Hardening

Spec: specs_draft/Spec_v25_ExplicitDBAccess.md
Plan: plans/Plan_v25.md

> ⚠️ Override note: TaskSet создан по явному запросу до активации Phase 25.
> Spec_v25 в статусе DRAFT; Phase 24 ещё ACTIVE. Активация невозможна до завершения Phase 24
> и одобрения Spec_v25 человеком.

---

T-2501: open_sdd_connection — make db_path required (remove implicit default)

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-1) · §3 Инварианты (I-DB-1) · §4 Контракты
Invariants:           I-DB-1
spec_refs:            [Spec_v25 §2, Spec_v25 §3, Spec_v25 §4]
produces_invariants:  [I-DB-1]
requires_invariants:  []
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/db.py
Acceptance:           open_sdd_connection("") raises ValueError("I-DB-1 violated"); open_sdd_connection() raises TypeError; implicit fallback lines removed; event_store_file import removed from db.py
Depends on:           —

---

T-2502: open_sdd_connection — add test-context fail-fast timeout

Status:               DONE
Spec ref:             Spec_v25 §3 Инварианты (I-DB-TEST-2) · §4 Контракты
Invariants:           I-DB-TEST-2
spec_refs:            [Spec_v25 §3, Spec_v25 §4]
produces_invariants:  [I-DB-TEST-2]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/db.py
Acceptance:           when PYTEST_CURRENT_TEST env var is set, open_sdd_connection passes timeout_secs=0.0 to duckdb.connect
Depends on:           T-2501

---

T-2503: open_sdd_connection — add production DB guard in test context

Status:               DONE
Spec ref:             Spec_v25 §3 Инварианты (I-DB-TEST-1) · §4 Контракты
Invariants:           I-DB-TEST-1
spec_refs:            [Spec_v25 §3, Spec_v25 §4]
produces_invariants:  [I-DB-TEST-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/db.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/db.py
Acceptance:           when PYTEST_CURRENT_TEST set and resolved db_path == production sdd_events.duckdb → RuntimeError raised before connect
Depends on:           T-2501

---

T-2504: metrics.py — add db_path parameter to get_phase_metrics and all open_sdd_connection callers

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-4) · §3 Инварианты (I-DB-1, I-DB-2) · §4 Контракты
Invariants:           I-DB-1, I-DB-2
spec_refs:            [Spec_v25 §2, Spec_v25 §3, Spec_v25 §4]
produces_invariants:  [I-DB-2]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/metrics.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/metrics.py
Acceptance:           get_phase_metrics(phase_n) without db_path raises TypeError; grep finds no bare open_sdd_connection() calls without db_path in metrics.py; event_store_file import removed from metrics.py
Depends on:           T-2501

---

T-2505: CLI callers — pass db_path=str(event_store_file()) explicitly at call sites

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-4) · §3 Инварианты (I-DB-2)
Invariants:           I-DB-2
spec_refs:            [Spec_v25 §2, Spec_v25 §3]
produces_invariants:  [I-DB-2]
requires_invariants:  [I-DB-1, I-DB-2]
Inputs:               src/sdd/infra/metrics.py, src/sdd/ (all callers of get_phase_metrics via grep)
Outputs:              src/sdd/ caller files at CLI layer (registry.py or domain commands calling get_phase_metrics)
Acceptance:           sdd CLI commands that use metrics complete without TypeError; grep -rn "get_phase_metrics" src/ shows all call sites pass db_path explicitly
Depends on:           T-2504

---

T-2506: tests/conftest.py — add _reset_sdd_root, _guard_production_db, sdd_home fixtures

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-5) · §3 Инварианты (I-DB-TEST-1, I-DB-TEST-2) · §6 Тесты
Invariants:           I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v25 §2, Spec_v25 §3, Spec_v25 §6]
produces_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/conftest.py, src/sdd/infra/paths.py
Outputs:              tests/conftest.py
Acceptance:           pytest --co shows _reset_sdd_root and _guard_production_db as autouse fixtures; sdd_home fixture available opt-in with tmp_path/.sdd and SDD_HOME set; existing tests still pass
Depends on:           T-2501, T-2503

---

T-2507: pyproject.toml — add pytest-timeout and configure --timeout=30

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-6) · §6 Тесты
Invariants:           I-DB-TEST-2
spec_refs:            [Spec_v25 §2, Spec_v25 §6]
produces_invariants:  [I-DB-TEST-2]
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              pyproject.toml
Acceptance:           pytest-timeout>=4.0 present in dev dependencies; addopts contains --timeout=30; pytest --help | grep timeout shows the flag
Depends on:           —

---

T-2508: tests/unit/infra/test_db.py — add unit tests for db.py hardening

Status:               DONE
Spec ref:             Spec_v25 §6 Тесты · §3 Инварианты (I-DB-1, I-DB-TEST-1, I-DB-TEST-2)
Invariants:           I-DB-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v25 §3, Spec_v25 §6]
produces_invariants:  [I-DB-1, I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  [I-DB-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/infra/db.py, tests/unit/infra/test_db.py
Outputs:              tests/unit/infra/test_db.py
Acceptance:           test_db_path_required passes (ValueError on empty string); test_fail_fast_in_test_context passes (timeout_secs=0.0 when PYTEST_CURRENT_TEST set); test_production_db_guard passes (RuntimeError when test context + prod path)
Depends on:           T-2501, T-2502, T-2503

---

T-2509: tests/unit/infra/test_metrics.py — add test for db_path requirement

Status:               DONE
Spec ref:             Spec_v25 §6 Тесты · §3 Инварианты (I-DB-1, I-DB-2)
Invariants:           I-DB-1, I-DB-2
spec_refs:            [Spec_v25 §3, Spec_v25 §6]
produces_invariants:  [I-DB-1, I-DB-2]
requires_invariants:  [I-DB-1, I-DB-2]
Inputs:               src/sdd/infra/metrics.py, tests/unit/infra/test_metrics.py
Outputs:              tests/unit/infra/test_metrics.py
Acceptance:           test_get_phase_metrics_requires_db_path passes (TypeError on call without db_path)
Depends on:           T-2504

---

T-2510: CLAUDE.md §INV — document DB Access Invariants (Phase 25)

Status:               DONE
Spec ref:             Spec_v25 §2 Scope (BC-DB-7) · §3 Инварианты
Invariants:           I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v25 §2, Spec_v25 §3]
produces_invariants:  [I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  [I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           CLAUDE.md §INV содержит строки I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2 с корректными формулировками из Spec_v25 §3
Depends on:           T-2501, T-2502, T-2503, T-2504, T-2505

---

T-2511: src/sdd/commands/validate_invariants.py — add --system flag; skip test command in task mode

Status:               DONE
Spec ref:             SDD_Improvements.md §IMP-001
Invariants:           IMP-001
spec_refs:            [SDD_Improvements.md §IMP-001]
produces_invariants:  [IMP-001]
requires_invariants:  []
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           (1) `validate-invariants --task T-NNN` (no --system): "test" key absent from build_commands in handle(); (2) `validate-invariants --system --phase N`: all build commands run including "test"; (3) --system is optional flag with default=False (CLI-2 compliant)
Depends on:           T-2510

---

T-2512: tests/unit/commands/test_validate_invariants.py — tests for task vs system mode

Status:               DONE
Spec ref:             SDD_Improvements.md §IMP-001
Invariants:           IMP-001
spec_refs:            [SDD_Improvements.md §IMP-001]
produces_invariants:  [IMP-001]
requires_invariants:  [IMP-001]
Inputs:               src/sdd/commands/validate_invariants.py, tests/unit/commands/test_validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           test_task_mode_skips_test_command: mock build_commands={lint,test,typecheck}, task mode → "test" not executed; test_system_mode_runs_all_commands: --system → all three commands executed
Depends on:           T-2511

---

<!-- Granularity: 12 tasks (TG-2 range: 10–30). All independently implementable and testable (TG-1). -->
<!-- Milestones covered: M1→T-2501..T-2503, M2→T-2504..T-2505, M3→T-2506..T-2509, M4→T-2510 (SDD-3). -->
