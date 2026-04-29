# TaskSet_v47 — Phase 47: EventLog Kernel Extraction & Post-DuckDB Cleanup

Spec: specs/Spec_v47_EventLogKernelExtraction.md
Plan: plans/Plan_v47.md

---

T-4701: BC-47-B — Поднять уровень лога invalidated_seqs до INFO в projections.py

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-B — Reducer INFO для инвалидированных событий
Invariants:           I-INVALIDATED-LOG-1
spec_refs:            [Spec_v47 §3 BC-47-B, Spec_v47 §6 I-INVALIDATED-LOG-1]
produces_invariants:  [I-INVALIDATED-LOG-1]
requires_invariants:  []
Inputs:               src/sdd/infra/projections.py
Outputs:              src/sdd/infra/projections.py
Acceptance:           grep -n "logger.info.*invalidat" src/sdd/infra/projections.py → найдено;
                      grep -n "logger.debug.*invalidat\|logger.warning.*invalidat" src/sdd/infra/projections.py → пусто
Depends on:           —

Реализация: найти ветку `if seq in invalidated_seqs` в replay/reducer, заменить уровень лога:
DEBUG → INFO (если BC-46-I выполнен) или WARNING → INFO (если BC-46-I был deferrable).
Текущий уровень определяется grep'ом перед правкой. Если уже INFO — task = N/A (отметить как DONE).

---

T-4702: BC-47-B — Unit-тесты mock-logger для I-INVALIDATED-LOG-1

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-B + §10 Tests #9, #10
Invariants:           I-INVALIDATED-LOG-1
spec_refs:            [Spec_v47 §3 BC-47-B, Spec_v47 §10]
produces_invariants:  [I-INVALIDATED-LOG-1]
requires_invariants:  [I-INVALIDATED-LOG-1]
Inputs:               src/sdd/infra/projections.py
Outputs:              tests/unit/infra/test_projections.py
Acceptance:           pytest tests/unit/infra/test_projections.py::test_reducer_info_for_invalidated_seq PASS;
                      pytest tests/unit/infra/test_projections.py::test_reducer_warning_for_non_invalidated_dup PASS
Depends on:           T-4701

Два теста с mock-logger:
1. `test_reducer_info_for_invalidated_seq` — replay с инвалидированным дублем → уровень INFO, не WARNING/DEBUG
2. `test_reducer_warning_for_non_invalidated_dup` — неинвалидированный дубль → WARNING

---

T-4703: BC-47-A — Аудит el_kernel.py + PostgresEventLog.append(), устранить утечки

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-A Шаги 1–2 — el_kernel finalization audit
Invariants:           I-EL-KERNEL-1
spec_refs:            [Spec_v47 §3 BC-47-A, Spec_v47 §5 Types & Interfaces, Spec_v47 §6 I-EL-KERNEL-1]
produces_invariants:  [I-EL-KERNEL-1]
requires_invariants:  [I-INVALIDATED-LOG-1]
Inputs:               src/sdd/infra/el_kernel.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/el_kernel.py, src/sdd/infra/event_log.py
Acceptance:           grep "import psycopg\|SELECT\|INSERT\|UPDATE\|DELETE" src/sdd/infra/el_kernel.py → пусто;
                      PostgresEventLog.append() не содержит дублирования resolve_batch_id/check_optimistic_lock/filter_duplicates логики
Depends on:           T-4702

Шаг 1: `grep -n "import psycopg\|SELECT\|INSERT\|UPDATE\|DELETE" src/sdd/infra/el_kernel.py` —
если найдено: вынести SQL/psycopg-код в event_log.py, kernel остаётся pure Python.
Шаг 2: аудит `PostgresEventLog.append()` — если lock/idempotency/batch логика дублируется
(не делегируется в _kernel.*), удалить inline дубли, оставить только делегирование.

---

T-4704: BC-47-A — Enforcement grep-тест test_el_kernel_no_psycopg_import

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-A Шаг 3 — enforcement CI-тест
Invariants:           I-EL-KERNEL-1
spec_refs:            [Spec_v47 §3 BC-47-A, Spec_v47 §10 Test #6]
produces_invariants:  [I-EL-KERNEL-1]
requires_invariants:  [I-EL-KERNEL-1]
Inputs:               src/sdd/infra/el_kernel.py
Outputs:              tests/unit/infra/test_el_kernel.py
Acceptance:           pytest tests/unit/infra/test_el_kernel.py::test_el_kernel_no_psycopg_import PASS
Depends on:           T-4703

Добавить grep-тест в `tests/unit/infra/test_el_kernel.py`:
`test_el_kernel_no_psycopg_import` — subprocess.run grep по el_kernel.py,
assert stdout == "" (нет psycopg/SQL). Файл test_el_kernel.py создаётся если не существует.

---

T-4705: BC-47-A — Unit-тесты для методов EventLogKernel

Status:               DONE
Spec ref:             Spec_v47 §8 UC-47-1 + §10 Tests #1–5
Invariants:           I-EL-KERNEL-1, I-EL-BATCH-ID-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1
spec_refs:            [Spec_v47 §8 UC-47-1, Spec_v47 §10]
produces_invariants:  [I-EL-KERNEL-1]
requires_invariants:  [I-EL-KERNEL-1]
Inputs:               src/sdd/infra/el_kernel.py
Outputs:              tests/unit/infra/test_el_kernel.py
Acceptance:           pytest tests/unit/infra/test_el_kernel.py -k "not no_psycopg" PASS (5 тестов)
Depends on:           T-4704

Добавить в `tests/unit/infra/test_el_kernel.py` (5 тестов, без PG):
1. `test_el_kernel_resolve_batch_id_multi` — 2+ events → UUID4 string
2. `test_el_kernel_resolve_batch_id_single` — 1 event → None
3. `test_el_kernel_check_optimistic_lock_pass` — current==expected → OK
4. `test_el_kernel_check_optimistic_lock_fail` — current≠expected → StaleStateError
5. `test_el_kernel_filter_duplicates` — known pair skipped; new pair passed

---

T-4706: BC-47-C Шаг 1 — show_path.py: убрать fallback event_store_file()

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-C Шаг 1 — show_path.py DuckDB fallback removal
Invariants:           I-EVENT-STORE-FILE-REMOVED-1
spec_refs:            [Spec_v47 §3 BC-47-C, Spec_v47 §8 UC-47-2]
produces_invariants:  []
requires_invariants:  [I-EL-KERNEL-1]
Inputs:               src/sdd/commands/show_path.py
Outputs:              src/sdd/commands/show_path.py
Acceptance:           grep "event_store_file" src/sdd/commands/show_path.py → пусто;
                      _show_event_store_path() без SDD_DATABASE_URL → возвращает строку "[ERROR] SDD_DATABASE_URL not set..."
Depends on:           T-4705

Заменить ветку fallback в `_show_event_store_path()`:
убрать вызов `event_store_file()`, добавить `return "[ERROR] SDD_DATABASE_URL not set. DuckDB removed in Phase 46."`.
Убрать `from sdd.infra.paths import event_store_file` из импортов если есть.

---

T-4707: BC-47-C Шаг 2 — Удалить event_store_file() из infra/paths.py

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-C Шаги 2–3 — event_store_file() final deletion
Invariants:           I-EVENT-STORE-FILE-REMOVED-1
spec_refs:            [Spec_v47 §3 BC-47-C, Spec_v47 §6 I-EVENT-STORE-FILE-REMOVED-1]
produces_invariants:  [I-EVENT-STORE-FILE-REMOVED-1]
requires_invariants:  []
Inputs:               src/sdd/infra/paths.py
Outputs:              src/sdd/infra/paths.py
Acceptance:           grep "event_store_file" src/sdd/infra/paths.py → пусто;
                      python3 -c "from sdd.infra.paths import event_store_file" → ImportError
Depends on:           T-4706

Предварительно: `grep -rn "event_store_file" . --include="*.py"` (весь репо) — убедиться что T-4706 убрал единственный caller.
Затем: удалить функцию `event_store_file()` из paths.py полностью.
Удалить `import warnings` если больше не используется в файле.

---

T-4708: BC-47-C — Enforcement-тесты I-EVENT-STORE-FILE-REMOVED-1

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-C Enforcement test + §10 Tests #7, #8
Invariants:           I-EVENT-STORE-FILE-REMOVED-1
spec_refs:            [Spec_v47 §3 BC-47-C, Spec_v47 §10]
produces_invariants:  [I-EVENT-STORE-FILE-REMOVED-1]
requires_invariants:  [I-EVENT-STORE-FILE-REMOVED-1]
Inputs:               src/sdd/infra/paths.py, src/sdd/commands/show_path.py
Outputs:              tests/unit/infra/test_paths.py, tests/unit/commands/test_show_path.py
Acceptance:           pytest tests/unit/infra/test_paths.py::test_event_store_file_removed PASS;
                      pytest tests/unit/commands/test_show_path.py::test_show_path_no_env_returns_error_message PASS
Depends on:           T-4707

1. `test_event_store_file_removed` в test_paths.py — subprocess grep paths.py → assert stdout == ""
2. `test_show_path_no_env_returns_error_message` в test_show_path.py — вызов без SDD_DATABASE_URL → содержит "[ERROR]", не DuckDB путь

---

T-4709: BC-47-D — Переписать pg_test_db fixture: TRUNCATE strategy

Status:               DONE
Spec ref:             Spec_v47 §3 BC-47-D — PG test fixtures TRUNCATE optimization
Invariants:           I-TEST-TRUNCATE-1
spec_refs:            [Spec_v47 §3 BC-47-D, Spec_v47 §6 I-TEST-TRUNCATE-1]
produces_invariants:  [I-TEST-TRUNCATE-1]
requires_invariants:  [I-EVENT-STORE-FILE-REMOVED-1]
Inputs:               tests/conftest.py
Outputs:              tests/conftest.py
Acceptance:           pytest -k pg (serial) → PASS; данные изолированы между тестами;
                      DDL (CREATE SCHEMA) выполняется один раз за test session
Depends on:           T-4708

Переписать в tests/conftest.py:
- Добавить `_pg_shared_schema` (scope="session"): CREATE SCHEMA test_sdd_<pid> + DDL + DROP в teardown
- Переписать `pg_test_db` (scope="function"): TRUNCATE event_log, p_tasks, p_phases, p_state + yield URL
- Убрать CREATE/DROP SCHEMA из function-scoped fixture

---

T-4710: BC-47-D — Интеграционные тесты TRUNCATE strategy

Status:               DONE
Spec ref:             Spec_v47 §8 UC-47-4 + §10 Tests #11, #12
Invariants:           I-TEST-TRUNCATE-1
spec_refs:            [Spec_v47 §8 UC-47-4, Spec_v47 §10]
produces_invariants:  [I-TEST-TRUNCATE-1]
requires_invariants:  [I-TEST-TRUNCATE-1]
Inputs:               tests/conftest.py, src/sdd/infra/event_log.py
Outputs:              tests/unit/infra/test_event_log.py
Acceptance:           pytest tests/unit/infra/test_event_log.py::test_pg_test_db_truncate_isolation PASS;
                      pytest tests/unit/infra/test_event_log.py::test_postgres_event_log_append_via_kernel PASS
Depends on:           T-4709

1. `test_pg_test_db_truncate_isolation` — два вызова pg_test_db в одном session → данные не пересекаются (TRUNCATE работает)
2. `test_postgres_event_log_append_via_kernel` — append через рефакторированный PostgresEventLog → seq корректны

---

<!-- Granularity: 10 tasks (TG-2). Все tasks независимо тестируемы (TG-1). -->
<!-- M1: T-4701..4702 | M2: T-4703..4705 | M3: T-4706..4708 | M4: T-4709..4710 -->
