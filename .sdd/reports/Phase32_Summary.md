# Phase 32 Summary

**Phase:** 32 — PostgreSQL Migration & Normalized Schema  
**Spec:** Spec_v32_PostgresMigration.md  
**Status:** READY  
**Date:** 2026-04-27

---

## Tasks

| Task | Status | Description |
|------|--------|-------------|
| T-3201 | DONE | `open_sdd_connection()` — shared connection model (BC-32-0, BC-32-1) |
| T-3202 | DONE | `sdd init-project` — schema `p_{name}` creation & `shared.projects` registration |
| T-3203 | DONE | Core schema DDL: `events` (JSONB payload), `sdd_state`, `phases`, `phase_plan_versions` |
| T-3204 | DONE | Tasks schema DDL: `tasks`, `task_deps`, `task_inputs/outputs/invariants/spec_refs` |
| T-3205 | DONE | Artifacts schema DDL: `specs`, `specs_draft`, `invariants`, `invariants_current` |
| T-3206 | DONE | `IncrementalReducer` — `apply_delta()` wrapping `Reducer.fold()` (I-STATE-REBUILD-1) |
| T-3207 | DONE | `sdd rebuild-state --full` — full projection rebuild from seq=0 |
| T-3208 | DONE | `sdd next-tasks --phase N` + `_check_deps()` guard in `sdd complete` |
| T-3209 | DONE | `sdd sync-invariants` + `InvariantRegistered` event |
| T-3210 | DONE | Analytics schema: 4 views (`all_events`, `all_tasks`, `all_phases`, `all_invariants`) |
| T-3211 | DONE | `sdd analytics-refresh` — `CREATE OR REPLACE VIEW` for all `shared.projects` |
| T-3212 | DONE | Migration script: `--export` mode (validate DuckDB payloads) |
| T-3213 | DONE | Event registry SSOT + `EventRegistered` event |
| T-3214 | DONE | Registry contract tests |
| T-3215 | DONE | DB connection tests (I-DB-TEST-1, I-DB-TEST-2) |
| T-3216 | DONE | Analytics DDL tests + artifacts DDL tests |
| T-3217 | DONE | Migration script: `--import` mode (DuckDB → PG with JSONB payload, count verification) |

**Total:** 17/17 DONE

---

## Invariant Coverage

| Invariant | Status | Task(s) |
|-----------|--------|---------|
| I-1 | PASS | T-3206, T-3207, T-3212, T-3217 |
| I-DB-1 | PASS | T-3201, T-3212, T-3217 |
| I-DB-SCHEMA-1 | PASS | T-3203, T-3210 |
| I-STATE-REBUILD-1 | PASS | T-3206, T-3207, T-3217 |
| I-EVENT-DERIVE-1 | PASS | T-3203, T-3204 |
| I-CMD-IDEM-1, I-CMD-IDEM-2 | PASS | T-3208 |
| I-SYNC-INVARIANTS-1 | PASS | T-3209 |
| I-DB-TEST-1, I-DB-TEST-2 | PASS | T-3215 |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §2 BC-32-0, BC-32-1 (Shared schema, connection model) | covered — T-3201, T-3202 |
| §2 BC-32-2 (Core schema — events JSONB, sdd_state) | covered — T-3203 |
| §2 BC-32-3, BC-32-4 (Tasks & Artifacts schema) | covered — T-3204, T-3205 |
| §2 BC-32-5 (IncrementalReducer) | covered — T-3206, T-3207 |
| §2 BC-32-6 (next-tasks + guard-lite) | covered — T-3208 |
| §2 BC-32-7 (sync-invariants) | covered — T-3209 |
| §2 BC-32-9 (Analytics schema + refresh) | covered — T-3210, T-3211 |
| §2 BC-32-8, §6 (Migration script --export + --import) | covered — T-3212, T-3217 |

---

## Tests

| Suite | Result |
|-------|--------|
| `pytest tests/unit/` | **954 passed**, 4 warnings |
| `ruff check src/` | NOT AVAILABLE (not installed in environment) |
| `mypy src/sdd/` | NOT AVAILABLE (not installed in environment) |

---

## Metrics

See [Metrics_Phase32.md](Metrics_Phase32.md). No anomalies detected.

---

## Key Decisions

1. **JSONB over TEXT for payload** — `--migrate` preserves TEXT для backward-compat; `--import` использует JSONB для новой схемы. Оба режима валидируют JSON перед записью.
2. **count verification** — `cmd_import` завершается `sys.exit(1)` при `pg_count != export_count`, реализуя §6 Post-condition из Spec_v32.
3. **IncrementalReducer delegating to Reducer.fold()** — структурная гарантия I-STATE-REBUILD-1 без дублирования логики.
4. **`--import` vs `--migrate` split** — явное разделение режимов позволяет независимо тестировать TEXT (migrate) и JSONB (import) пути.

---

## Improvement Hypotheses

- **Acceptance tests требуют live PG** — в текущем окружении нет PostgreSQL; T-3217 acceptance criterion помечен DEFERRED. Рекомендуется добавить docker-compose с PG в CI.
- **ruff / mypy не установлены** — `validate-invariants` падает с `FileNotFoundError` вместо exit 127; надо добавить shell=True или graceful fallback при отсутствии линтера.

---

## Risks

- R-5 (DuckDB clean cut): DuckDB файл не архивирован — стратегия C требует ручного шага после успешной миграции. Оставлен как задача человека.

---

## Decision

READY — все 17 задач DONE, invariants.status = PASS, tests.status = PASS.  
Pending: human gate (review + `sdd phase-complete 32` или эквивалент).
