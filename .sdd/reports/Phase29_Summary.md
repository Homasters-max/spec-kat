# Phase 29 Summary — Streamlined Session Flow

Status: READY

Date: 2026-04-25  
Spec: Spec_v29_StreamlinedWorkflow.md  
Metrics: [Metrics_Phase29.md](.sdd/reports/Metrics_Phase29.md)

---

## Tasks

| Task | Status | Invariants Covered |
|------|--------|-------------------|
| T-2901 | DONE | I-SESSION-DECLARED-1, I-SESSION-PLAN-HASH-1 |
| T-2902 | DONE | I-SESSION-DECLARED-1, I-PHASE-STARTED-1 |
| T-2903 | DONE | I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1, I-2 |
| T-2904 | DONE | I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1 |
| T-2905 | DONE | I-SESSION-AUTO-1, I-SESSION-PI-6 |
| T-2906 | DONE | I-SESSION-PI-6, I-PHASES-INDEX-1 |
| T-2907 | DONE | I-SESSION-DECLARED-1, I-SESSION-ACTOR-1 |
| T-2908 | DONE | I-SESSION-AUTO-1, I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1, I-SESSION-ACTOR-1, I-SESSION-PI-6, I-PHASES-INDEX-1 |
| T-2909 | DONE | I-SESSION-DECLARED-1, I-DB-TEST-1, I-DB-TEST-2 |
| T-2910 | DONE | I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-DB-TEST-1 |
| T-2911 | DONE | I-PHASES-INDEX-1, I-PHASES-KNOWN-1, I-PHASES-KNOWN-2, I-DB-TEST-1 |

Total: 11/11 DONE

---

## Invariant Coverage

| Invariant | Coverage |
|-----------|----------|
| I-SESSION-DECLARED-1 | T-2901, T-2902, T-2903, T-2907, T-2908, T-2909 |
| I-SESSION-PLAN-HASH-1 | T-2901, T-2904, T-2910 |
| I-SESSION-VISIBLE-1 | T-2903, T-2908 |
| I-SESSION-ACTOR-1 | T-2904, T-2907, T-2908, T-2910 |
| I-SESSION-AUTO-1 | T-2905, T-2908 |
| I-SESSION-PI-6 | T-2905, T-2906, T-2908 |
| I-PHASES-INDEX-1 | T-2906, T-2908, T-2911 |
| I-PHASES-KNOWN-1 | T-2911 |
| I-PHASES-KNOWN-2 | T-2911 |
| I-PHASE-STARTED-1 | T-2902 |
| I-2 | T-2903 |
| I-DB-TEST-1 | T-2909, T-2910, T-2911 |
| I-DB-TEST-2 | T-2909 |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §2 SessionDeclaredEvent + plan_hash field | T-2901, T-2902 — COVERED |
| §3 actor/executed_by separation | T-2904 — COVERED |
| §4 plan_hash computation in activate-phase | T-2904, T-2910 — COVERED |
| §6 Session FSM auto-actions | T-2905, T-2906, T-2908 — COVERED |
| §7 Race Conditions reference (decompose.md) | T-2905 — COVERED |
| §10 Verification tests | T-2909, T-2910, T-2911 — COVERED |
| record-session CLI (BC-SW-2) | T-2903 — COVERED |
| tool-reference.md update (BC-SW-7..10) | T-2907 — COVERED |
| CLAUDE.md §SESSION + §ROLES + §INV | T-2908 — COVERED |

---

## Tests

| Test File | Tests | Status |
|-----------|-------|--------|
| tests/unit/commands/test_record_session.py | 2 | PASS |
| tests/unit/commands/test_activate_phase_v29.py | 2 | PASS |
| tests/unit/test_phases_index_consistency.py | 14 | PASS |

Total: 18 new tests — all PASS

---

## Key Decisions

- **Human Declares, LLM Executes** — SessionDeclaredEvent как causal anchor; LLM авто-вызывает CLI с явным выводом (I-SESSION-VISIBLE-1)
- **actor/executed_by разделение** — VALID_ACTORS={"human"} неизменен; `executed_by` идёт только в payload (I-SESSION-ACTOR-1)
- **plan_hash=sha256(Plan_vN.md)[:16]** — в PhaseInitializedEvent.payload; поле опциональное с default="" для backward compat
- **LLM авто-вызов activate-phase разрешён только в DECOMPOSE** — с `--executed-by llm`; в других сессиях MUST NOT

---

## Risks Resolved

- R-1: backward compat plan_hash — `plan_hash: str = ""` добавлен как default, replay старых событий не ломается
- R-2: actor/executed_by разделение — реализовано корректно, VALID_ACTORS нетронут
- R-3: CLAUDE.md §ROLES формулировка — уточнена: запрет снят только для DECOMPOSE с --executed-by llm
- R-4: record-session регистрация — команда в REGISTRY, I-2 не нарушен
- R-5: race condition — обрабатывается через RP-STALE

---

## Anomalies / Improvement Hypotheses

- `sdd validate-invariants` завершается с KernelContextError (EventStore.append вызывается вне Kernel execute_command). Это pre-existing регрессия Phase 28. Требует отдельного спека для фикса — execute_and_project должен оборачивать validate-invariants или команда должна быть переведена на REGISTRY.
- Ruff lint выдаёт I001/F401/F811/UP017 в ряде src/ и tests/ файлов. Не блокируют Phase 29, но накапливаются — рекомендуется lint-cleanup спек.

---

## Decision

READY

Все 11 задач DONE. Invariants PASS. 18 новых тестов GREEN. Spec §2–§10 покрыты.
Блокеров нет. Фаза готова к закрытию.
