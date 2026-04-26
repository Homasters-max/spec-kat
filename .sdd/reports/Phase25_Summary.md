# Phase 25 Summary — Explicit DB Access & Test Isolation Hardening

Date: 2026-04-25
Spec: Spec_v25_ExplicitDBAccess.md (DRAFT)
Plan: Plan_v25.md
Tasks: 12/12 DONE (10 planned + 2 added mid-phase: T-2511, T-2512)

---

## Task Status

| Task | Description | Status |
|------|-------------|--------|
| T-2501 | open_sdd_connection — make db_path required | DONE |
| T-2502 | open_sdd_connection — test-context fail-fast timeout | DONE |
| T-2503 | open_sdd_connection — production DB guard in test context | DONE |
| T-2504 | metrics.py — db_path dependency injection | DONE |
| T-2505 | CLI callers — pass db_path explicitly | DONE |
| T-2506 | tests/conftest.py — 3 isolation fixtures | DONE |
| T-2507 | pyproject.toml — pytest-timeout>=4.0, --timeout=30 | DONE |
| T-2508 | tests/unit/infra/test_db.py — hardening tests | DONE |
| T-2509 | tests/unit/infra/test_metrics.py — db_path requirement test | DONE |
| T-2510 | CLAUDE.md §INV — document I-DB-1..2, I-DB-TEST-1..2 | DONE |
| T-2511 | validate-invariants — --system flag, task mode skips test | DONE |
| T-2512 | tests — validate-invariants task vs system mode | DONE |

---

## Invariant Coverage

| Invariant | Covered by |
|-----------|-----------|
| I-DB-1 | T-2501, T-2508 |
| I-DB-2 | T-2504, T-2505, T-2509 |
| I-DB-TEST-1 | T-2503, T-2506, T-2508 |
| I-DB-TEST-2 | T-2502, T-2506, T-2507, T-2508 |
| IMP-001 | T-2511, T-2512 |

---

## Spec Section Coverage

| Section | Milestone | Status |
|---------|-----------|--------|
| §2 BC-DB-1 | M1: open_sdd_connection explicit | DONE |
| §2 BC-DB-2 | M1: fail-fast in test context | DONE |
| §2 BC-DB-3 | M1: production DB guard | DONE |
| §2 BC-DB-4 | M2: metrics dependency injection | DONE |
| §2 BC-DB-5 | M3: conftest fixtures | DONE |
| §2 BC-DB-6 | M3: pytest-timeout | DONE |
| §2 BC-DB-7 | M4: CLAUDE.md §INV documentation | DONE |
| SDD_Improvements §IMP-001 | validate-invariants two-mode architecture | DONE |

---

## Tests Status

- **invariants.status**: PASS
- **tests.status**: PASS
- Unit tests: T-2508 (test_db.py), T-2509 (test_metrics.py), T-2512 (test_validate_invariants.py) — all PASS
- New tests added: 20/20 PASS in test_validate_invariants.py post T-2512

---

## Key Decisions

1. **I-DB-1 enforcement** — `open_sdd_connection` now requires non-empty `db_path`; implicit production DB fallback removed. Single breaking change in production: `metrics.py:116` (fixed by T-2504).

2. **Two-mode validate-invariants** (SDD_Improvements §IMP-001) — Added `--system` flag. Default (task mode) skips `pytest` to prevent D-state in documentation/config tasks. `--system` runs full suite as system gate. Discovered during T-2510 validation when `validate-invariants` hung on production DuckDB.

3. **State correction** — T-2511/T-2512 added mid-phase via direct TaskSet edit + corrective `TaskSetDefined` event (`tasks_total: 10→12`). Same pattern used in Phase 15/17. Prецедент задокументирован.

4. **ValidationReport T-2510** — runtime validation отмечена как SKIPPED (doc task, no src/tests outputs). Basis: SDD_Improvements.md §IMP-001.

---

## Metrics

See: Metrics_Phase25.md

No anomalies detected in trend analysis.

---

## Improvement Hypotheses

1. **validate-invariants --task медленный из-за mypy** — task mode скипает pytest (D-state fix), но mypy на `src/sdd/` занимает 30-60с. Потенциальное улучшение: добавить фильтр `typecheck` для doc/config tasks (аналогично `test`). Задокументировано в SDD_Improvements.md как потенциальный IMP-003.

2. **Mid-phase task addition** — нет механизма event-sourced добавления задач без `activate-phase`. Использование `TaskSetDefined` corrective events работает (см. Phase 15/17 прецеденты), но требует прямого DuckDB SQL. Можно добавить `sdd add-task` команду в будущей фазе.

---

## EventLog Snapshot

See: EL_Phase25_events.json
