# Spec_v46 — Phase 46: Remove DuckDB (DESTRUCTIVE)

Status: Draft  
Baseline: Spec_v45_EnforcePostgres.md  
Architectural analysis: `.claude/plans/dazzling-dreaming-stardust.md`

---

## 0. Goal

Полное удаление DuckDB из codebase и зависимостей. Устранение операционных проблем,
выявленных по итогам Phase 45.

После Phase 46:
- никакого DuckDB-кода в `src/sdd/`; `duckdb` отсутствует в `pyproject.toml`
- `in_memory_db` и `tmp_db_path` фикстуры заменены на PG-аналоги
- `invalidate_event` работает на PG — можно инвалидировать загрязняющие TestEvent записи
- reducer не генерирует WARNING-шум для инвалидированных событий при replay
- `sdd record-session` не создаёт дубли SessionDeclared внутри одной сессии/дня

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

**Примечание по P-2/P-3:** если DuckDB-файл `.sdd/state/sdd_events.duckdb` отсутствует
или пуст (все данные уже в PG с Phase 32), считать P-2/P-3 выполненными (N/A).
Верификация: `ls -la .sdd/state/sdd_events.duckdb || echo "absent"`.
Если файл существует → обязательно запустить `pytest -m migration`.

---

## 2. Scope

### In-Scope

- BC-46-A: `el_kernel.py` — minimal extraction: создать модуль с тремя методами pure Python; `PostgresEventLog` делегирует в `_kernel`
- BC-46-B: `infra/db.py` — удаление DuckDB-ветки, `DuckDBLockTimeoutError`, `_restart_sequence()`
- BC-46-C: `db/connection.py` — удаление `_open_duckdb()` и DuckDB-ветки
- BC-46-D: `infra/paths.py` — `event_store_file()` → `DeprecationWarning` + final deprecated
- BC-46-E: DuckDB тест-фикстуры → замена на PG test schema + fail-fast guard
- BC-46-F: `pyproject.toml` — подтвердить отсутствие `duckdb` (по данным плана: уже удалён в T-4311)
- BC-46-G: Финальный enforcement тест I-NO-DUCKDB-1 + I-DB-ENTRY-1
- BC-46-H: `invalidate_event.py` — миграция на PG (I-INVALIDATE-PG-1) + --force guard
- BC-46-I: reducer — suppress DEBUG для инвалидированных событий при replay (deferrable; Phase 47 поднимет до INFO)
- BC-46-J: `record_session.py` — SessionDeclared idempotent dedup via stable command_id (I-SESSION-DEDUP-1)

### Out of Scope

- `el_kernel.py` thin adapter finalization (BC-47-A) — Phase 47 (`PostgresEventLog` становится pure SQL-адаптером; enforcement grep-тест `no psycopg in el_kernel`)
- `_sdd_root` глобал инвертирование — Phase 47+
- `execute_command` монолит рефактор — Phase 47+
- `GuardContext` разбивка — Phase 47+
- `sync_projections` инкапсуляция — Phase 47+
- PG test fixtures оптимизация (transaction rollback / TRUNCATE) — Phase 47+

---

## 3. Architecture / BCs

### BC-46-A: el_kernel.py — minimal extraction

**Новый файл:** `src/sdd/infra/el_kernel.py`  
**Изменяемый файл:** `src/sdd/infra/event_log.py`

**Граница Phase 46 / Phase 47:**

| Фаза | Что делается |
|------|-------------|
| Phase 46 (BC-46-A) | Создать `el_kernel.py` с тремя методами; `PostgresEventLog.append()` делегирует в `_kernel.*`; логика idempotency/optimistic lock/batch_id перенесена в kernel |
| Phase 47 (BC-47-A) | Убедиться что `el_kernel.py` не содержит `import psycopg` / SQL; `PostgresEventLog` — pure SQL-адаптер; добавить enforcement grep-тест |

**Три метода `EventLogKernel` (pure Python, no SQL, no psycopg):**

```python
# src/sdd/infra/el_kernel.py

from __future__ import annotations
import uuid
from typing import Any


class EventLogKernel:
    """Business logic for event log writes: optimistic lock, idempotency, batch ID.

    I-EL-KERNEL-1 (Phase 47): PostgresEventLog delegates here; no SQL in this class.
    Phase 46: module created and wired; Phase 47: enforcement verified.
    """

    def resolve_batch_id(self, events: list[Any]) -> str | None:
        """I-EL-BATCH-ID-1: UUID4 for multi-event calls, None for single."""
        return str(uuid.uuid4()) if len(events) > 1 else None

    def check_optimistic_lock(self, current_max: int | None, expected_head: int | None) -> None:
        """I-OPTLOCK-1: raise StaleStateError if current_max != expected_head.

        Both None → skip check (initial empty log or lock not required).
        """
        if expected_head is not None and current_max != expected_head:
            from sdd.infra.event_log import StaleStateError
            raise StaleStateError(
                f"Optimistic lock failed: expected head={expected_head}, "
                f"current max={current_max}"
            )

    def filter_duplicates(
        self,
        events: list[dict],
        existing_pairs: set[tuple[str, int]],
    ) -> tuple[list[dict], list[dict]]:
        """I-IDEM-SCHEMA-1: split events into (new, duplicate) lists.

        existing_pairs: set of (command_id, event_index) already in event_log.
        Returns (to_insert, skipped).
        """
        to_insert = []
        skipped = []
        for event in events:
            key = (event.get("command_id"), event.get("event_index", 0))
            if key[0] is not None and key in existing_pairs:
                skipped.append(event)
            else:
                to_insert.append(event)
        return to_insert, skipped
```

**`PostgresEventLog.append()` после BC-46-A (паттерн делегирования):**

```python
_kernel = EventLogKernel()

def append(self, events, command_id, expected_head, ...):
    batch_id = _kernel.resolve_batch_id(events)

    with self._conn() as conn:
        current_max = conn.execute(
            "SELECT MAX(sequence_id) FROM event_log"
        ).fetchone()[0]
        _kernel.check_optimistic_lock(current_max, expected_head)

        existing = self._fetch_existing_pairs(conn, command_id)
        to_insert, skipped = _kernel.filter_duplicates(events_with_ids, existing)

        if not to_insert:
            logger.info("All %d events are duplicates, skipping insert", len(skipped))
            return []

        seq_ids = self._insert_events(conn, to_insert, batch_id)
        conn.commit()
        return seq_ids
```

**Pre:**
- `PostgresEventLog.append()` существует в `event_log.py`
- Все тесты зелёные перед рефактором

**Post:**
- `src/sdd/infra/el_kernel.py` существует с тремя методами
- `PostgresEventLog.append()` вызывает `_kernel.resolve_batch_id`, `_kernel.check_optimistic_lock`, `_kernel.filter_duplicates`
- `pytest` PASS (поведение идентично до и после)
- `python3 -c "from sdd.infra.el_kernel import EventLogKernel; print('OK')"` → OK

**Примечание:** enforcement-тест на отсутствие `import psycopg` в `el_kernel.py` — Phase 47 (BC-47-A).
BC-46-A не требует CI-grep; достаточно code review + unit-тестов метода.

---

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
@pytest.fixture(scope="session")
def _require_sdd_database_url():
    """Fail-fast guard: skip PG tests if SDD_DATABASE_URL not set.

    FakeEventLog unit tests work without PG — only PG fixtures call this.
    """
    url = os.environ.get("SDD_DATABASE_URL")
    if not url:
        pytest.skip("SDD_DATABASE_URL not set — skipping PG integration tests")
    return url


@pytest.fixture
def pg_test_db(_require_sdd_database_url):
    """Temporary PostgreSQL schema for isolated test.

    Creates schema test_<uuid>, applies DDL, yields connection URL.
    Drops schema in teardown.
    """
    import uuid
    schema = f"test_{uuid.uuid4().hex[:8]}"
    base_url = _require_sdd_database_url
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
Unit-тесты с `FakeEventLog` (не открывают БД) — продолжают работать без PG (пропускают PG-фикстуры через `_require_sdd_database_url`).

### BC-46-F: pyproject.toml — подтверждение

**По данным плана:** `duckdb` уже удалён в T-4311.

Верификация:

```bash
grep "duckdb" pyproject.toml
# ожидаемый результат: пусто
```

Если `duckdb` обнаружен → удалить из `[project.dependencies]`.

### BC-46-H: invalidate_event.py — миграция на PG

**Файл:** `src/sdd/commands/invalidate_event.py`

**Мотивация:** команда `sdd invalidate-event` использует DuckDB SQL-синтаксис:
таблицу `events` (DuckDB schema) вместо `event_log` (PG schema), placeholder `?`
вместо `%s`. После BC-46-B эти вызовы сломаются. Миграция на PG обязательна **перед** BC-46-B.

После BC-46-H команда `sdd invalidate-event` позволит инвалидировать TestEvent-записи
в production DB (seq 25886–25893, загрязнение от 2026-04-25).

**Изменения:**

```python
# invalidate_event.py — заменить DuckDB-запросы на PG

EVENT_LOG_TABLE = "event_log"  # константа вместо строкового литерала

# Было (DuckDB):
conn = open_sdd_connection(self._db_path)
row = conn.execute(
    "SELECT event_type FROM events WHERE seq = ?", [_cmd.target_seq]
).fetchone()
existing = conn.execute(
    "SELECT 1 FROM events WHERE event_type = 'EventInvalidated' "
    "AND CAST(payload->>'target_seq' AS INTEGER) = ?",
    [_cmd.target_seq],
).fetchone()

# Стало (PG):
# I-DB-ENTRY-1: только open_sdd_connection(), не psycopg.connect() напрямую
conn = open_sdd_connection(event_store_url())
row = conn.execute(
    f"SELECT event_type FROM {EVENT_LOG_TABLE} WHERE sequence_id = %s", [_cmd.target_seq]
).fetchone()
existing = conn.execute(
    f"SELECT 1 FROM {EVENT_LOG_TABLE} WHERE event_type = 'EventInvalidated' "
    "AND (payload->>'target_seq')::INTEGER = %s",
    [_cmd.target_seq],
).fetchone()
```

**--force guard (production safety):**

`sdd invalidate-event` — необратимая операция. Без флага `--force` при подключении
к production store команда MUST завершиться с ошибкой:

```python
if is_production_event_store(event_store_url()) and not _cmd.force:
    raise ValueError(
        "invalidate-event targets production event store. "
        "Pass --force to confirm. This action is irreversible."
    )
```

**Инвариант I-INVALIDATE-PG-1:** `invalidate_event.py` MUST использовать таблицу `EVENT_LOG_TABLE`,
`%s` placeholders и `open_sdd_connection(event_store_url())`.
Использование строки `"events"`, placeholder `?`, `event_store_file()`, `psycopg.connect()` →
нарушение.

**Pre:**
- `SDD_DATABASE_URL` установлен
- BC-46-H MUST выполниться **до BC-46-B**

**Post:**
- `sdd invalidate-event --seq N --force` работает против PG `event_log`
- `sdd invalidate-event --seq N` без `--force` на production → `ValueError`
- DuckDB SQL-синтаксис полностью удалён из `invalidate_event.py`

---

### BC-46-I: Reducer — DEBUG для инвалидированных событий (deferrable)

**Файл:** `src/sdd/domain/state/` (reducer) или `src/sdd/infra/projections.py`

**Статус:** не блокирует удаление DuckDB. Выполняется последним в фазе; при нехватке
времени — переносится в Phase 47 как первый task.

**Мотивация:** при replay 27k+ событий reducer может логировать WARNING на повторные
`PhaseCompleted` (seq 27161, 27197, 27239, 27300, 27328). По I-PHASE-LIFECYCLE-2 они
обрабатываются idempotently, но WARNING-шум засоряет логи.

**Перед реализацией:** найти конкретные места WARNING в codebase (`grep -n "logger.warning"
src/sdd/`). Если WARNING для инвалидированных seq уже отсутствует (projections.py:217
уже делает `continue` без лога) — BC-46-I закрыть как N/A.

**Изменение Phase 46:** перед emit WARNING в reducer проверить `seq ∈ _invalidated_seqs`.
Если событие инвалидировано → уровень лога понизить до DEBUG (консервативно; Phase 47 поднимет до INFO).

```python
# Паттерн (в месте WARNING в reducer):
if seq in invalidated_seqs:
    logger.debug("Skipping invalidated event seq=%d type=%s", seq, event_type)
else:
    logger.warning("Unexpected duplicate %s at seq=%d", event_type, seq)
```

**Логика уровней:** DEBUG в Phase 46 — пока операторы знакомятся с семантикой invalidated events.
Phase 47 (BC-47-B) поднимет до INFO — когда invalidation стабильно и нужна audit-trail.

**Применимость:** только reducer-WARNING, которые срабатывают для seq ∈ invalidated_seqs.
Неинвалидированные WARNING-события MUST остаться на уровне WARNING.

**Pre:**
- `_get_invalidated_seqs()` доступен в контексте reducer (через ProjectionContext или параметром)

**Post:**
- Replay 27k событий без WARNING-шума для инвалидированных seq
- Неинвалидированные WARNING-события по-прежнему логируются на WARNING

---

### BC-46-J: SessionDeclared idempotent dedup

**Файл:** `src/sdd/commands/record_session.py`

**Мотивация:** каждый вызов `sdd record-session` генерирует свежий `uuid.uuid4()`
как `command_id` → EventLog.append() не может дедуплицировать → каждая сессия создаёт
новый `SessionDeclared` даже с теми же параметрами. Event log засорён дублями.

**Решение — стабильный command_id + существующая idempotency EventLog:**

`PostgresEventLog.append()` уже реализует дедупликацию по `(command_id, event_index)`
через I-IDEM-SCHEMA-1. Достаточно передавать детерминированный `command_id` вместо `uuid4()`.
Никакого дополнительного `exists_command()` check на уровне CLI не требуется.

```python
# record_session.py — заменить uuid4() на stable command_id
import hashlib
import datetime


def _stable_session_command_id(session_type: str, phase_id: int) -> str:
    """Deterministic command_id: same (session_type, phase_id, UTC date) → same ID.

    Uses UTC date to avoid timezone-dependent midnight boundary issues.
    EventLog.append() deduplicates automatically via I-IDEM-SCHEMA-1.
    """
    today_utc = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    key = f"{session_type}:{phase_id}:{today_utc}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


# При формировании команды:
command_id = _stable_session_command_id(session_type, phase_id)
# Передаётся в execute_and_project → EventLog.append(command_id=command_id)
# Повторный вызов с теми же параметрами → EventLog пропускает дубль автоматически
```

**Поведение:**
- Первый вызов `sdd record-session --type IMPLEMENT --phase 46` в UTC-день → `SessionDeclared` записывается
- Повторный вызов с теми же параметрами → EventLog видит `(command_id, 0)` уже в индексе → silently skip
- Новый UTC-день → новый `command_id` → новый `SessionDeclared`

**Инвариант I-SESSION-DEDUP-1:** `sdd record-session` MUST NOT emit `SessionDeclared`
если event с `command_id == _stable_session_command_id(session_type, phase_id)` уже присутствует
в event_log. Дедупликация делегируется EventLog-level idempotency (I-IDEM-SCHEMA-1).

**Pre:**
- `PostgresEventLog` поддерживает idempotency по `command_id` (I-IDEM-SCHEMA-1 — уже реализован)

**Post:**
- Повторный `sdd record-session` с теми же параметрами в тот же UTC-день → нет новых событий
- `sdd query-events --type SessionDeclared --limit 5` → нет дублей за сегодня

---

### BC-46-G: Enforcement тесты I-NO-DUCKDB-1 + I-DB-ENTRY-1

Новые тесты в `tests/unit/infra/test_paths.py`:

```python
def test_no_duckdb_imports_in_src():
    """I-NO-DUCKDB-1: DuckDB fully removed from src/sdd/.

    Intentionally strict: catches any 'duckdb' mention — imports, strings, comments.
    If a legitimate exception exists (e.g. DeprecationWarning message), add it to allowlist.
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "duckdb", "src/sdd/", "--include=*.py"],
        capture_output=True, text=True
    )
    # Allow only the DeprecationWarning message in paths.py (legacy callers)
    lines = [l for l in result.stdout.splitlines()
             if "DeprecationWarning" not in l and "event_store_file" not in l]
    assert not lines, (
        f"I-NO-DUCKDB-1 violated. DuckDB references found:\n" + "\n".join(lines)
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


def test_no_direct_psycopg_connect_in_src():
    """I-DB-ENTRY-1: all DB access via open_sdd_connection(), not psycopg.connect() directly."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", r"psycopg\.connect(", "src/sdd/", "--include=*.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-DB-ENTRY-1 violated. Direct psycopg.connect() calls found:\n{result.stdout}"
    )


def test_invalidate_event_uses_pg_syntax():
    """I-INVALIDATE-PG-1: invalidate_event.py uses event_log table, %s placeholders, open_sdd_connection."""
    import subprocess
    violations = subprocess.run(
        ["grep", "-n", r'event_store_file\|"events"\|= ?', "src/sdd/commands/invalidate_event.py"],
        capture_output=True, text=True
    )
    assert violations.stdout == "", (
        f"I-INVALIDATE-PG-1 violated:\n{violations.stdout}"
    )
```

---

## 4. Domain Events

Phase 46 не вводит новых domain events.

---

## 5. Types & Interfaces

```python
# src/sdd/infra/db.py — упрощённая после BC-46-B

def open_sdd_connection(db_url: str) -> psycopg.Connection:
    """PG-only. Raises ValueError for non-PG URLs (DuckDB removed).

    I-DB-ENTRY-1: единственный разрешённый entry point для SQL-доступа в src/sdd/.
    Прямой psycopg.connect() запрещён везде в production-коде.
    """
    ...

# Удалены: DuckDBLockTimeoutError, _restart_sequence()
```

```python
# src/sdd/infra/paths.py — event_store_file() deprecated

def event_store_file() -> Path:
    """Deprecated since Phase 46. Emits DeprecationWarning. Will raise RuntimeError in Phase 47.

    Retained only for legacy callers: show_path.py, migration scripts.
    Known callers tracked for Phase 47 removal.
    """
    ...

# event_store_url() — без изменений (Phase 45)
# is_production_event_store() — без изменений (Phase 45)
```

```python
# src/sdd/commands/invalidate_event.py — BC-46-H

EVENT_LOG_TABLE = "event_log"  # константа, не строковый литерал

# Изменение: open_sdd_connection(event_store_url()) + event_log таблица + %s placeholders
# Убраны: таблица events, placeholder ?, event_store_file(), прямой psycopg.connect()
# Добавлен: --force guard для production event store
```

```python
# src/sdd/commands/record_session.py — BC-46-J

def _stable_session_command_id(session_type: str, phase_id: int) -> str:
    """Deterministic command_id: same (session_type, phase_id, UTC date) → same ID.

    I-SESSION-DEDUP-1: dedup delegated to EventLog.append() via I-IDEM-SCHEMA-1.
    """
    ...
```

---

## 6. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-NO-DUCKDB-1 | DuckDB полностью удалён из `src/sdd/` и зависимостей; любое упоминание `duckdb` в src/sdd/ (кроме DeprecationWarning строки в `paths.py`) — нарушение; enforcement: grep CI-тест (BC-46-G) | 46 |
| I-DB-ENTRY-1 | Весь SQL-доступ в `src/sdd/` MUST проходить через `open_sdd_connection()`; прямой `psycopg.connect()` запрещён; enforcement: grep CI-тест (BC-46-G) | 46 |
| I-MIGRATION-1 | `replay(DuckDB_events) == replay(event_log_PG)` для одинакового набора событий; верификация выполнена до BC-46-B | 46 (pre) |
| I-INVALIDATE-PG-1 | `invalidate_event.py` MUST использовать константу `EVENT_LOG_TABLE`, placeholder `%s` и `open_sdd_connection(event_store_url())`; использование строки `"events"`, `?`, `event_store_file()`, `psycopg.connect()` — нарушение; enforcement: grep тест | 46 |
| I-SESSION-DEDUP-1 | `sdd record-session` MUST NOT emit `SessionDeclared` если event с `command_id == _stable_session_command_id(session_type, phase_id)` уже есть в event_log; дедупликация по UTC-дате; механизм — EventLog-level idempotency (I-IDEM-SCHEMA-1) | 46 |
| I-EL-KERNEL-WIRED-1 | `el_kernel.py` существует; `PostgresEventLog.append()` делегирует в `_kernel.resolve_batch_id`, `_kernel.check_optimistic_lock`, `_kernel.filter_duplicates`; enforcement: unit-тесты BC-46-A (Phase 47 добавит grep-тест на отсутствие psycopg) | 46 |

### Обновлённые инварианты

| ID | Обновление |
|----|-----------|
| I-DB-1 | `open_sdd_connection(db_url)` принимает только PG URL; non-PG → `ValueError` (DuckDB removed) |
| I-DB-TEST-1 | Tests MUST NOT open production event store; `is_production_event_store(db_url)` — единственный guard; DuckDB fixture comparison удалён |
| I-LAZY-DUCK-1 | Утрачивает силу: `import duckdb` полностью удалён из src/sdd/ (I-NO-DUCKDB-1) |

### Инварианты Phase 47 (требуют завершения BC-46-A как базы)

| ID | Statement | Phase |
|----|-----------|-------|
| I-EL-KERNEL-1 | `el_kernel.py` не содержит `import psycopg` и SQL; `PostgresEventLog` — pure SQL-адаптер; enforcement: grep CI-тест (Phase 47 BC-47-A) | 47 |
| I-INVALIDATED-LOG-1 | Reducer MUST log INFO (не WARNING, не DEBUG) для seq ∈ invalidated_seqs; Phase 47 поднимает с DEBUG (Phase 46) до INFO | 47 |

---

## 7. Pre/Post Conditions

### BC-46-B + BC-46-C: удаление DuckDB кода

**Pre:**
- BC-46-H выполнен (invalidate_event.py мигрирован)
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

### BC-46-H: invalidate_event.py PG migration

**Pre:**
- `SDD_DATABASE_URL` установлен
- BC-46-H MUST выполниться **до BC-46-B** (иначе команда сломается при удалении DuckDB-ветки)
- BC-46-H MUST выполниться **до BC-46-B** (иначе команда сломается при удалении DuckDB-ветки)

**Post:**
- `sdd invalidate-event --seq N` работает против `event_log` таблицы в PG
- `sdd invalidate-event --seq N --force` работает против PG `event_log`
- `sdd invalidate-event --seq N` без `--force` на production → `ValueError`
- `grep "events WHERE seq\|event_store_file\|psycopg\.connect" src/sdd/commands/invalidate_event.py` → пусто
- I-INVALIDATE-PG-1 PASS, I-DB-ENTRY-1 PASS

### BC-46-A: el_kernel.py minimal extraction

**Pre:**
- `PostgresEventLog.append()` существует с inline idempotency/lock/batch логикой
- Все тесты зелёные перед рефактором

**Post:**
- `src/sdd/infra/el_kernel.py` существует; `EventLogKernel` с тремя методами
- `PostgresEventLog.append()` делегирует в `_kernel.*`
- `pytest` PASS (поведение идентично)
- I-EL-KERNEL-WIRED-1 PASS

### BC-46-I: Reducer suppress DEBUG

**Pre:**
- `_get_invalidated_seqs()` доступен в контексте reducer

**Post:**
- `replay()` при наличии инвалидированных дубликатов → нет WARNING для них (только DEBUG)
- Неинвалидированные дублированные события → по-прежнему WARNING
- Phase 47 BC-47-B поднимет уровень с DEBUG до INFO

### BC-46-J: SessionDeclared dedup

**Pre:**
- `PostgresEventLog` поддерживает idempotency по `command_id` (I-IDEM-SCHEMA-1 — уже реализован)
- `SDD_DATABASE_URL` установлен

**Post:**
- Повторный `sdd record-session --type T --phase N` в тот же UTC-день → нет новых событий
- Первый вызов нового UTC-дня → `SessionDeclared` записывается
- I-SESSION-DEDUP-1 PASS

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

### UC-46-4: Инвалидация TestEvent из production DB

**Pre:** Phase 46 завершена; `SDD_DATABASE_URL` установлен; TestEvent seq 25886–25893 в event_log  
**Steps:**
1. `sdd invalidate-event --seq 25886 --force`
2. `invalidate_event.py` → `open_sdd_connection(event_store_url())` → PG connection
3. `is_production_event_store()` → True; `--force` присутствует → продолжаем
4. `conn.execute("SELECT event_type FROM event_log WHERE sequence_id = %s", [25886])`
5. Проверка: event_type == "TestEvent", не инвалидировано ранее
6. Emit `EventInvalidated(target_seq=25886)` → append в event_log
7. Повторить для seq 25887–25893
**Post:** TestEvent-записи помечены инвалидированными; replay их пропускает

### UC-46-4b: Попытка инвалидации без --force на production

**Pre:** `SDD_DATABASE_URL` указывает на production event store  
**Steps:**
1. `sdd invalidate-event --seq 25886` (без --force)
2. `is_production_event_store()` → True; `--force` отсутствует
3. `ValueError("invalidate-event targets production event store. Pass --force to confirm.")`
**Post:** операция отклонена без изменений в event_log

### UC-46-5: Повторный sdd record-session в тот же UTC-день

**Pre:** `sdd record-session --type IMPLEMENT --phase 46` уже запущен сегодня (UTC)  
**Steps:**
1. `record_session.py` вызывает `_stable_session_command_id("IMPLEMENT", 46)` → deterministic hash
2. `execute_and_project` передаёт `command_id=stable_id` в `PostgresEventLog.append()`
3. `EventLog.append()`: `(command_id, event_index=0)` уже в индексе → silently skip (I-IDEM-SCHEMA-1)
4. Никакого нового события в event_log
**Post:** нет нового `SessionDeclared` в event_log; event log не засоряется

---

## 9. Integration

### Порядок применения BC (строгий)

```
Предусловия P-1, P-2, P-3 → верифицированы
  ↓
BC-46-H: invalidate_event.py → PG + --force guard   ← ОБЯЗАТЕЛЬНО ПЕРВЫМ (деструктивный предохранитель)
BC-46-J: SessionDeclared dedup (stable command_id)    (параллельно с BC-46-H)
BC-46-A: el_kernel.py minimal extraction              (параллельно или после BC-46-H; НЕ до BC-46-H)
  ↓
  pytest PASS (DuckDB-код ещё существует, но invalidate_event на PG; kernel создан)
  ↓
BC-46-B: infra/db.py удаление DuckDB-ветки
BC-46-C: db/connection.py удаление DuckDB-ветки    (параллельно с BC-46-B)
BC-46-D: paths.py DeprecationWarning               (параллельно)
BC-46-E: PG тест-фикстуры + fail-fast guard        (параллельно)
  ↓
BC-46-F: pyproject.toml верификация
BC-46-I: reducer DEBUG для инвалидированных событий  (deferrable — если время позволяет)
BC-46-G: enforcement тесты I-NO-DUCKDB-1 + I-DB-ENTRY-1  (последним)
  ↓
  pytest (все) PASS
```

**BC-46-H MUST применяться первым среди деструктивных шагов.** После удаления DuckDB-ветки
в `db.py` вызов `open_sdd_connection(duckdb_path)` поднимает `ValueError` — `invalidate_event.py`
сломается до миграции.

**BC-46-A — параллельно с BC-46-H, но не первым.** Kernel extraction — рефактор,
не деструктивное изменение. Если extraction упадёт, `PostgresEventLog` продолжает
работать (без делегирования), DuckDB-код ещё не тронут. Нельзя ставить BC-46-A первым,
чтобы не добавлять риск до верификации BC-46-H.

**BC-46-I — deferrable.** Не блокирует удаление DuckDB. При нехватке времени — переносится
в Phase 47 первым task'ом (там поднимется с DEBUG до INFO как BC-47-B).

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
| 1 | `test_no_duckdb_imports_in_src` — grep src/sdd/ с allowlist для DeprecationWarning строки → пусто | I-NO-DUCKDB-1 |
| 2 | `test_duckdb_not_in_dependencies` — grep pyproject.toml → пусто | I-NO-DUCKDB-1 |
| 3 | `test_no_direct_psycopg_connect_in_src` — grep `psycopg.connect(` в src/sdd/ → пусто | I-DB-ENTRY-1 |
| 4 | `test_invalidate_event_uses_pg_syntax` — grep invalidate_event.py → no `events`, `?`, `event_store_file`, `psycopg.connect` | I-INVALIDATE-PG-1 |
| 5 | `test_open_sdd_connection_rejects_duckdb_path` — передать `.duckdb` path → ValueError | I-NO-DUCKDB-1, I-DB-1 |
| 6 | `test_event_store_file_emits_deprecation_warning` — вызов → DeprecationWarning | BC-46-D |
| 7 | `test_pg_test_db_fixture_isolated` — два теста с `pg_test_db` → разные схемы | BC-46-E |
| 8 | `test_migration_replay_parity` — `replay(DuckDB) == replay(PG)` (pytest -m migration) | I-MIGRATION-1 |
| 9 | `test_invalidate_event_rejects_production_without_force` — вызов без `--force` на production → ValueError | BC-46-H |
| 10 | `test_session_dedup_same_utc_day` — повторный record-session с теми же params → EventLog idempotency → нет нового события | I-SESSION-DEDUP-1 |
| 11 | `test_session_dedup_different_utc_day` — stable_id с другой UTC-датой → новый event создаётся | I-SESSION-DEDUP-1 |
| 12 | `test_stable_command_id_uses_utc` — `_stable_session_command_id` с явным UTC-datetime → стабильный hash | BC-46-J |
| 13 | `test_reducer_debug_for_invalidated_seq` — replay с инвалидированным дублем → WARNING не emit, только DEBUG (deferrable; Phase 47 изменит на INFO) | BC-46-I |
| 14 | `test_el_kernel_resolve_batch_id` — `EventLogKernel.resolve_batch_id([e1,e2])` → UUID4; `([e1])` → None | I-EL-KERNEL-WIRED-1 |
| 15 | `test_el_kernel_check_optimistic_lock` — current==expected → OK; current≠expected → StaleStateError | I-EL-KERNEL-WIRED-1 |
| 16 | `test_el_kernel_filter_duplicates` — известная пара → skipped; новая → to_insert | I-EL-KERNEL-WIRED-1 |

### Integration Tests (PG)

| # | Test | Invariant(s) |
|---|------|--------------|
| 17 | `test_pg_full_pipeline_no_duckdb` — execute_and_project → event_log → p_* → YAML; нет упоминаний DuckDB в стеке | I-NO-DUCKDB-1 |
| 18 | `test_pg_rebuild_state_from_scratch` — TRUNCATE p_* → full replay → I-REPLAY-1 PASS | I-REPLAY-1, I-REBUILD-ATOMIC-1 |
| 19 | `test_invalidate_event_pg_roundtrip` — `sdd invalidate-event --seq N --force` на тестовой схеме → EventInvalidated в event_log → replay пропускает seq N | I-INVALIDATE-PG-1 |

### Final Smoke

```bash
# 1. Нет duckdb в src/sdd/ (кроме DeprecationWarning строки в paths.py)
grep -rn "duckdb" src/sdd/ --include="*.py" | grep -v "DeprecationWarning\|event_store_file"
# ожидаемый результат: пусто

# 2. Нет duckdb в зависимостях
grep "duckdb" pyproject.toml
# ожидаемый результат: пусто

# 3. Нет прямых psycopg.connect() в src/sdd/ (I-DB-ENTRY-1)
grep -rn "psycopg\.connect(" src/sdd/ --include="*.py"
# ожидаемый результат: пусто

# 4. invalidate_event использует PG-синтаксис (I-INVALIDATE-PG-1)
grep -n 'event_store_file\|"events"\|'"'"'events'"'"'\|= ?\|psycopg\.connect' src/sdd/commands/invalidate_event.py
# ожидаемый результат: пусто

# 5. SessionDeclared dedup работает (I-SESSION-DEDUP-1)
SDD_DATABASE_URL=... sdd record-session --type IMPLEMENT --phase 46
SDD_DATABASE_URL=... sdd record-session --type IMPLEMENT --phase 46
# второй вызов: EventLog idempotency → нет нового SessionDeclared

# 6. Все тесты
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest --cov=sdd

# 7. sdd show-state работает
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd sdd show-state

# 8. Инвалидация TestEvent (post-phase action) — требует --force
SDD_DATABASE_URL=... sdd invalidate-event --seq 25886 --force
SDD_DATABASE_URL=... sdd invalidate-event --seq 25887 --force
# ... повторить для seq 25888–25893
```

---

## 11. Architectural Debt (Phase 47+)

Phase 46 решает DuckDB-удаление. Следующие issues остаются:

| Issue | Файл | Суть |
|-------|------|------|
| `el_kernel.py` extraction (BC-46-A) | `infra/event_log.py` | Вынести shared transaction/idempotency kernel из `PostgresEventLog` в изоляции; I-EL-KERNEL-1 |
| `event_store_file()` final deletion | `infra/paths.py` | Удалить функцию после удаления callers: `show_path.py`, legacy migration scripts; заменить `DeprecationWarning` на `RuntimeError` |
| Reducer INFO для инвалидированных событий (BC-46-I) | `infra/projections.py` | Если WARNING-шум обнаружен — понизить до INFO; deferrable из Phase 46 |
| PG test fixtures оптимизация | `tests/conftest.py` | Transaction rollback или TRUNCATE вместо CREATE/DROP SCHEMA для ускорения test suite |
| `execute_command` монолит | `commands/registry.py:615–870` | 4 фазы Write Kernel без швов |
| `_sdd_root` глобал (Путь B) | `infra/paths.py` | инвертировать зависимость → чистые функции |
| `GuardContext` overly broad | `domain/guards/context.py` | 7 полей; разбить на минимальные протоколы |
| `sync_projections` инкапсуляция | `infra/projections.py` | `rebuild_state()` + `rebuild_taskset()` раздельно |
| Два пути guard construction | `commands/registry.py` | `_default_build_guards()` vs `guard_factory()` |
| State_index.yaml staleness overhead | `infra/projections.py` | 27k событий → replay latency растёт; рассмотреть incremental projection или p_* direct query |

---

## 12. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `el_kernel.py` extraction (BC-46-A) | Phase 47+ |
| `event_store_file()` final deletion + RuntimeError | Phase 47+ (после удаления callers) |
| `_sdd_root` глобал инвертирование | Phase 47+ |
| `execute_command` монолит рефактор | Phase 47+ |
| `GuardContext` разбивка | Phase 47+ |
| PG test fixtures оптимизация (rollback/TRUNCATE) | Phase 47+ |
| `show_path.py` → PG query вместо YAML | Future |
| State_index.yaml staleness latency fix | Phase 47+ |
| Удаление State_index.yaml (замена на p_* query) | Future (явное решение нужно) |
