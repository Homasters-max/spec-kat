# Plan_v22 — Phase 22: ValidationRuntime Refinement (VRR)

Status: ACTIVE
Spec: specs/Spec_v22_ValidationRuntimeRefinement.md

---

## Milestones

### M1: DuckDBLockTimeoutError — типизированная ошибка lock contention

```text
Spec:       §2 BC-22-1 — DuckDBLockTimeoutError
BCs:        BC-22-1
Invariants: I-LOCK-1, I-LOCK-2
Depends:    — (независимый, начальная точка)
Risks:      duckdb.IOException string-matching нестабилен между версиями DuckDB;
            lock-маркер "Could not set lock" — best-effort классификация,
            задокументирована в spec §2 и §6
```

### M2: TIMEOUT_RETURN_CODE — sentinel вместо магического -1

```text
Spec:       §2 BC-22-0 — TIMEOUT_RETURN_CODE
BCs:        BC-22-0
Invariants: I-TIMEOUT-1, I-CMD-7
Depends:    — (независимый; M1 параллелен)
Risks:      returncode=124 теоретически конфликтует с реальным exit-кодом процесса;
            семантика "timeout" применяется только при TimeoutExpired (задокументировано в spec §2)
```

### M3: _run_acceptance_check — reuse test_returncode из build loop

```text
Spec:       §2 BC-22-2 — _run_acceptance_check fail-fast semantics
BCs:        BC-22-2
Invariants: I-ACCEPT-REUSE-1, I-ACCEPT-1, I-ERROR-1
Depends:    M2 (TIMEOUT_RETURN_CODE используется для интерпретации test_returncode)
Risks:      main() должен корректно извлекать test_rc из events build loop;
            если TestRunCompleted.name=="test" отсутствует — test_returncode=None → return 1 (не crash);
            удаление fallback subprocess меняет поведение при отсутствии "test" команды
```

### M4: Test-level separation — test / test_full в project_profile.yaml

```text
Spec:       §2 BC-22-3 — Test-level separation
BCs:        BC-22-3
Invariants: I-TEST-1, I-TEST-2
Depends:    M3 (acceptance шаблон обновляется одновременно с BC-22-2 в validate_invariants)
Risks:      I-TEST-2 — process-level норма, не enforced CLI; ответственность человека при review;
            переименование команды "test" → "test" + "test_full" требует согласованного обновления
            acceptance-шаблона и project_profile.yaml в одном коммите
```

### M5: Test suite — 10 тестов, покрывающих все новые инварианты

```text
Spec:       §9 Verification
BCs:        BC-22-0, BC-22-1, BC-22-2, BC-22-3
Invariants: I-TIMEOUT-1, I-CMD-7, I-LOCK-1, I-LOCK-2, I-ACCEPT-REUSE-1, I-TEST-1
Depends:    M1, M2, M3, M4 (тесты пишутся после реализации)
Risks:      test_subprocess_uses_start_new_session — требует mock Popen;
            test_validate_inv_idempotent — обновление существующего теста (mock Popen, not real run)
```

---

## Risk Notes

- R-1: **DuckDB version sensitivity** — строковый маркер `"Could not set lock"` может измениться в новых версиях DuckDB. Митигация: классификация задокументирована как best-effort в spec §2 и §6; non-lock IOException пробрасывается немедленно без retry.
- R-2: **TIMEOUT_RETURN_CODE collision** — exit code 124 не зарезервирован POSIX; реальный процесс может вернуть 124. Митигация: значение устанавливается только при `TimeoutExpired` exception; семантика ограничена ValidationRuntime (spec §2 BC-22-0).
- R-3: **test / test_full split** — изменение структуры build.commands потенциально ломает validation pipeline, если какой-либо код ожидает только `"test"`. Митигация: M4 требует atomic update project_profile.yaml + acceptance шаблон (один коммит).
- R-4: **acceptance fallback removal** — удаление subprocess pytest из `_run_acceptance_check` необратимо меняет поведение. Митигация: I-ACCEPT-REUSE-1 явно требует `test_returncode is None → return 1 (not raise)`, сохраняя I-ERROR-1.
