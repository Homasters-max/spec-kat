# Plan_v45 — Phase 45: Enforce PostgreSQL (BREAKING)

Status: DRAFT
Spec: specs/Spec_v45_EnforcePostgres.md

---

## Logical Context

```
type: none
rationale: "Standard phase. Continues Phase 44 (Routing Switch) by removing DuckDB fallback from event_store_url(). Phase 44 established that all CLI routing flows through event_store_url(); Phase 45 enforces SDD_DATABASE_URL as mandatory."
```

---

## Milestones

### M1: Test Audit & Fixture Isolation Fix

```text
Spec:       §8 "Pre-requisites" + §2 BC-45-G + §2 BC-45-E
BCs:        BC-45-G, BC-45-E
Invariants: I-DB-TEST-1, I-DB-TEST-2
Depends:    — (first step; must complete before any BC-45-A work begins)
Risks:      If implicit DB resolution tests are not identified and fixed before BC-45-A,
            the entire test suite will fail with EnvironmentError. Audit MUST precede all
            other milestones. BC-45-E (fixture fix) must be applied before tests re-run.
```

Действия:
1. Запустить audit-команду из §8: `unset SDD_DATABASE_URL && pytest -m "not pg" --tb=no -q 2>&1 | grep FAILED`
2. Для каждого упавшего теста — передать `db_path` явно или monkeypatch `SDD_DATABASE_URL`
3. Обновить `_isolate_sdd_home` в `tests/conftest.py`: passthrough `SDD_DATABASE_URL` если установлен (Путь A)

### M2: Subprocess Passthrough & Staleness Guard

```text
Spec:       §2 BC-45-C + §2 BC-45-D
BCs:        BC-45-C, BC-45-D
Invariants: I-SUBPROCESS-ENV-1, I-STATE-READ-1
Depends:    M1 (fixture fix ready; tests safe to run)
Risks:      BC-45-D staleness guard requires _pg_max_seq() helper — verify projections.py
            structure before implementation. BC-45-C _ALWAYS_PASSTHROUGH must be a frozenset
            constant, not configurable via CommandSpec.
```

Действия:
1. Добавить `_ALWAYS_PASSTHROUGH` константу в `validate_invariants.py`; расширить env construction
2. Реализовать `_pg_max_seq(db_url)` helper: `SELECT COALESCE(MAX(sequence_id), 0) FROM event_log`
3. Реализовать `get_current_state(db_url, full_replay=False)` с YAML-first + staleness fallback
4. Написать unit tests для BC-45-C (тест 5) и BC-45-D (тесты 6–9 из §10)

### M3: Core Enforcement — Remove DuckDB Fallback

```text
Spec:       §2 BC-45-B + §2 BC-45-A + §4 + §5 (новые инварианты)
BCs:        BC-45-B, BC-45-A
Invariants: I-DB-URL-REQUIRED-1, I-PROD-GUARD-1, I-EVENT-STORE-URL-1
Depends:    M1 (tests fixed), M2 (subprocess passthrough in place)
Risks:      BC-45-A — BREAKING CHANGE. Применять последним из двух.
            BC-45-B должен быть применён до BC-45-A, т.к. is_production_event_store()
            вызывается внутри event_log.py (3 места) которые уже должны быть safe.
            Порядок: BC-45-B → BC-45-A (из §8).
```

Действия:
1. Обновить `is_production_event_store()` в `paths.py`: убрать вызов `event_store_file()`,
   добавить `EnvironmentError` при отсутствии `SDD_DATABASE_URL` (BC-45-B)
2. Обновить `event_store_url()` в `paths.py`: убрать DuckDB fallback,
   поднимать `EnvironmentError` с сообщением `"Run: source scripts/dev-up.sh"` (BC-45-A)
3. Написать unit tests 1–4 из §10 (EnvironmentError + correct PG URL)
4. Smoke-test: `unset SDD_DATABASE_URL && sdd show-state 2>&1 | grep "SDD_DATABASE_URL"`

### M4: Diagnostic Fix & Full Validation

```text
Spec:       §2 BC-45-F + §10 Verification
BCs:        BC-45-F
Invariants: I-DB-URL-REQUIRED-1 (smoke), I-SUBPROCESS-ENV-1 (smoke)
Depends:    M1, M2, M3 (all BCs applied)
Risks:      show_path.py password masking — verify urlparse behaviour with
            postgresql://user:pass@host/db format. Test 10 from §10.
```

Действия:
1. Обновить `show_path.py`: в PG mode скрывать пароль через `urlparse`
2. Написать test 10 из §10 (`test_show_path_pg_mode_hides_password`)
3. Запустить полный smoke-тест из §10:
   - `unset SDD_DATABASE_URL && pytest -m "not pg" --cov=sdd`
   - `SDD_DATABASE_URL=... pytest -m pg`
4. Запустить `sdd validate-invariants --check I-PHASES-INDEX-1`

---

## Risk Notes

- R-1: **Test cascade (критический)** — BC-45-A ломает все тесты с implicit DB resolution.
  Митигация: M1 (аудит + фикс) ДОЛЖЕН быть завершён до M3. Порядок milestones строго линейный.

- R-2: **Staleness guard и _pg_max_seq** — требует живого PG соединения при каждом
  вызове `get_current_state()`. Митигация: убедиться, что connection timeout в dev/CI приемлем;
  для unit-тестов мокировать `_pg_max_seq`.

- R-3: **is_production_event_store() в event_log.py** — вызывается в 3 местах (строки 83, 352, 647).
  После BC-45-B все три поднимут `EnvironmentError` без `SDD_DATABASE_URL`.
  Митигация: проверить, что все 3 call-sites защищены M1-тестами до M3.

- R-4: **_ALWAYS_PASSTHROUGH как frozenset** — I-SUBPROCESS-ENV-1 запрещает конфигурировать
  список через CommandSpec. Митигация: константа определена в `validate_invariants.py`, не в `sdd_config.yaml`.
