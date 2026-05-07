# Spec_v43 — Phase 43: Unified PostgreSQL EventLog

Status: Draft  
Baseline: Spec_v32_PostgresMigration.md · Spec_v42_DockerCIInfrastructure.md  
Architectural analysis: `.claude/plans/encapsulated-launching-shell.md`

---

## 0. Goal

Перевести EventLog (SSOT системы) с DuckDB на PostgreSQL. Устранить зависимость от DuckDB полностью.
Финальная архитектура:

```
Command → validate → INSERT event_log (PG, TX1) → Projector.apply() → UPDATE p_* (PG, TX2) → project_all() → State_index.yaml
```

DuckDB удаляется из зависимостей. Все данные — в Postgres. Rebuild = TRUNCATE p_* → replay(event_log).
State_index.yaml сохраняется как YAML-кеш для CLI (I-1 уже это гарантирует).

---

## 1. Scope

### In-Scope

- BC-43-A: `event_store_url()` + `is_production_event_store()` — единые точки маршрутизации
- BC-43-B: `infra/db.py` — lazy DuckDB import + PG-ветка в `open_sdd_connection`
- BC-43-C: `EventLogKernelProtocol` — абстрактный интерфейс для kernel injection
- BC-43-D: `PostgresEventLog` — PG-реализация EventLog с PostgreSQL DDL и SQL-диалектом
- BC-43-E: `Projector` — применение domain events к `p_*` таблицам
- BC-43-F: Write pipeline — инжекция Projector в `execute_and_project`
- BC-43-G: Удаление DuckDB из `pyproject.toml`; `psycopg[binary]` → mandatory
- BC-43-H: `get_current_state()` PG-ветка — `event_log` + `sequence_id` + JSONB-safe десериализация

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-43-A: URL-aware routing (paths.py)

```
src/sdd/infra/paths.py
  event_store_url()            # единственная точка определения backend
  is_production_event_store()  # единственный guard production DB
```

`event_store_url()` — единственное место, где определяется backend. Все callers, которым
нужен backend-agnostic путь к event store, используют `event_store_url()`.
`event_store_file()` сохраняется без изменений (DuckDB file guard, тесты).

`is_production_event_store(db_path)` — унифицированный guard для обеих баз (DuckDB и PG),
используется вместо inline `Path(db_path).resolve() == event_store_file().resolve()` в 3 местах.

### BC-43-B: Lazy DuckDB import (infra/db.py)

```
src/sdd/infra/db.py
  open_sdd_connection()   # PG-routing добавлен; import duckdb → lazy (внутри DuckDB-ветки)
```

После удаления DuckDB (`pyproject.toml`) модуль не ломается при импорте.
PG URL → делегирует в `sdd.db.connection.open_db_connection`.

### BC-43-C: EventLogKernelProtocol (infra/event_log.py)

```
src/sdd/infra/event_log.py
  EventLogKernelProtocol   # Protocol: max_seq + append (покрывает 7 мест в kernel)
```

Минимальный интерфейс для `execute_command` и `execute_and_project`.
`EventLog` и `PostgresEventLog` реализуют его структурно (без explicit `implements`).
Handlers используют `EventLog(db_path)` напрямую — за пределами scope этого Protocol.

### BC-43-D: PostgresEventLog (infra/event_log.py)

```
src/sdd/infra/event_log.py
  class PostgresEventLog     # PG-реализация: таблица event_log, JSONB, BIGSERIAL
```

PostgreSQL DDL:
```sql
CREATE TABLE IF NOT EXISTS event_log (
    event_id     UUID          PRIMARY KEY,
    event_type   TEXT          NOT NULL,
    payload      JSONB         NOT NULL,
    metadata     JSONB         DEFAULT '{}',
    created_at   TIMESTAMPTZ   DEFAULT now(),
    sequence_id  BIGSERIAL     UNIQUE,
    level        TEXT          DEFAULT NULL,
    event_source TEXT          NOT NULL DEFAULT 'runtime',
    caused_by_meta_seq BIGINT  DEFAULT NULL,
    expired      BOOLEAN       NOT NULL DEFAULT FALSE,
    batch_id     UUID          DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_el_event_type
    ON event_log (event_type);

CREATE UNIQUE INDEX IF NOT EXISTS idx_el_cmd_idx
    ON event_log ((payload->>'command_id'), (payload->>'event_index'))
    WHERE payload->>'command_id' IS NOT NULL;

CREATE TABLE IF NOT EXISTS p_meta (
    singleton        BOOLEAN       PRIMARY KEY DEFAULT TRUE,
    last_applied_sequence_id BIGINT NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ   DEFAULT now(),
    CONSTRAINT p_meta_singleton CHECK (singleton = TRUE)
);
INSERT INTO p_meta DEFAULT VALUES ON CONFLICT DO NOTHING;
```

`p_meta` — единая строка-синглтон (I-PROJ-VERSION-1). Обновляется атомарно
в конце каждого `rebuild()`. Позволяет детектировать stale-проекции:
`p_meta.last_applied_sequence_id < MAX(event_log.sequence_id)` → projections stale.

SQL-диалект: полный переход на PostgreSQL. DuckDB-специфика удаляется:

| DuckDB | PostgreSQL |
|--------|-----------|
| `events` | `event_log` |
| `json_extract_string(payload, '$.x')` | `payload->>'x'` |
| `json_extract(payload, '$.x')` | `payload->'x'` |
| `nextval('sdd_event_seq')` | `DEFAULT` (BIGSERIAL) |
| `payload VARCHAR` (JSON string) | `payload JSONB` |
| `SELECT COALESCE(MAX(seq), 0)` | `SELECT COALESCE(MAX(sequence_id), 0)` |

### BC-43-E: Projector (infra/projector.py)

```
src/sdd/infra/projector.py
  class Projector            # apply(event: DomainEvent) → UPDATE p_* (idempotent)
```

Новый модуль. Применяет каждый domain event к соответствующей `p_*` таблице.
Неизвестные типы событий → NO-OP (I-PROJ-NOOP-1, forward compatibility).

### BC-43-F: Write pipeline (commands/registry.py)

```
src/sdd/commands/registry.py
  execute_command()         # + event_log param (EventLogKernelProtocol | None)
  execute_and_project()     # + Projector injection (_build_projector_if_configured)
  _apply_projector_safe()   # новый: поглощает исключения Projector (I-FAIL-1, I-PROJ-SAFE-1)
  _build_projector_if_configured()  # новый: конструирует Projector из SDD_DATABASE_URL
```

### BC-43-G: Dependencies (pyproject.toml)

```toml
[project]
dependencies = [
    "psycopg[binary]>=3.1",   # обязательная (было optional)
    "PyYAML>=6.0",
    "click>=8.0",
    # "duckdb>=0.10"  ← УДАЛИТЬ
]
```

### BC-43-H: get_current_state() PG-ветка (infra/projections.py)

```
src/sdd/infra/projections.py
  get_current_state()   # PG-ветка: event_log + sequence_id + JSONB-safe десериализация
```

**Pre:**
- `db_path`: PG URL или DuckDB file path
- `open_sdd_connection(db_path)` возвращает соединение соответствующего типа

**Post:**
- PG-ветка: `SELECT` из `event_log`, колонка `sequence_id`
- DuckDB-ветка: `SELECT` из `events`, колонка `seq` (без изменений)
- JSONB-safe: `payload: dict = row_payload if isinstance(row_payload, dict) else json.loads(row_payload or "{}")`
- Результат идентичен при одинаковой истории событий (I-1)

**Изменения:**
- DuckDB SQL (`events` / `seq`) → PG SQL (`event_log` / `sequence_id`) в PG-ветке
- Тип-guard при десериализации payload: psycopg3 автоматически десериализует JSONB → dict; `json.loads(dict)` → `TypeError`; guard обязателен (R-3)
- Определение ветки: `is_postgres_url(db_path)` из BC-43-A

### Dependencies

```text
BC-43-A → (все остальные BC)          : event_store_url() — точка входа
BC-43-B → BC-43-A                     : uses is_postgres_url from db.connection
BC-43-C → BC-43-A                     : execute_command вызывает event_store_url()
BC-43-D → BC-43-A, BC-43-B            : PostgresEventLog opens via open_sdd_connection
BC-43-E → BC-43-D                     : Projector читает из event_log (PG)
BC-43-F → BC-43-C, BC-43-D, BC-43-E  : inject в execute_command + execute_and_project
BC-43-G → все                         : DuckDB удалён, psycopg mandatory (LAST — см. §8)
BC-43-H → BC-43-A, BC-43-B            : использует is_postgres_url() и open_sdd_connection()
```

---

## 3. Domain Events

Phase 43 не вводит новых domain events. Projector подписывается на существующие события
через `event.event_type` dispatch.

### Projector event handlers (dispatch map)

| Event | p_* таблица | Операция |
|-------|-------------|---------|
| `TaskImplemented` | `p_tasks` | `UPDATE SET status='DONE'` |
| `TaskValidated` | `p_tasks` | `UPDATE SET validation_result=...` |
| `PhaseInitialized` | `p_phases` | `INSERT ... ON CONFLICT DO UPDATE` |
| `PhaseStarted` | — | NO-OP (I-PHASE-STARTED-1: informational only; status='ACTIVE' устанавливается через `PhaseInitialized`) |
| `PhaseCompleted` | `p_phases` | `UPDATE SET status='COMPLETE'` |
| `PhaseContextSwitched` | `p_phases` | `UPDATE SET is_current=...` (см. примечание ниже) |
| `SessionDeclared` | `p_sessions` | `INSERT ... ON CONFLICT DO NOTHING` |
| `DecisionRecorded` | `p_decisions` | `INSERT ... ON CONFLICT DO NOTHING` |
| `InvariantRegistered` | `p_invariants` | `INSERT ... ON CONFLICT DO UPDATE` |
| `SpecApproved` | `p_specs` | `INSERT ... ON CONFLICT DO NOTHING` |
| _(все остальные)_ | — | NO-OP (I-PROJ-NOOP-1) |

> **PhaseContextSwitched → p_phases:** двухшаговое обновление обязательно:
> ```sql
> UPDATE p_phases SET is_current = FALSE WHERE is_current = TRUE;
> UPDATE p_phases SET is_current = TRUE WHERE phase_id = <target_phase_id>;
> -- или эквивалентно:
> UPDATE p_phases SET is_current = (phase_id = <target_phase_id>);
> ```
> Инвариант: ровно одна строка `p_phases` имеет `is_current=TRUE` после любого `apply()`.
> Однострочный `UPDATE SET is_current=TRUE` без сброса предыдущего нарушает этот инвариант.

---

## 4. Types & Interfaces

```python
# src/sdd/infra/event_log.py

from typing import Protocol, Literal, runtime_checkable

@runtime_checkable
class EventLogKernelProtocol(Protocol):
    """Minimum interface required by execute_command and execute_and_project.

    Covers all 7 EventLog instantiations in the kernel (6 in execute_command,
    1 in execute_and_project). Handlers outside the kernel use EventLog(db_path)
    directly — this Protocol is NOT for them.
    """
    def max_seq(self) -> int | None: ...
    def append(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: Literal["bootstrap", "test", "metrics"] | None = None,
        batch_id: str | None = None,
    ) -> None: ...


class PostgresEventLog:
    """PG implementation of EventLog.

    Uses event_log table (BIGSERIAL sequence_id, JSONB payload).
    Implements EventLogKernelProtocol + full public EventLog interface.
    """
    def __init__(self, db_url: str) -> None: ...
    def max_seq(self) -> int | None: ...
    def append(self, events, source, command_id=None, expected_head=None,
               allow_outside_kernel=None, batch_id=None) -> None: ...
    def replay(self, after_seq=None, level="L1", source="runtime",
               include_expired=False) -> list[dict]: ...
    def exists_command(self, command_id: str) -> bool: ...
    def exists_semantic(self, command_type, task_id, phase_id, payload_hash) -> bool: ...
    def get_error_count(self, command_id: str) -> int: ...
```

```python
# src/sdd/infra/projector.py

class Projector:
    """Apply domain events to p_* projection tables.

    Idempotent: all handlers use ON CONFLICT DO UPDATE.
    Unknown event types: NO-OP with DEBUG log (I-PROJ-NOOP-1).

    Connection lifecycle: single psycopg connection opened in __init__,
    reused across all apply() calls, closed in close() / __exit__.
    Use as context manager for rebuild (many events); for single events
    _apply_projector_safe() calls close() after the batch.
    """
    def __init__(self, pg_url: str) -> None: ...
    def apply(self, event: DomainEvent) -> None: ...  # reuses self._conn
    def close(self) -> None: ...
    def __enter__(self) -> "Projector": ...
    def __exit__(self, *_: object) -> None: ...
```

```python
# src/sdd/infra/paths.py  — новые функции

def event_store_url() -> str:
    """Single routing point: PG URL if SDD_DATABASE_URL set; else DuckDB file path.

    I-EVENT-STORE-URL-1: this is the ONLY place where event store backend is determined.
    All callers that need backend-agnostic path MUST use this function.
    """
    ...

def is_production_event_store(db_path: str) -> bool:
    """True if db_path refers to the production event store.

    I-PROD-GUARD-1: single guard for both DuckDB (file path) and PG (URL) backends.
    Replaces inline Path.resolve() comparisons in infra/db.py and event_log.py.
    """
    ...
```

```python
# src/sdd/commands/registry.py  — изменения

def execute_command(
    spec: CommandSpec,
    cmd: Any,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
    event_log: EventLogKernelProtocol | None = None,  # инжекция для тестов
) -> list[DomainEvent]: ...

def execute_and_project(
    spec: CommandSpec,
    cmd: Any,
    db_path: str | None = None,
    state_path: str | None = None,
    taskset_path: str | None = None,
    norm_path: str | None = None,
    projector: Projector | None = None,  # инжекция для тестов; None → auto-build
) -> list[DomainEvent]: ...

def _build_projector_if_configured() -> Projector | None:
    """Construct Projector from SDD_DATABASE_URL if set. Returns None for DuckDB."""
    ...

def _apply_projector_safe(projector: Projector, events: list[DomainEvent]) -> None:
    """I-FAIL-1, I-PROJ-SAFE-1: apply Projector; swallow exceptions; emit audit."""
    ...
```

---

## 5. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-EVENT-1 | `event_log` append-only: DELETE и UPDATE строк запрещены (application-level convention, не DB constraint; enforcement через code review; PG trigger/RLS — Phase 44+) | 43 |
| I-EVENT-2 | Строки `event_log` immutable после INSERT (application-level convention; см. I-EVENT-1) | 43 |
| I-ORDER-1 | Порядок событий = `sequence_id` (BIGSERIAL, monotonic, UNIQUE) | 43 |
| I-PROJ-1 | `p_* = f(event_log)`; прямая запись в `p_*` минуя event запрещена | 43 |
| I-REPLAY-1 | `rebuild(event_log) == текущее состояние p_*` в любой момент | 43 |
| I-FAIL-1 | Сбой Projector.apply() НЕ откатывает INSERT event_log (TX1 независим от TX2) | 43 |
| I-EVENT-STORE-URL-1 | `event_store_url()` — единственная точка определения event store backend; прямое чтение `SDD_DATABASE_URL` в callers запрещено | 43 |
| I-PROD-GUARD-1 | `is_production_event_store(db_path)` — единственный guard для идентификации production DB; inline `Path.resolve() == event_store_file().resolve()` запрещены | 43 |
| I-ELK-PROTO-1 | Все 7 инстанциаций EventLog в kernel (execute_command + execute_and_project) MUST использовать инжектированный `EventLogKernelProtocol`; прямой `EventLog(_db)` внутри kernel запрещён | 43 |
| I-PROJ-NOOP-1 | `Projector.apply()` MUST быть NO-OP для неизвестных event_type (forward compatibility); отсутствие handler → DEBUG log, нет исключения | 43 |
| I-PROJ-SAFE-1 | `_apply_projector_safe()` MUST перехватывать все исключения Projector.apply(), логировать WARNING, эмитировать audit event, НЕ re-raise (I-FAIL-1) | 43 |
| I-LAZY-DUCK-1 | `import duckdb` MUST быть lazy (внутри DuckDB-ветки функции); top-level import в `infra/db.py` запрещён с Phase 43 | 43 |
| I-PG-DDL-1 | `event_log` таблица MUST иметь: `event_id UUID PK`, `payload JSONB`, `sequence_id BIGSERIAL UNIQUE`, `(payload->>'command_id', payload->>'event_index') UNIQUE WHERE command_id IS NOT NULL` | 43 |
| I-REBUILD-ATOMIC-1 | `rebuild()` MUST выполнять `TRUNCATE p_* + replay + UPDATE p_meta.last_applied_sequence_id` в одной транзакции; `p_*` видны пустыми только внутри TX и никогда снаружи | 43 |
| I-PROJ-WRITE-1 | `p_*` таблицы MUST изменяться ТОЛЬКО через `Projector.apply()`; прямые INSERT/UPDATE/DELETE в `p_*` из любого другого слоя запрещены (enforcement: code review + grep; DB-level REVOKE — Phase 44+) | 43 |
| I-PROJ-VERSION-1 | `p_meta.last_applied_sequence_id <= MAX(event_log.sequence_id)` в любой момент; при `last_seq < max_seq` проекции stale → CLI MUST эмитировать WARNING и рекомендовать `sdd rebuild-state`; автоматический rebuild — Out of Scope Phase 43 | 43 |
| I-TABLE-SEP-1 | `event_log` и `p_*` таблицы MUST NOT смешиваться в одном SQL-запросе (JOIN, subquery); Projector читает `event_log` только через `PostgresEventLog.replay()`; p_*-handlers работают только с p_*-таблицами | 43 |
| I-LAYER-1 | Строгое разделение слоёв: Layer 1 `event_log` (SSOT, append-only) → Layer 2 `p_*` (projection cache, rebuildable) → Layer 3 YAML/CLI (read interface); запись возможна только в направлении L1→L2→L3; L2 и L3 НЕ являются источником истины | 43 |
| I-EVENT-PURE-1 | PostgreSQL = storage only; бизнес-логика реализуется исключительно в Python; DB-side triggers с бизнес-логикой, stored procedures, implicit mutations через DB constraints запрещены | 43 |
| I-MIGRATION-1 | `replay(DuckDB_events) == replay(event_log_PG)` для одинакового набора событий; верификация обязательна перед применением BC-43-G | 43 |

### Обновлённые инварианты

| ID | Обновление |
|----|-----------|
| I-DB-1 | `open_sdd_connection(db_url)` — `db_url` MUST быть explicit non-empty str; DuckDB-ветка удалена после Phase 43 |
| I-DB-TEST-1 | Tests MUST NOT open production event store; проверка через `is_production_event_store(db_path)` (было: `Path.resolve() == event_store_file().resolve()`) |

### Сохраняемые инварианты (referenced)

| ID | Statement |
|----|-----------|
| I-1 | All SDD state = reduce(events); State_index.yaml — readonly snapshot, never truth source |
| I-DB-TEST-2 | В test context (`PYTEST_CURRENT_TEST`): `timeout_secs = 0.0` (fail-fast) |
| I-OPTLOCK-1 | Optimistic lock check: `MAX(sequence_id) == expected_head` inside transaction |
| I-IDEM-SCHEMA-1 | Idempotency dedup via `(command_id, event_index)` UNIQUE constraint |
| I-EL-NON-KERNEL-1 | `sdd_append_batch` MUST NOT be called inside `execute_command` |
| I-KERNEL-WRITE-1 | Production event store writes only via `execute_command` |

---

## 6. Pre/Post Conditions

### BC-43-A: event_store_url()

**Pre:**
- `SDD_DATABASE_URL` либо установлен (PG) либо нет (DuckDB fallback)

**Post:**
- Если `SDD_DATABASE_URL` → PG URL → `is_postgres_url(result) == True`
- Иначе → `str(get_sdd_root() / "state" / "sdd_events.duckdb")`
- Детерминировано: одинаковые env → одинаковый result

### BC-43-B: open_sdd_connection() после PG-routing

**Pre:**
- `db_path` non-empty str (I-DB-1)

**Post:**
- `is_postgres_url(db_path)` → psycopg connection через `open_db_connection`
- иначе → DuckDB connection (без top-level import failure, I-LAZY-DUCK-1)
- В обоих случаях: одинаковый duck-typed interface для callers

### BC-43-D: PostgresEventLog.append()

**Pre:**
- `events` non-empty list[DomainEvent]
- `expected_head` соответствует текущему `MAX(sequence_id)` (I-OPTLOCK-1)

**Post:**
- Все события вставлены в `event_log` одной транзакцией (I-EVENT-1)
- Дубликаты `(command_id, event_index)` → skip via UNIQUE constraint (I-IDEM-SCHEMA-1)
- `MAX(sequence_id)` увеличился на количество вставленных строк (I-ORDER-1)
- При `current_max != expected_head` → rollback + `StaleStateError` (I-OPTLOCK-1)

### BC-43-E: Projector.apply()

**Pre:**
- `event` — один DomainEvent из `handler_events`
- PG connection открыт и валиден

**Post:**
- Если `event.event_type` в `_HANDLERS` → соответствующая `p_*` таблица обновлена (ON CONFLICT DO UPDATE)
- Если `event.event_type` не в `_HANDLERS` → NO-OP + DEBUG log (I-PROJ-NOOP-1)
- `p_* = f(event_log)` выполняется (I-PROJ-1)
- Исключение из Projector НЕ откатывает event_log INSERT (I-FAIL-1) — отвечает `_apply_projector_safe`

### BC-43-F: execute_and_project() порядок

**Pre:**
- `execute_command` вернул `handler_events` (TX1 committed)

**Post:**  
Строгий порядок:
```
1. TX1 committed (event_log INSERT) ← execute_command
2. _apply_projector_safe(projector, handler_events)  # TX2: p_* (I-FAIL-1)
3. project_all(spec.projection, ...)                 # YAML rebuild
```
Сбой на шаге 2 → логируется, не пробрасывается; state_index.yaml обновляется на шаге 3.  
Сбой на шаге 3 → audit event, `ProjectionError` пробрасывается (recovery: `sdd sync-state`).

### Rebuild

**Pre:**
- `event_log` содержит полную историю событий

**Post:**
- `BEGIN` транзакция
- `TRUNCATE p_tasks, p_phases, p_invariants, p_sessions` (и др.) — внутри TX
- `SELECT * FROM event_log ORDER BY sequence_id` — внутри TX
- `Projector.apply(event)` для каждой строки — внутри TX
- `UPDATE p_meta SET last_applied_sequence_id = MAX(sequence_id), updated_at = now()` — внутри TX
- `COMMIT`
- `rebuild(event_log) == current state p_*` (I-REPLAY-1, I-REBUILD-ATOMIC-1)
- `p_meta.last_applied_sequence_id == MAX(event_log.sequence_id)` после COMMIT (I-PROJ-VERSION-1)

> `p_*` таблицы видны пустыми только внутри транзакции. Читатели снаружи TX
> видят либо старое состояние, либо новое — read gap исключён (I-REBUILD-ATOMIC-1).

---

## 7. Use Cases

### UC-43-1: Стандартное выполнение команды с PG EventLog

**Actor:** LLM (CLI)  
**Trigger:** `sdd complete T-4301`  
**Pre:** `SDD_DATABASE_URL` установлен; `event_log` таблица существует; Phase 43 ACTIVE  
**Steps:**
1. CLI вызывает `execute_and_project(spec, cmd)`
2. `execute_command` строит GuardContext из EventLog replay (PG)
3. Guard pipeline → ALLOW
4. Handler возвращает `[TaskImplementedEvent]`
5. `PostgresEventLog.append([TaskImplementedEvent], expected_head=N)` → INSERT в event_log (TX1)
6. `_build_projector_if_configured()` → `Projector(pg_url)`
7. `_apply_projector_safe(projector, [TaskImplementedEvent])`:
   - `projector.apply(TaskImplementedEvent)` → `UPDATE p_tasks SET status='DONE' WHERE task_id=...` (TX2)
8. `project_all(FULL, ...)` → State_index.yaml rebuilt from PG EventLog replay
**Post:** `event_log` содержит новую строку; `p_tasks.status='DONE'`; `State_index.yaml` актуален

### UC-43-2: Сбой Projector — консистентность сохраняется

**Actor:** CLI (автоматически)  
**Trigger:** `Projector.apply()` поднимает исключение  
**Pre:** TX1 committed (event в event_log)  
**Steps:**
1. `_apply_projector_safe` перехватывает исключение
2. WARNING log: "Projector failed for TaskImplemented: ... Run sdd rebuild-state"
3. Audit event записан в audit_log.jsonl
4. `project_all(...)` → State_index.yaml rebuilt (шаг 3 выполнится)
**Post:** `event_log` консистентен; `p_tasks` stale (но `rebuild-state` восстановит)

### UC-43-3: Rebuild — восстановление p_* из event_log

**Actor:** Human или LLM  
**Trigger:** `sdd rebuild-state`  
**Pre:** `SDD_DATABASE_URL` установлен; `event_log` содержит полную историю  
**Steps:**
1. `RebuildStateHandler.handle()` вызывает `rebuild(pg_conn)`
2. `BEGIN` транзакция
3. `TRUNCATE p_tasks, p_phases, p_invariants, p_sessions` (+ `p_meta` сбрасывается далее)
4. `SELECT * FROM event_log ORDER BY sequence_id`
5. `with Projector(pg_url) as projector:` — одно соединение на весь rebuild
6. Для каждой строки: `projector.apply(deserialize(row))`
7. `UPDATE p_meta SET last_applied_sequence_id = <max_seq_from_step_4>, updated_at = now()`
8. `COMMIT`
9. `project_all(FULL, ...)` → State_index.yaml
**Post:** `p_* == f(event_log)` (I-REPLAY-1, I-REBUILD-ATOMIC-1); `p_meta.last_applied_sequence_id == MAX(event_log.sequence_id)` (I-PROJ-VERSION-1); `State_index.yaml` актуален

### UC-43-4: Тест Write Kernel без реальной БД

**Actor:** pytest  
**Trigger:** unit test для `execute_command`  
**Pre:** `FakeEventLog` реализует `EventLogKernelProtocol`  
**Steps:**
1. `fake_el = FakeEventLog()`
2. `execute_command(spec, cmd, event_log=fake_el)`
3. Kernel использует `fake_el.max_seq()` и `fake_el.append(...)` — без открытия БД
**Post:** Kernel logic протестирована изолированно; `fake_el.appended` содержит записанные события

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-32 PostgreSQL infra | this → BC-32 | `open_db_connection`, psycopg connection |
| BC-15 Write Kernel (registry.py) | this → BC-15 | inject EventLogKernelProtocol в execute_command |
| BC-INFRA (event_log.py) | this extends BC-INFRA | PostgresEventLog добавляется рядом с EventLog |
| BC-INFRA (projections.py) | this → projections | `project_all()` продолжает писать State_index.yaml |

### Reducer Extensions

Phase 43 не расширяет SDDReducer. Projector — отдельный механизм (не reducer).

### Порядок применения BC-43-G (DuckDB removal)

**CONSTRAINT: BC-43-G MUST применяться последним в TaskSet Phase 43.**

```
1. BC-43-A…BC-43-F, BC-43-H реализованы и протестированы
2. scripts/migrate_duckdb_to_pg.py выполнен и верифицирован (все данные в PG)
3. Integration tests (pytest -m pg) проходят на PG EventLog
4. ТОЛЬКО ПОСЛЕ → BC-43-G: удалить duckdb из pyproject.toml
```

Нарушение порядка: если BC-43-G применяется до п.2, `migrate_duckdb_to_pg.py`
не запустится (нет `import duckdb`). DuckDB остаётся временной зависимостью
до завершения миграции и верификации.

**Обязательная проверка перед BC-43-G (I-MIGRATION-1):**
```python
# Псевдокод верификации
duck_state  = EventReducer().reduce(replay_from_duckdb())
pg_state    = EventReducer().reduce(replay_from_pg())
assert duck_state == pg_state, "Migration integrity violation"
```
Тест: `test_migration_replay_parity` (pytest -m migration).

### Порядок инициализации (первый запуск с PG)

```
1. sdd init-project --name <project>    ← создаёт shared + p_<name> схемы (уже существует)
2. Применить DDL event_log              ← новая миграция в InitProjectHandler или отдельная задача
3. SDD_DATABASE_URL=<pg_url> sdd show-state  ← проверка replay из PG EventLog
```

---

## 9. Verification

### Unit Tests (без БД)

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `test_execute_command_uses_injected_event_log` — FakeEventLog инжектируется, реальная БД не открывается | I-ELK-PROTO-1 |
| 2 | `test_fake_event_log_captures_appended_events` — FakeEventLog хранит events в памяти | I-ELK-PROTO-1 |
| 3 | `test_event_store_url_pg_when_env_set` — SDD_DATABASE_URL → PG URL | I-EVENT-STORE-URL-1 |
| 4 | `test_event_store_url_duckdb_fallback` — без env → DuckDB path | I-EVENT-STORE-URL-1 |
| 5 | `test_is_production_event_store_pg` — PG URL matches SDD_DATABASE_URL | I-PROD-GUARD-1 |
| 6 | `test_is_production_event_store_duckdb` — file path comparison | I-PROD-GUARD-1 |
| 7 | `test_projector_noop_for_unknown_event` — неизвестный event_type → NO-OP | I-PROJ-NOOP-1 |
| 8 | `test_apply_projector_safe_swallows_exception` — исключение Projector не пробрасывается | I-FAIL-1, I-PROJ-SAFE-1 |
| 9 | `test_open_sdd_connection_no_top_level_duckdb_import` — импорт infra.db не требует duckdb | I-LAZY-DUCK-1 |
| 10 | `test_get_current_state_jsonb_dict_payload` — если `payload` уже `dict` (psycopg3 JSONB), `json.loads()` не вызывается; нет `TypeError` | I-DB-1 (R-3) |

### Integration Tests (PG, `pytest -m pg`)

| # | Test | Invariant(s) |
|---|------|--------------|
| 10 | `test_pg_event_log_append_replay` — append → SELECT из event_log → порядок sequence_id | I-EVENT-1, I-ORDER-1 |
| 11 | `test_pg_event_log_optimistic_lock` — concurrent append → StaleStateError | I-OPTLOCK-1 |
| 12 | `test_pg_event_log_idempotency` — дубликат (command_id, event_index) → skip | I-IDEM-SCHEMA-1 |
| 13 | `test_pg_projector_apply_task_implemented` — event → p_tasks обновлена | I-PROJ-1 |
| 14 | `test_pg_projector_idempotent` — повторный apply → нет дублей в p_tasks | I-PROJ-1 |
| 15 | `test_pg_rebuild_state` — TRUNCATE + replay → p_* == state | I-REPLAY-1 |
| 16 | `test_pg_execute_and_project_full_pipeline` — full pipeline TX1+TX2+YAML | I-FAIL-1, I-PROJ-1 |
| 17 | `test_pg_projector_failure_does_not_rollback_event_log` — исключение в TX2 → event_log цел | I-FAIL-1 |
| 18 | `test_pg_event_log_no_direct_mutations` — grep по source: ни один модуль SDD не содержит `UPDATE event_log` или `DELETE FROM event_log` (application-level enforcement I-EVENT-1/I-EVENT-2; DB-level PG trigger/RLS — Phase 44+); тест реализован как `ast.parse` или subprocess grep | I-EVENT-1, I-EVENT-2 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Incremental YAML rebuild (after_seq оптимизация) | Phase 44+ |
| EventLog snapshot (partial replay от checkpoint) | Phase 44+ |
| Auto-rebuild при обнаружении stale projections (I-PROJ-VERSION-1 только warn) | Phase 44+ |
| Удаление State_index.yaml (замена на p_* query) | Future phase (явное решение нужно) |
| GraphNavigation (Phase 36) | Строится поверх Phase 43 |
| TemporalNavigation (Phase 37) | Строится поверх Phase 43 |
| MutationGovernance (Phase 38) | Строится поверх Phase 43 |
| EventRegistrySSot (Phase 39) | Строится поверх Phase 43 |
| Connection pooling для Projector | Phase 44+ |
| Миграция существующих DuckDB данных в PG | scripts/migrate_duckdb_to_pg.py (уже частично готов) |
| PG-версия sdd_append / sdd_append_batch (non-kernel paths) | Phase 43, но отдельная задача TaskSet |
