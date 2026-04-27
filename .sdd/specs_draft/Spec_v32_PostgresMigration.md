# Spec_v32 — Phase 32: PostgreSQL Migration & Normalized Schema

Status: Draft
Baseline: Spec_v31_GovernanceCommands.md

---

## 0. Goal

SDD сейчас использует DuckDB как единый файл-based storage: EventLog, State,
spatial_nodes/edges — всё в `sdd_events.duckdb`. Это создаёт три ограничения:

1. **Single-writer**: DuckDB не поддерживает concurrent writers — timeout при
   параллельных сессиях (I-DB-TEST-2 закрывает это для тестов, но не для prod).

2. **Flat state**: `State_index.yaml` пересчитывается через полный EventLog replay
   при каждом write-команде — O(N) событий.

3. **No multi-project**: один файл = один проект. Нет изоляции между проектами.

Phase 32 мигрирует на PostgreSQL с нормализованной схемой, multi-project
архитектурой (schema per project) и incremental state projection.

**Принцип:** I-1 сохраняется — `state = reduce(events)`. Incremental reducer
применяет только новые события через `last_applied_seq` checkpoint.

---

## 1. Scope

### In-Scope

- **BC-32-0**: `shared` schema — `projects` + `invariants` (фреймворковые)
- **BC-32-1**: Connection model — `SDD_DATABASE_URL` + `sdd_config.yaml` + `sdd init-project`
- **BC-32-2**: Core schema per project — `events`, `sdd_state`, `phases`, `phase_plan_versions`
- **BC-32-3**: Tasks schema — `tasks`, `task_deps`, `task_inputs`, `task_outputs`, `task_invariants`, `task_spec_refs`
- **BC-32-4**: Artifacts schema — `specs`, `specs_draft`, `invariants`, `invariants_current`
- **BC-32-5**: Incremental state projection — `sdd_state.last_applied_seq` + incremental reducer
- **BC-32-6**: `sdd next-tasks` — dependency graph + guard-lite
- **BC-32-7**: `sdd sync-invariants` + `InvariantRegistered` event
- **BC-32-8**: Migration script — DuckDB → PostgreSQL (clean cut)
- **BC-32-9**: `analytics` schema — cross-project views
- **BC-32-10**: `sdd rebuild-state --full` + I-STATE-REBUILD-1

### Out of Scope

- DWH fact/dim analytics layer (C в future) — отдельный проект
- `task_ready` materialized view — только если объём потребует
- ML ranking, embedding — никогда
- Git bridge / ContentAddressableStore

---

## 2. Architecture / BCs

### BC-32-0: shared schema

```sql
-- shared.projects: реестр всех проектов
CREATE TABLE shared.projects (
    id          TEXT PRIMARY KEY,        -- "sdd", "dwh"
    name        TEXT NOT NULL,
    db_schema   TEXT NOT NULL UNIQUE,    -- "p_sdd", "p_dwh"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta        JSONB NOT NULL DEFAULT '{}'
);

-- shared.invariants: фреймворковые инварианты SDD (I-1, I-2, I-DB-1, ...)
-- Проектные инварианты живут в p_{name}.invariants с FK → shared.invariants
CREATE TABLE shared.invariants (
    id              TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    statement       TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'framework',  -- 'framework' | 'shared'
    introduced_seq  BIGINT,       -- NULL для pre-migration инвариантов
    meta            JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, version)
);
```

**Правило нейминга схем:** `p_{project_name}`. Примеры: `p_sdd`, `p_dwh`.
Префикс `p_` защищает от конфликтов с зарезервированными именами Postgres.

---

### BC-32-1: Connection model + sdd init-project

**Connection resolution (приоритет):**
```
1. SDD_DATABASE_URL env var          ← credentials (не в файлах)
2. .sdd/config/sdd_config.yaml       ← host/dbname без credentials
   database:
     url: postgresql://localhost/sdd_db
     project: sdd                    → schema p_sdd
3. :memory: / file path              ← тесты (backward compat)
```

**Project context resolution:**
```
1. SDD_PROJECT env var               ← явный override
2. .sdd/config/sdd_config.yaml       ← project: sdd
→ SET search_path = p_sdd, shared
```

**Новый файл** `src/sdd/commands/init_project.py`:
```python
# sdd init-project --name sdd [--schema p_sdd] [--db-url postgresql://...]
# 1. CREATE SCHEMA p_{name}
# 2. Run all DDL migrations in p_{name}
# 3. INSERT INTO shared.projects (id, name, db_schema, ...)
# 4. Create .sdd/config/sdd_config.yaml с project: {name}
```

**`open_sdd_connection()`** — обновить сигнатуру:
```python
def open_sdd_connection(
    db_url: str | None = None,    # из env или config
    project: str | None = None    # → SET search_path
) -> Connection: ...
```

**I-DB-1 переформулируется:** `db_url` MUST be explicit non-empty str OR
resolved from SDD_DATABASE_URL / sdd_config.yaml. Empty string запрещён.

---

### BC-32-2: Core schema per project

```sql
-- EventLog (payload переезжает из VARCHAR → JSONB)
CREATE TABLE events (
    seq             BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL UNIQUE,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    task_id         TEXT,                              -- денорм (I-EVENT-DERIVE-1)
    phase_id        INTEGER,                           -- денорм (I-EVENT-DERIVE-1)
    appended_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    level           TEXT NOT NULL DEFAULT 'L1',
    event_source    TEXT NOT NULL DEFAULT 'runtime',
    caused_by_seq   BIGINT REFERENCES events(seq),
    expired         BOOLEAN NOT NULL DEFAULT FALSE,
    batch_id        TEXT
);

CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_task ON events(task_id, event_type);
CREATE INDEX idx_events_phase ON events(phase_id, event_type);

-- Incremental state projection
CREATE TABLE sdd_state (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    last_applied_seq BIGINT NOT NULL DEFAULT 0,
    phase_current   INTEGER,
    phase_status    TEXT,
    tasks_total     INTEGER NOT NULL DEFAULT 0,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    invariants_status TEXT,
    tests_status    TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      TEXT
);
INSERT INTO sdd_state (id, last_applied_seq, updated_at) VALUES (1, 0, now());

-- Phases history
CREATE TABLE phases (
    id              INTEGER PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'PLANNED',   -- PLANNED|ACTIVE|COMPLETE
    spec_hash       TEXT,
    spec_seq        BIGINT REFERENCES events(seq),     -- SpecApproved event
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Plan versions per phase (поддержка PlanAmended)
CREATE TABLE phase_plan_versions (
    id          BIGSERIAL PRIMARY KEY,
    phase_id    INTEGER NOT NULL REFERENCES phases(id),
    hash        TEXT NOT NULL,
    seq         BIGINT NOT NULL REFERENCES events(seq),  -- PhaseInitialized или PlanAmended
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Текущий plan_hash: SELECT hash FROM phase_plan_versions WHERE phase_id=N ORDER BY seq DESC LIMIT 1
```

**I-EVENT-DERIVE-1** (новый инвариант):
```
Denormalized columns in events (task_id, phase_id) MUST be derivable
from payload. payload is source of truth. Denormalized fields are
optimization only — never used as primary logic keys.
```

---

### BC-32-3: Tasks schema

```sql
CREATE TABLE tasks (
    id          TEXT NOT NULL,
    phase_id    INTEGER NOT NULL REFERENCES phases(id),
    title       TEXT NOT NULL,
    spec_ref    TEXT,                        -- "Spec_v29 §2"
    created_seq BIGINT NOT NULL REFERENCES events(seq),  -- TaskDefined event
    meta        JSONB NOT NULL DEFAULT '{}', -- acceptance_criteria, notes
    PRIMARY KEY (id, phase_id)
);

-- Dependency graph
CREATE TABLE task_deps (
    task_id             TEXT NOT NULL,
    task_phase_id       INTEGER NOT NULL,
    depends_on_task_id  TEXT NOT NULL,
    depends_on_phase_id INTEGER NOT NULL,
    FOREIGN KEY (task_id, task_phase_id) REFERENCES tasks(id, phase_id),
    FOREIGN KEY (depends_on_task_id, depends_on_phase_id) REFERENCES tasks(id, phase_id),
    PRIMARY KEY (task_id, task_phase_id, depends_on_task_id, depends_on_phase_id)
);

CREATE TABLE task_inputs  (task_id TEXT, phase_id INTEGER, file_path TEXT,
    FOREIGN KEY (task_id, phase_id) REFERENCES tasks(id, phase_id),
    PRIMARY KEY (task_id, phase_id, file_path));
CREATE TABLE task_outputs (task_id TEXT, phase_id INTEGER, file_path TEXT,
    FOREIGN KEY (task_id, phase_id) REFERENCES tasks(id, phase_id),
    PRIMARY KEY (task_id, phase_id, file_path));
CREATE TABLE task_invariants (task_id TEXT, phase_id INTEGER,
    invariant_id TEXT, role TEXT NOT NULL,  -- 'produces' | 'requires'
    FOREIGN KEY (task_id, phase_id) REFERENCES tasks(id, phase_id),
    PRIMARY KEY (task_id, phase_id, invariant_id, role));
CREATE TABLE task_spec_refs (task_id TEXT, phase_id INTEGER,
    spec_phase_id INTEGER, section TEXT NOT NULL,
    FOREIGN KEY (task_id, phase_id) REFERENCES tasks(id, phase_id),
    PRIMARY KEY (task_id, phase_id, spec_phase_id, section));

-- Индексы для sdd next-tasks
CREATE INDEX idx_task_deps_on ON task_deps(depends_on_task_id, depends_on_phase_id);
CREATE INDEX idx_events_task_type ON events(task_id, event_type);
```

**tasks INSERT-only:** после INSERT строка не обновляется. Статус задачи —
всегда запрос к EventLog: `SELECT seq FROM events WHERE task_id=? AND event_type='TaskImplementedEvent'`.

**TaskDefined event** (новый) в `src/sdd/core/events.py`:
```python
@dataclass(frozen=True)
class TaskDefined(DomainEvent):
    event_type: str = "TaskDefined"
    task_id: str = ""
    phase_id: int = 0
    title: str = ""
    actor: str = "human"
```

---

### BC-32-4: Artifacts schema

```sql
-- Approved specs (после sdd approve-spec)
CREATE TABLE specs (
    id              BIGSERIAL PRIMARY KEY,
    phase_id        INTEGER NOT NULL REFERENCES phases(id),
    file_path       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    approved_seq    BIGINT REFERENCES events(seq)  -- SpecApproved event
);

-- Draft specs
CREATE TABLE specs_draft (
    id              BIGSERIAL PRIMARY KEY,
    phase_id        INTEGER,                        -- NULL для DRAFT_SPEC сессии
    file_path       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Invariants (versioned)
CREATE TABLE invariants (
    id              TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    statement       TEXT NOT NULL,
    phase_id        INTEGER REFERENCES phases(id),  -- NULL для pre-migration
    introduced_seq  BIGINT REFERENCES events(seq),  -- InvariantRegistered event
    parent_id       TEXT,     -- FK → shared.invariants.id (фреймворковые)
    meta            JSONB NOT NULL DEFAULT '{}',    -- verification_cmd, check_mechanism
    PRIMARY KEY (id, version)
);

-- Materialized current version (projector обновляет)
CREATE TABLE invariants_current (
    id              TEXT PRIMARY KEY,
    version         INTEGER NOT NULL,
    statement       TEXT NOT NULL,
    phase_id        INTEGER,
    introduced_seq  BIGINT,
    parent_id       TEXT,
    meta            JSONB NOT NULL DEFAULT '{}'
);
```

---

### BC-32-5: Incremental state projection

**Алгоритм A' (incremental reducer):**
```python
def apply_incremental(conn: Connection, reducer: Reducer) -> None:
    """
    Применяет только новые события к sdd_state.
    Атомарная транзакция: SELECT events + UPDATE sdd_state.
    """
    with conn.transaction():
        state = conn.execute(
            "SELECT * FROM sdd_state WHERE id = 1 FOR UPDATE"
        ).fetchone()

        new_events = conn.execute("""
            SELECT seq, event_type, payload
            FROM events
            WHERE seq > %s
            ORDER BY seq ASC
        """, [state.last_applied_seq]).fetchall()

        if not new_events:
            return

        new_state = reducer.apply_delta(state, new_events)
        new_state.last_applied_seq = new_events[-1].seq

        conn.execute("""
            UPDATE sdd_state SET
                last_applied_seq = %s,
                phase_current = %s,
                phase_status = %s,
                tasks_total = %s,
                tasks_completed = %s,
                updated_at = now(),
                updated_by = %s
            WHERE id = 1
        """, [new_state.last_applied_seq, ...])
```

**I-STATE-REBUILD-1** (новый инвариант):
```
System MUST support full rebuild of ALL projections from EventLog at any time.
sdd rebuild-state --full MUST produce identical result to incremental A'
for any consistent EventLog. This is both a correctness guarantee and a
break-glass recovery command.
```

**sdd rebuild-state --full:**
```bash
# Пересчитывает sdd_state, phases, phase_plan_versions, invariants_current
# из EventLog с seq=0. Используется при подозрении на corruption.
sdd rebuild-state --full
```

---

### BC-32-6: sdd next-tasks + guard-lite

**sdd next-tasks --phase N:**
```sql
-- Задачи готовые к выполнению: все зависимости DONE
SELECT t.id, t.title
FROM tasks t
WHERE t.phase_id = $N
  AND NOT EXISTS (
    SELECT 1 FROM task_deps d
    WHERE d.task_id = t.id AND d.task_phase_id = $N
      AND (d.depends_on_task_id, d.depends_on_phase_id) NOT IN (
        SELECT task_id, phase_id::integer
        FROM events
        WHERE event_type = 'TaskImplementedEvent'
          AND task_id IS NOT NULL
      )
  )
  AND t.id NOT IN (
    SELECT task_id FROM events
    WHERE event_type = 'TaskImplementedEvent' AND phase_id = $N
  )
ORDER BY t.id;
```

**Guard-lite** в `sdd complete T-NNN`:
```python
# Перед emit TaskImplementedEvent — проверить зависимости
def _check_deps(task_id: str, phase_id: int, conn: Connection) -> bool:
    """Returns True if all dependencies are DONE."""
    # SELECT task_deps WHERE task_id=? AND depends_on NOT IN (completed tasks)
    # exit 1 с JSON error если зависимость не выполнена
```

---

### BC-32-7: sdd sync-invariants + InvariantRegistered

**Новый event** в `src/sdd/core/events.py`:
```python
@dataclass(frozen=True)
class InvariantRegistered(DomainEvent):
    event_type: str = "InvariantRegistered"
    invariant_id: str = ""
    version: int = 1
    statement: str = ""
    phase_id: Optional[int] = None
    source: str = ""   # "norm_catalog" | "claude_md" | "spec"
    actor: str = "human"
```

**sdd sync-invariants:**
```
1. Читает norm_catalog.yaml + CLAUDE.md §INV
2. Сравнивает с invariants_current (через EventLog projection)
3. Для каждого нового/изменённого инварианта:
   → emit InvariantRegistered(id, version, statement, source)
4. Incremental reducer обновляет invariants + invariants_current
```

**Правило:** `sdd sync-invariants` НЕ делает прямой UPDATE в invariants.
Только emit → reducer. Silent sync запрещён (SEM-8).

---

### BC-32-8: Migration script (DuckDB → PostgreSQL)

**Стратегия: clean cut (вариант C из архитектурного разбора).**

```bash
# Шаги миграции:
# 1. Export events из DuckDB → JSONL
python3 scripts/migrate_duckdb_to_pg.py --export \
    --input .sdd/state/sdd_events.duckdb \
    --output .sdd/migration/events_export.jsonl

# 2. Трансформация: payload VARCHAR → JSONB-совместимый JSON
# (DuckDB хранит payload как строку; нужна валидация JSON)

# 3. sdd init-project --name sdd (создаёт схему p_sdd + все таблицы)

# 4. Import events → PostgreSQL
python3 scripts/migrate_duckdb_to_pg.py --import \
    --input .sdd/migration/events_export.jsonl \
    --db-url $SDD_DATABASE_URL

# 5. Валидация:
# SELECT count(*) FROM events;  -- должно совпасть с DuckDB count
# sdd rebuild-state --full       -- пересчитать все проекции
# sdd show-state                 -- проверить консистентность

# 6. Архивировать DuckDB: mv sdd_events.duckdb sdd_events.duckdb.bak
```

**Скрипт:** `scripts/migrate_duckdb_to_pg.py` — новый файл.

**Валидационный invariant:** `count(events Postgres) == count(events DuckDB)`.
Если не совпадает → STOP, не архивировать DuckDB.

---

### BC-32-9: analytics schema (views layer)

```sql
-- Cross-project views (A — views сейчас)
CREATE SCHEMA analytics;

CREATE VIEW analytics.all_events AS
    SELECT 'sdd'::text AS project, * FROM p_sdd.events
    UNION ALL
    SELECT 'dwh'::text AS project, * FROM p_dwh.events;

CREATE VIEW analytics.all_tasks AS
    SELECT 'sdd'::text AS project, * FROM p_sdd.tasks
    UNION ALL
    SELECT 'dwh'::text AS project, * FROM p_dwh.tasks;

CREATE VIEW analytics.all_phases AS
    SELECT 'sdd'::text AS project, * FROM p_sdd.phases
    UNION ALL
    SELECT 'dwh'::text AS project, * FROM p_dwh.phases;

CREATE VIEW analytics.all_invariants AS
    SELECT 'sdd'::text AS project, * FROM p_sdd.invariants_current
    UNION ALL
    SELECT 'dwh'::text AS project, * FROM p_dwh.invariants_current;
```

**Правило:** `analytics` — read-only. CLI пишет только в `p_{name}` схемы.
Добавление нового проекта = добавление UNION ALL в каждый view через
`sdd analytics-refresh`.

**`sdd analytics-refresh` — стратегия обновления view:**

```python
# src/sdd/commands/analytics_refresh.py
# 1. SELECT id, db_schema FROM shared.projects ORDER BY id
# 2. Для каждого view генерирует DDL с явным column list (не SELECT *):
#    col_map = {
#        "all_events":     "seq, event_id, event_type, payload, task_id, phase_id, ...",
#        "all_tasks":      "id, phase_id, title, spec_ref, created_seq, meta",
#        "all_phases":     "id, title, status, spec_hash, spec_seq, created_at, updated_at",
#        "all_invariants": "id, version, statement, phase_id, introduced_seq, parent_id, meta",
#    }
#    union_parts = [
#        f"SELECT '{p.id}'::text AS project, {col_map[view]} FROM {p.db_schema}.{table}"
#        for p in projects
#    ]
#    ddl = f"CREATE OR REPLACE VIEW analytics.{view} AS\n" + "\nUNION ALL\n".join(union_parts)
# 3. Все четыре view пересоздаются в одной транзакции
```

**Стратегия:** `CREATE OR REPLACE VIEW` не блокирует читателей (в отличие от DROP+CREATE).
`SELECT *` запрещён: Postgres разворачивает `*` в момент `CREATE VIEW`; новые колонки
не подхватываются без пересоздания view.
При добавлении колонки в схему (`events`, `tasks`, etc.): обновить `col_map` в
`analytics_refresh.py` + запустить `sdd analytics-refresh`.

---

### BC-32-10: sdd rebuild-state --full

```python
# src/sdd/commands/rebuild_state.py
# Пересчитывает ВСЕ проекции из EventLog:
# - sdd_state (last_applied_seq = max(seq))
# - phases (из PhaseInitialized, PhaseCompleted, SpecApproved событий)
# - phase_plan_versions (из PhaseInitialized, PlanAmended)
# - invariants + invariants_current (из InvariantRegistered)
# Не трогает: tasks, task_deps (INSERT-only, не проекции)
```

---

## 3. Domain Events

| Event | Emitter | Description |
|-------|---------|-------------|
| `TaskDefined` | `DefineTaskHandler` | Задача создана в DECOMPOSE |
| `InvariantRegistered` | `SyncInvariantsHandler` | Инвариант зарегистрирован из norm_catalog/CLAUDE.md |

Плюс события из Phase 31: `SpecApproved`, `PlanAmended`.

---

## 4. Types & Interfaces

```python
# Обновлённая сигнатура подключения
def open_sdd_connection(
    db_url: str | None = None,
    project: str | None = None,
    schema: str | None = None
) -> Connection: ...

# Incremental reducer interface
class IncrementalReducer:
    """
    I-STATE-REBUILD-1: apply_delta MUST delegate to Reducer.fold() — не дублировать логику.
    Паттерн реализации:
      state_obj = SDDState.from_row(current_state)   # SDDStateRow → SDDState (domain type)
      for event in new_events:
          state_obj = Reducer.fold(state_obj, event)  # существующий reducer (единственная реализация)
      return SDDStateRow.from_state(state_obj, new_events[-1].seq)  # SDDState → SDDStateRow
    Запрещено: реализовывать apply_delta с собственной event-обработкой.
    I-STATE-REBUILD-1 доказуем структурно: rebuild-state --full = IncrementalReducer(all_events, state_0).
    """
    def apply_delta(
        self,
        current_state: SDDStateRow,
        new_events: list[EventRow]
    ) -> SDDStateRow: ...
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-STATE-REBUILD-1 | System MUST support full rebuild of all projections from EventLog. `sdd rebuild-state --full` MUST produce identical result to incremental A'. | 32 |
| I-EVENT-DERIVE-1 | Denormalized columns in events (task_id, phase_id) MUST be derivable from payload. payload is source of truth. | 32 |
| I-DB-SCHEMA-1 | Each project MUST have its own PostgreSQL schema named `p_{project_id}`. Direct table creation outside `sdd init-project` is forbidden. | 32 |
| I-SYNC-INVARIANTS-1 | `sdd sync-invariants` MUST emit `InvariantRegistered` events — direct UPDATE of invariants table without EventLog is forbidden. | 32 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-1 | All SDD state = reduce(events) — сохраняется через incremental A' |
| I-DB-1 | `db_url` MUST be explicit non-empty str (переформулирован для Postgres) |
| I-DB-TEST-1 | Tests MUST NOT open production DB |
| I-DB-TEST-2 | In test context: `timeout_secs = 0.0` |

---

## 6. Pre/Post Conditions

### Migration (BC-32-8)

**Pre:**
- DuckDB файл существует и читаем
- PostgreSQL instance доступен
- `SDD_DATABASE_URL` установлен
- `sdd init-project --name sdd` выполнен (схема создана)

**Post:**
- `count(events Postgres) == count(events DuckDB)`
- `sdd show-state` возвращает те же значения что и до миграции
- DuckDB файл заархивирован (не удалён)
- `sdd rebuild-state --full` завершается exit 0

### sdd init-project

**Pre:**
- `shared` схема существует
- Проект с именем N не зарегистрирован в `shared.projects`

**Post:**
- Схема `p_{name}` создана со всеми таблицами
- `shared.projects` содержит запись для нового проекта
- `.sdd/config/sdd_config.yaml` содержит `project: {name}`

---

## 7. Use Cases

### UC-32-1: Инициализация нового проекта DWH

**Actor:** Human
**Steps:**
1. `export SDD_DATABASE_URL=postgresql://localhost/sdd_db`
2. `cd /projects/dwh && sdd init-project --name dwh`
3. CLI создаёт схему `p_dwh`, регистрирует в `shared.projects`
4. Создаётся `.sdd/config/sdd_config.yaml` с `project: dwh`
5. `sdd show-state` → phase.current=0, phase.status=PLANNED
**Post:** два проекта `p_sdd` и `p_dwh` изолированы в одной базе

### UC-32-2: Cross-project аналитика

**Actor:** Human / BI инструмент
**Steps:**
1. `SELECT * FROM analytics.all_tasks WHERE project = 'sdd' AND phase_id = 29`
2. `SELECT * FROM analytics.all_invariants WHERE id LIKE 'I-SESSION-%'`
**Post:** данные из обоих проектов в единой view без дополнительной конфигурации

### UC-32-3: sdd next-tasks показывает параллельные задачи

**Actor:** LLM в IMPLEMENT сессии
**Trigger:** `sdd next-tasks --phase 32`
**Post:** список задач без незавершённых зависимостей — LLM знает что можно делать параллельно

### UC-32-4: guard-lite блокирует нарушение цепочки

**Actor:** LLM
**Trigger:** `sdd complete T-3202` когда `T-3201` (зависимость) не DONE
**Post:** exit 1, JSON stderr с `error_type=DependencyNotMet`, LLM останавливается

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| Phase 31 BC-31-1 (SpecApproved) | required | SpecApproved event нужен для specs таблицы |
| Phase 31 BC-31-2 (PlanAmended) | required | PlanAmended нужен для phase_plan_versions |

---

## 9. Verification

| # | Проверка | BC |
|---|----------|----|
| 1 | `sdd init-project --name test` → exit 0, схема `p_test` создана | BC-32-1 |
| 2 | `count(events Postgres) == count(events DuckDB)` после миграции | BC-32-8 |
| 3 | `sdd rebuild-state --full` → exit 0, state идентичен до и после | BC-32-10 |
| 4 | `sdd next-tasks --phase N` возвращает только задачи с выполненными deps | BC-32-6 |
| 5 | `sdd complete T-NNN` с невыполненной dep → exit 1 DependencyNotMet | BC-32-6 |
| 6 | `sdd sync-invariants` → `InvariantRegistered` в EventLog для новых инвариантов | BC-32-7 |
| 7 | `SELECT * FROM analytics.all_tasks` возвращает задачи из всех проектов | BC-32-9 |
| 8 | `sdd show-state` после incremental update == `sdd rebuild-state --full` | BC-32-5 |
| 9 | Test context: подключение к `p_test_*` схеме, не к `p_sdd` | BC-32-1 |

---

## 10. Out of Scope

| Item | Owner |
|------|-------|
| DWH fact/dim analytics (ETL layer) | Отдельный DWH проект |
| `task_ready` materialized view | Phase 33+ если объём потребует |
| ML ranking, embedding | Никогда |
| Git bridge | Никогда |
| `analytics` → DWH ETL pipeline | DWH проект |
