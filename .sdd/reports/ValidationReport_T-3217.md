# ValidationReport T-3217

**Date:** 2026-04-27  
**Phase:** 32  
**Task:** T-3217  
**Result:** PASS (unit suite) / DEFERRED (acceptance — requires live PG)

---

## Spec Section Covered

Spec_v32 §Migration — `--import` mode: DuckDB → PostgreSQL with JSONB payload column.

---

## Invariants Checked

| Invariant | Check | Result |
|-----------|-------|--------|
| I-1 | Event log not modified by script; DuckDB read-only in `--import` mode | PASS |
| I-STATE-REBUILD-1 | `sdd rebuild-state --full` unaffected (operates on DuckDB, not PG) | PASS |
| I-DB-1 | `open_sdd_connection(db_url=...)` called with explicit non-empty `db_url` in all branches | PASS |

---

## Implementation

Added to `scripts/migrate_duckdb_to_pg.py`:

- `_PG_CREATE_JSONB` — DDL with `payload JSONB NOT NULL`
- `_PG_INSERT_JSONB` — INSERT using `%s::jsonb` cast
- `cmd_import(duckdb_url, pg_url, pg_schema)`:
  1. Reads all rows from DuckDB via `_fetch_all_rows`
  2. Validates every payload with `_validate_payload`; aborts on first invalid batch
  3. Inserts into PG in `_BATCH_SIZE=500` batches via `_PG_INSERT_JSONB`
  4. Queries `SELECT COUNT(*) FROM events`; exits 1 if `pg_count != export_count`
- CLI: `--import` added to mutually-exclusive mode group (`dest="import_mode"`)
- `main()`: validates `--pg-url` required; dispatches to `cmd_import`

---

## Acceptance Criterion

**Criterion:** `test_import_mode: --import загружает JSON в Postgres events с JSONB payload; count(Postgres) == count(export); sdd rebuild-state --full и sdd show-state проходят без ошибок`

**Status:** DEFERRED — live PostgreSQL not available in CI environment.  
Code review confirms:
- Table created with `payload JSONB NOT NULL` ✓
- Count check `pg_count != export_count` → `sys.exit(1)` ✓
- `sdd rebuild-state --full` operates on DuckDB event store; unaffected by PG import ✓

---

## Test Results

| Suite | Result |
|-------|--------|
| `pytest tests/unit/` | **954 passed**, 4 warnings |
| `ruff check src/` | NOT AVAILABLE (ruff not installed in environment) |
| `mypy src/sdd/` | NOT AVAILABLE (mypy not installed in environment) |
| Acceptance (`--import` against live PG) | DEFERRED |

---

## Regression

No existing tests broken. Output file scope limited to `scripts/migrate_duckdb_to_pg.py` only.
