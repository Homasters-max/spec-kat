# Spec_v47 — Phase 47: EventLog Kernel Extraction & Post-DuckDB Cleanup

Status: Draft  
Baseline: Spec_v46_RemoveDuckDB.md

---

## 0. Goal

Phase 47 завершает инфраструктурный рефакторинг, начатый в Phase 46.

Phase 46 создала `el_kernel.py` (BC-46-A) и подключила `PostgresEventLog` к `_kernel.*`.
Phase 47 завершает: верифицирует инварианты kernel, делает `PostgresEventLog` pure SQL-адаптером,
добавляет enforcement-тесты.

После Phase 47:
- `el_kernel.py` не содержит `import psycopg` / SQL; `PostgresEventLog` — pure SQL-адаптер (I-EL-KERNEL-1)
- `event_store_file()` полностью удалена из `infra/paths.py`; `show_path.py` работает без DuckDB fallback
- Reducer логирует INFO (не DEBUG) для инвалидированных событий при replay (carryover BC-46-I → BC-47-B)
- PG test fixtures используют TRUNCATE вместо CREATE/DROP SCHEMA → тесты быстрее

Phase 47 — чистый рефактор и cleanup: **нет новых domain events, нет изменений в бизнес-логике**.

---

## 1. Предусловия (все обязательны, блокирующие)

| # | Предусловие | Верификация |
|---|-------------|-------------|
| P-1 | Phase 46 завершена, все тесты зелёные | `SDD_DATABASE_URL=... pytest` → 0 FAILED |
| P-2 | I-NO-DUCKDB-1 PASS — DuckDB полностью удалён из src/sdd/ | `grep -rn "duckdb" src/sdd/ --include=*.py \| grep -v "DeprecationWarning\|event_store_file"` → пусто |
| P-3 | `event_store_file()` существует в `infra/paths.py` с `DeprecationWarning` (Phase 46 BC-46-D) | `grep "DeprecationWarning" src/sdd/infra/paths.py` → найдено |
| P-4 | `el_kernel.py` существует с тремя методами (Phase 46 BC-46-A); `PostgresEventLog` делегирует в `_kernel.*` | `python3 -c "from sdd.infra.el_kernel import EventLogKernel; print('OK')"` → OK |

**LLM MUST проверить все три предусловия через `sdd show-state` и запуск grep-проверок
перед началом любой задачи Phase 47.**

---

## 2. Scope

### In-Scope

- BC-47-A: `el_kernel.py` — вынести transaction/idempotency kernel из `PostgresEventLog` (I-EL-KERNEL-1)
- BC-47-B: Reducer INFO для инвалидированных событий — carryover из deferrable BC-46-I
- BC-47-C: `event_store_file()` финальное удаление — `show_path.py` caller + RuntimeError + удаление
- BC-47-D: PG test fixtures optimization — TRUNCATE вместо CREATE/DROP SCHEMA

### Out of Scope

- `execute_command` монолит рефактор (`commands/registry.py:615–787`) — Phase 48+
- `_sdd_root` глобал инвертирование (`infra/paths.py`) — Phase 48+
- `GuardContext` разбивка (7 полей → минимальные протоколы) — Phase 48+
- `sync_projections` инкапсуляция — Phase 48+
- `show_path.py` → PG query вместо YAML — Future
- State_index.yaml staleness latency fix (incremental projection / p_* query) — Future

---

## 3. Architecture / BCs

### BC-47-A: el_kernel.py — finalization (thin adapter enforcement)

**Файл:** `src/sdd/infra/el_kernel.py` (уже создан в Phase 46 BC-46-A)  
**Файл:** `src/sdd/infra/event_log.py` (уже делегирует в `_kernel.*`)

**Мотивация:** Phase 46 создала `el_kernel.py` и подключила `PostgresEventLog` к `_kernel.*`.
Phase 47 верифицирует что инвариант I-EL-KERNEL-1 выполнен: kernel не утёк psycopg/SQL,
PostgresEventLog не содержит дублирования business logic. Добавляет enforcement CI-тест.

**Действия BC-47-A:**

1. **Аудит `el_kernel.py`:** убедиться что нет `import psycopg`, нет SQL-строк.
   Если утечки обнаружены — вынести в `event_log.py` (SQL остаётся там).

2. **Аудит `PostgresEventLog.append()`:** убедиться что optimistic lock, idempotency, batch_id
   логика не дублируется — вся в `_kernel.*`. Удалить inline дубли если есть.

3. **Добавить enforcement grep-тест:**

```python
def test_el_kernel_no_psycopg_import():
    """I-EL-KERNEL-1: el_kernel.py must not import psycopg or contain SQL."""
    import subprocess
    result = subprocess.run(
        ["grep", "-n", r"import psycopg\|SELECT\|INSERT\|UPDATE\|DELETE",
         "src/sdd/infra/el_kernel.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-EL-KERNEL-1 violated. psycopg/SQL found in el_kernel.py:\n{result.stdout}"
    )
```

**Pre:**
- P-4: `el_kernel.py` существует, `PostgresEventLog` делегирует в `_kernel.*` (Phase 46 BC-46-A)
- Все тесты зелёные

**Post:**
- `grep "import psycopg\|SELECT\|INSERT" src/sdd/infra/el_kernel.py` → пусто
- `PostgresEventLog` не содержит дублирования lock/idempotency/batch логики
- `pytest tests/unit/infra/test_el_kernel.py` → PASS
- I-EL-KERNEL-1 PASS

### BC-47-B: Reducer INFO для инвалидированных событий (carryover BC-46-I)

**Файл:** `src/sdd/infra/projections.py`

**Мотивация:** carryover из Phase 46. Phase 46 (BC-46-I) понизила WARNING до DEBUG для
инвалидированных seq — консервативный первый шаг. Phase 47 поднимает до INFO: invalidation
теперь стабильна, нужна audit-trail без засорения WARNING-канала.

**Предварительная проверка:**

```bash
grep -n "logger.debug\|logger.warning" src/sdd/infra/projections.py
```

Если Phase 46 BC-46-I выполнен → найти `logger.debug("Skipping invalidated event")` → заменить на INFO.
Если BC-46-I не выполнен (deferrable) → искать `logger.warning` для invalidated seq → заменить на INFO напрямую.

**Изменение:**

```python
# Было (Phase 46 BC-46-I):
if seq in invalidated_seqs:
    logger.debug("Skipping invalidated event seq=%d type=%s", seq, event_type)
else:
    logger.warning("Unexpected duplicate %s at seq=%d", event_type, seq)

# Стало (Phase 47 BC-47-B):
if seq in invalidated_seqs:
    logger.info(
        "Skipping invalidated event seq=%d type=%s (I-INVALIDATED-LOG-1)",
        seq, event_type
    )
else:
    logger.warning(
        "Unexpected duplicate %s at seq=%d", event_type, seq
    )
```

**Инвариант I-INVALIDATED-LOG-1:**
Reducer MUST log INFO (не WARNING, не DEBUG) для событий, seq которых ∈ invalidated_seqs.
Неинвалидированные WARNING-события MUST остаться на WARNING.

**Pre:**
- `_get_invalidated_seqs()` доступен в контексте reducer

**Post:**
- `replay()` при наличии инвалидированных дублей → нет WARNING для их seq; только INFO
- Replay 27k событий: WARNING остаются только для реально неожиданных дублей
- I-INVALIDATED-LOG-1 PASS

### BC-47-C: event_store_file() — финальное удаление

**Затрагиваемые файлы:**
- `src/sdd/commands/show_path.py` — единственный caller
- `src/sdd/infra/paths.py` — определение функции

**Шаг 1: show_path.py — убрать зависимость от event_store_file()**

После Phase 46, `SDD_DATABASE_URL` обязателен (I-DB-URL-REQUIRED-1). `show_path.py` должен
отображать PG URL (с маскировкой пароля) или явную ошибку, если переменная не установлена.
DuckDB fallback — удалить.

```python
# show_path.py — было:
def _show_event_store_path() -> str:
    db_url = os.environ.get("SDD_DATABASE_URL")
    if db_url:
        return f"[PG] {_mask_password(db_url)}"
    return str(event_store_file())   # ← удалить этот fallback

# show_path.py — стало:
def _show_event_store_path() -> str:
    db_url = os.environ.get("SDD_DATABASE_URL")
    if not db_url:
        return "[ERROR] SDD_DATABASE_URL not set. DuckDB removed in Phase 46."
    return f"[PG] {_mask_password(db_url)}"
```

После изменения `show_path.py` — **нет callers `event_store_file()` в `src/sdd/`**.

**Шаг 2: event_store_file() → RuntimeError**

```python
# infra/paths.py — заменить DeprecationWarning на RuntimeError:
def event_store_file() -> Path:
    """Removed in Phase 47. DuckDB fully deleted in Phase 46.

    I-EVENT-STORE-FILE-REMOVED-1.
    """
    raise RuntimeError(
        "event_store_file() removed in Phase 47. "
        "DuckDB removed in Phase 46. Use event_store_url() instead."
    )
```

**Шаг 3: финальное удаление функции**

Удалить `event_store_file()` из `infra/paths.py` полностью.
Удалить `import warnings` если больше нигде не используется.

**Enforcement test:**

```python
def test_event_store_file_removed():
    """I-EVENT-STORE-FILE-REMOVED-1: event_store_file() absent from infra/paths.py."""
    import subprocess
    result = subprocess.run(
        ["grep", "-n", "event_store_file", "src/sdd/infra/paths.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-EVENT-STORE-FILE-REMOVED-1 violated. event_store_file still in paths.py:\n{result.stdout}"
    )
```

**Pre:**
- BC-47-A завершён (clean state после extraction)
- `show_path.py` не вызывает `event_store_file()` (Шаг 1 выполнен)

**Post:**
- `from sdd.infra.paths import event_store_file` → `ImportError`
- `grep "event_store_file" src/sdd/ -rn` → пусто
- `sdd show-path` выводит PG URL или ERROR-сообщение (не DuckDB путь)

### BC-47-D: PG test fixtures optimization — TRUNCATE вместо CREATE/DROP SCHEMA

**Файл:** `tests/conftest.py`

**Мотивация:** Текущая `pg_test_db` фикстура (Phase 46 BC-46-E) создаёт и удаляет schema
для каждого теста (`CREATE SCHEMA test_<uuid>` + DDL + `DROP SCHEMA CASCADE`). На 27k+ событий
DDL overhead ощутим при большом количестве интеграционных тестов.

**Оптимизация:** shared PG schema, изоляция через `TRUNCATE` внутри транзакции.

```python
# Стратегия: session-scoped schema + function-scoped TRUNCATE

@pytest.fixture(scope="session")
def _pg_shared_schema(_require_sdd_database_url):
    """Create shared test schema once per test session.

    Schema name: test_sdd_<pid> — per-process unique, prevents parallel conflicts.
    """
    import os
    schema = f"test_sdd_{os.getpid()}"
    base_url = _require_sdd_database_url
    conn = psycopg.connect(base_url)
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    _apply_sdd_ddl(conn, schema)
    conn.commit()
    conn.close()

    yield schema, base_url

    conn = psycopg.connect(base_url)
    conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def pg_test_db(_pg_shared_schema):
    """Isolated PG test: TRUNCATE all SDD tables before yield.

    I-TEST-TRUNCATE-1: faster than CREATE/DROP SCHEMA per test.
    Schema shared within session; data cleared between tests.
    """
    schema, base_url = _pg_shared_schema
    test_url = f"{base_url}?options=-csearch_path%3D{schema}"

    conn = psycopg.connect(base_url)
    conn.execute(f"SET search_path = {schema}, shared")
    conn.execute("TRUNCATE event_log, p_tasks, p_phases, p_state CASCADE")
    conn.commit()
    conn.close()

    yield test_url
```

**Инвариант I-TEST-TRUNCATE-1:** `pg_test_db` fixture MUST использовать TRUNCATE (не CREATE SCHEMA)
для изоляции между тестами. DDL выполняется один раз за session. Нарушение: если в teardown
присутствует `DROP SCHEMA` для основной фикстуры.

**Pre:**
- `SDD_DATABASE_URL` установлен
- DDL стабилен (таблицы: `event_log`, `p_tasks`, `p_phases`, `p_state`)

**Post:**
- Интеграционные тесты работают в 2-5x быстрее (нет DDL overhead per test)
- `pytest -k pg` → все тесты PASS с изолированными данными
- Параллельный запуск (`pytest-xdist -n auto`) безопасен (per-pid schema)

---

## 4. Domain Events

Phase 47 не вводит новых domain events. Чистый рефактор и cleanup.

---

## 5. Types & Interfaces

```python
# src/sdd/infra/el_kernel.py — новый модуль

class EventLogKernel:
    """Business logic kernel for event log writes.

    I-EL-KERNEL-1: no SQL, no psycopg imports. Pure Python business logic.
    PostgresEventLog delegates here; any future backend reuses this class.
    """

    def resolve_batch_id(self, events: list) -> str | None: ...
    def check_optimistic_lock(self, current_max: int, expected_head: int | None) -> None: ...
    def filter_duplicates(
        self,
        events: list[dict],
        existing_pairs: set[tuple[str, int]],
    ) -> tuple[list[dict], list[dict]]: ...
```

```python
# src/sdd/infra/event_log.py — PostgresEventLog после BC-47-A

class PostgresEventLog:
    """PostgreSQL-backed event log. SQL adapter only.

    I-EL-KERNEL-1: business logic delegated to EventLogKernel.
    This class: SQL specifics, psycopg3 connection, schema mapping.
    """
    _kernel: EventLogKernel = EventLogKernel()

    def append(self, events, ...) -> list[int]:
        # Delegates: batch_id, lock check, dedup → _kernel
        # SQL: SELECT MAX, INSERT, fetch existing pairs → this class
        ...
```

```python
# src/sdd/infra/paths.py — после BC-47-C

# event_store_file() — УДАЛЕНА (I-EVENT-STORE-FILE-REMOVED-1)
# event_store_url() — без изменений
# is_production_event_store() — без изменений
```

```python
# src/sdd/commands/show_path.py — после BC-47-C шага 1

def _show_event_store_path() -> str:
    """Show PG event store URL or error if SDD_DATABASE_URL not set."""
    db_url = os.environ.get("SDD_DATABASE_URL")
    if not db_url:
        return "[ERROR] SDD_DATABASE_URL not set. DuckDB removed in Phase 46."
    return f"[PG] {_mask_password(db_url)}"
```

---

## 6. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-EL-KERNEL-1 | `el_kernel.py` не содержит `import psycopg` и SQL; `PostgresEventLog` — pure SQL-адаптер без дублирования lock/idempotency/batch логики; enforcement: grep CI-тест (`test_el_kernel_no_psycopg_import` в BC-47-A) | 47 |
| I-EVENT-STORE-FILE-REMOVED-1 | `event_store_file()` удалена из `infra/paths.py`; `grep "event_store_file" src/sdd/` → пусто; enforcement: grep CI-тест | 47 |
| I-INVALIDATED-LOG-1 | Reducer MUST log INFO (не WARNING, не DEBUG) для событий, seq которых ∈ invalidated_seqs; неинвалидированные WARNING остаются WARNING; Phase 46 использовал DEBUG — Phase 47 поднимает до INFO; enforcement: тест с mock-logger | 47 |
| I-TEST-TRUNCATE-1 | `pg_test_db` fixture MUST использовать TRUNCATE (не CREATE SCHEMA) для изоляции; DDL выполняется один раз за session; enforcement: code review conftest.py | 47 |

### Обновлённые инварианты

| ID | Обновление |
|----|-----------|
| I-DB-1 | Без изменений — `open_sdd_connection(db_url)` принимает только PG URL (Phase 46) |
| I-EL-KERNEL-1 | Введён в Phase 47 (был вынесен из Phase 46 как Phase 47+ item) |

---

## 7. Pre/Post Conditions

### BC-47-A: el_kernel.py finalization

**Pre:**
- P-4: `el_kernel.py` существует (Phase 46 BC-46-A); `PostgresEventLog` делегирует в `_kernel.*`
- Все тесты зелёные

**Post:**
- `grep "import psycopg\|SELECT\|INSERT" src/sdd/infra/el_kernel.py` → пусто
- `PostgresEventLog.append()` не содержит дублирования lock/idempotency/batch логики
- Enforcement grep-тест `test_el_kernel_no_psycopg_import` добавлен и PASS
- I-EL-KERNEL-1 PASS

### BC-47-B: Reducer INFO (carryover BC-46-I)

**Pre:**
- `_get_invalidated_seqs()` доступен в контексте reducer
- `grep -n "logger.debug\|logger.warning" src/sdd/infra/projections.py` — найти текущий уровень для invalidated seq

**Post:**
- Replay 27k событий: нет WARNING и нет DEBUG для seq ∈ invalidated_seqs; только INFO
- Неинвалидированные дубли: по-прежнему WARNING
- I-INVALIDATED-LOG-1 PASS
- Если уровень для invalidated seq уже был INFO (или события подавлены без лога) → BC-47-B = N/A

### BC-47-C: event_store_file() финальное удаление

**Pre:**
- BC-47-A завершён (clean state)
- `show_path.py` — единственный caller `event_store_file()` в `src/sdd/`

**Post:**
- `grep -rn "event_store_file" src/sdd/` → пусто
- `sdd show-path` с `SDD_DATABASE_URL` → `[PG] postgresql://...` (пароль замаскирован)
- `sdd show-path` без `SDD_DATABASE_URL` → `[ERROR] SDD_DATABASE_URL not set...`
- `from sdd.infra.paths import event_store_file` → `ImportError`
- I-EVENT-STORE-FILE-REMOVED-1 PASS

### BC-47-D: PG test fixtures optimization

**Pre:**
- `SDD_DATABASE_URL` установлен
- `pg_test_db` фикстура существует (Phase 46 BC-46-E)

**Post:**
- `_pg_shared_schema` выполняет DDL один раз за session
- `pg_test_db` выполняет TRUNCATE перед каждым тестом
- `pytest -k pg` → PASS; изоляция данных между тестами сохранена
- I-TEST-TRUNCATE-1 PASS

---

## 8. Use Cases

### UC-47-1: FakeEventLog unit test (el_kernel в изоляции)

**Pre:** `EventLogKernel` существует как отдельный модуль  
**Steps:**
1. `kernel = EventLogKernel()`
2. `kernel.check_optimistic_lock(current_max=10, expected_head=10)` → OK
3. `kernel.check_optimistic_lock(current_max=11, expected_head=10)` → `StaleStateError`
4. `kernel.resolve_batch_id([e1, e2])` → UUID4 string
5. `kernel.resolve_batch_id([e1])` → None
6. `kernel.filter_duplicates(events, existing={(cmd_id, 0)})` → ([e_new], [e_dup])
**Post:** все тесты через Python — без PG; I-EL-KERNEL-1 демонстрирует изоляцию

### UC-47-2: show-path без SDD_DATABASE_URL после Phase 47

**Pre:** Phase 47 завершена; `SDD_DATABASE_URL` не установлен  
**Steps:**
1. `sdd show-path`
2. `_show_event_store_path()` → `os.environ.get("SDD_DATABASE_URL")` → None
3. Возвращает `"[ERROR] SDD_DATABASE_URL not set. DuckDB removed in Phase 46."`
**Post:** явное сообщение об ошибке; нет `FileNotFoundError` от event_store_file()

### UC-47-3: Replay инвалидированных событий без WARNING-шума

**Pre:** event_log содержит инвалидированные seq (25886–25893 TestEvent)  
**Steps:**
1. `sdd rebuild-state` → `_replay_from_event_log()`
2. Для каждого инвалидированного seq: `seq in invalidated_seqs` → True
3. `logger.info("Skipping invalidated event seq=%d ...", seq)` (не WARNING)
**Post:** replay без WARNING-шума; реальные неожиданные дубли по-прежнему WARNING

### UC-47-4: Интеграционный тест с pg_test_db (TRUNCATE strategy)

**Pre:** `SDD_DATABASE_URL` установлен; `_pg_shared_schema` создал схему в начале session  
**Steps:**
1. Тест A: `pg_test_db` fixture → TRUNCATE → append 3 events → assert max_seq = 3
2. Тест B: `pg_test_db` fixture → TRUNCATE → event_log пуст → append 1 event → max_seq = 1
**Post:** изоляция данных между тестами; DDL overhead только один раз за session

---

## 9. Integration

### Порядок применения BC (строгий)

```
Предусловия P-1, P-2, P-3, P-4 → верифицированы
  ↓
BC-47-B: Reducer INFO для инвалидированных событий   ← ПЕРВЫМ (изолированный carryover)
  Найти logger.debug/warning для invalidated_seqs → заменить на logger.info
  pytest PASS → replay без WARNING-шума для invalidated seq
  ↓
BC-47-A: el_kernel.py finalization                   ← основная работа
  Шаг 1: Аудит el_kernel.py — убедиться нет psycopg/SQL
  Шаг 2: Аудит PostgresEventLog.append() — нет дублирования логики
  Шаг 3: Добавить enforcement grep-тест test_el_kernel_no_psycopg_import
  Шаг 4: pytest PASS; I-EL-KERNEL-1 PASS
  ↓
BC-47-C: event_store_file() финальное удаление        ← после BC-47-A
  Шаг 1: show_path.py — убрать вызов event_store_file()
  Шаг 2: event_store_file() → RuntimeError
  Шаг 3: удалить event_store_file() из paths.py
  Шаг 4: pytest PASS + grep-тест I-EVENT-STORE-FILE-REMOVED-1
  ↓
BC-47-D: PG test fixtures optimization                ← последним (deferrable)
  pytest PASS; быстрее чем до оптимизации
```

**BC-47-B ПЕРВЫМ:** изолированный patch в projections.py; не зависит от BC-47-A.

**BC-47-A = finalization, не creation:** `el_kernel.py` уже создан в Phase 46.
Задача — верифицировать инварианты и добавить CI enforcement.

**BC-47-A ПЕРЕД BC-47-C:** после audit — clean state; легче верифицировать отсутствие callers.

**BC-47-D — последним и deferrable:** не блокирует ни одно другое BC; при нехватке времени переносится в Phase 48 первым task'ом.

### Влияние на CI

- `SDD_DATABASE_URL` обязателен (Phase 46+) — без изменений
- `pytest --cov=sdd` охватывает `el_kernel.py` — добавить в coverage scope
- `pytest -n auto` (xdist) безопасен с per-pid schema стратегией BC-47-D

---

## 10. Verification

### Unit Tests

| # | Test | Файл | Invariant(s) |
|---|------|------|--------------|
| 1 | `test_el_kernel_resolve_batch_id_multi` — 2+ events → UUID4 string | `tests/unit/infra/test_el_kernel.py` | I-EL-BATCH-ID-1 |
| 2 | `test_el_kernel_resolve_batch_id_single` — 1 event → None | `tests/unit/infra/test_el_kernel.py` | I-EL-BATCH-ID-1 |
| 3 | `test_el_kernel_check_optimistic_lock_pass` — current==expected → OK | `tests/unit/infra/test_el_kernel.py` | I-OPTLOCK-1 |
| 4 | `test_el_kernel_check_optimistic_lock_fail` — current≠expected → StaleStateError | `tests/unit/infra/test_el_kernel.py` | I-OPTLOCK-1 |
| 5 | `test_el_kernel_filter_duplicates` — known pair skipped; new pair passed | `tests/unit/infra/test_el_kernel.py` | I-IDEM-SCHEMA-1 |
| 6 | `test_el_kernel_no_psycopg_import` — grep el_kernel.py → нет psycopg/SQL (enforcement BC-47-A) | `tests/unit/infra/test_el_kernel.py` | I-EL-KERNEL-1 |
| 7 | `test_event_store_file_removed` — grep paths.py → пусто | `tests/unit/infra/test_paths.py` | I-EVENT-STORE-FILE-REMOVED-1 |
| 8 | `test_show_path_no_env_returns_error_message` — без SDD_DATABASE_URL → ERROR строка, не DuckDB путь | `tests/unit/commands/test_show_path.py` | BC-47-C |
| 9 | `test_reducer_info_for_invalidated_seq` — replay с инвалидированным дублем → уровень INFO, не WARNING и не DEBUG (mock logger) | `tests/unit/infra/test_projections.py` | I-INVALIDATED-LOG-1 |
| 10 | `test_reducer_warning_for_non_invalidated_dup` — неинвалидированный дубль → WARNING | `tests/unit/infra/test_projections.py` | I-INVALIDATED-LOG-1 |

### Integration Tests (PG)

| # | Test | Файл | Invariant(s) |
|---|------|------|--------------|
| 11 | `test_postgres_event_log_append_via_kernel` — append через рефакторированный PostgresEventLog → seq корректны | `tests/unit/infra/test_event_log.py` | I-EL-KERNEL-1 |
| 12 | `test_pg_test_db_truncate_isolation` — два теста с `pg_test_db` → данные не пересекаются | `tests/conftest.py` → тест в `test_event_log.py` | I-TEST-TRUNCATE-1 |

### Final Smoke

```bash
# 1. el_kernel.py существует, нет psycopg импортов
python3 -c "from sdd.infra.el_kernel import EventLogKernel; print('OK')"
grep -n "import psycopg" src/sdd/infra/el_kernel.py
# ожидаемый результат: пусто

# 2. event_store_file удалена
grep -rn "event_store_file" src/sdd/ --include="*.py"
# ожидаемый результат: пусто

# 3. show-path выдаёт PG URL
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd sdd show-path
# ожидаемый результат: [PG] postgresql://sdd:***@localhost:5432/sdd

# 4. show-path без SDD_DATABASE_URL — ERROR, не DuckDB путь
sdd show-path
# ожидаемый результат: [ERROR] SDD_DATABASE_URL not set. DuckDB removed in Phase 46.

# 5. replay без WARNING-шума для инвалидированных seq
SDD_DATABASE_URL=... sdd rebuild-state 2>&1 | grep -c "WARNING"
# ожидаемый результат: 0 (или только реальные WARNING, не от invalidated seq)

# 6. Все тесты
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest --cov=sdd
# ожидаемый результат: 0 FAILED
```

---

## 11. Architectural Debt (Phase 48+)

| Issue | Файл | Суть |
|-------|------|------|
| `execute_command` монолит | `commands/registry.py:615–787` | 5-шаговый pipeline без явных швов; рефакторинг в именованные функции |
| `_sdd_root` глобал (Путь B) | `infra/paths.py` | Инвертировать зависимость → чистые функции с явными параметрами |
| `GuardContext` разбивка | `domain/guards/context.py` | 7 полей; разбить на минимальные протоколы (StateView, TaskView, NormView) |
| `sync_projections` инкапсуляция | `infra/projections.py` | `rebuild_state()` и `rebuild_taskset()` слишком связаны |
| Два пути guard construction | `commands/registry.py` | `_default_build_guards()` vs `guard_factory()` — унифицировать |
| State_index.yaml staleness latency | `infra/projections.py` | 27k+ событий → replay latency растёт; incremental projection или p_* direct query |
| Удаление State_index.yaml | `infra/projections.py` | Замена на прямые p_* query — требует явного архитектурного решения |
| `show_path.py` → PG query | `commands/show_path.py` | Отображать live данные из PG вместо YAML snapshot |
| BC-47-D (если deferrable) | `tests/conftest.py` | TRUNCATE fixtures — если не вошло в Phase 47 |

---

## 12. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `execute_command` монолит рефактор | Phase 48+ |
| `_sdd_root` глобал инвертирование | Phase 48+ |
| `GuardContext` разбивка | Phase 48+ |
| `sync_projections` инкапсуляция | Phase 48+ |
| `show_path.py` → PG query вместо YAML | Future |
| State_index.yaml staleness latency fix | Future |
| Удаление State_index.yaml (замена на p_* query) | Future (явное архитектурное решение) |
| BC-47-D PG fixtures optimization (если deferrable) | Phase 48 первым task'ом |
