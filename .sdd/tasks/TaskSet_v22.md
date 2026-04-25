# TaskSet_v22 — Phase 22: ValidationRuntime Refinement (VRR)

Spec: specs/Spec_v22_ValidationRuntimeRefinement.md
Plan: plans/Plan_v22.md

---

T-2201: DuckDBLockTimeoutError — новый exception-тип и retry в open_sdd_connection

Status:               DONE
Spec ref:             Spec_v22 §2 BC-22-1 — DuckDBLockTimeoutError
Invariants:           I-LOCK-1, I-LOCK-2
spec_refs:            [Spec_v22 §2 BC-22-1, §4 Types, §6 Pre/Post, I-LOCK-1, I-LOCK-2]
produces_invariants:  [I-LOCK-1, I-LOCK-2]
requires_invariants:  [I-2, I-3]
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/db.py
Acceptance:           pytest tests/unit/infra/test_db_lock.py::test_open_sdd_connection_raises_lock_timeout_error passes; pytest tests/unit/infra/test_db_lock.py::test_open_sdd_connection_memory_no_retry passes
Depends on:           —

---

T-2202: TIMEOUT_RETURN_CODE + start_new_session + subprocess timeout handler

Status:               DONE
Spec ref:             Spec_v22 §2 BC-22-0 — TIMEOUT_RETURN_CODE
Invariants:           I-TIMEOUT-1, I-CMD-7
spec_refs:            [Spec_v22 §2 BC-22-0, §4 Types, §5 Invariants, I-TIMEOUT-1, I-CMD-7, I-CMD-6]
produces_invariants:  [I-TIMEOUT-1, I-CMD-7]
requires_invariants:  [I-CMD-6]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           pytest tests/unit/commands/test_validate_timeout.py::test_subprocess_timeout_records_124_and_continues passes; pytest tests/unit/commands/test_validate_timeout.py::test_subprocess_uses_start_new_session passes
Depends on:           —

---

T-2203: _run_acceptance_check — параметр test_returncode, удаление fallback subprocess

Status:               DONE
Spec ref:             Spec_v22 §2 BC-22-2 — _run_acceptance_check fail-fast semantics
Invariants:           I-ACCEPT-REUSE-1, I-ACCEPT-1, I-ERROR-1
spec_refs:            [Spec_v22 §2 BC-22-2, §4 Types, §6 Pre/Post, §7 UC-22-1, I-ACCEPT-REUSE-1, I-ACCEPT-1, I-ERROR-1]
produces_invariants:  [I-ACCEPT-REUSE-1]
requires_invariants:  [I-TIMEOUT-1, I-ACCEPT-1, I-ERROR-1, I-CMD-6]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           pytest tests/unit/commands/test_validate_acceptance.py::test_acceptance_skips_pytest_when_test_passed passes; pytest tests/unit/commands/test_validate_acceptance.py::test_acceptance_returns_1_when_no_test_result passes
Depends on:           T-2202

---

T-2204: Test-level separation — test / test_full в project_profile.yaml

Status:               DONE
Spec ref:             Spec_v22 §2 BC-22-3 — Test-level separation
Invariants:           I-TEST-1, I-TEST-2
spec_refs:            [Spec_v22 §2 BC-22-3, §5 Invariants, I-TEST-1, I-TEST-2]
produces_invariants:  [I-TEST-1, I-TEST-2]
requires_invariants:  [I-ACCEPT-REUSE-1]
Inputs:               .sdd/config/project_profile.yaml
Outputs:              .sdd/config/project_profile.yaml
Acceptance:           sdd validate-config --phase 22 passes; project_profile.yaml содержит команду test: pytest tests/unit/ tests/integration/ -q и команду test_full: pytest tests/ -q
Depends on:           T-2203

---

T-2205: Тесты для DuckDBLockTimeoutError (spec §9 tests 3–5)

Status:               DONE
Spec ref:             Spec_v22 §9 Verification — тесты 3, 4, 5
Invariants:           I-LOCK-1, I-LOCK-2
spec_refs:            [Spec_v22 §9, I-LOCK-1, I-LOCK-2]
produces_invariants:  [I-LOCK-1, I-LOCK-2]
requires_invariants:  [I-LOCK-1, I-LOCK-2]
Inputs:               src/sdd/infra/db.py
Outputs:              tests/unit/infra/test_db_lock.py
Acceptance:           pytest tests/unit/infra/test_db_lock.py -v выполняет все 3 теста (raises_lock_timeout_error, raises_io_error_immediately, memory_no_retry) — все PASSED
Depends on:           T-2201

---

T-2206: Тесты для timeout sentinel и start_new_session (spec §9 tests 1–2)

Status:               DONE
Spec ref:             Spec_v22 §9 Verification — тесты 1, 2
Invariants:           I-TIMEOUT-1, I-CMD-7
spec_refs:            [Spec_v22 §9, I-TIMEOUT-1, I-CMD-7, I-CMD-6]
produces_invariants:  [I-TIMEOUT-1, I-CMD-7]
requires_invariants:  [I-TIMEOUT-1, I-CMD-7]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              tests/unit/commands/test_validate_timeout.py
Acceptance:           pytest tests/unit/commands/test_validate_timeout.py -v выполняет оба теста (timeout_records_124_and_continues, uses_start_new_session) — все PASSED
Depends on:           T-2202

---

T-2207: Тесты для _run_acceptance_check (spec §9 tests 6–9)

Status:               DONE
Spec ref:             Spec_v22 §9 Verification — тесты 6, 7, 8, 9
Invariants:           I-ACCEPT-REUSE-1, I-ACCEPT-1
spec_refs:            [Spec_v22 §9, I-ACCEPT-REUSE-1, I-ACCEPT-1]
produces_invariants:  [I-ACCEPT-REUSE-1]
requires_invariants:  [I-ACCEPT-REUSE-1, I-ACCEPT-1]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              tests/unit/commands/test_validate_acceptance.py
Acceptance:           pytest tests/unit/commands/test_validate_acceptance.py -v выполняет все 4 теста (skips_pytest_when_test_passed, returns_failure_from_test_returncode, returns_1_when_no_test_result, uses_last_test_event_when_multiple) — все PASSED
Depends on:           T-2203

---

T-2208: Обновление test_validate_inv_idempotent — mock Popen вместо реального запуска (spec §9 test 10)

Status:               DONE
Spec ref:             Spec_v22 §9 Verification — тест 10
Invariants:           I-CMD-1
spec_refs:            [Spec_v22 §9, I-CMD-1]
produces_invariants:  [I-CMD-1]
requires_invariants:  [I-CMD-1, I-TIMEOUT-1, I-ACCEPT-REUSE-1]
Inputs:               src/sdd/commands/validate_invariants.py, tests/unit/commands/test_validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           pytest tests/unit/commands/test_validate_invariants.py::test_validate_inv_idempotent passes с mock Popen (subprocess не запускается реально)
Depends on:           T-2202, T-2203
