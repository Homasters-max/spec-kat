# TaskSet_v46 — Phase 46: Remove DuckDB (DESTRUCTIVE)

Spec: specs/Spec_v46_RemoveDuckDB.md
Plan: plans/Plan_v46.md

---

T-4601: invalidate_event.py — PG migration + --force guard

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-H — invalidate_event.py PG migration
Invariants:           I-INVALIDATE-PG-1, I-DB-ENTRY-1
spec_refs:            [Spec_v46 §3 BC-46-H, §7 BC-46-H, §10 tests 4,9,19, I-INVALIDATE-PG-1, I-DB-ENTRY-1]
produces_invariants:  [I-INVALIDATE-PG-1]
requires_invariants:  [I-DB-1, I-MIGRATION-1]
Inputs:               src/sdd/commands/invalidate_event.py
Outputs:              src/sdd/commands/invalidate_event.py, tests/commands/test_invalidate_event.py
Acceptance:           test_invalidate_event_uses_pg_syntax PASS; test_invalidate_event_rejects_production_without_force PASS; test_invalidate_event_pg_roundtrip PASS; grep "event_store_file\|events WHERE seq\|= ?\|psycopg.connect" src/sdd/commands/invalidate_event.py → пусто
Depends on:           —

---

T-4602: record_session.py — SessionDeclared stable command_id dedup

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-J — SessionDeclared idempotent dedup via stable command_id
Invariants:           I-SESSION-DEDUP-1
spec_refs:            [Spec_v46 §3 BC-46-J, §8 UC-46-5, §10 tests 10,11,12, I-SESSION-DEDUP-1]
produces_invariants:  [I-SESSION-DEDUP-1]
requires_invariants:  [I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/record_session.py
Outputs:              src/sdd/commands/record_session.py, tests/commands/test_record_session.py
Acceptance:           test_session_dedup_same_utc_day PASS; test_session_dedup_different_utc_day PASS; test_stable_command_id_uses_utc PASS; повторный sdd record-session в тот же UTC-день → нет нового SessionDeclared в event_log
Depends on:           —

---

T-4603: el_kernel.py — minimal extraction

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-A — el_kernel.py minimal extraction
Invariants:           I-EL-KERNEL-WIRED-1
spec_refs:            [Spec_v46 §3 BC-46-A, §7 BC-46-A, §10 tests 14,15,16, I-EL-KERNEL-WIRED-1]
produces_invariants:  [I-EL-KERNEL-WIRED-1]
requires_invariants:  [I-INVALIDATE-PG-1]
Inputs:               src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/el_kernel.py, src/sdd/infra/event_log.py, tests/infra/test_el_kernel.py
Acceptance:           test_el_kernel_resolve_batch_id PASS; test_el_kernel_check_optimistic_lock PASS; test_el_kernel_filter_duplicates PASS; python3 -c "from sdd.infra.el_kernel import EventLogKernel; print('OK')" → OK; pytest PASS (поведение append идентично)
Depends on:           T-4601

---

T-4604: db.py + connection.py — удаление DuckDB-ветки

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-B, BC-46-C — DuckDB removal from db.py + connection.py
Invariants:           I-NO-DUCKDB-1, I-DB-1
spec_refs:            [Spec_v46 §3 BC-46-B, §3 BC-46-C, §7 BC-46-B, §8 UC-46-1, §10 tests 1,5,17, I-NO-DUCKDB-1, I-DB-1]
produces_invariants:  [I-NO-DUCKDB-1]
requires_invariants:  [I-INVALIDATE-PG-1, I-EL-KERNEL-WIRED-1]
Inputs:               src/sdd/infra/db.py, src/sdd/db/connection.py
Outputs:              src/sdd/infra/db.py, src/sdd/db/connection.py, tests/infra/test_db.py
Acceptance:           test_open_sdd_connection_rejects_duckdb_path PASS; grep -r "duckdb" src/sdd/ --include="*.py" | grep -v "DeprecationWarning\|event_store_file" → пусто; DuckDBLockTimeoutError и _restart_sequence() отсутствуют в codebase; pytest PASS
Depends on:           T-4601, T-4603

---

T-4605: paths.py — event_store_file() DeprecationWarning

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-D — paths.py event_store_file() DeprecationWarning
Invariants:           I-NO-DUCKDB-1
spec_refs:            [Spec_v46 §3 BC-46-D, §10 test 6, I-NO-DUCKDB-1]
produces_invariants:  []
requires_invariants:  [I-INVALIDATE-PG-1]
Inputs:               src/sdd/infra/paths.py
Outputs:              src/sdd/infra/paths.py, tests/infra/test_paths.py
Acceptance:           test_event_store_file_emits_deprecation_warning PASS; вызов event_store_file() → DeprecationWarning с инструкцией; pytest PASS
Depends on:           T-4601

---

T-4606: PG test fixtures + pyproject.toml верификация

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-E, BC-46-F — PG test fixtures + pyproject.toml check
Invariants:           I-DB-TEST-1, I-NO-DUCKDB-1
spec_refs:            [Spec_v46 §3 BC-46-E, §3 BC-46-F, §7 BC-46-E, §10 tests 2,7, I-DB-TEST-1, I-NO-DUCKDB-1]
produces_invariants:  [I-DB-TEST-1]
requires_invariants:  [I-NO-DUCKDB-1]
Inputs:               tests/conftest.py, pyproject.toml
Outputs:              tests/conftest.py, pyproject.toml
Acceptance:           test_duckdb_not_in_dependencies PASS; test_pg_test_db_fixture_isolated PASS; pytest -m "not pg" → PASS; in_memory_db и tmp_db_path фикстуры удалены или заменены pg_test_db; grep "duckdb" pyproject.toml → пусто
Depends on:           T-4604

---

T-4607: reducer — suppress DEBUG для инвалидированных событий (deferrable)

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-I — reducer suppress DEBUG for invalidated events
Invariants:           I-INVALIDATE-PG-1
spec_refs:            [Spec_v46 §3 BC-46-I, §7 BC-46-I, §10 test 13, §11 Architectural Debt]
produces_invariants:  []
requires_invariants:  [I-NO-DUCKDB-1]
Inputs:               src/sdd/infra/projections.py (или файл где находится reducer/replay)
Outputs:              src/sdd/infra/projections.py, tests/infra/test_reducer_invalidated.py
Acceptance:           test_reducer_debug_for_invalidated_seq PASS; replay с инвалидированным дублем → нет WARNING, только DEBUG; grep "_get_invalidated_seqs" → функция доступна в контексте reducer; если _get_invalidated_seqs недоступен без рефактора — зафиксировать как BC-47-B и пропустить задачу
Depends on:           T-4604

---

T-4609: event_log.py — удалить DuckDB API, мигрировать на PG

Status:               DONE
Spec ref:             Plan_v46 T-4609 — migrate sdd_append/sdd_replay/EventLog to PG
Invariants:           I-NO-DUCKDB-1
spec_refs:            [Plan_v46 T-4609]
produces_invariants:  []
requires_invariants:  [I-NO-DUCKDB-1]
Inputs:               src/sdd/infra/event_log.py, tests/unit/infra/test_event_log*.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           grep -n "class EventLog" event_log.py → пусто (EventLog = alias); pytest tests/unit/infra/ -x → 0 FAILED (после удаления DuckDB unit тестов); sdd_append/sdd_replay работают с PG соединением
Depends on:           T-4604, T-4606

---

T-4610: тесты — заменить .duckdb пути на pg_test_db + удалить DuckDB-only тесты

Status:               DONE
Spec ref:             Plan_v46 T-4610 — replace hardcoded duckdb paths in ~49 test files
Invariants:           I-DB-TEST-1
spec_refs:            [Plan_v46 T-4610]
produces_invariants:  []
requires_invariants:  [I-NO-DUCKDB-1, I-DB-TEST-1]
Inputs:               tests/unit/commands/*.py, tests/unit/hooks/*.py, tests/unit/guards/*.py, tests/test_db_connection.py
Outputs:              (test files updated)
Acceptance:           pytest --collect-only → 0 ERROR; pytest tests/unit/ -x → 0 FAILED
Depends on:           T-4609

---

T-4608: enforcement tests — I-NO-DUCKDB-1 + I-DB-ENTRY-1 + final smoke

Status:               DONE
Spec ref:             Spec_v46 §3 BC-46-G, §10 Verification — enforcement grep tests + final smoke
Invariants:           I-NO-DUCKDB-1, I-DB-ENTRY-1, I-INVALIDATE-PG-1, I-SESSION-DEDUP-1
spec_refs:            [Spec_v46 §3 BC-46-G, §10 tests 1,2,3,4,17,18,19, I-NO-DUCKDB-1, I-DB-ENTRY-1]
produces_invariants:  [I-NO-DUCKDB-1, I-DB-ENTRY-1]
requires_invariants:  [I-NO-DUCKDB-1, I-DB-TEST-1, I-INVALIDATE-PG-1]
Inputs:               src/sdd/ (grep targets), tests/
Outputs:              tests/test_enforcement_phase46.py
Acceptance:           test_no_duckdb_imports_in_src PASS; test_duckdb_not_in_dependencies PASS; test_no_direct_psycopg_connect_in_src PASS; test_invalidate_event_uses_pg_syntax PASS; test_pg_full_pipeline_no_duckdb PASS; test_pg_rebuild_state_from_scratch PASS; final smoke §10 шаги 1–7 PASS; SDD_DATABASE_URL=... pytest --cov=sdd → 0 FAILED
Depends on:           T-4604, T-4606, T-4607

---

<!-- Granularity: 8 tasks (TG-2: 10–30 recommended; 8 допустимо при высокой связности BC). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
