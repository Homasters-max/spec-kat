# Phase 48 Summary — Session Dedup (Domain-Level, Safe)

Status: READY

---

## Tasks

| Task | Status | Описание |
|------|--------|----------|
| T-4801 | DONE | PG-fixture isolation — `pg_test_db` fixture, conftest cleanup |
| T-4802 | DONE | `SessionRecord` + `SessionsView` (frozen dataclass, O(1) index) в `infra/projector.py` |
| T-4803 | DONE | `p_sessions.seq BIGINT NOT NULL` — schema migration + backfill из `event_log.sequence_id` |
| T-4804 | DONE | `_sync_p_sessions(conn)` + `build_sessions_view(conn)` с транзитивным фильтром инвалидации |
| T-4805 | DONE | `SessionDedupPolicy.should_emit()` — pure domain policy в `domain/session/policy.py` |
| T-4806 | DONE | `CommandSpec.dedup_policy` field + Pre-Step в `execute_command` (conditional sync) |
| T-4807 | DONE | Step 2.5 в `execute_command` — dedup check, INFO log, metric `session_dedup_skipped_total` |
| T-4808 | DONE | `REGISTRY["record-session"]` wire-up: `dedup_policy=SessionDedupPolicy()` |
| T-4809 | DONE | Unit tests: `tests/unit/domain/test_session_dedup.py` (6 тестов, policy purity) |
| T-4810 | DONE | Unit tests: `tests/unit/infra/test_projector_sessions.py` (5 тестов, O(1), invalidation) |
| T-4811 | DONE | Unit tests: `tests/unit/commands/test_record_session_dedup.py` (5 тестов, observability) |
| T-4812 | DONE | Integration tests: `tests/unit/commands/test_record_session_dedup_integration.py` (4 теста, PG) |
| T-4813 | DONE | Верификация: smoke tests + `pytest tests/unit -k "dedup or session"` → 95/95 PASS |

**Итого: 13/13 DONE**

---

## Invariant Coverage

| Invariant | Покрытие | Задачи |
|-----------|----------|--------|
| I-SESSION-DEDUP-2 | PASS | T-4805, T-4808, T-4809, T-4812, T-4813 |
| I-SESSION-DEDUP-SCOPE-1 | PASS | T-4805, T-4809, T-4812, T-4813 |
| I-SESSION-INVALIDATION-1 | PASS | T-4805, T-4812, T-4813 |
| I-INVALIDATION-FINAL-1 | PASS | T-4804, T-4810, T-4812 |
| I-DEDUP-DOMAIN-1 | PASS | T-4805, T-4809 |
| I-SESSIONSVIEW-O1-1 | PASS | T-4802, T-4810 |
| I-PSESSIONS-SEQ-1 | PASS | T-4803, T-4810 |
| I-PROJECTION-FRESH-1 | PASS | T-4804, T-4806, T-4812 |
| I-PROJECTION-SESSIONS-1 | PASS | T-4804 |
| I-PROJECTION-ORDER-1 | PASS | T-4804, T-4810 |
| I-DEDUP-PROJECTION-CONSISTENCY-1 | PASS | T-4804, T-4812 |
| I-GUARD-PURE-1 | PASS | T-4802, T-4805, T-4813 |
| I-GUARD-CONTEXT-UNCHANGED-1 | PASS | T-4806, T-4811, T-4813 |
| I-SESSIONS-VIEW-LOCAL-1 | PASS | T-4806, T-4811 |
| I-COMMAND-NOOP-1 | PASS | T-4807 |
| I-COMMAND-NOOP-2 | PASS | T-4807, T-4811 |
| I-COMMAND-OBSERVABILITY-1 | PASS | T-4807, T-4808, T-4811, T-4813 |
| I-COMMAND-ID-IMMUTABLE-1 | PASS | T-4806 |
| I-DEDUP-NOT-STRONG-1 | PASS | T-4807 |
| I-DB-TEST-1 | PASS | T-4801 |
| I-DB-TEST-2 | PASS | T-4801 |

---

## Spec Coverage

| Раздел Spec_v48 | Покрытие |
|-----------------|----------|
| §0 Goal | covered — дедупликация без изменения семантики EventLog |
| §1 Non-Goals | covered — command_id, replay, GuardContext не изменены |
| §2 Scope | covered — все BC-48-A..F реализованы |
| §3 Architecture | covered — SessionsView local var, dedup policy pre-guard |
| §4 Domain Events | covered — новые события не вводились |
| §5 Types & Interfaces | covered — SessionRecord, SessionsView, SessionDedupPolicy, CommandSpec |
| §6 Migration | covered — p_sessions.seq NOT NULL, backfill из event_log |
| §7 Behaviour (dedup flow) | covered — Step 0 + Step 2.5 в execute_command |
| §8 Use Cases UC-48-1..5 | covered — все UC верифицированы тестами |
| §9 Build Commands | covered |
| §10 Verification | covered — 20 unit/integration тестов + smoke 1,4,5,6,7 PASS |
| §11 Architectural Debt | documented (Phase 49+) |

---

## Tests

| Тест | Статус |
|------|--------|
| `pytest tests/unit -k "dedup or session"` | **95/95 PASS** |
| `test_policy_no_view_returns_true` | PASS |
| `test_policy_matching_session_returns_false` | PASS |
| `test_policy_different_type_returns_true` | PASS |
| `test_policy_pure_no_io` | PASS |
| `test_sessions_view_respects_transitive_invalidation` | PASS |
| `test_sessions_view_is_frozen` | PASS |
| `test_dedup_logs_info_not_warning` | PASS |
| `test_dedup_increments_metric_with_labels` | PASS |
| `test_noop_does_not_affect_projections` | PASS |
| `test_guard_context_has_no_sessions_view` | PASS |
| `test_double_record_session_emits_one_event` (PG) | PASS |
| `test_after_invalidate_record_session_emits_new` (PG) | PASS |
| `test_different_types_both_emitted` (PG) | PASS |
| `test_sync_before_sessions_view` (PG) | PASS |

---

## Metrics

См. [Metrics_Phase48.md](Metrics_Phase48.md) — аномалий не обнаружено.

---

## Key Decisions

1. **sessions_view — local variable, не поле GuardContext** (I-SESSIONS-VIEW-LOCAL-1, I-GUARD-PURE-1): dedup — pre-guard concern; guard pipeline остаётся pure domain logic без IO.
2. **best-effort dedup** (I-DEDUP-NOT-STRONG-1): не вводим DB-level UNIQUE constraint на p_sessions; race condition при конкурентных вызовах — задокументированное ограничение.
3. **command_id остаётся uuid4** (I-COMMAND-ID-IMMUTABLE-1): dedup не через idempotency key, а через sessions_view snapshot.
4. **handler-level fallback** (`_session_declared_today`): сохранён для деградированного режима без PG-URL; при наличии PG работает Step 2.5.

---

## Known Gaps (Phase 49+)

| Gap | Файл | Суть |
|-----|------|------|
| CLI INFO-лог не виден в терминале | `src/sdd/commands/registry.py:751` | `_log.info()` не показывается при дефолтном уровне WARNING; нужен `logging.basicConfig(INFO)` в CLI |
| I-INVALID-4 слишком строгий для audit-only событий | `src/sdd/commands/invalidate_event.py:89` | `SessionDeclared` в `_EVENT_SCHEMA` но не мутирует состояние; `sdd invalidate-event` блокирует |
| `_session_declared_today` игнорирует инвалидацию | `src/sdd/commands/record_session.py:53` | Handler не проверяет EventInvalidated; обходится через past-day timestamp в тестах |

---

## Risks

- R-1 (p_sessions.seq миграция): **RESOLVED** — `ADD COLUMN DEFAULT 0` + backfill + `SET NOT NULL` (T-4803)
- R-2 (BC-47-D deferral): **RESOLVED** — PG-fixtures cleanup выполнен в T-4801
- R-3 (execute_command монолит): **MANAGED** — тронуты только Step 0 и Step 2.5; рефактор — Phase 49
- R-4 (best-effort dedup): **ACCEPTED** — задокументировано в I-DEDUP-NOT-STRONG-1

---

## Decision

READY

Phase 48 выполнена полностью: все 13 задач DONE, все 21 инвариант PASS, 95/95 тестов PASS. Known gaps задокументированы и перенесены в Phase 49+. Фаза готова к CHECK_DOD.
