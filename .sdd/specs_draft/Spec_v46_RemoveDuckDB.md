# Spec_v46 — Phase 46: Remove DuckDB (DESTRUCTIVE)

Status: Draft  
Baseline: Spec_v45_EnforcePostgres.md  
Architectural analysis: `.claude/plans/dazzling-dreaming-stardust.md`

---

## 0. Goal

Полное удаление DuckDB из codebase и зависимостей.  
После Phase 46: никакого DuckDB-кода в `src/sdd/`; `duckdb` отсутствует в `pyproject.toml`;
`in_memory_db` и `tmp_db_path` фикстуры заменены на PG-аналоги.

**Это DESTRUCTIVE CHANGE.** Откат невозможен без git reset.
Предусловия строго обязательны — все три должны быть выполнены и верифицированы
до первого commit Phase 46.

---

## 1. Предусловия (все обязательны, блокирующие)

| # | Предусловие | Верификация |
|---|-------------|-------------|
| P-1 | Phase 45 завершена, все тесты зелёные | `SDD_DATABASE_URL=... pytest` → 0 FAILED |
| P-2 | `scripts/migrate_duckdb_to_pg.py` выполнен и верифицирован | скрипт завершился без ошибок |
| P-3 | `replay(DuckDB) == replay(PG)` — I-MIGRATION-1 PASS | `pytest -m migration` → PASS |

**LLM MUST проверить все три предусловия через `sdd show-state` и запуск тестов
перед началом любой задачи Phase 46.**

---

## 2. Scope

### In-Scope

- BC-46-A: `el_kernel.py` extraction — shared transaction/idempotency kernel (prerequisite)
- BC-46-B: `infra/db.py` — удаление DuckDB-ветки, `DuckDBLockTimeoutError`, `_restart_sequence()`
- BC-46-C: `db/connection.py` — удаление `_open_duckdb()` и DuckDB-ветки
- BC-46-D: `infra/paths.py` — `event_store_file()` → `DeprecationWarning` + final deprecated
- BC-46-E: DuckDB тест-фикстуры → замена на PG test schema
- BC-46-F: `pyproject.toml` — подтвердить отсутствие `duckdb` (по данным плана: уже удалён в T-4311)
- BC-46-G: Финальный enforcement тест I-NO-DUCKDB-1

### Out of Scope

- `_sdd_root` глобал инвертирование — Phase 47+
- `execute_command` монолит рефактор — Phase 47+
- `GuardContext` разбивка — Phase 47+
- `sync_projections` инкапсуляция — Phase 47+

---

## 3. Architecture / BCs

### BC-46-A: el_kernel.py — Shared EventLog Kernel (PREREQUISITE)

**Файл:** `src/sdd/infra/el_kernel.py` (новый)

**Мотивация:** `EventLog` (DuckDB, ~200 строк) и `PostgresEventLog` (PG, ~270 строк) дублируют
130+ строк: логика идемпотентности, transaction handling, conflict-resolution, optimistic lock.
Перед удалением DuckDB-адаптера нужно вынести shared kernel — иначе `PostgresEventLog`
остаётся 270-строчным монолитом без шва.

**Архитектура:**

```python
# src/sdd/infra/el_kernel.py

class EventLogKernel:
    """Shared transaction/idempotency kernel for EventLog adapters.

    SQL adapters (EventLog, PostgresEventLog) delegate all business logic here.
    Each adapter provides: _execute_sql(), _check_conflict(), _next_seq() — ≤ 10 lines.
    I-EL-KERNEL-1: SQL adapters ≤ 10 lines each after extraction.
    """

    def check_idempotent(
        self,
        command_id: str | None,
        event_index: int,
        event_type: str,
        task_id: str | None,
        phase_id: int | None,
        payload_hash: str,
    ) -> bool:
        """Returns True if this event was already appended (dedup by command_id+event_index)."""
        ...

    def check_optimistic_lock(
        self,
        conn: Any,
        expected_head: int | None,
    ) -> None:
        """Raises StaleStateError if MAX(sequence_id) != expected_head."""
        ...

    def build_append_batch(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None,
        batch_id: str | None,
    ) -> list[dict]:
        """Serialize events to row dicts for batch INSERT."""
        ...

    def resolve_conflict(
        self,
        event: DomainEvent,
        command_id: str | None,
        event_index: int,
    ) -> ConflictResolution:
        """Returns SKIP (idempotent dup) or RAISE (genuine conflict)."""
        ...
```

**После извлечения:**
- `EventLog` (DuckDB) → SQL-диалект ≤ 10 строк: делегирует в `EventLogKernel`
- `PostgresEventLog` (PG) → SQL-диалект ≤ 10 строк: делегирует в `EventLogKernel`
- Тесты логики: бьют по `EventLogKernel` напрямую (без БД)

**Инвариант I-EL-KERNEL-1:** после BC-46-A каждый SQL-адаптер содержит ≤ 10 строк не-DDL кода.
Enforcement: тест `test_el_adapters_are_thin` (grep/ast).

### BC-46-B: infra/db.py — удаление DuckDB-ветки

**Файл:** `src/sdd/infra/db.py`

Удалить:
- DuckDB-ветку в `open_sdd_connection()`
- `DuckDBLockTimeoutError` exception класс
- `_restart_sequence()` функцию (DuckDB-specific)
- `import duckdb` (lazy и все упоминания)

После BC-46-B `open_sdd_connection(db_url)` принимает только PG URL.
Если передан не-PG URL → `ValueError("DuckDB is no longer supported. Use SDD_DATABASE_URL.")`.

```python
def open_sdd_connection(db_url: str) -> psycopg.Connection:
    """Open PostgreSQL connection.

    I-NO-DUCKDB-1: DuckDB removed in Phase 46.
    Raises ValueError for non-PG URLs.
    """
    if not is_postgres_url(db_url):
        raise ValueError(
            f"DuckDB is no longer supported. "
            f"Set SDD_DATABASE_URL and use event_store_url(). Got: {db_url!r}"
        )
    from sdd.db.connection import open_db_connection
    return open_db_connection(db_url)
```

### BC-46-C: db/connection.py — удаление DuckDB-ветки

**Файл:** `src/sdd/db/connection.py`

Удалить:
- `_open_duckdb()` функцию и все её вызовы
- DuckDB-ветку в `open_db_connection()`
- `import duckdb` (если есть)

### BC-46-D: infra/paths.py — event_store_file() deprecated

**Файл:** `src/sdd/infra/paths.py`

```python
import warnings

def event_store_file() -> Path:
    """Deprecated since Phase 46. DuckDB removed.

    Use event_store_url() for event store access.
    Retained only for legacy migration scripts.
    """
    warnings.warn(
        "event_store_file() is deprecated. DuckDB removed in Phase 46. "
        "Use event_store_url() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_sdd_root() / "state" / "sdd_events.duckdb"
```

Финальное удаление `event_store_file()` — отдельная задача Phase 47+ (после удаления
последних callers: `show_path.py`, legacy migration scripts).

### BC-46-E: Замена DuckDB тест-фикстур

**Файл:** `tests/conftest.py`

| Старая фикстура | Новая фикстура | Стратегия |
|-----------------|----------------|-----------|
| `in_memory_db` (`:memory:` DuckDB) | `pg_test_db` — временная PG schema | `CREATE SCHEMA test_<uuid>` + DDL; DROP в teardown |
| `tmp_db_path` (explicit DuckDB path) | `pg_test_url` — PG URL с test schema | аналогично |

**pg_test_db pattern:**

```python
@pytest.fixture
def pg_test_db(request):
    """Temporary PostgreSQL schema for isolated test.

    Creates schema test_<uuid>, applies DDL, yields connection URL.
    Drops schema in teardown.
    """
    import uuid
    schema = f"test_{uuid.uuid4().hex[:8]}"
    base_url = os.environ["SDD_DATABASE_URL"]
    test_url = f"{base_url}?options=-csearch_path%3D{schema}"

    conn = psycopg.connect(base_url)
    conn.execute(f"CREATE SCHEMA {schema}")
    # Применить DDL (event_log, p_*)
    _apply_sdd_ddl(conn, schema)
    conn.commit()
    conn.close()

    yield test_url

    conn = psycopg.connect(base_url)
    conn.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.commit()
    conn.close()
```

**Требование:** `SDD_DATABASE_URL` установлен в CI для всех тестов Phase 46+.
Unit-тесты с `FakeEventLog` (не открывают БД) — продолжают работать без PG.

### BC-46-F: pyproject.toml — подтверждение

**По данным плана:** `duckdb` уже удалён в T-4311.

Верификация:

```bash
grep "duckdb" pyproject.toml
# ожидаемый результат: пусто
```

Если `duckdb` обнаружен → удалить из `[project.dependencies]`.

### BC-46-G: Enforcement тест I-NO-DUCKDB-1

Новый тест в `tests/unit/infra/test_paths.py`:

```python
def test_no_duckdb_imports_in_src():
    """I-NO-DUCKDB-1: DuckDB fully removed from src/sdd/.

    Checks: no 'import duckdb', no 'from duckdb', no 'duckdb' string literals.
    Exception: migration scripts in scripts/ (legacy only).
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "duckdb", "src/sdd/", "--include=*.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-NO-DUCKDB-1 violated. DuckDB references found:\n{result.stdout}"
    )


def test_duckdb_not_in_dependencies():
    """I-NO-DUCKDB-1: duckdb absent from pyproject.toml dependencies."""
    import subprocess
    result = subprocess.run(
        ["grep", "duckdb", "pyproject.toml"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-NO-DUCKDB-1 violated. duckdb in pyproject.toml:\n{result.stdout}"
    )
```

---

## 4. Domain Events

Phase 46 не вводит новых domain events.

---

## 5. Types & Interfaces

```python
# src/sdd/infra/el_kernel.py — новый модуль

class ConflictResolution(Enum):
    SKIP = "skip"    # idempotent duplicate — silently skip
    RAISE = "raise"  # genuine conflict — raise ConflictError

class EventLogKernel:
    """Shared kernel extracted from EventLog and PostgresEventLog."""
    def check_idempotent(self, ...) -> bool: ...
    def check_optimistic_lock(self, conn, expected_head) -> None: ...
    def build_append_batch(self, events, source, command_id, batch_id) -> list[dict]: ...
    def resolve_conflict(self, event, command_id, event_index) -> ConflictResolution: ...
```

```python
# src/sdd/infra/db.py — упрощённая после BC-46-B

def open_sdd_connection(db_url: str) -> psycopg.Connection:
    """PG-only. Raises ValueError for non-PG URLs (DuckDB removed)."""
    ...

# Удалены: DuckDBLockTimeoutError, _restart_sequence()
```

```python
# src/sdd/infra/paths.py — event_store_file() deprecated

def event_store_file() -> Path:
    """Deprecated since Phase 46. Will raise DeprecationWarning."""
    ...

# event_store_url() — без изменений (Phase 45)
# is_production_event_store() — без изменений (Phase 45)
```

---

## 6. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-NO-DUCKDB-1 | DuckDB полностью удалён из `src/sdd/` и зависимостей; `import duckdb` нигде в src не встречается; enforcement: grep CI-тест (BC-46-G) | 46 |
| I-EL-KERNEL-1 | Shared transaction/idempotency kernel вынесен в `el_kernel.py`; SQL-адаптеры (`EventLog`, `PostgresEventLog`) содержат ≤ 10 строк не-DDL кода каждый; enforcement: ast-тест | 46 |
| I-MIGRATION-1 | `replay(DuckDB_events) == replay(event_log_PG)` для одинакового набора событий; верификация выполнена до BC-46-B | 46 (pre) |

### Обновлённые инварианты

| ID | Обновление |
|----|-----------|
| I-DB-1 | `open_sdd_connection(db_url)` принимает только PG URL; non-PG → `ValueError` (DuckDB removed) |
| I-DB-TEST-1 | Tests MUST NOT open production event store; `is_production_event_store(db_path)` — единственный guard; DuckDB fixture comparison удалён |
| I-LAZY-DUCK-1 | Утрачивает силу: `import duckdb` полностью удалён из src/sdd/ (I-NO-DUCKDB-1) |

---

## 7. Pre/Post Conditions

### BC-46-A: el_kernel.py

**Pre:**
- `EventLog` и `PostgresEventLog` существуют и оба реализуют `EventLogKernelProtocol`

**Post:**
- `el_kernel.py` существует и содержит `EventLogKernel`
- `EventLog` делегирует в `EventLogKernel`; собственный код ≤ 10 строк
- `PostgresEventLog` делегирует в `EventLogKernel`; собственный код ≤ 10 строк
- `pytest -m "not pg"` → PASS (без изменений)
- `pytest -m pg` → PASS (без изменений)

### BC-46-B + BC-46-C: удаление DuckDB кода

**Pre:**
- BC-46-A выполнен
- I-MIGRATION-1 PASS (данные в PG, верифицированы)

**Post:**
- `grep -r "duckdb" src/sdd/` → пусто (кроме `DeprecationWarning` строки в `paths.py`)
- `DuckDBLockTimeoutError` нет в codebase
- `_restart_sequence()` нет в codebase
- `open_sdd_connection(non_pg_url)` → `ValueError`

### BC-46-E: PG тест-фикстуры

**Pre:**
- `SDD_DATABASE_URL` установлен в CI/test environment

**Post:**
- `pytest -m "not pg"` → PASS (FakeEventLog-тесты без PG)
- `pytest` (все) с `SDD_DATABASE_URL` → PASS
- `in_memory_db` и `tmp_db_path` фикстуры удалены или заменены

---

## 8. Use Cases

### UC-46-1: Попытка использовать DuckDB URL после Phase 46

**Pre:** кто-то пытается передать `db_path=".sdd/state/sdd_events.duckdb"`  
**Steps:**
1. `open_sdd_connection(".sdd/state/sdd_events.duckdb")`
2. `is_postgres_url(...)` → False
3. `ValueError("DuckDB is no longer supported...")`
**Post:** явное сообщение с инструкцией

### UC-46-2: rebuild-state полностью из PG

**Pre:** Phase 46 завершена; `SDD_DATABASE_URL` установлен  
**Steps:**
1. `sdd rebuild-state`
2. `get_current_state(db_url, full_replay=True)` → replay из `event_log` (PG)
3. `Projector.apply()` для каждого события
4. `State_index.yaml` rebuilt
**Post:** консистентное состояние; DuckDB не упоминается нигде в стеке

### UC-46-3: EventLog unit test через FakeEventLog (без PG)

**Pre:** `FakeEventLog` реализует `EventLogKernelProtocol`  
**Steps:**
1. `fake_el = FakeEventLog()`
2. `execute_command(spec, cmd, event_log=fake_el)`
3. Kernel использует `fake_el.max_seq()` и `fake_el.append(...)`
**Post:** unit test работает без PG; I-NO-DUCKDB-1 не нарушен (FakeEventLog = in-memory Python)

---

## 9. Integration

### Порядок применения BC (строгий)

```
Предусловия P-1, P-2, P-3 → верифицированы
  ↓
BC-46-A: el_kernel.py extraction  (prerequisite — реструктурирование без удаления)
  ↓
  pytest PASS (без DuckDB-удаления)
  ↓
BC-46-B: infra/db.py удаление DuckDB-ветки
BC-46-C: db/connection.py удаление DuckDB-ветки   (параллельно с BC-46-B)
BC-46-D: paths.py DeprecationWarning              (параллельно)
BC-46-E: тест-фикстуры замена                     (параллельно)
  ↓
BC-46-F: pyproject.toml верификация
BC-46-G: enforcement тест                         (последним)
  ↓
  pytest (все) PASS
```

**BC-46-A MUST применяться первым.** Без него удаление DuckDB-адаптера оставляет
`PostgresEventLog` с дублированной логикой без шва (I-EL-KERNEL-1).

### Влияние на CI

После Phase 46: CI **обязательно** устанавливает `SDD_DATABASE_URL`.
Без PG в CI → все тесты (кроме FakeEventLog-юнитов) упадут.

Рекомендация: Docker Compose из Phase 42 (`docker-compose.yml`) остаётся как dev-среда;
CI использует managed PG service (GitHub Actions `services: postgres:`).

---

## 10. Verification

### Unit Tests

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `test_no_duckdb_imports_in_src` — grep src/sdd/ → пусто | I-NO-DUCKDB-1 |
| 2 | `test_duckdb_not_in_dependencies` — grep pyproject.toml → пусто | I-NO-DUCKDB-1 |
| 3 | `test_el_adapters_are_thin` — ast: EventLog и PostgresEventLog ≤ 10 non-DDL строк | I-EL-KERNEL-1 |
| 4 | `test_el_kernel_idempotency_check` — EventLogKernel.check_idempotent без БД | I-EL-KERNEL-1 |
| 5 | `test_el_kernel_optimistic_lock` — EventLogKernel.check_optimistic_lock: stale → StaleStateError | I-EL-KERNEL-1 |
| 6 | `test_open_sdd_connection_rejects_duckdb_path` — передать `.duckdb` path → ValueError | I-NO-DUCKDB-1, I-DB-1 |
| 7 | `test_event_store_file_emits_deprecation_warning` — вызов → DeprecationWarning | BC-46-D |
| 8 | `test_pg_test_db_fixture_isolated` — два теста с `pg_test_db` → разные схемы | BC-46-E |
| 9 | `test_migration_replay_parity` — `replay(DuckDB) == replay(PG)` (pytest -m migration) | I-MIGRATION-1 |

### Integration Tests (PG)

| # | Test | Invariant(s) |
|---|------|--------------|
| 10 | `test_pg_full_pipeline_no_duckdb` — execute_and_project → event_log → p_* → YAML; нет упоминаний DuckDB в стеке | I-NO-DUCKDB-1 |
| 11 | `test_pg_rebuild_state_from_scratch` — TRUNCATE p_* → full replay → I-REPLAY-1 PASS | I-REPLAY-1, I-REBUILD-ATOMIC-1 |

### Final Smoke

```bash
# 1. Нет duckdb в src/sdd/
grep -r "duckdb" src/sdd/ --include="*.py"
# ожидаемый результат: пусто (или только DeprecationWarning строка в paths.py)

# 2. Нет duckdb в зависимостях
grep "duckdb" pyproject.toml
# ожидаемый результат: пусто

# 3. Все тесты
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest --cov=sdd

# 4. sdd show-state работает
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd sdd show-state
```

---

## 11. Architectural Debt (Phase 47+)

Phase 46 решает DuckDB-удаление. Следующие issues остаются:

| Issue | Файл | Суть |
|-------|------|------|
| `execute_command` монолит | `commands/registry.py:615–870` | 4 фазы Write Kernel без швов |
| `_sdd_root` глобал (Путь B) | `infra/paths.py` | инвертировать зависимость → чистые функции |
| `GuardContext` overly broad | `domain/guards/context.py` | 7 полей; разбить на минимальные протоколы |
| `sync_projections` инкапсуляция | `infra/projections.py` | `rebuild_state()` + `rebuild_taskset()` раздельно |
| Два пути guard construction | `commands/registry.py` | `_default_build_guards()` vs `guard_factory()` |
| `event_store_file()` final deletion | `infra/paths.py` | после удаления callers в `show_path.py` |

---

## 12. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `event_store_file()` final deletion | Phase 47+ |
| `_sdd_root` глобал инвертирование | Phase 47+ |
| `execute_command` монолит рефактор | Phase 47+ |
| `GuardContext` разбивка | Phase 47+ |
| `show_path.py` → PG query вместо YAML | Future |
| Удаление State_index.yaml (замена на p_* query) | Future (явное решение нужно) |
