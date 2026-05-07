# Plan_v43 — Phase 43: Unified PostgreSQL EventLog

Status: DRAFT  
Spec: specs/Spec_v43_UnifiedPostgresEventLog.md

---

## Logical Context

type: none  
rationale: "Standard new phase. Migrates EventLog SSOT from DuckDB to PostgreSQL. Builds on Phase 42 (Docker/CI infrastructure) and Phase 32 (psycopg3 connection layer)."

---

## Milestones

### M1: URL-aware routing layer (BC-43-A)

```text
Spec:       §2 BC-43-A, §4 paths.py, §5 I-EVENT-STORE-URL-1, I-PROD-GUARD-1, §6 BC-43-A
BCs:        BC-43-A
Invariants: I-EVENT-STORE-URL-1, I-PROD-GUARD-1
Depends:    — (foundation; all other BCs depend on this)
Risks:      Если event_store_url() не станет единственной точкой routing — inline
            SDD_DATABASE_URL-reads в callers нарушат I-EVENT-STORE-URL-1.
            Необходимо заменить все 3 inline Path.resolve() на is_production_event_store().
```

**Deliverable:**  
`src/sdd/infra/paths.py` получает два новых метода:  
- `event_store_url() -> str` — PG URL если `SDD_DATABASE_URL` установлен, иначе DuckDB file path  
- `is_production_event_store(db_path: str) -> bool` — единый guard для обоих backend  

---

### M2: Lazy DuckDB import + PG routing в open_sdd_connection (BC-43-B)

```text
Spec:       §2 BC-43-B, §5 I-LAZY-DUCK-1, §6 BC-43-B
BCs:        BC-43-B
Invariants: I-LAZY-DUCK-1, I-DB-1
Depends:    M1 (uses is_postgres_url from M1)
Risks:      Top-level `import duckdb` сломает infra/db.py при удалении duckdb (BC-43-G).
            Lazy import обязателен ДО применения BC-43-G.
```

**Deliverable:**  
`src/sdd/infra/db.py`: `import duckdb` перемещён внутрь DuckDB-ветки (lazy).  
`open_sdd_connection()` маршрутизирует PG URL → `open_db_connection(url)` из `sdd.db.connection`.

---

### M3: EventLogKernelProtocol + PostgresEventLog (BC-43-C, BC-43-D)

```text
Spec:       §2 BC-43-C, §2 BC-43-D, §4 Types, §5 I-ELK-PROTO-1, I-PG-DDL-1,
            I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1,
            §6 BC-43-D
BCs:        BC-43-C, BC-43-D
Invariants: I-ELK-PROTO-1, I-PG-DDL-1, I-EVENT-1, I-EVENT-2, I-ORDER-1,
            I-OPTLOCK-1, I-IDEM-SCHEMA-1
Depends:    M1, M2 (PostgresEventLog opens via open_sdd_connection; PG routing from M1)
Risks:      JSONB payload: psycopg3 автоматически десериализует JSONB → dict;
            json.loads(dict) → TypeError (R-3 из Spec). Type-guard обязателен везде
            где обрабатывается payload.
            DDL должно быть идемпотентным (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS).
```

**Deliverable:**  
`src/sdd/infra/event_log.py`:
- `EventLogKernelProtocol` — `@runtime_checkable Protocol` с `max_seq()` + `append(...)`
- `PostgresEventLog` — полная PG-реализация: DDL (`event_log` + `p_meta`), `append()` с optimistic lock,
  `replay()`, `exists_command()`, `exists_semantic()`, `get_error_count()`

DDL: `event_log` (UUID PK, JSONB, BIGSERIAL UNIQUE), `p_meta` (singleton), индексы из §2 BC-43-D.

---

### M4: Projector — применение событий к p_* (BC-43-E)

```text
Spec:       §2 BC-43-E, §3 Projector dispatch map, §4 Projector class, §5 I-PROJ-1,
            I-REPLAY-1, I-PROJ-NOOP-1, I-PROJ-WRITE-1, I-REBUILD-ATOMIC-1,
            I-TABLE-SEP-1, I-PROJ-VERSION-1, §6 BC-43-E, §7 UC-43-3
BCs:        BC-43-E
Invariants: I-PROJ-1, I-REPLAY-1, I-PROJ-NOOP-1, I-PROJ-WRITE-1, I-REBUILD-ATOMIC-1,
            I-TABLE-SEP-1, I-PROJ-VERSION-1
Depends:    M3 (читает event_log через PostgresEventLog.replay())
Risks:      PhaseContextSwitched требует двухшагового UPDATE (сброс is_current=FALSE, затем SET TRUE).
            Однострочный UPDATE нарушает инвариант "ровно одна строка is_current=TRUE".
            rebuild() MUST выполняться в одной транзакции (TRUNCATE + replay + p_meta UPDATE).
```

**Deliverable:**  
`src/sdd/infra/projector.py` (новый модуль):
- `Projector` — context manager; `apply(event)` dispatch по `event_type`
- Handlers для: `TaskImplemented`, `TaskValidated`, `PhaseInitialized`, `PhaseCompleted`,
  `PhaseContextSwitched`, `SessionDeclared`, `DecisionRecorded`, `InvariantRegistered`, `SpecApproved`
- `PhaseStarted` → NO-OP (I-PHASE-STARTED-1)
- Все остальные → NO-OP + DEBUG log (I-PROJ-NOOP-1)
- `rebuild(pg_conn)` — атомарная транзакция: TRUNCATE p_* → replay → UPDATE p_meta

---

### M5: Write pipeline injection (BC-43-F)

```text
Spec:       §2 BC-43-F, §4 registry.py changes, §5 I-ELK-PROTO-1, I-FAIL-1, I-PROJ-SAFE-1,
            §6 BC-43-F, §7 UC-43-1, UC-43-2, UC-43-4
BCs:        BC-43-F
Invariants: I-ELK-PROTO-1, I-FAIL-1, I-PROJ-SAFE-1, I-LAYER-1
Depends:    M3 (EventLogKernelProtocol), M4 (Projector)
Risks:      Порядок TX1 → TX2 → YAML строго регламентирован. Сбой TX2 НЕ откатывает TX1.
            _apply_projector_safe MUST поглощать все исключения и эмитировать audit event.
```

**Deliverable:**  
`src/sdd/commands/registry.py`:
- `execute_command(... event_log: EventLogKernelProtocol | None = None)` — инжекция для тестов
- `execute_and_project(... projector: Projector | None = None)` — инжекция; None → auto-build
- `_build_projector_if_configured() -> Projector | None` — конструирует из SDD_DATABASE_URL
- `_apply_projector_safe(projector, events)` — TX2 с полным поглощением исключений + audit

---

### M6: get_current_state() PG-ветка (BC-43-H)

```text
Spec:       §2 BC-43-H, §5 I-DB-1, I-REPLAY-1
BCs:        BC-43-H
Invariants: I-DB-1 (updated: db_url вместо db_path), I-REPLAY-1
Depends:    M1 (is_postgres_url()), M2 (open_sdd_connection() с PG routing)
Risks:      JSONB type-guard: psycopg3 возвращает dict, не str.
            `json.loads(row_payload)` → TypeError если payload уже dict.
            Guard обязателен: `if isinstance(row_payload, dict) else json.loads(row_payload or "{}"))`.
```

**Deliverable:**  
`src/sdd/infra/projections.py`: `get_current_state()` получает PG-ветку:
- `event_log` таблица вместо `events`
- `sequence_id` колонка вместо `seq`
- JSONB-safe payload десериализация

---

### M7: Unit tests (без БД)

```text
Spec:       §9 Unit Tests (тесты 1–10)
BCs:        BC-43-A, BC-43-C, BC-43-E, BC-43-F, BC-43-B, BC-43-H
Invariants: I-ELK-PROTO-1, I-EVENT-STORE-URL-1, I-PROD-GUARD-1, I-PROJ-NOOP-1,
            I-FAIL-1, I-PROJ-SAFE-1, I-LAZY-DUCK-1
Depends:    M1–M6 (все BC реализованы)
Risks:      FakeEventLog должен реализовывать EventLogKernelProtocol структурно
            (runtime_checkable). Тест I-LAZY-DUCK-1 требует импортировать infra.db
            без установленного duckdb (изоляция через venv или mock).
```

**Deliverable:**  
10 unit-тестов из §9: FakeEventLog injection, event_store_url routing,
is_production_event_store, projector NOOP, _apply_projector_safe swallows,
open_sdd_connection no top-level duckdb import, JSONB dict payload guard.

---

### M8: Integration tests (pytest -m pg)

```text
Spec:       §9 Integration Tests (тесты 10–18)
BCs:        BC-43-D, BC-43-E, BC-43-F
Invariants: I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1,
            I-PROJ-1, I-REPLAY-1, I-FAIL-1, I-REBUILD-ATOMIC-1, I-PROJ-VERSION-1
Depends:    M3–M6 (PG pipeline полностью реализован), Docker Compose (Phase 42)
Risks:      test_migration_replay_parity (I-MIGRATION-1) обязателен перед BC-43-G.
            test_pg_event_log_no_direct_mutations реализован через grep/ast.parse.
            CI должен запускать `pytest -m pg` с реальным PostgreSQL (docker-compose up).
```

**Deliverable:**  
9 интеграционных тестов из §9: append/replay, optimistic lock, idempotency,
Projector apply, idempotent Projector, rebuild, full pipeline TX1+TX2+YAML,
Projector failure isolation, no direct mutations check.

---

### M9: DuckDB removal (BC-43-G)

```text
Spec:       §2 BC-43-G, §8 Порядок применения BC-43-G
BCs:        BC-43-G
Invariants: I-LAZY-DUCK-1, I-MIGRATION-1
Depends:    M1–M8 COMPLETE; scripts/migrate_duckdb_to_pg.py выполнен и верифицирован;
            test_migration_replay_parity PASS; integration tests (pytest -m pg) PASS
Risks:      CONSTRAINT из Spec §8: BC-43-G MUST применяться последним.
            Удаление duckdb до верификации миграции (I-MIGRATION-1) разрушает
            возможность запустить migrate_duckdb_to_pg.py.
```

**Deliverable:**  
`pyproject.toml`: `duckdb` удалён из dependencies; `psycopg[binary]>=3.1` переведён в mandatory.  
Финальный smoke test: `SDD_DATABASE_URL=<pg_url> sdd show-state` работает без duckdb.

---

## Risk Notes

- R-1: **JSONB payload type-guard** — psycopg3 автоматически десериализует JSONB → dict; прямой вызов `json.loads(dict)` → TypeError. Type-guard обязателен в BC-43-D, BC-43-H и везде, где обрабатывается payload из PG.
- R-2: **DuckDB removal ordering** — BC-43-G MUST применяться после верификации миграции (I-MIGRATION-1). Преждевременное удаление заблокирует migrate_duckdb_to_pg.py.
- R-3: **Projector TX isolation** — TX1 (event_log INSERT) и TX2 (p_* UPDATE) независимы. Сбой TX2 не откатывает TX1; _apply_projector_safe поглощает все исключения (I-FAIL-1, I-PROJ-SAFE-1). Stale p_* восстанавливается через sdd rebuild-state.
- R-4: **PhaseContextSwitched двухшаговый UPDATE** — однострочный UPDATE нарушает инвариант "ровно одна строка is_current=TRUE". Обязателен сброс всех строк перед установкой новой.
- R-5: **Rebuild atomicity** — TRUNCATE p_* видно снаружи TX пустым только в DuckDB (no MVCC). В PostgreSQL с MVCC: TRUNCATE внутри открытой транзакции не видно читателям снаружи до COMMIT. Rebuild MUST выполняться в одной транзакции (I-REBUILD-ATOMIC-1).
- R-6: **I-PHASE-STARTED-1** — PhaseStarted → NO-OP в Projector. Статус ACTIVE устанавливается через PhaseInitialized, не PhaseStarted. Ошибка здесь нарушит I-PHASE-LIFECYCLE-2.
