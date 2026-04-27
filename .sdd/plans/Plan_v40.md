# Plan_v40 — Phase 40: Docker CI Infrastructure for PostgreSQL

Status: DRAFT
Spec: specs/Spec_v40_DockerCIInfrastructure.md

---

## Milestones

### M1: Connection API Refactoring (BC-40-0 + BC-40-0a)

```text
Spec:       §2 Architecture/BCs — BC-40-0, BC-40-0a
BCs:        BC-40-0, BC-40-0a
Invariants: I-DB-1, I-DB-TEST-1, I-DB-TEST-2, I-DB-SCHEMA-1
Depends:    — (foundation milestone, no prerequisites)
Risks:      15+ callers of sdd.infra.db.open_sdd_connection MUST NOT be touched;
            sdd.db.connection.open_sdd_connection is the only renamed symbol.
            Caller update (BC-40-0a) must happen atomically with BC-40-0
            or unit tests will fail with ImportError.
```

Устраняет friction-точки C1–C5:
- `open_sdd_connection` → `open_db_connection` в `sdd.db.connection` (C2)
- `_is_postgres` → публичная `is_postgres_url()` с поддержкой `postgres://` (C4)
- новая `resolve_pg_url()` — единственный owner `SDD_DATABASE_URL` (C5)
- `src/sdd/db/__init__.py` экспортирует все три функции
- 4 production callers + 2 test-файла обновляют import/call (BC-40-0a)

### M2: Docker Infrastructure (BC-40-1 + BC-40-5)

```text
Spec:       §2 Architecture/BCs — BC-40-1, BC-40-5
BCs:        BC-40-1, BC-40-5
Invariants: I-CI-PG-4
Depends:    — (независим от M1; можно параллельно)
Risks:      Порт 5432 может быть занят локально — healthcheck обязателен
            для корректного ожидания в CI и scripts/dev-up.sh.
```

- `docker-compose.yml` с postgres:16-alpine, healthcheck, volume `pg_data`
- `scripts/dev-up.sh` — ждёт healthcheck, печатает `SDD_DATABASE_URL`
- `Makefile`: цели `pg-up`, `pg-down`, `ci-pg`

### M3: Test Infrastructure (BC-40-4 + BC-40-6)

```text
Spec:       §2 Architecture/BCs — BC-40-4, BC-40-6; §5 Invariants
BCs:        BC-40-4, BC-40-6
Invariants: I-CI-PG-2, I-CI-PG-3, I-DB-SCHEMA-1, I-DB-TEST-1
Depends:    M1 (pg_conn fixture использует open_db_connection, is_postgres_url, resolve_pg_url)
Risks:      C3 (двойная изоляция схем) — fixture ДОЛЖЕН использовать monkeypatch
            для SDD_PROJECT, иначе CLI subprocess видит другую схему.
            pg marker ДОЛЖЕН быть объявлен в pyproject.toml до создания тестов.
```

- `tests/conftest.py`: fixtures `pg_url` + `pg_conn` с исправлениями C1–C5
- `pyproject.toml`: `postgres` extra, `pg` marker, `scripts/` в pythonpath

### M4: PG Integration Tests (BC-40-3)

```text
Spec:       §2 Architecture/BCs — BC-40-3; §7 Use Cases; §9 Verification
BCs:        BC-40-3
Invariants: I-CI-PG-1, I-CI-PG-2, I-CI-PG-3, I-CI-PG-4, I-DB-SCHEMA-1,
            I-STATE-REBUILD-1
Depends:    M1 (open_db_connection), M3 (pg_conn fixture + pg marker)
Risks:      test_migration_round_trip требует доступного migrate_duckdb_to_pg.py
            (уже существует как untracked file); скрипт должен быть в pythonpath.
            Без живого PG все тесты должны SKIP (I-CI-PG-3), не FAIL.
```

3 файла в `tests/integration/`:
- `test_pg_init_project.py` — schema creation, search_path coverage (C1, I-DB-SCHEMA-1)
- `test_pg_migration.py` — round-trip migration + skip без PG (I-STATE-REBUILD-1, I-CI-PG-3)
- `test_pg_rebuild_state.py` — schema isolation + teardown guard (I-CI-PG-2, I-DB-TEST-1)

### M5: GitHub Actions CI (BC-40-2)

```text
Spec:       §2 Architecture/BCs — BC-40-2; §6 Pre/Post Conditions; §9 Verification
BCs:        BC-40-2
Invariants: I-CI-PG-1, I-CI-PG-4
Depends:    M2 (docker-compose images и credentials), M3 (pg marker), M4 (tests/integration/)
Risks:      Матрица Python 3.11×3.12 / PG 15×16 = 4 job'а — все должны быть зелёными.
            Job `unit` ДОЛЖЕН запускаться без PG; `pg-integration` job добавляет
            service container. Healthcheck wait-loop обязателен (I-CI-PG-4).
```

- `.github/workflows/ci.yml`: два job'а — `unit` и `pg-integration`
- Job `unit`: lint (ruff) + mypy + unit tests + check-handler-purity (без PG)
- Job `pg-integration`: матрица Python×PG, PG service container, `SDD_DATABASE_URL`, integration tests

---

## Risk Notes

- R-1: **Rename scope** — `open_sdd_connection` переименовывается только в `sdd.db.connection`
  (multi-dialect). `sdd.infra.db.open_sdd_connection` (DuckDB event store, 15+ callers) НЕТРОНУТ.
  Смешение этих двух — критическая ошибка. Mitigation: BC-40-0a фиксирует список из 6 файлов.

- R-2: **Schema isolation C3** — autouse fixture `_test_postgres_schema` устанавливает
  `SDD_PROJECT=test_default`; `pg_conn` должен делать monkeypatch для перекрытия.
  Без monkeypatch CLI subprocess видит другую схему → тесты нестабильны.
  Mitigation: BC-40-4 явно документирует monkeypatch.setenv("SDD_PROJECT", project_name).

- R-3: **Порядок M3→M4** — `pg` marker должен быть объявлен в pyproject.toml (M3)
  до запуска тестов из M4, иначе pytest выдаст warning/error о неизвестном маркере.
  Mitigation: M4 зависит от M3 (явная зависимость в плане).

- R-4: **CI secrets** — credentials `sdd/sdd` публичны в docker-compose.yml и CI;
  это intentional (dev/test только). Mitigation: spec §10 явно исключает production PG.
