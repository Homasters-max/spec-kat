# Phase 27 Summary

Status: READY

---

## Tasks

| Task | Status | Description |
|------|--------|-------------|
| T-2701 | DONE | CommandSpec.idempotent field + execute_command non-idempotent path (BC-CI-1, BC-CI-2, BC-CI-3) |
| T-2702 | DONE | Tests: test_registry_contract extensions for idempotent field (BC-CI-5 partial) |
| T-2703 | DONE | CLAUDE.md §INV: добавлены I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1 (BC-CI-4) |
| T-2704 | DONE | Test suite: test_command_idempotency.py — 4 теста для I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1 (BC-CI-5) |

---

## Invariant Coverage

| Invariant | Status | Covered by |
|-----------|--------|------------|
| I-CMD-IDEM-1 | PASS | T-2701 (impl), T-2703 (doc), T-2704 (test) |
| I-CMD-IDEM-2 | PASS | T-2701 (impl), T-2703 (doc) |
| I-CMD-NAV-1 | PASS | T-2703 (doc), T-2704 (test via I-IDEM-SCHEMA-1) |
| I-IDEM-SCHEMA-1 | PASS | T-2704 (`test_complete_still_idempotent`) |
| I-OPTLOCK-1 | PASS | T-2704 (`test_switch_phase_optlock_preserved`) |
| I-DB-TEST-1 | PASS | T-2704 (tmp_path DB в всех тестах) |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §1 Диагностика D-7, D-8 | covered — BC-CI-2 исправляет D-7 через uuid4() |
| §2 Scope | covered — BC-CI-1..5 реализованы полностью |
| §3 Архитектурная модель | covered — CommandSpec.idempotent + execute_command Step 5 |
| §4 Invariants | covered — I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1 в CLAUDE.md §INV |
| §5 Pre/Post Conditions | covered — поведение верифицировано тестами |
| §6 Verification | covered — все 4 теста из таблицы §6 реализованы и PASS |

---

## Tests

| Test | Status |
|------|--------|
| `test_switch_phase_non_idempotent` | PASS |
| `test_complete_still_idempotent` | PASS |
| `test_switch_phase_optlock_preserved` | PASS |
| `test_command_spec_idempotent_default` | PASS |

---

## Key Decisions

- D-1: Тесты реализованы через EventStore.append напрямую (не execute_and_project),
  поскольку тестируется механизм dedup на уровне EventStore. Связь с REGISTRY
  обеспечена через `test_command_spec_idempotent_default`.
- D-2: uuid4() выбран вместо None для non-idempotent command_id — сохраняет
  traceability в EventLog (command_id присутствует для audit correlation).

---

## Metrics

See: Metrics_Phase27.md

---

## Improvement Hypotheses

- H-1: Lint autofixable ошибки (ruff UP037/F541) обнаружены на этапе validate.
  Добавить `ruff check --fix` в pre-implement checklist для более раннего обнаружения.

---

## Decision

READY

Все 4 задачи DONE, invariants.status = PASS, tests.status = PASS.
Spec_v27 §2 Scope полностью покрыт (BC-CI-1..5).
D-7 (navigation команда ошибочно идемпотентна) устранён.
