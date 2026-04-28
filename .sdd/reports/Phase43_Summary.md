# Phase 43 Summary — Unified PostgreSQL EventLog

Status: COMPLETE  
DoD: PASS  
Spec: Spec_v43_UnifiedPostgresEventLog.md  
Metrics: [Metrics_Phase43.md](Metrics_Phase43.md)

---

## Tasks

| Task | Status | Description |
|------|--------|-------------|
| T-4301 | DONE | BC-43-A: event_store_url() + is_production_event_store() в paths.py |
| T-4302 | DONE | BC-43-B: lazy duckdb import + PG-routing в open_sdd_connection() |
| T-4303 | DONE | BC-43-C: EventLogKernelProtocol (runtime_checkable Protocol) |
| T-4304 | DONE | BC-43-D: PostgresEventLog — PG DDL, append, replay, idempotency, optimistic lock |
| T-4305 | DONE | BC-43-E: Projector — apply domain events к p_* таблицам |
| T-4306 | DONE | BC-43-F: execute_and_project — инжекция Projector, _apply_projector_safe |
| T-4307 | DONE | BC-43-G: удаление duckdb из pyproject.toml, psycopg[binary] → mandatory |
| T-4308 | DONE | BC-43-H: get_current_state() PG-ветка (event_log + sequence_id + JSONB guard) |
| T-4309 | DONE | Unit тесты: протокол, routing, production guard, NOOP, idempotency (tests 1–9) |
| T-4310 | DONE | Интеграционные тесты PG EventLog + Projector (tests 10–18, 9/9 PASS) |
| T-4311 | DONE | BC-43-G финал: duckdb удалён из зависимостей pyproject.toml |

**Итого: 11/11 DONE.**

---

## Invariant Coverage

| Invariant | Status | Covered в |
|-----------|--------|-----------|
| I-EVENT-1 | PASS | test_10, test_18 (static AST) |
| I-EVENT-2 | PASS | test_10 |
| I-ORDER-1 | PASS | test_10 |
| I-OPTLOCK-1 | PASS | test_11 |
| I-IDEM-SCHEMA-1 | PASS | test_12 |
| I-PROJ-1 | PASS | test_13, test_14, test_16 |
| I-REPLAY-1 | PASS | test_15 |
| I-FAIL-1 | PASS | test_16, test_17 |
| I-REBUILD-ATOMIC-1 | PASS | test_15 |
| I-PROJ-VERSION-1 | PASS | test_15 |
| I-PROJ-WRITE-1 | PASS | test_18 (static AST grep) |
| I-ELK-PROTO-1 | PASS | test_pg_eventlog_protocol.py test_1, test_2 |
| I-EVENT-STORE-URL-1 | PASS | test_pg_eventlog_protocol.py test_3, test_4 |
| I-PROD-GUARD-1 | PASS | test_pg_eventlog_protocol.py test_5, test_6 |
| I-PROJ-NOOP-1 | PASS | test_pg_eventlog_protocol.py test_7 |
| I-PROJ-SAFE-1 | PASS | test_pg_eventlog_protocol.py test_8, test_17 |
| I-LAZY-DUCK-1 | PASS | test_pg_eventlog_protocol.py test_9 |
| I-PG-DDL-1 | PASS | PostgresEventLog._ensure_schema() DDL |
| I-LAYER-1 | PASS | test_16 (TX1→TX2→YAML pipeline) |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §1 Scope (BC-43-A..H) | полностью покрыт (11 задач) |
| §2 Architecture / BCs | все 8 BC реализованы |
| §3 Domain Events / Projector dispatch | полностью (10 handlers в Projector) |
| §4 Types & Interfaces | EventLogKernelProtocol, PostgresEventLog, Projector |
| §5 Invariants (19 новых + 2 обновлённых) | PASS для всех проверяемых |
| §6 Pre/Post Conditions | верифицированы тестами 10–18 |
| §7 Use Cases UC-43-1..4 | UC-1,2,3 покрыты тестами; UC-4 покрыт unit-тестами |

---

## Tests

| Файл | Тесты | Статус |
|------|-------|--------|
| `tests/unit/infra/test_pg_eventlog_protocol.py` | 1–10 (unit, without PG) | PASS |
| `tests/integration/test_pg_event_log.py` | 10–18 (integration, live PG) | 9/9 PASS |
| `tests/integration/test_pg_projector.py` | Projector apply/idempotent/pipeline/failure | PASS |
| `tests/integration/test_pg_rebuild_state.py` | RebuildStateHandler PG | PASS |
| `tests/integration/test_pg_init_project.py` | InitProject schemas | PASS |

`pytest tests/integration/test_pg_event_log.py -m pg -v` → 9/9 PASS с live PostgreSQL.

---

## Key Decisions

- **EventLogKernelProtocol** введён как `@runtime_checkable Protocol` — позволяет тестировать Write Kernel с `FakeEventLog` без реальной БД (UC-43-4).
- **TX1/TX2 isolation** (I-FAIL-1): Projector failure swallowed в `_apply_projector_safe` — event_log никогда не rollback-ается из-за сбоя проекции.
- **Статический AST-анализ** (test_18): вместо DB-level REVOKE (Phase 44+) применён code-level enforcement через ast.walk по SQL string literals.
- **p_meta singleton** (`last_applied_sequence_id`): позволяет детектировать stale-проекции без дополнительных запросов к event_log.

---

## Anomalies & Improvement Hypotheses

Аномалий по метрикам не обнаружено (см. Metrics_Phase43.md).

**Гипотезы улучшений:**
1. **DB-level enforcement Phase 44**: заменить code-review guard I-PROJ-WRITE-1 на `REVOKE INSERT/UPDATE/DELETE ON p_* FROM app_user` + отдельный `projector_user`.
2. **Stale projection warning**: добавить в `sdd show-state` автоматический check `p_meta.last_applied_sequence_id < MAX(event_log.sequence_id)` с WARNING-сообщением (I-PROJ-VERSION-1 наблюдение).
3. **RLS для event_log**: PostgreSQL Row Level Security как альтернатива application-level I-EVENT-1 (упомянуто в спеке как Phase 44+).

---

## Decision

**READY** — Фаза 43 COMPLETE. DuckDB удалён, PostgreSQL EventLog является единственным SSOT.  
Все 11 задач DONE. DoD PASS. Spec_v43 операционально утверждён для downstream фаз.
