# Plan_v32 — Phase 32: PostgreSQL Migration & Normalized Schema

Status: DRAFT
Spec: specs/Spec_v32_PostgresMigration.md

---

## Milestones

### M1: Shared Schema & Connection Model

```text
Spec:       §2 BC-32-0, BC-32-1
BCs:        BC-32-0, BC-32-1
Invariants: I-DB-1 (reformulated), I-DB-SCHEMA-1
Depends:    — (foundation, все последующие M зависят от M1)
Risks:      open_sdd_connection() используется во всех командах;
            неправильная сигнатура сломает весь CLI.
            Митигация: backward-compat параметры, тесты на оба пути (env / config).
```

Создаётся `shared` схема с таблицами `projects` и `invariants`.
Обновляется `open_sdd_connection()` с новой сигнатурой (`db_url`, `project`, `schema`).
Реализуется `sdd init-project` — создание схемы `p_{name}` и регистрация в `shared.projects`.
Тесты: подключение через `SDD_DATABASE_URL`, через `sdd_config.yaml`, тест-изоляция `p_test_*`.

---

### M2: Core Schema (events, sdd_state, phases, phase_plan_versions)

```text
Spec:       §2 BC-32-2
BCs:        BC-32-2
Invariants: I-1, I-EVENT-DERIVE-1, I-STATE-REBUILD-1
Depends:    M1 (схема p_{name} должна существовать)
Risks:      payload VARCHAR → JSONB меняет тип колонки; все существующие запросы
            к payload должны использовать JSONB операторы.
            Митигация: DDL migration без auto-cast, явная валидация JSON при импорте.
```

DDL для `events` (JSONB payload, денорм поля `task_id`/`phase_id`),
`sdd_state` с `last_applied_seq`, `phases`, `phase_plan_versions`.
Индексы для производительности (`idx_events_type`, `idx_events_task`, `idx_events_phase`).

---

### M3: Tasks & Artifacts Schema

```text
Spec:       §2 BC-32-3, BC-32-4
BCs:        BC-32-3, BC-32-4
Invariants: I-EVENT-DERIVE-1
Depends:    M2 (FK → events.seq, phases.id)
Risks:      tasks INSERT-only — статус только через EventLog;
            попытка UPDATE tasks нарушает инвариант.
            Митигация: тест на отсутствие UPDATE-команд в task handler-ах.
```

DDL для `tasks`, `task_deps`, `task_inputs`, `task_outputs`, `task_invariants`, `task_spec_refs`.
DDL для `specs`, `specs_draft`, `invariants`, `invariants_current`.
Новые события: `TaskDefined`, `InvariantRegistered` в `src/sdd/core/events.py`.

---

### M4: Incremental State Projection & rebuild-state

```text
Spec:       §2 BC-32-5, BC-32-10
BCs:        BC-32-5, BC-32-10
Invariants: I-1, I-STATE-REBUILD-1
Depends:    M2 (sdd_state таблица), M3 (события)
Risks:      apply_delta MUST delegate к Reducer.fold() — дублирование логики нарушает I-1.
            Митигация: IncrementalReducer не реализует свою event-обработку,
            вызывает существующий Reducer.fold() в цикле.
```

`IncrementalReducer.apply_delta()` — обёртка над существующим `Reducer.fold()`.
`sdd rebuild-state --full` — пересчёт всех проекций из EventLog с seq=0.
Тест: `rebuild-state --full` == инкрементальный результат для одного и того же EventLog.

---

### M5: next-tasks + guard-lite

```text
Spec:       §2 BC-32-6
BCs:        BC-32-6
Invariants: I-CMD-IDEM-1, I-CMD-IDEM-2
Depends:    M3 (task_deps таблица)
Risks:      SQL запрос зависит от event_type 'TaskImplementedEvent';
            если имя события изменится — guard сломается молча.
            Митигация: константа EVENT_TASK_DONE в одном месте, ссылка из guard.
```

`sdd next-tasks --phase N` — SQL запрос к `task_deps` и EventLog.
`_check_deps()` в `sdd complete` — guard-lite перед emit `TaskImplementedEvent`.
Тест: `sdd complete T-NNN` с невыполненной dep → exit 1 `DependencyNotMet`.

---

### M6: sync-invariants + InvariantRegistered

```text
Spec:       §2 BC-32-7
BCs:        BC-32-7
Invariants: I-SYNC-INVARIANTS-1, I-1
Depends:    M3 (invariants таблица, InvariantRegistered event)
Risks:      sync-invariants читает norm_catalog.yaml — изменение формата yaml
            без обновления парсера сломает sync.
            Митигация: schema validation norm_catalog при старте sync.
```

`sdd sync-invariants` — emit `InvariantRegistered` для новых/изменённых инвариантов.
Incremental reducer обновляет `invariants` и `invariants_current`.
Тест: новый инвариант в norm_catalog → `InvariantRegistered` в EventLog.

---

### M7: Analytics Schema + sdd analytics-refresh

```text
Spec:       §2 BC-32-9
BCs:        BC-32-9
Invariants: I-DB-SCHEMA-1
Depends:    M1 (shared.projects), M2–M3 (таблицы в p_{name})
Risks:      SELECT * в view не подхватывает новые колонки после ALTER TABLE.
            Митигация: явный col_map в analytics_refresh.py, SELECT * запрещён.
```

`CREATE SCHEMA analytics` с четырьмя views: `all_events`, `all_tasks`, `all_phases`, `all_invariants`.
`sdd analytics-refresh` — `CREATE OR REPLACE VIEW` для всех проектов из `shared.projects`.
Тест: после `sdd init-project --name test`, `sdd analytics-refresh` включает `p_test` в views.

---

### M8: Migration Script (DuckDB → PostgreSQL)

```text
Spec:       §2 BC-32-8, §6 Pre/Post Conditions
BCs:        BC-32-8
Invariants: I-1, I-STATE-REBUILD-1
Depends:    M1–M4 (PostgreSQL схема полностью готова)
Risks:      payload хранится как VARCHAR строка в DuckDB;
            невалидный JSON прервёт импорт.
            Митигация: --export валидирует каждую строку как JSON перед записью.
            count(*) проверка обязательна до архивирования DuckDB файла.
```

`scripts/migrate_duckdb_to_pg.py` — `--export` и `--import` режимы.
Трансформация `payload VARCHAR → JSONB` с валидацией.
Post-migration: `count(Postgres) == count(DuckDB)`, `sdd rebuild-state --full`, `sdd show-state`.

---

## Risk Notes

- R-1: **Backward compatibility** — `open_sdd_connection()` должна поддерживать
  DuckDB-путь в тестах (`:memory:`, file path). Митигация: тип соединения
  определяется по URL-схеме (`postgresql://` vs path/`:memory:`).

- R-2: **INSERT-only invariant для tasks** — любая команда, пытающаяся UPDATE tasks,
  нарушает инвариант. Митигация: code review + тест на отсутствие UPDATE в task handlers.

- R-3: **IncrementalReducer дублирование логики** — apply_delta MUST вызывать
  Reducer.fold(), иначе нарушается I-1. Митигация: структурное доказательство
  через делегирование; rebuild-state --full как regression тест.

- R-4: **analytics SELECT \*** — Postgres разворачивает `*` в момент CREATE VIEW;
  новые колонки не подхватываются. Митигация: явный col_map, запрет SELECT * в DDL views.

- R-5: **DuckDB clean cut** — стратегия C (миграция без rollback). DuckDB файл
  архивируется, не удаляется. При провале миграции восстановление через .bak файл.
  Митигация: count-check обязателен до архивирования.
