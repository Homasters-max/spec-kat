# Plan_v47 — Phase 47: EventLog Kernel Extraction & Post-DuckDB Cleanup

Status: DRAFT
Spec: specs/Spec_v47_EventLogKernelExtraction.md

---

## Logical Context

```
type: none
rationale: "Standard continuation of Phase 46. Finalizes kernel extraction (BC-47-A),
            removes final DuckDB artifact event_store_file() (BC-47-C), promotes
            invalidated-event logging from DEBUG to INFO (BC-47-B, carryover from
            planned-but-deferred BC-46-I), and optimises PG test fixtures (BC-47-D).
            No new domain events, no business logic changes."
```

---

## Milestones

### M1: Reducer INFO для инвалидированных событий (BC-47-B)

```text
Spec:       §3 BC-47-B + §6 I-INVALIDATED-LOG-1
BCs:        BC-47-B
Invariants: I-INVALIDATED-LOG-1
Depends:    — (изолированный patch в projections.py, не зависит от других BC)
Risks:      Если BC-46-I был deferred и WARNING не сменён на DEBUG в Phase 46 —
            заменяем WARNING → INFO напрямую; дополнительно проверить grep перед изменением
```

Задача: в `src/sdd/infra/projections.py` найти ветку `if seq in invalidated_seqs`
и поднять уровень лога до `logger.info(...)` (если текущий DEBUG — carryover BC-46-I PASS;
если WARNING — прямая замена). Добавить два unit-теста с mock-logger:
`test_reducer_info_for_invalidated_seq` и `test_reducer_warning_for_non_invalidated_dup`.

### M2: el_kernel.py — финализация thin-adapter (BC-47-A)

```text
Spec:       §3 BC-47-A + §5 Types & Interfaces + §6 I-EL-KERNEL-1
BCs:        BC-47-A
Invariants: I-EL-KERNEL-1
Depends:    M1 (чистое состояние тестов перед аудитом)
Risks:      Аудит может обнаружить residual psycopg/SQL leak в el_kernel.py —
            потребуется фактическое вынесение кода, не только enforcement-тест;
            оцениваем: если утечки найдены, task занимает больше времени
```

Задача: аудит `el_kernel.py` (нет `import psycopg`, нет SQL-строк); аудит
`PostgresEventLog.append()` (нет дублирования lock/idempotency/batch логики);
добавить enforcement grep-тест `test_el_kernel_no_psycopg_import`.
Unit-тесты для всех трёх методов `EventLogKernel` (resolve_batch_id ×2,
check_optimistic_lock ×2, filter_duplicates ×1).

### M3: event_store_file() — финальное удаление (BC-47-C)

```text
Spec:       §3 BC-47-C + §6 I-EVENT-STORE-FILE-REMOVED-1
BCs:        BC-47-C
Invariants: I-EVENT-STORE-FILE-REMOVED-1
Depends:    M2 (после аудита/clean state — легче верифицировать отсутствие callers)
Risks:      Если test code содержит hidden callers event_store_file() —
            потребуется дополнительная правка тестов;
            grep по всему репо (src/ + tests/) перед удалением
```

Задача (3 шага последовательно):
1. `show_path.py` — убрать fallback-вызов `event_store_file()`, заменить на ERROR-строку;
2. `infra/paths.py` — удалить функцию `event_store_file()` полностью;
3. Добавить enforcement grep-тест `test_event_store_file_removed` + тест
   `test_show_path_no_env_returns_error_message`.

### M4: PG test fixtures optimization — TRUNCATE strategy (BC-47-D)

```text
Spec:       §3 BC-47-D + §6 I-TEST-TRUNCATE-1
BCs:        BC-47-D
Invariants: I-TEST-TRUNCATE-1
Depends:    M3 (стабильная инфраструктура; DDL должен быть финальным)
Risks:      Session-scoped schema + per-pid naming требует проверки с pytest-xdist;
            если параллельный запуск ломает тесты — fallback на function-scoped CREATE
            (deferrable: этот BC можно перенести в Phase 48 первым task'ом)
```

Задача: переписать `pg_test_db` fixture в `tests/conftest.py` —
`_pg_shared_schema` (session-scoped, DDL один раз) + `pg_test_db` (TRUNCATE per test).
Добавить `test_pg_test_db_truncate_isolation` и `test_postgres_event_log_append_via_kernel`.

---

## Risk Notes

- R-1: **BC-47-A residual leak** — если `el_kernel.py` содержит psycopg/SQL (Phase 46 не завершил extraction), M2 потребует фактического рефакторинга кода, а не только добавления теста. Митигация: аудит grep выполняется в первом шаге M2 перед любым написанием кода.
- R-2: **BC-47-C hidden callers** — `event_store_file()` может использоваться в тестах или hooks вне `src/sdd/`. Митигация: `grep -rn "event_store_file" .` (весь репо) перед удалением функции.
- R-3: **BC-47-D xdist incompatibility** — TRUNCATE strategy с session-scoped schema безопасна для serial запуска, но per-pid naming требует проверки при `pytest -n auto`. Митигация: BC-47-D помечен deferrable; при проблемах переносится в Phase 48 первым task'ом без блокировки Phase 47.
- R-4: **BC-47-B already at INFO** — если Phase 46 BC-46-I уже поднял уровень до INFO (а не DEBUG), BC-47-B = N/A. Митигация: grep в первом шаге M1 определяет текущий уровень и BC-47-B = no-op если INFO уже стоит.
