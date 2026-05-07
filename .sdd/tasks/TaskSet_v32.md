# TaskSet_v32 — Phase 32: PostgreSQL Migration & Normalized Schema

Spec: specs/Spec_v32_PostgresMigration.md
Plan: plans/Plan_v32.md

---

T-3201: Create shared schema DDL (projects, invariants tables)

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-0 — Shared Schema
Invariants:           I-DB-SCHEMA-1, I-DB-1
spec_refs:            [Spec_v32 §2 BC-32-0, I-DB-SCHEMA-1]
produces_invariants:  [I-DB-SCHEMA-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/db/connection.py
Outputs:              src/sdd/db/migrations/001_shared_schema.sql
Acceptance:           test_shared_schema_created: таблицы shared.projects и shared.invariants существуют после применения DDL
Depends on:           —

---

T-3202: Update open_sdd_connection() with new signature

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-1 — Connection Model
Invariants:           I-DB-1, I-DB-2
spec_refs:            [Spec_v32 §2 BC-32-1, I-DB-1, I-DB-2]
produces_invariants:  [I-DB-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/db/connection.py
Outputs:              src/sdd/db/connection.py
Acceptance:           test_connection_routing: postgresql:// URL → psycopg; path/:memory: → DuckDB; оба пути проходят connect()
Depends on:           T-3201

---

T-3203: Implement sdd init-project command

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-1 — init-project
Invariants:           I-DB-SCHEMA-1, I-DB-1
spec_refs:            [Spec_v32 §2 BC-32-1, I-DB-SCHEMA-1]
produces_invariants:  [I-DB-SCHEMA-1]
requires_invariants:  [I-DB-SCHEMA-1]
Inputs:               src/sdd/db/connection.py, src/sdd/db/migrations/001_shared_schema.sql, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/init_project.py, src/sdd/commands/registry.py
Acceptance:           test_init_project: sdd init-project --name foo создаёт схему p_foo и запись в shared.projects
Depends on:           T-3202

---

T-3204: Tests — M1 connection, test isolation p_test_*

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-1 — Test Isolation
Invariants:           I-DB-TEST-1, I-DB-TEST-2, I-DB-1
spec_refs:            [Spec_v32 §2 BC-32-1, I-DB-TEST-1, I-DB-TEST-2]
produces_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  [I-DB-SCHEMA-1]
Inputs:               src/sdd/db/connection.py, src/sdd/commands/init_project.py, tests/conftest.py
Outputs:              tests/test_db_connection.py, tests/conftest.py
Acceptance:           test_isolation: тесты используют p_test_* схему; prod DB путь никогда не открывается в PYTEST_CURRENT_TEST
Depends on:           T-3203

---

T-3205: DDL core schema — events (JSONB), sdd_state, phases, phase_plan_versions

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-2 — Core Schema
Invariants:           I-1, I-EVENT-DERIVE-1, I-STATE-REBUILD-1
spec_refs:            [Spec_v32 §2 BC-32-2, I-1, I-EVENT-DERIVE-1]
produces_invariants:  [I-EVENT-DERIVE-1, I-STATE-REBUILD-1]
requires_invariants:  [I-DB-SCHEMA-1]
Inputs:               src/sdd/db/migrations/001_shared_schema.sql
Outputs:              src/sdd/db/migrations/002_core_schema.sql
Acceptance:           test_core_ddl: таблицы events, sdd_state, phases, phase_plan_versions создаются; payload колонка имеет тип JSONB; индексы idx_events_type/task/phase присутствуют
Depends on:           T-3201

---

T-3206: DDL task tables — tasks, task_deps, task_inputs, task_outputs, task_invariants, task_spec_refs

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-3 — Tasks Schema
Invariants:           I-EVENT-DERIVE-1
spec_refs:            [Spec_v32 §2 BC-32-3, I-EVENT-DERIVE-1]
produces_invariants:  [I-EVENT-DERIVE-1]
requires_invariants:  [I-EVENT-DERIVE-1, I-STATE-REBUILD-1]
Inputs:               src/sdd/db/migrations/002_core_schema.sql
Outputs:              src/sdd/db/migrations/003_tasks_schema.sql
Acceptance:           test_tasks_ddl: все 6 таблиц созданы с FK → events.seq и phases.id; INSERT-only (отсутствует DEFAULT для status в tasks)
Depends on:           T-3205

---

T-3207: DDL artifact tables — specs, specs_draft, invariants, invariants_current

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-4 — Artifacts Schema
Invariants:           I-EVENT-DERIVE-1, I-DB-SCHEMA-1
spec_refs:            [Spec_v32 §2 BC-32-4, I-DB-SCHEMA-1]
produces_invariants:  [I-DB-SCHEMA-1]
requires_invariants:  [I-EVENT-DERIVE-1]
Inputs:               src/sdd/db/migrations/003_tasks_schema.sql
Outputs:              src/sdd/db/migrations/004_artifacts_schema.sql
Acceptance:           test_artifacts_ddl: таблицы specs, specs_draft, invariants, invariants_current созданы; invariants_current — view или таблица с FK → invariants
Depends on:           T-3206

---

T-3208: New events TaskDefined and InvariantRegistered in events.py

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-3, BC-32-7 — New Events
Invariants:           I-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v32 §2 BC-32-3, Spec_v32 §2 BC-32-7, I-1, I-HANDLER-PURE-1]
produces_invariants:  [I-HANDLER-PURE-1]
requires_invariants:  [I-1]
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py
Acceptance:           test_new_events: TaskDefined и InvariantRegistered импортируются из events.py; handle() методы возвращают только события (no side effects)
Depends on:           T-3207

---

T-3209: IncrementalReducer.apply_delta() delegating to Reducer.fold()

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-5 — Incremental State Projection
Invariants:           I-1, I-STATE-REBUILD-1
spec_refs:            [Spec_v32 §2 BC-32-5, I-1, I-STATE-REBUILD-1]
produces_invariants:  [I-STATE-REBUILD-1]
requires_invariants:  [I-1, I-HANDLER-PURE-1]
Inputs:               src/sdd/core/reducer.py, src/sdd/db/migrations/002_core_schema.sql
Outputs:              src/sdd/core/incremental_reducer.py
Acceptance:           test_incremental_reducer: apply_delta делегирует Reducer.fold(), не реализует свою event-обработку; результат идентичен полному replay для тех же событий
Depends on:           T-3208

---

T-3210: sdd rebuild-state --full command

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-10 — rebuild-state
Invariants:           I-1, I-STATE-REBUILD-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v32 §2 BC-32-10, I-1, I-STATE-REBUILD-1]
produces_invariants:  [I-STATE-REBUILD-1]
requires_invariants:  [I-STATE-REBUILD-1]
Inputs:               src/sdd/core/incremental_reducer.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/rebuild_state.py, src/sdd/commands/registry.py
Acceptance:           test_rebuild_state_full: sdd rebuild-state --full пересчитывает проекцию с seq=0; результат == инкрементальному при том же EventLog
Depends on:           T-3209

---

T-3211: sdd next-tasks --phase N command

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-6 — next-tasks
Invariants:           I-CMD-IDEM-1, I-CMD-IDEM-2
spec_refs:            [Spec_v32 §2 BC-32-6, I-CMD-IDEM-1]
produces_invariants:  [I-CMD-IDEM-1]
requires_invariants:  [I-EVENT-DERIVE-1]
Inputs:               src/sdd/db/connection.py, src/sdd/commands/registry.py, src/sdd/db/migrations/003_tasks_schema.sql
Outputs:              src/sdd/commands/next_tasks.py, src/sdd/commands/registry.py
Acceptance:           test_next_tasks: sdd next-tasks --phase N возвращает задачи без невыполненных deps; EVENT_TASK_DONE константа определена в одном месте
Depends on:           T-3210

---

T-3212: _check_deps() guard in sdd complete (guard-lite)

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-6 — guard-lite
Invariants:           I-CMD-IDEM-1, I-CMD-IDEM-2, I-HANDLER-PURE-1
spec_refs:            [Spec_v32 §2 BC-32-6, I-CMD-IDEM-1, I-CMD-IDEM-2]
produces_invariants:  [I-CMD-IDEM-2]
requires_invariants:  [I-CMD-IDEM-1]
Inputs:               src/sdd/commands/complete.py, src/sdd/commands/next_tasks.py
Outputs:              src/sdd/commands/complete.py
Acceptance:           test_check_deps: sdd complete T-NNN с невыполненной dep завершается exit 1 с error_type=DependencyNotMet
Depends on:           T-3211

---

T-3213: sdd sync-invariants command + InvariantRegistered projection

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-7 — sync-invariants
Invariants:           I-SYNC-INVARIANTS-1, I-1
spec_refs:            [Spec_v32 §2 BC-32-7, I-SYNC-INVARIANTS-1, I-1]
produces_invariants:  [I-SYNC-INVARIANTS-1]
requires_invariants:  [I-1, I-HANDLER-PURE-1]
Inputs:               src/sdd/core/events.py, .sdd/norms/norm_catalog.yaml, src/sdd/commands/registry.py, src/sdd/db/migrations/004_artifacts_schema.sql
Outputs:              src/sdd/commands/sync_invariants.py, src/sdd/commands/registry.py
Acceptance:           test_sync_invariants: новый инвариант в norm_catalog.yaml → sdd sync-invariants эмитирует InvariantRegistered; incremental reducer обновляет invariants_current
Depends on:           T-3212

---

T-3214: Analytics schema DDL — 4 cross-project views

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-9 — Analytics Schema
Invariants:           I-DB-SCHEMA-1
spec_refs:            [Spec_v32 §2 BC-32-9, I-DB-SCHEMA-1]
produces_invariants:  [I-DB-SCHEMA-1]
requires_invariants:  [I-DB-SCHEMA-1]
Inputs:               src/sdd/db/migrations/004_artifacts_schema.sql
Outputs:              src/sdd/db/migrations/005_analytics_schema.sql
Acceptance:           test_analytics_ddl: CREATE SCHEMA analytics; views all_events, all_tasks, all_phases, all_invariants созданы с явным col_map (SELECT * запрещён)
Depends on:           T-3207

---

T-3215: sdd analytics-refresh command

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-9 — analytics-refresh
Invariants:           I-DB-SCHEMA-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v32 §2 BC-32-9, I-DB-SCHEMA-1]
produces_invariants:  [I-DB-SCHEMA-1]
requires_invariants:  [I-DB-SCHEMA-1]
Inputs:               src/sdd/db/migrations/005_analytics_schema.sql, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/analytics_refresh.py, src/sdd/commands/registry.py
Acceptance:           test_analytics_refresh: после sdd init-project --name test; sdd analytics-refresh — views включают p_test в FROM; проверка через INFORMATION_SCHEMA
Depends on:           T-3214, T-3203

---

T-3216: Migration script --export mode (DuckDB → JSON)

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-8, §6 — Migration Script
Invariants:           I-1, I-STATE-REBUILD-1
spec_refs:            [Spec_v32 §2 BC-32-8, I-1]
produces_invariants:  [I-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/db/connection.py, .sdd/state/sdd_events.duckdb (read-only source)
Outputs:              scripts/migrate_duckdb_to_pg.py
Acceptance:           test_export_mode: --export валидирует каждую строку payload как JSON; count(export) == count(DuckDB events); невалидный JSON → exit 1 с подробным сообщением
Depends on:           T-3202

---

T-3217: Migration script --import mode (JSON → PostgreSQL) + post-migration validation

Status:               DONE
Spec ref:             Spec_v32 §2 BC-32-8, §6 Pre/Post Conditions — Migration Import
Invariants:           I-1, I-STATE-REBUILD-1, I-DB-1
spec_refs:            [Spec_v32 §2 BC-32-8, §6, I-STATE-REBUILD-1]
produces_invariants:  [I-STATE-REBUILD-1]
requires_invariants:  [I-1]
Inputs:               scripts/migrate_duckdb_to_pg.py, src/sdd/commands/rebuild_state.py
Outputs:              scripts/migrate_duckdb_to_pg.py
Acceptance:           test_import_mode: --import загружает JSON в Postgres events с JSONB payload; count(Postgres) == count(export); sdd rebuild-state --full и sdd show-state проходят без ошибок
Depends on:           T-3216, T-3210

---

<!-- Granularity: 17 tasks, в диапазоне TG-2 (10–30). Каждая задача независимо реализуема и тестируема (TG-1). -->
