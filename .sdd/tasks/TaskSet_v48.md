# TaskSet_v48 — Phase 48: Session Dedup (Domain-Level, Safe)

Spec: specs/Spec_v48_SessionDedup.md
Plan: plans/Plan_v48.md

---

T-4801: [Conditional] Verify BC-47-D — PG fixtures TRUNCATE isolation

Status:               DONE
Spec ref:             Spec_v48 §2 — Out of Scope / deferral note
Invariants:           I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v48 §2, I-DB-TEST-1, I-DB-TEST-2]
produces_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
requires_invariants:  []
Inputs:               tests/integration/ (existing integration test fixtures)
Outputs:              tests/conftest.py или tests/integration/conftest.py (если изменение нужно)
Acceptance:           Проверить: если PG integration тесты используют TRUNCATE-based isolation между тестами — принять как выполненное. Иначе: добавить TRUNCATE в setUp/tearDown PG фикстур. `pytest tests/integration/ -x` → PASS без cross-test data leakage.
Depends on:           —

NOTE: Условный таск. Если BC-47-D был реализован в Phase 47 (T-4701..T-4710), пропустить.
Признак выполненности: `grep -r "TRUNCATE\|truncate_tables\|pg_truncate" tests/` возвращает результаты в integration conftest.

---

T-4802: SessionRecord + SessionsView frozen dataclasses

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-C, шаг 1)
Invariants:           I-SESSIONSVIEW-O1-1, I-GUARD-PURE-1
spec_refs:            [Spec_v48 §5, I-SESSIONSVIEW-O1-1, I-GUARD-PURE-1]
produces_invariants:  [I-SESSIONSVIEW-O1-1]
requires_invariants:  []
Inputs:               src/sdd/infra/projector.py
Outputs:              src/sdd/infra/projector.py
Acceptance:           `python3 -c "from sdd.infra.projector import SessionRecord, SessionsView; v = SessionsView(_index={}); assert v.get_last('X', 1) is None; print('OK')"` → OK. `SessionsView` и `SessionRecord` — frozen dataclass. `_index: dict[tuple[str, int | None], SessionRecord]`. `get_last` возвращает `None` при отсутствии ключа (O(1)).
Depends on:           —

---

T-4803: p_sessions.seq column migration + _handle_session_declared update

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-C2)
Invariants:           I-PSESSIONS-SEQ-1
spec_refs:            [Spec_v48 §5, I-PSESSIONS-SEQ-1]
produces_invariants:  [I-PSESSIONS-SEQ-1]
requires_invariants:  [I-SESSIONSVIEW-O1-1]
Inputs:               src/sdd/infra/projector.py
Outputs:              src/sdd/infra/projector.py
Acceptance:           1) Schema: `ALTER TABLE p_sessions ADD COLUMN IF NOT EXISTS seq BIGINT` (+ NOT NULL constraint после backfill существующих строк seq=0). 2) `_handle_session_declared` записывает `seq` из `event.seq` (sequence_id из event_log). 3) `psql -c "SELECT column_name FROM information_schema.columns WHERE table_name='p_sessions' AND column_name='seq'"` → возвращает строку.
Depends on:           T-4802

---

T-4804: _sync_p_sessions + build_sessions_view functions

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-C, шаги 3-5)
Invariants:           I-PROJECTION-FRESH-1, I-PROJECTION-SESSIONS-1, I-INVALIDATION-FINAL-1, I-PROJECTION-ORDER-1, I-DEDUP-PROJECTION-CONSISTENCY-1
spec_refs:            [Spec_v48 §5, I-PROJECTION-FRESH-1, I-PROJECTION-SESSIONS-1, I-INVALIDATION-FINAL-1, I-PROJECTION-ORDER-1]
produces_invariants:  [I-PROJECTION-FRESH-1, I-PROJECTION-SESSIONS-1, I-INVALIDATION-FINAL-1, I-PROJECTION-ORDER-1]
requires_invariants:  [I-PSESSIONS-SEQ-1, I-SESSIONSVIEW-O1-1]
Inputs:               src/sdd/infra/projector.py
Outputs:              src/sdd/infra/projector.py
Acceptance:           `python3 -c "from sdd.infra.projector import build_sessions_view, _sync_p_sessions; print('OK')"` → OK. `_sync_p_sessions(conn)`: находит `MAX(seq)` в p_sessions, применяет SessionDeclared из event_log с seq > MAX, ORDER BY seq ASC. `build_sessions_view(conn)`: SQL с `WHERE seq NOT IN (SELECT DISTINCT target_seq FROM invalidated_events WHERE transitive_invalidation = TRUE)`, ORDER BY seq ASC, последний seq per key побеждает, возвращает `SessionsView`.
Depends on:           T-4803

---

T-4805: SessionDedupPolicy — pure domain policy

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-A)
Invariants:           I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1, I-SESSION-INVALIDATION-1, I-GUARD-PURE-1
spec_refs:            [Spec_v48 §5, I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1, I-GUARD-PURE-1]
produces_invariants:  [I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1, I-SESSION-INVALIDATION-1]
requires_invariants:  [I-SESSIONSVIEW-O1-1]
Inputs:               src/sdd/infra/projector.py (SessionsView type)
Outputs:              src/sdd/domain/session/__init__.py, src/sdd/domain/session/policy.py
Acceptance:           1) `python3 -c "from sdd.domain.session.policy import SessionDedupPolicy; print('OK')"` → OK. 2) `should_emit(None, cmd)` → `True`. 3) `should_emit(view_с_совпадением, cmd)` → `False`. 4) `should_emit(view_без_совпадения, cmd)` → `True`. 5) Чистота: `grep -n "import psycopg\|open(" src/sdd/domain/session/policy.py` → пусто. 6) `SessionDedupPolicy` — frozen dataclass.
Depends on:           T-4802

---

T-4806: CommandSpec.dedup_policy field + execute_command Step 0

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-B, шаги 1-2)
Invariants:           I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1, I-PROJECTION-FRESH-1, I-COMMAND-ID-IMMUTABLE-1
spec_refs:            [Spec_v48 §5, I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1, I-PROJECTION-FRESH-1]
produces_invariants:  [I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1, I-PROJECTION-FRESH-1]
requires_invariants:  [I-PROJECTION-FRESH-1, I-SESSIONSVIEW-O1-1, I-SESSION-DEDUP-2]
Inputs:               src/sdd/commands/registry.py, src/sdd/domain/session/policy.py, src/sdd/infra/projector.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           1) `CommandSpec` имеет поле `dedup_policy: SessionDedupPolicy | None = None`. 2) В `execute_command`: если `spec.dedup_policy is not None` → Step 0 вызывает `_sync_p_sessions(conn)`, затем `sessions_view = build_sessions_view(conn)` (local variable). 3) Если `spec.dedup_policy is None` → Step 0 полностью пропускается (нет лишнего DB round-trip). 4) `GuardContext` не получает `sessions_view` — поля GuardContext неизменны. 5) `command_id` генерация (uuid4) не затронута.
Depends on:           T-4804, T-4805

---

T-4807: execute_command Step 2.5 — dedup check + observability (BC-48-B шаг 3 + BC-48-E)

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-B step 3, BC-48-E)
Invariants:           I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1, I-DEDUP-NOT-STRONG-1
spec_refs:            [Spec_v48 §5, I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1]
produces_invariants:  [I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1]
requires_invariants:  [I-SESSIONS-VIEW-LOCAL-1, I-SESSION-DEDUP-2]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           1) Step 2.5 расположен после guard pipeline, до `handler.handle()`. 2) При `should_emit() == False`: `logger.info("Session deduplicated: type=%s phase=%s", ...)` (уровень INFO, не WARNING). 3) `record_metric("session_dedup_skipped_total", labels={"session_type": ..., "phase_id": ...})`. 4) `return` без эмиссии событий — проекции и состояние не изменены. 5) Step 2.5 активен только если `spec.dedup_policy is not None`.
Depends on:           T-4806

---

T-4808: record-session CommandSpec wire-up (BC-48-D)

Status:               DONE
Spec ref:             Spec_v48 §5 — Types & Interfaces (BC-48-D)
Invariants:           I-SESSION-DEDUP-2, I-COMMAND-OBSERVABILITY-1
spec_refs:            [Spec_v48 §5, I-SESSION-DEDUP-2]
produces_invariants:  [I-SESSION-DEDUP-2]
requires_invariants:  [I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-SESSION-DEDUP-SCOPE-1]
Inputs:               src/sdd/commands/record_session.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/record_session.py
Acceptance:           1) `REGISTRY["record-session"]` CommandSpec содержит `dedup_policy=SessionDedupPolicy()`. 2) UC-48-1: `sdd record-session --type IMPLEMENT --phase 48` (×2) → ровно 1 `SessionDeclared` в event_log для (IMPLEMENT, 48). 3) UC-48-5: команда без `dedup_policy` (например, `sdd complete`) → Step 0 и Step 2.5 полностью пропускаются.
Depends on:           T-4807

---

T-4809: Unit tests — domain policy (BC-48-F тесты 1-5, 10)

Status:               DONE
Spec ref:             Spec_v48 §10 — Verification (unit tests 1-5, 10)
Invariants:           I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1, I-GUARD-PURE-1, I-DEDUP-DOMAIN-1
spec_refs:            [Spec_v48 §10, I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1, I-GUARD-PURE-1]
produces_invariants:  [I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1, I-GUARD-PURE-1, I-DEDUP-DOMAIN-1]
requires_invariants:  [I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1]
Inputs:               src/sdd/domain/session/policy.py, src/sdd/infra/projector.py (SessionsView)
Outputs:              tests/unit/domain/test_session_dedup.py
Acceptance:           `pytest tests/unit/domain/test_session_dedup.py -v` → PASS. Тесты: test_policy_no_view_returns_true, test_policy_no_matching_session_returns_true, test_policy_matching_session_returns_false, test_policy_different_type_returns_true, test_policy_different_phase_returns_true, test_policy_pure_no_io. Все 6 тестов PASS.
Depends on:           T-4805

---

T-4810: Unit tests — infra projector sessions (BC-48-F тесты 6-9, 16)

Status:               DONE
Spec ref:             Spec_v48 §10 — Verification (unit tests 6-9, 16)
Invariants:           I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1, I-SESSION-INVALIDATION-1, I-PROJECTION-ORDER-1, I-PSESSIONS-SEQ-1
spec_refs:            [Spec_v48 §10, I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1, I-PROJECTION-ORDER-1, I-PSESSIONS-SEQ-1]
produces_invariants:  [I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1, I-SESSION-INVALIDATION-1, I-PROJECTION-ORDER-1, I-PSESSIONS-SEQ-1]
requires_invariants:  [I-PSESSIONS-SEQ-1, I-SESSIONSVIEW-O1-1, I-PROJECTION-FRESH-1]
Inputs:               src/sdd/infra/projector.py (SessionRecord, SessionsView, build_sessions_view)
Outputs:              tests/unit/infra/test_projector_sessions.py
Acceptance:           `pytest tests/unit/infra/test_projector_sessions.py -v` → PASS. Тесты: test_sessions_view_get_last_o1, test_sessions_view_respects_transitive_invalidation, test_sessions_view_last_seq_wins, test_sessions_view_is_frozen, test_psessions_seq_column_populated. Все 5 тестов PASS.
Depends on:           T-4804

---

T-4811: Unit tests — commands dedup (BC-48-F тесты 11-15)

Status:               DONE
Spec ref:             Spec_v48 §10 — Verification (unit tests 11-15)
Invariants:           I-COMMAND-OBSERVABILITY-1, I-COMMAND-NOOP-2, I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1
spec_refs:            [Spec_v48 §10, I-COMMAND-OBSERVABILITY-1, I-COMMAND-NOOP-2, I-GUARD-CONTEXT-UNCHANGED-1]
produces_invariants:  [I-COMMAND-OBSERVABILITY-1, I-COMMAND-NOOP-2, I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1]
requires_invariants:  [I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1]
Inputs:               src/sdd/commands/registry.py (execute_command, CommandSpec)
Outputs:              tests/unit/commands/test_record_session_dedup.py
Acceptance:           `pytest tests/unit/commands/test_record_session_dedup.py -v` → PASS. Тесты: test_dedup_logs_info_not_warning, test_dedup_increments_metric_with_labels, test_noop_does_not_affect_projections, test_non_dedup_command_skips_step0, test_guard_context_has_no_sessions_view. Все 5 тестов PASS.
Depends on:           T-4808

---

T-4812: Integration tests — record-session dedup (BC-48-F тесты 17-20)

Status:               DONE
Spec ref:             Spec_v48 §10 — Verification (integration tests 17-20)
Invariants:           I-SESSION-DEDUP-2, I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1, I-SESSION-DEDUP-SCOPE-1, I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1
spec_refs:            [Spec_v48 §10, I-SESSION-DEDUP-2, I-SESSION-INVALIDATION-1, I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1]
produces_invariants:  [I-SESSION-DEDUP-2, I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1, I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1]
requires_invariants:  [I-SESSION-DEDUP-2, I-COMMAND-NOOP-1, I-SESSION-DEDUP-SCOPE-1]
Inputs:               src/sdd/commands/record_session.py, src/sdd/infra/projector.py, PostgreSQL (SDD_DATABASE_URL)
Outputs:              tests/unit/commands/test_record_session_dedup_integration.py
Acceptance:           `SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest tests/unit/commands/test_record_session_dedup_integration.py -v` → PASS. Тесты: test_double_record_session_emits_one_event, test_after_invalidate_record_session_emits_new, test_different_types_both_emitted, test_sync_before_sessions_view. Все 4 теста PASS. NOTE: тест на concurrency (UC-48-4) НЕ включается — I-DEDUP-NOT-STRONG-1 документирует best-effort ограничение.
Depends on:           T-4811, T-4810

---

T-4813: Smoke verification — end-to-end (BC-48-F §10 smoke)

Status:               DONE
Spec ref:             Spec_v48 §10 — Verification (Final Smoke, 7 команд)
Invariants:           I-SESSION-DEDUP-2, I-COMMAND-OBSERVABILITY-1, I-SESSION-INVALIDATION-1, I-SESSION-DEDUP-SCOPE-1, I-GUARD-CONTEXT-UNCHANGED-1, I-GUARD-PURE-1
spec_refs:            [Spec_v48 §10, I-SESSION-DEDUP-2, I-COMMAND-OBSERVABILITY-1, I-GUARD-CONTEXT-UNCHANGED-1]
produces_invariants:  [I-SESSION-DEDUP-2, I-COMMAND-OBSERVABILITY-1, I-SESSION-INVALIDATION-1, I-SESSION-DEDUP-SCOPE-1, I-GUARD-CONTEXT-UNCHANGED-1, I-GUARD-PURE-1]
requires_invariants:  [I-SESSION-DEDUP-2, I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1, I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1]
Inputs:               sdd CLI (полностью собранный после T-4808), PostgreSQL
Outputs:              (нет файлов — только верификация)
Acceptance:           Все 7 smoke-команд из Spec_v48 §10 выполняются без ошибок: (1) двойной вызов → 1 событие; (2) второй вызов → INFO "Session deduplicated" в stdout; (3) invalidate → разрешает новый (итого 2 события); (4) разные типы PLAN+DECOMPOSE → оба создаются; (5) GuardContext не содержит sessions_view; (6) policy.py без IO импортов; (7) `pytest tests/unit -k "dedup or session" -v` → все PASS.
Depends on:           T-4812

---

<!-- Granularity: 13 tasks (TG-2: 10–30). All tasks independently implementable (TG-1). -->
<!-- Every task declares Invariants Covered (TG-3). -->
