# TaskSet_v42 — Phase 42: Docker CI Infrastructure for PostgreSQL

Spec: specs/Spec_v40_DockerCIInfrastructure.md
Plan: plans/Plan_v42.md

---

T-4201: Refactor `sdd.db.connection` public API

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-0
Invariants:           I-DB-1, I-DB-TEST-2
spec_refs:            [Spec_v40 §2 BC-40-0, I-DB-1, I-DB-TEST-2]
produces_invariants:  [I-DB-1]
requires_invariants:  []
Inputs:               src/sdd/db/connection.py
Outputs:              src/sdd/db/connection.py
Acceptance:           `open_db_connection`, `is_postgres_url`, `resolve_pg_url` exist in module; `open_sdd_connection` removed; `is_postgres_url("postgres://x")` returns True
Depends on:           —

---

T-4202: Export new API from `sdd.db.__init__`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-0
Invariants:           I-DB-1
spec_refs:            [Spec_v40 §2 BC-40-0, I-DB-1]
produces_invariants:  [I-DB-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/db/__init__.py, src/sdd/db/connection.py
Outputs:              src/sdd/db/__init__.py
Acceptance:           `from sdd.db import open_db_connection, is_postgres_url, resolve_pg_url` succeeds without error
Depends on:           T-4201

---

T-4203: Update callers to new API (BC-40-0a)

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-0a
Invariants:           I-DB-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v40 §2 BC-40-0a, I-DB-1, I-DB-TEST-1]
produces_invariants:  [I-DB-TEST-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/commands/init_project.py, src/sdd/commands/analytics_refresh.py, tests/test_db_connection.py, tests/unit/commands/test_init_project.py
Outputs:              src/sdd/commands/init_project.py, src/sdd/commands/analytics_refresh.py, tests/test_db_connection.py, tests/unit/commands/test_init_project.py
Acceptance:           `pytest tests/test_db_connection.py tests/unit/commands/test_init_project.py` PASS; no import of `sdd.db.connection.open_sdd_connection` remains in updated files
Depends on:           T-4201, T-4202

---

T-4204: Create `docker-compose.yml` with postgres:16-alpine

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-1
Invariants:           I-CI-PG-4
spec_refs:            [Spec_v40 §2 BC-40-1, I-CI-PG-4]
produces_invariants:  [I-CI-PG-4]
requires_invariants:  []
Inputs:               —
Outputs:              docker-compose.yml
Acceptance:           `docker compose config` exits 0; service `postgres` present with healthcheck and volume `pg_data`; credentials user=sdd password=sdd db=sdd
Depends on:           —

---

T-4205: Create `scripts/dev-up.sh`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-5
Invariants:           I-CI-PG-4
spec_refs:            [Spec_v40 §2 BC-40-5, I-CI-PG-4]
produces_invariants:  [I-CI-PG-4]
requires_invariants:  [I-CI-PG-4]
Inputs:               docker-compose.yml
Outputs:              scripts/dev-up.sh
Acceptance:           Script is executable; contains healthcheck wait loop; prints `SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd`
Depends on:           T-4204

---

T-4206: Add Makefile targets `pg-up`, `pg-down`, `ci-pg`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-5
Invariants:           I-CI-PG-4
spec_refs:            [Spec_v40 §2 BC-40-5, I-CI-PG-4]
produces_invariants:  [I-CI-PG-4]
requires_invariants:  [I-CI-PG-4]
Inputs:               Makefile, docker-compose.yml
Outputs:              Makefile
Acceptance:           `make -n pg-up` and `make -n pg-down` and `make -n ci-pg` exit 0 (dry-run)
Depends on:           T-4204

---

T-4207: Update `pyproject.toml` — postgres extra, pg marker, scripts/ pythonpath

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-6
Invariants:           I-CI-PG-3, I-DB-SCHEMA-1
spec_refs:            [Spec_v40 §2 BC-40-6, §5 Invariants, I-CI-PG-3]
produces_invariants:  [I-CI-PG-3]
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              pyproject.toml
Acceptance:           `pytest --co -q -m pg tests/` exits without "unknown mark" warning; `psycopg` in optional `postgres` extra; `scripts/` in `pythonpath`
Depends on:           —

---

T-4208: Update `tests/conftest.py` — pg_url and pg_conn fixtures

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-4
Invariants:           I-CI-PG-2, I-CI-PG-3, I-DB-TEST-1, I-DB-SCHEMA-1
spec_refs:            [Spec_v40 §2 BC-40-4, §5 Invariants, I-CI-PG-2, I-CI-PG-3, I-DB-TEST-1]
produces_invariants:  [I-CI-PG-2, I-CI-PG-3]
requires_invariants:  [I-DB-1]
Inputs:               tests/conftest.py, src/sdd/db/connection.py
Outputs:              tests/conftest.py
Acceptance:           `pg_url` fixture returns skip when SDD_DATABASE_URL unset; `pg_conn` fixture uses monkeypatch.setenv("SDD_PROJECT", ...) for schema isolation; existing DuckDB fixtures unaffected
Depends on:           T-4201, T-4207

---

T-4209: Create `tests/integration/test_pg_init_project.py`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-3; §7 Use Cases
Invariants:           I-CI-PG-1, I-CI-PG-2, I-DB-SCHEMA-1
spec_refs:            [Spec_v40 §2 BC-40-3, §7, I-CI-PG-1, I-DB-SCHEMA-1]
produces_invariants:  [I-CI-PG-1]
requires_invariants:  [I-CI-PG-2, I-CI-PG-3, I-DB-1]
Inputs:               src/sdd/commands/init_project.py, tests/conftest.py
Outputs:              tests/integration/test_pg_init_project.py
Acceptance:           Test covers schema creation and `search_path` set to project schema; `@pytest.mark.pg` applied; test skips when no PG available (I-CI-PG-3)
Depends on:           T-4203, T-4208

---

T-4210: Create `tests/integration/test_pg_migration.py`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-3; §9 Verification
Invariants:           I-CI-PG-1, I-CI-PG-3, I-STATE-REBUILD-1
spec_refs:            [Spec_v40 §2 BC-40-3, §9, I-CI-PG-3, I-STATE-REBUILD-1]
produces_invariants:  [I-STATE-REBUILD-1]
requires_invariants:  [I-CI-PG-2, I-CI-PG-3, I-DB-1]
Inputs:               scripts/migrate_duckdb_to_pg.py, tests/conftest.py
Outputs:              tests/integration/test_pg_migration.py
Acceptance:           `test_migration_round_trip` PASS with live PG; SKIP (not FAIL) when SDD_DATABASE_URL unset; event count matches before/after migration
Depends on:           T-4208

---

T-4211: Create `tests/integration/test_pg_rebuild_state.py`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-3; §9 Verification
Invariants:           I-CI-PG-2, I-DB-TEST-1, I-DB-SCHEMA-1
spec_refs:            [Spec_v40 §2 BC-40-3, §9, I-CI-PG-2, I-DB-TEST-1]
produces_invariants:  [I-CI-PG-2]
requires_invariants:  [I-CI-PG-2, I-CI-PG-3, I-DB-1]
Inputs:               src/sdd/commands/rebuild_state.py, tests/conftest.py
Outputs:              tests/integration/test_pg_rebuild_state.py
Acceptance:           Schema isolation verified: test schema torn down after test; teardown guard confirms no schema leaks to other tests; `@pytest.mark.pg` applied
Depends on:           T-4208

---

T-4212: Create `.github/workflows/ci.yml`

Status:               TODO
Spec ref:             Spec_v40 §2 Architecture/BCs — BC-40-2; §6 Pre/Post Conditions; §9 Verification
Invariants:           I-CI-PG-1, I-CI-PG-4
spec_refs:            [Spec_v40 §2 BC-40-2, §6, §9, I-CI-PG-1, I-CI-PG-4]
produces_invariants:  [I-CI-PG-1, I-CI-PG-4]
requires_invariants:  [I-CI-PG-4]
Inputs:               docker-compose.yml, pyproject.toml, tests/integration/test_pg_init_project.py, tests/integration/test_pg_migration.py, tests/integration/test_pg_rebuild_state.py
Outputs:              .github/workflows/ci.yml
Acceptance:           Job `unit` runs lint+mypy+unit tests without PG; job `pg-integration` runs matrix Python3.11×3.12 / PG15×16 with service container; healthcheck wait-loop present; `SDD_DATABASE_URL` injected via env
Depends on:           T-4204, T-4207, T-4209, T-4210, T-4211

---

<!-- Granularity: 12 tasks (TG-2: 10–30). Each task independently implementable and testable (TG-1). -->
