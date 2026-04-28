# TaskSet_v43 — Phase 43: Unified PostgreSQL EventLog

Spec: specs/Spec_v43_UnifiedPostgresEventLog.md
Plan: plans/Plan_v43.md

---

T-4301: BC-43-A — URL-aware routing layer (paths.py)

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-A, §4 Types (paths.py), §5 I-EVENT-STORE-URL-1, I-PROD-GUARD-1, §6 BC-43-A
Invariants:           I-EVENT-STORE-URL-1, I-PROD-GUARD-1
spec_refs:            [Spec_v43 §2 BC-43-A, §4, §5 I-EVENT-STORE-URL-1, §5 I-PROD-GUARD-1]
produces_invariants:  [I-EVENT-STORE-URL-1, I-PROD-GUARD-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/paths.py, src/sdd/infra/db.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/paths.py (add event_store_url(), is_production_event_store()); src/sdd/infra/db.py (replace inline Path.resolve() guard with is_production_event_store()); src/sdd/infra/event_log.py (replace inline Path.resolve() guards — 3 locations total)
Acceptance:           test_event_store_url_pg_when_env_set PASS; test_event_store_url_duckdb_fallback PASS; test_is_production_event_store_pg PASS; test_is_production_event_store_duckdb PASS; grep shows no inline `Path(db_path).resolve() == event_store_file().resolve()` outside paths.py
Depends on:           —

---

T-4302: BC-43-B — Lazy DuckDB import + PG routing in db.py

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-B, §5 I-LAZY-DUCK-1, §6 BC-43-B
Invariants:           I-LAZY-DUCK-1, I-DB-1
spec_refs:            [Spec_v43 §2 BC-43-B, §5 I-LAZY-DUCK-1]
produces_invariants:  [I-LAZY-DUCK-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/infra/db.py, src/sdd/db/connection.py
Outputs:              src/sdd/infra/db.py (move top-level `import duckdb` → lazy inside DuckDB branch; add PG URL branch routing to open_db_connection())
Acceptance:           test_open_sdd_connection_no_top_level_duckdb_import PASS; import of sdd.infra.db succeeds without duckdb installed
Depends on:           T-4301

---

T-4303: BC-43-C — EventLogKernelProtocol interface

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-C, §4 Types (EventLogKernelProtocol), §5 I-ELK-PROTO-1
Invariants:           I-ELK-PROTO-1
spec_refs:            [Spec_v43 §2 BC-43-C, §4 EventLogKernelProtocol, §5 I-ELK-PROTO-1]
produces_invariants:  [I-ELK-PROTO-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/event_log.py (add @runtime_checkable EventLogKernelProtocol with max_seq() and append())
Acceptance:           test_execute_command_uses_injected_event_log PASS; test_fake_event_log_captures_appended_events PASS; isinstance(FakeEventLog(), EventLogKernelProtocol) == True
Depends on:           T-4301

---

T-4304: BC-43-D — PostgresEventLog full implementation

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-D, §4 Types (PostgresEventLog), §5 I-PG-DDL-1, I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1, §6 BC-43-D
Invariants:           I-PG-DDL-1, I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1
spec_refs:            [Spec_v43 §2 BC-43-D, §4 PostgresEventLog, §5 I-PG-DDL-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1]
produces_invariants:  [I-PG-DDL-1, I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1]
requires_invariants:  [I-EVENT-STORE-URL-1, I-LAZY-DUCK-1, I-DB-1]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/db.py, src/sdd/db/connection.py
Outputs:              src/sdd/infra/event_log.py (add PostgresEventLog class: DDL event_log+p_meta+indexes, append() with optimistic lock, replay(), exists_command(), exists_semantic(), get_error_count())
Acceptance:           test_pg_event_log_append_replay PASS; test_pg_event_log_optimistic_lock PASS; test_pg_event_log_idempotency PASS
Depends on:           T-4301, T-4302

---

T-4305: BC-43-E (1/2) — Projector.apply() dispatch handlers

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-E, §3 Projector dispatch map, §4 Types (Projector), §5 I-PROJ-1, I-PROJ-NOOP-1, I-TABLE-SEP-1, I-EVENT-PURE-1
Invariants:           I-PROJ-1, I-PROJ-NOOP-1, I-TABLE-SEP-1, I-EVENT-PURE-1
spec_refs:            [Spec_v43 §2 BC-43-E, §3 dispatch map, §4 Projector, §5 I-PROJ-1, I-PROJ-NOOP-1]
produces_invariants:  [I-PROJ-1, I-PROJ-NOOP-1, I-TABLE-SEP-1]
requires_invariants:  [I-PG-DDL-1, I-EVENT-1]
Inputs:               src/sdd/infra/event_log.py (PostgresEventLog.replay()), src/sdd/core/events.py
Outputs:              src/sdd/infra/projector.py (new module: Projector class with __init__, apply(), close(), __enter__, __exit__; handlers for TaskImplemented, TaskValidated, PhaseInitialized, PhaseCompleted, PhaseContextSwitched, SessionDeclared, DecisionRecorded, InvariantRegistered, SpecApproved; PhaseStarted → NO-OP; unknown → NO-OP+DEBUG)
Acceptance:           test_projector_noop_for_unknown_event PASS; test_pg_projector_apply_task_implemented PASS; test_pg_projector_idempotent PASS
Depends on:           T-4303, T-4304

---

T-4306: BC-43-E (2/2) — Projector.rebuild() atomic transaction

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-E, §5 I-REPLAY-1, I-REBUILD-ATOMIC-1, I-PROJ-WRITE-1, I-PROJ-VERSION-1, §6 Rebuild, §7 UC-43-3
Invariants:           I-REPLAY-1, I-REBUILD-ATOMIC-1, I-PROJ-WRITE-1, I-PROJ-VERSION-1
spec_refs:            [Spec_v43 §2 BC-43-E, §5 I-REBUILD-ATOMIC-1, I-REPLAY-1, I-PROJ-VERSION-1, §7 UC-43-3]
produces_invariants:  [I-REPLAY-1, I-REBUILD-ATOMIC-1, I-PROJ-VERSION-1]
requires_invariants:  [I-PROJ-1, I-PROJ-NOOP-1]
Inputs:               src/sdd/infra/projector.py (Projector from T-4305), src/sdd/infra/event_log.py (PostgresEventLog.replay())
Outputs:              src/sdd/infra/projector.py (add rebuild(pg_conn) method: BEGIN TX → TRUNCATE p_* → replay() → Projector.apply() each event → UPDATE p_meta → COMMIT)
Acceptance:           test_pg_rebuild_state PASS; TRUNCATE+replay+p_meta UPDATE in single transaction; p_meta.last_applied_sequence_id == MAX(event_log.sequence_id) after rebuild
Depends on:           T-4305

---

T-4307: BC-43-F — Write pipeline injection (registry.py)

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-F, §4 Types (registry.py changes), §5 I-ELK-PROTO-1, I-FAIL-1, I-PROJ-SAFE-1, I-LAYER-1, §6 BC-43-F, §7 UC-43-1, UC-43-2, UC-43-4
Invariants:           I-ELK-PROTO-1, I-FAIL-1, I-PROJ-SAFE-1, I-LAYER-1
spec_refs:            [Spec_v43 §2 BC-43-F, §4 registry.py, §5 I-FAIL-1, I-PROJ-SAFE-1, §7 UC-43-1, UC-43-4]
produces_invariants:  [I-FAIL-1, I-PROJ-SAFE-1, I-LAYER-1]
requires_invariants:  [I-ELK-PROTO-1, I-PROJ-1, I-REBUILD-ATOMIC-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/infra/event_log.py, src/sdd/infra/projector.py
Outputs:              src/sdd/commands/registry.py (add event_log param to execute_command(); add projector param + _build_projector_if_configured() + _apply_projector_safe() to execute_and_project())
Acceptance:           test_apply_projector_safe_swallows_exception PASS; test_pg_execute_and_project_full_pipeline PASS; test_pg_projector_failure_does_not_rollback_event_log PASS
Depends on:           T-4303, T-4305, T-4306

---

T-4308: BC-43-H — get_current_state() PG branch

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-H, §5 I-DB-1, I-REPLAY-1, §6 BC-43-H
Invariants:           I-DB-1, I-REPLAY-1
spec_refs:            [Spec_v43 §2 BC-43-H, §5 I-DB-1, §6 BC-43-H]
produces_invariants:  [I-DB-1]
requires_invariants:  [I-EVENT-STORE-URL-1, I-LAZY-DUCK-1]
Inputs:               src/sdd/infra/projections.py, src/sdd/infra/paths.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/projections.py (add PG branch in get_current_state(): SELECT from event_log, column sequence_id, JSONB-safe payload deserialization guard: isinstance(row_payload, dict) check)
Acceptance:           test_get_current_state_jsonb_dict_payload PASS; PG branch uses event_log+sequence_id; DuckDB branch (events+seq) unchanged
Depends on:           T-4301, T-4302

---

T-4309: M7 — Unit tests (10 tests, no DB)

Status:               DONE
Spec ref:             Spec_v43 §9 Unit Tests (тесты 1–10)
Invariants:           I-ELK-PROTO-1, I-EVENT-STORE-URL-1, I-PROD-GUARD-1, I-PROJ-NOOP-1, I-FAIL-1, I-PROJ-SAFE-1, I-LAZY-DUCK-1
spec_refs:            [Spec_v43 §9 Unit Tests]
produces_invariants:  [I-ELK-PROTO-1, I-EVENT-STORE-URL-1, I-PROD-GUARD-1, I-PROJ-NOOP-1, I-FAIL-1, I-PROJ-SAFE-1, I-LAZY-DUCK-1]
requires_invariants:  [I-ELK-PROTO-1, I-EVENT-STORE-URL-1, I-PROD-GUARD-1, I-PROJ-NOOP-1, I-LAZY-DUCK-1]
Inputs:               src/sdd/infra/paths.py, src/sdd/infra/db.py, src/sdd/infra/event_log.py, src/sdd/infra/projector.py, src/sdd/commands/registry.py, src/sdd/infra/projections.py
Outputs:              tests/unit/infra/test_pg_eventlog_protocol.py (tests 1–10: FakeEventLog injection, event_store_url routing, is_production_event_store, projector NOOP, _apply_projector_safe swallows, lazy duckdb import, JSONB dict guard)
Acceptance:           pytest tests/unit/infra/test_pg_eventlog_protocol.py -v → 10/10 PASS; no real DB connections opened during unit test suite
Depends on:           T-4301, T-4302, T-4303, T-4305, T-4307, T-4308

---

T-4310: M8 — Integration tests (9 tests, pytest -m pg)

Status:               DONE
Spec ref:             Spec_v43 §9 Integration Tests (тесты 10–18)
Invariants:           I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1, I-PROJ-1, I-REPLAY-1, I-FAIL-1, I-REBUILD-ATOMIC-1, I-PROJ-VERSION-1
spec_refs:            [Spec_v43 §9 Integration Tests, §5 I-EVENT-1, I-OPTLOCK-1, I-REBUILD-ATOMIC-1]
produces_invariants:  [I-EVENT-1, I-EVENT-2, I-ORDER-1, I-OPTLOCK-1, I-IDEM-SCHEMA-1, I-PROJ-1, I-REPLAY-1, I-REBUILD-ATOMIC-1, I-PROJ-VERSION-1]
requires_invariants:  [I-PG-DDL-1, I-PROJ-1, I-REPLAY-1, I-REBUILD-ATOMIC-1, I-FAIL-1]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/projector.py, src/sdd/commands/registry.py, docker-compose.yml, tests/conftest.py
Outputs:              tests/integration/test_pg_event_log.py (tests 10–18: append/replay, optimistic lock, idempotency, Projector apply, idempotent Projector, rebuild, full pipeline TX1+TX2+YAML, Projector failure isolation, no direct mutations grep/ast check)
Acceptance:           pytest tests/integration/test_pg_event_log.py -m pg -v → 9/9 PASS with live PostgreSQL (docker-compose up)
Depends on:           T-4304, T-4305, T-4306, T-4307

---

T-4311: BC-43-G — DuckDB removal from pyproject.toml

Status:               DONE
Spec ref:             Spec_v43 §2 BC-43-G, §8 (порядок применения BC-43-G), §5 I-LAZY-DUCK-1, I-MIGRATION-1
Invariants:           I-LAZY-DUCK-1, I-MIGRATION-1
spec_refs:            [Spec_v43 §2 BC-43-G, §8 порядок BC-43-G, §5 I-MIGRATION-1]
produces_invariants:  [I-MIGRATION-1]
requires_invariants:  [I-LAZY-DUCK-1, I-REPLAY-1, I-REBUILD-ATOMIC-1]
Inputs:               pyproject.toml, scripts/migrate_duckdb_to_pg.py (pre-existing), tests/integration/ (pytest -m pg PASS from T-4310)
Outputs:              pyproject.toml (remove duckdb from dependencies; make psycopg[binary]>=3.1 mandatory)
Acceptance:           test_migration_replay_parity PASS (duck_state == pg_state); pytest -m pg → all PASS; SDD_DATABASE_URL=<pg_url> sdd show-state exits 0 without duckdb installed
Depends on:           T-4309, T-4310

---

<!-- Granularity: 11 tasks (10–30 recommended by TG-2). -->
<!-- Every task independently implementable and independently testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Phase 43 не вводит новых domain events (Spec_v43 §3). Правило I-EREG-SCOPE-1 не применяется.
