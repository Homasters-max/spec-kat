# Phase 23 Summary — Activation Guard

Status: READY

Spec: Spec_v23_ActivationGuard.md
Metrics: [Metrics_Phase23.md](Metrics_Phase23.md)

---

## Tasks

| Task | Status | Scope |
|------|--------|-------|
| T-2301 | DONE | `_resolve_tasks_total` + `--tasks default=None` + DeprecationWarning in `activate_phase.py` |
| T-2302 | DONE | `--tasks default=None` verified (covered by T-2301) |
| T-2303 | DONE | 5 unit tests for `_resolve_tasks_total` (I-PHASE-INIT-2, I-PHASE-INIT-3) |
| T-2304 | DONE | 4 integration tests for `main()` (I-PHASE-INIT-2, I-PHASE-INIT-3, BC-23-2) |

---

## Invariant Coverage

| Invariant | Status | Evidence |
|-----------|--------|---------|
| I-PHASE-INIT-2 | PASS | `_resolve_tasks_total` raises `Inconsistency` when `tasks_arg != actual`; test_resolve_tasks_total_mismatch, test_main_mismatch |
| I-PHASE-INIT-3 | PASS | `_resolve_tasks_total` raises `MissingContext` on absent/empty TaskSet; `parse_taskset` raises before `actual <= 0` branch; test_resolve_tasks_total_missing_file, test_resolve_tasks_total_empty_taskset, test_main_missing_taskset |
| I-TASKSET-IMMUTABLE-1 | DOCUMENTED | Process invariant; no runtime enforcement in Phase 23 (§10 Out of Scope — checksum deferred to Phase 24+) |
| I-HANDLER-PURE-1 | PRESERVED | `ActivatePhaseHandler.handle()` unchanged; `_resolve_tasks_total` called in `main()` only, before command construction |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §0 Goal — root cause (tasks_total=0 bug) | covered — auto-detect + guard eliminates the gap |
| §1 Scope — BC-23-1, BC-23-2 | covered |
| §2 Architecture — `_resolve_tasks_total`, `--tasks` deprecation | covered |
| §3 Domain Events — no schema change | covered (PhaseInitializedEvent unchanged) |
| §4 Types & Interfaces | covered — signature matches spec exactly |
| §5 Invariants — I-PHASE-INIT-2/3, I-TASKSET-IMMUTABLE-1 | covered |
| §6 Pre/Post Conditions | covered — enforced at `_resolve_tasks_total` call site |
| §7 Use Cases — UC-23-1, UC-23-2, UC-23-3 | covered by test_main_* tests |
| §9 Verification — tests 1..9 | covered — all 9 tests passing (5 unit + 4 integration) |
| §10 Out of Scope | acknowledged — `--tasks` removal + checksum deferred |

---

## Tests

| Test | Status | Invariant |
|------|--------|-----------|
| `test_resolve_tasks_total_autodetect` | PASS | I-PHASE-INIT-2 |
| `test_resolve_tasks_total_explicit_match` | PASS | I-PHASE-INIT-2 |
| `test_resolve_tasks_total_mismatch` | PASS | I-PHASE-INIT-2 |
| `test_resolve_tasks_total_missing_file` | PASS | I-PHASE-INIT-3 |
| `test_resolve_tasks_total_empty_taskset` | PASS | I-PHASE-INIT-3 |
| `test_main_autodetect_happy_path` | PASS | I-PHASE-INIT-2/3 |
| `test_main_missing_taskset` | PASS | I-PHASE-INIT-3 |
| `test_main_mismatch` | PASS | I-PHASE-INIT-2 |
| `test_main_deprecated_tasks_arg` | PASS | BC-23-2 |
| Pre-existing tests (7) | PASS | I-ACT-1, I-HANDLER-BATCH-PURE-1, I-PHASE-EVENT-PAIR-1, I-IDEM-SCHEMA-1 |

Total: 16 tests, 16 PASS.

---

## Key Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D-23-1 | T-2301 и T-2302 реализованы совместно в одном коммите | `default=None` и `_resolve_tasks_total` неделимы — разделение создало бы промежуточное невалидное состояние (tasks_total=0 всё ещё возможен между T-2301 и T-2302) |
| D-23-2 | Unit-тесты мокают `taskset_file`, но `parse_taskset` вызывается реально | Мок `taskset_file` изолирует тест от файловой системы; реальный `parse_taskset` верифицирует контракт парсера — Plan risk R-1 закрыт |
| D-23-3 | `actual <= 0` ветка в `_resolve_tasks_total` недостижима | `parse_taskset` уже бросает `MissingContext` при отсутствии задач (line 88-89 parser.py); ветка сохранена для явного выражения инварианта I-PHASE-INIT-3 |

---

## Risks

- R-1 (closed): `parse_taskset` signature `(str) -> list[Task]` подтверждена до реализации BC-23-1; контракт соответствует спеку §8.
- R-2 (open → Phase 24+): `--tasks` остаётся в CLI как deprecated; полное удаление запланировано в Phase 24+ после deprecation period.
- R-3 (open → Phase 24+): I-TASKSET-IMMUTABLE-1 не имеет runtime enforcement — нарушение обнаруживается только постфактум. Checksum в PhaseInitializedEvent требует изменения event schema (§10).

---

## Improvement Hypotheses

Метрический анализ: аномалий не обнаружено (0 отклонений > 2σ). Trend data отсутствует для Phase 23 (первый запуск metrics-report для этой фазы).

Гипотезы из ретроспективы:
- **H-23-1:** T-2302 как отдельная задача избыточна — изменение `default=None` атомарно с `_resolve_tasks_total`. В следующих фазах аналогичные атомарные изменения стоит объединять в одну задачу на уровне декомпозиции.
- **H-23-2:** `sdd validate T-NNN` не запускался для Phase 23 — `invariants.status = UNKNOWN`. Рекомендуется добавить validate-шаг как обязательный между complete и summarize.

---

## Decision

READY

Все 4 задачи DONE. Все 9 spec-тестов + 7 pre-existing тестов проходят (16/16). Инварианты I-PHASE-INIT-2 и I-PHASE-INIT-3 покрыты кодом и тестами. BC-23-2 (deprecation) реализован и верифицирован. Phase 23 готова к human review и PhaseCompleted.
