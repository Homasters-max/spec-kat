# Phase 44 Summary — Routing Switch

Status: READY

---

## Tasks

| Task | Status |
|------|--------|
| T-4401 | DONE |
| T-4402 | DONE |
| T-4403 | DONE |
| T-4404 | DONE |
| T-4405 | DONE |
| T-4406 | DONE |
| T-4407 | DONE |
| T-4408 | DONE |
| T-4409 | DONE |
| T-4410 | DONE |
| T-4411 | DONE |
| T-4412 | DONE |
| T-4413 | DONE |
| T-4414 | DONE |

Total: 14/14 DONE.

---

## Invariant Coverage

| Invariant | Status |
|-----------|--------|
| I-CLI-DB-RESOLUTION-1 | PASS |
| I-EVENT-STORE-URL-1 | PASS |
| I-DB-1 | PASS |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §2 BC-44-A: event_store_file() → event_store_url() в 10 CLI-модулях | covered |
| §2 BC-44-B: argparse eager evaluation fix (update_state, query_events, report_error) | covered |
| §2 BC-44-C: cli.py hardcoded DuckDB path → event_store_url() | covered |
| §2 BC-44-D: log_tool.py subprocess routing fix | covered |
| §2 BC-44-E: enforcement тест I-CLI-DB-RESOLUTION-1 (6 тестов) | covered |

---

## Tests

| Test | Status |
|------|--------|
| `test_no_event_store_file_calls_in_cli` | PASS |
| `test_no_duckdb_hardcodes_in_cli` | PASS |
| `test_update_state_argparse_no_eager_eval` | PASS |
| `test_query_events_argparse_no_eager_eval` | PASS |
| `test_report_error_argparse_no_eager_eval` | PASS |
| `test_log_tool_uses_event_store_url_fallback` | PASS |
| All unit tests (1010 total) | PASS |

---

## Key Decisions

- `activate_phase.py:186` содержал hardcoded DuckDB path (`get_sdd_root() / "state" / "sdd_events.duckdb"`) вместо `event_store_file()`. Исправлен при написании enforcement-теста T-4414.
- `cli.py` module-level import `from sdd.infra.paths import event_store_url` нарушал I-CLI-1 (pure router). Исправлено lazy-импортом через `sdd.commands.registry` (реэкспорт).
- Тесты `test_next_tasks.py` и `test_switch_phase_nav_guard.py` патчили `event_store_file` после переключения на `event_store_url`. Исправлены.

---

## Metrics

See: [Metrics_Phase44.md](Metrics_Phase44.md)

No anomalies detected.

---

## Decision

READY

Все 14 задач DONE. Инварианты PASS. Тесты PASS (1010/1010). I-CLI-DB-RESOLUTION-1 технически соблюдён: все CLI entry points маршрутизируются через `event_store_url()`.
