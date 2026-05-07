# Plan_v48 — Phase 48: Session Dedup (Domain-Level, Safe)

Status: DRAFT
Spec: specs/Spec_v48_SessionDedup.md

---

## Logical Context

type: none
rationale: "Standard new phase. Domain refinement поверх Phase 47 (EL Kernel Extraction). Не исправляет ошибку предыдущей фазы и не заполняет пропущенный gap."

---

## Milestones

### M1: Projector layer — types, schema, sync (BC-48-C + BC-48-C2)

```text
Spec:       §3 Architecture, §5 Types & Interfaces (BC-48-C / BC-48-C2)
BCs:        BC-48-C, BC-48-C2
Invariants: I-PSESSIONS-SEQ-1, I-GUARD-PURE-1, I-SESSIONSVIEW-O1-1,
            I-PROJECTION-SESSIONS-1, I-INVALIDATION-FINAL-1,
            I-PROJECTION-ORDER-1, I-DEDUP-PROJECTION-CONSISTENCY-1,
            I-PROJECTION-FRESH-1
Depends:    — (first milestone)
Files:      src/sdd/infra/projector.py
Risks:      p_sessions.seq NOT NULL требует либо пустой таблицы, либо backfill из
            event_log.sequence_id. При наличии старых строк без seq — ALTER TABLE упадёт.
            Решение: заполнить seq=0 для существующих строк, затем добавить NOT NULL constraint.
```

**Steps (строгий порядок из §9 BC-48-C):**

1. `SessionRecord` + `SessionsView` (frozen dataclass, `_index: dict`, `get_last` O(1)) — в `infra/projector.py`
2. `p_sessions` schema: `ALTER TABLE p_sessions ADD COLUMN seq BIGINT NOT NULL DEFAULT 0` → затем `ALTER TABLE DROP DEFAULT`; `_handle_session_declared` пишет `seq` из `event.seq` (из `event_log.sequence_id`)
3. `_sync_p_sessions(conn)` — находит `max(seq)` в p_sessions, применяет пропущенные `SessionDeclared` из event_log ORDER BY seq ASC
4. `build_sessions_view(conn)` — SQL с фильтром транзитивной инвалидации (`WHERE seq NOT IN (SELECT DISTINCT target_seq FROM invalidated_events WHERE transitive_invalidation = TRUE)`), ORDER BY seq ASC; последний seq побеждает
5. `GuardContext` — **не изменяется** (I-GUARD-CONTEXT-UNCHANGED-1)

**Acceptance:**
- `python3 -c "from sdd.infra.projector import SessionsView, build_sessions_view; print('OK')"` → OK
- I-GUARD-PURE-1, I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1, I-PSESSIONS-SEQ-1 PASS

---

### M2: Domain policy + execute_command integration (BC-48-B + BC-48-A)

```text
Spec:       §3 Architecture (flow после Phase 48), §5 Types & Interfaces (BC-48-B / BC-48-A)
BCs:        BC-48-B, BC-48-A
Invariants: I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1,
            I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1,
            I-GUARD-CONTEXT-UNCHANGED-1, I-SESSIONS-VIEW-LOCAL-1,
            I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1,
            I-SESSION-INVALIDATION-1, I-COMMAND-ID-IMMUTABLE-1,
            I-DEDUP-NOT-STRONG-1
Depends:    M1 (SessionsView + _sync_p_sessions + build_sessions_view должны существовать)
Files:      src/sdd/domain/session/__init__.py,
            src/sdd/domain/session/policy.py,
            src/sdd/commands/registry.py
Risks:      execute_command — монолит (строки 615–787). Изменение только целевых шагов
            (Step 0 и Step 2.5); не рефакторить структуру (Phase 49+).
            sessions_view — только local variable, НЕ поле GuardContext (I-SESSIONS-VIEW-LOCAL-1).
```

**Steps (строгий порядок):**

**BC-48-B: execute_command + CommandSpec**

1. `CommandSpec` += `dedup_policy: SessionDedupPolicy | None = None`
2. Step 0 в `execute_command` (conditional, только если `spec.dedup_policy is not None`):
   - `_sync_p_sessions(conn)` → `sessions_view = build_sessions_view(conn)` (local var)
3. Step 2.5 после guard pipeline:
   - если `not spec.dedup_policy.should_emit(sessions_view, cmd)` → `logger.info(...)` + `record_metric(...)` + `return`

**BC-48-A: SessionDedupPolicy**

4. `src/sdd/domain/session/__init__.py` (пустой пакет)
5. `src/sdd/domain/session/policy.py` — `SessionDedupPolicy` (frozen dataclass, pure):
   - `should_emit(sessions_view, cmd) → bool`
   - `None sessions_view` → `True` (degraded gracefully)
   - Без IO: `grep "import psycopg\|open(" policy.py` → пусто

**Acceptance:**
- I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1 PASS
- I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1, I-SESSION-INVALIDATION-1 PASS (unit)

---

### M3: Wire-up record-session + observability (BC-48-D + BC-48-E)

```text
Spec:       §5 Types & Interfaces (BC-48-D / BC-48-E), §8 Use Cases UC-48-1..UC-48-5
BCs:        BC-48-D, BC-48-E
Invariants: I-SESSION-DEDUP-2, I-COMMAND-OBSERVABILITY-1
Depends:    M1, M2 (SessionDedupPolicy + dedup_policy field в CommandSpec)
Files:      src/sdd/commands/record_session.py
Risks:      Wire-up меняет поведение только record-session; все остальные команды
            (CommandSpec.dedup_policy = None по умолчанию) работают без изменений (UC-48-5).
```

**Steps:**

1. `REGISTRY["record-session"]` CommandSpec: добавить `dedup_policy=SessionDedupPolicy()`
2. Проверить UC-48-1: повторный вызов → 1 событие в EventLog
3. Проверить UC-48-5: команда без dedup_policy пропускает Step 0 и Step 2.5 (нет лишнего DB round-trip)
4. BC-48-E — observability при dedup:
   - `logger.info("Session deduplicated: type=%s phase=%s", ...)` уровень INFO (не WARNING)
   - `record_metric("session_dedup_skipped_total", labels={"session_type": ..., "phase_id": ...})`

**Acceptance:**
- `sdd record-session --type IMPLEMENT --phase 48` (×2) → 1 `SessionDeclared` в EventLog
- Второй вызов → INFO-строка "Session deduplicated" в stdout
- I-COMMAND-OBSERVABILITY-1 PASS

---

### M4: Tests (BC-48-F)

```text
Spec:       §10 Verification (таблицы unit 1..16, integration 17..20, smoke §10)
BCs:        BC-48-F
Invariants: все инварианты Phase 48
Depends:    M1, M2, M3
Files:      tests/unit/domain/test_session_dedup.py,
            tests/unit/infra/test_projector_sessions.py,
            tests/unit/commands/test_record_session_dedup.py,
            tests/unit/commands/test_record_session_dedup_integration.py
Risks:      Integration-тесты требуют PG; использовать SDD_DATABASE_URL.
            Тест на concurrency (UC-48-4) — только документируем best-effort,
            НЕ assert строгой уникальности (I-DEDUP-NOT-STRONG-1).
```

**Unit tests (1–16 из §10):** покрывают политику, SessionsView O(1), invalidation-фильтр, frozen snapshot, observability, noop isolation, guard purity.

**Integration tests (17–20 из §10):** двойной вызов → 1 событие; invalidate → разрешает новый; разные типы → оба создаются; sync перед view.

**Smoke (§10 Verification):** 7 команд проверяют end-to-end: двойной вызов, INFO-лог, invalidate-cycle, разные типы, GuardContext чистота, policy.py чистота, `pytest -k "dedup or session"`.

**Acceptance:**
- `pytest tests/unit -k "dedup or session" -v` → все PASS
- Smoke-скрипт §10 выполнен без ошибок

---

## Risk Notes

- R-1: **p_sessions.seq NOT NULL миграция** — если в p_sessions есть строки без seq, `ALTER TABLE ADD COLUMN seq BIGINT NOT NULL` упадёт. Решение: сначала `ADD COLUMN seq BIGINT DEFAULT 0`, заполнить NULL значения из event_log.sequence_id, затем `SET NOT NULL`. Проверить состояние таблицы в начале M1.
- R-2: **BC-47-D (PG fixtures TRUNCATE) deferral** — Spec_v48 §2 указывает: если BC-47-D был deferred из Phase 47, он должен быть первым task'ом Phase 48. Проверить при DECOMPOSE: наличие незакрытого BC-47-D в Phase 47 TaskSet.
- R-3: **execute_command монолит** — строки 615–787 в `registry.py` трогать только в рамках Step 0 и Step 2.5; общая структура функции не рефакторируется (Phase 49).
- R-4: **Best-effort dedup** — не вводить DB-level UNIQUE(session_type, phase_id). Конкурентные дубли — задокументированное ограничение (I-DEDUP-NOT-STRONG-1). Тесты не должны assert строгость при конкурентности.
