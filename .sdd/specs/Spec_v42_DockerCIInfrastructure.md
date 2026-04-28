# Spec_v40 — Phase 40: Docker CI Infrastructure for PostgreSQL

Status: Draft
Baseline: Spec_v32_PostgresMigration.md, Spec_v35_TestHarnessElevation.md

---

## 0. Goal

Phase 32 реализовала полный слой PostgreSQL (схема, соединение, миграционный скрипт),
но acceptance-тесты помечены DEFERRED — PostgreSQL недоступен в CI и локальном окружении.
Тесты запускаются только против DuckDB (`:memory:`), что нарушает TP-2 для всего PG-слоя.

Перед добавлением PG integration-тестов необходимо устранить 5 архитектурных friction-точек
в текущей кодовой базе, иначе тесты будут некорректными:

| ID | Severity | Проблема |
|----|----------|----------|
| C1 | HIGH / correctness | `pg_conn` fixture использует raw `psycopg2.connect()`, минуя шов `open_sdd_connection` → нет `driver selection` + `SET search_path`; у тестов нет production-path coverage |
| C2 | MEDIUM / навигируемость | два `open_sdd_connection` с несовместимыми сигнатурами: `sdd.db.connection` (multi-dialect) и `sdd.infra.db` (DuckDB event store) — одинаковое имя, разная семантика |
| C3 | HIGH / correctness | двойная изоляция схем: autouse `_test_postgres_schema` даёт `p_test_default` для subprocess/CLI, а `pg_conn` создаёт `p_test_{uuid}` — CLI и тест видят разные схемы |
| C4 | MEDIUM / subtle bug | `url.startswith("postgresql")` пропускает `postgres://` схему → тесты скипались бы даже при доступном PG |
| C5 | LOW / локальность | `SDD_DATABASE_URL` читается в двух местах независимо — нет единственного owner |

Эта фаза:
1. Исправляет C1–C5 через рефакторинг `src/sdd/db/connection.py` и `conftest.py`.
2. Добавляет `docker-compose.yml` с Postgres-сервисом, конфигурирует CI (GitHub Actions).
3. Поднимает все ранее DEFERRED acceptance-тесты до статуса PASS в автоматическом режиме.

**Принцип:** инфраструктура — это код. `docker-compose.yml` и CI-конфиг живут в репо,
версионируются вместе с кодом, проверяются при каждом PR.

---

## 1. Scope

### In-Scope

- **BC-40-0**: `src/sdd/db/connection.py` + `src/sdd/db/__init__.py` — рефакторинг (C1–C5)
  - `open_sdd_connection` → `open_db_connection` (C2)
  - `_is_postgres` → публичная `is_postgres_url(url)` с поддержкой `postgres://` (C4)
  - новая `resolve_pg_url() -> str | None` — единственный owner env var resolution (C5)
- **BC-40-0a**: обновление 4 callers + 2 test-файлов (`open_sdd_connection` → `open_db_connection`)
- **BC-40-1**: `docker-compose.yml` — Postgres-сервис для локальной разработки и тестов
- **BC-40-2**: `.github/workflows/ci.yml` — GitHub Actions с PG service container (2 job'а)
- **BC-40-3**: `tests/integration/` — 3 файла с PG acceptance-тестами
- **BC-40-4**: `tests/conftest.py` — `pg_conn` fixture с исправлениями C1–C5
- **BC-40-5**: `Makefile` / `scripts/dev-up.sh` — команды для быстрого старта локального окружения
- **BC-40-6**: `pyproject.toml` — `postgres` extra + `pg` marker + `scripts/` в pythonpath

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-40-0: `src/sdd/db/connection.py` + `src/sdd/db/__init__.py`

**Три изменения в `connection.py`:**

1. `_is_postgres` → публичная `is_postgres_url(url: str) -> bool` (C4)
2. `open_sdd_connection` → `open_db_connection` (C2)
3. Новая `resolve_pg_url() -> str | None` (C5)

```python
def is_postgres_url(url: str) -> bool:
    """Return True for postgresql:// or postgres:// schemes."""
    return url.startswith("postgresql://") or url.startswith("postgres://")

_is_postgres = is_postgres_url  # internal alias — existing call-sites unchanged

def resolve_pg_url() -> str | None:
    """Return SDD_DATABASE_URL if it is a PostgreSQL URL, else None. Never raises."""
    env = os.environ.get("SDD_DATABASE_URL", "")
    return env if (env and is_postgres_url(env)) else None

def open_db_connection(               # renamed from open_sdd_connection
    db_url: str | None = None,
    project: str | None = None,
    schema: str | None = None,
) -> Any:
    """Open SDD connection routing by URL scheme (I-DB-1). Body unchanged."""
    resolved = _resolve_url(db_url)
    if _is_postgres(resolved):
        return _open_postgres(resolved, project, schema)
    return _open_duckdb(resolved)
```

**Не трогать:** `_resolve_url`, `_open_postgres`, `_open_duckdb` — тела без изменений.  
**Не трогать:** `sdd.infra.db.open_sdd_connection` (DuckDB event store, 15+ callers).

**`src/sdd/db/__init__.py`** (текущее содержимое пусто, добавить экспорты):

```python
from sdd.db.connection import is_postgres_url, open_db_connection, resolve_pg_url

__all__ = ["is_postgres_url", "open_db_connection", "resolve_pg_url"]
```

### BC-40-0a: Обновление callers (C2)

4 production-файла + 2 test-файла, все меняют только import + вызовы:

| Файл | Изменение |
|------|-----------|
| `src/sdd/commands/init_project.py` | `open_sdd_connection` → `open_db_connection` (1 вызов) |
| `src/sdd/commands/analytics_refresh.py` | то же (1 вызов) |
| `scripts/migrate_duckdb_to_pg.py` | то же (~5 вызовов) |
| `tests/test_db_connection.py` | то же (import + 4 call-sites); rename класса; добавить `TestIsPostgresUrl`, `TestResolvePgUrl` |
| `tests/unit/commands/test_init_project.py` | 5 строк `patch("sdd.commands.init_project.open_sdd_connection", ...)` → `open_db_connection` |

### BC-40-1: docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: sdd
      POSTGRES_PASSWORD: sdd
      POSTGRES_DB: sdd
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sdd -d sdd"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 5s
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  pg_data:
```

Стандартный URL: `postgresql://sdd:sdd@localhost:5432/sdd`

### BC-40-2: GitHub Actions CI

Два отдельных job'а: `unit` (без PG) и `pg-integration` (матрица Python × PG):

```yaml
name: CI

on:
  push:
    branches: ["main", "dev/**"]
  pull_request:

jobs:
  unit:
    name: Unit (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]" psycopg2-binary
      - run: ruff check src/
      - run: mypy src/sdd/
      - run: pytest tests/unit/ tests/test_db_connection.py -q --tb=short
      - run: make check-handler-purity

  pg-integration:
    name: PG (Python ${{ matrix.python-version }}, PG ${{ matrix.pg-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
        pg-version: ["15", "16"]
    services:
      postgres:
        image: postgres:${{ matrix.pg-version }}-alpine
        env:
          POSTGRES_USER: sdd
          POSTGRES_PASSWORD: sdd
          POSTGRES_DB: sdd
        options: >-
          --health-cmd "pg_isready -U sdd -d sdd"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
        ports:
          - 5432:5432
    env:
      SDD_DATABASE_URL: postgresql://sdd:sdd@localhost:5432/sdd
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]" psycopg2-binary
      - name: Wait for PostgreSQL  # I-CI-PG-4
        run: |
          for i in $(seq 1 30); do
            pg_isready -h localhost -U sdd -d sdd && break
            echo "Waiting ($i/30)..."; sleep 2
          done
      - run: pytest tests/integration/ -m pg -v --tb=short
```

### BC-40-3: PG integration tests

```
tests/integration/
  __init__.py
  test_pg_init_project.py   # schema creation + search_path coverage (C1)
  test_pg_migration.py      # --import + count verification; pg_skip check
  test_pg_rebuild_state.py  # schema isolation, teardown guard
```

Все файлы начинаются с `pytestmark = pytest.mark.pg`.

**`test_pg_init_project.py`** — тесты:
- `test_init_project_creates_schema` — `pg_conn` fixture создаёт schema, проверяем через `information_schema.schemata`
- `test_schema_name_follows_convention` — schema == `f"p_{project_name}"` (I-DB-SCHEMA-1)
- `test_search_path_set_correctly` — `SHOW search_path` содержит schema (C1 coverage)

**`test_pg_migration.py`** — тесты:
- `test_pg_skip_when_no_url` — без `SDD_DATABASE_URL` тест должен быть SKIP, не FAIL (I-CI-PG-3)
- `test_migration_round_trip` — synthetic DuckDB event store → migration script `--import` → `count(PG) == count(DuckDB)` (I-STATE-REBUILD-1)

**`test_pg_rebuild_state.py`** — тесты:
- `test_pg_connection_is_isolated` — `current_schema()` == schema (I-CI-PG-2)
- `test_pg_conn_schema_prefix_is_p_test` — schema начинается с `p_test_` (I-DB-TEST-1 extended)
- `test_schema_dropped_in_teardown` — после теста schema не существует (teardown guard)

### BC-40-4: pg_conn fixture (conftest.py)

Исправленная версия с устранёнными C1–C5:

```python
import uuid
from sdd.db import is_postgres_url, resolve_pg_url
from sdd.db.connection import open_db_connection

@pytest.fixture()
def pg_url() -> str:
    """Возвращает SDD_DATABASE_URL если это живой PostgreSQL, иначе skip.

    C4: is_postgres_url() catches both postgresql:// and postgres://
    C5: resolve_pg_url() — единственный owner env var resolution
    I-CI-PG-3: skip (not FAIL) when PG not configured
    """
    url = resolve_pg_url()
    if url is None:
        pytest.skip("SDD_DATABASE_URL not set or not a PostgreSQL URL — PG tests skipped")
    return url


@pytest.fixture()
def pg_conn(pg_url: str, monkeypatch: pytest.MonkeyPatch):
    """Изолированная PG-схема на время одного теста.

    Yields: tuple[connection, schema_name, project_name]

    C1: open_db_connection() — production seam (driver selection + SET search_path)
    C3: monkeypatch SDD_PROJECT=test_{uuid} → subprocess CLI видит ту же схему
    I-CI-PG-2: per-test schema isolation, DROP CASCADE в teardown
    I-DB-TEST-1: никогда не трогает production-схему
    """
    project_name = f"test_{uuid.uuid4().hex[:8]}"
    schema = f"p_{project_name}"  # same formula as _open_postgres: p_{project}

    # Override autouse _test_postgres_schema (SDD_PROJECT=test_default)
    # so subprocess CLI calls в этом тесте используют тот же schema (C3)
    monkeypatch.setenv("SDD_PROJECT", project_name)

    import psycopg2
    admin_conn = psycopg2.connect(pg_url)
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema}")
    admin_conn.close()

    # Production-seam connection: psycopg3/psycopg2 fallback + SET search_path (C1)
    conn = open_db_connection(db_url=pg_url, project=project_name)

    yield conn, schema, project_name

    try:
        conn.close()
    finally:
        cleanup = psycopg2.connect(pg_url)
        cleanup.autocommit = True
        with cleanup.cursor() as cur:
            cur.execute(f"DROP SCHEMA {schema} CASCADE")
        cleanup.close()
```

**Исправления относительно предыдущей версии BC-40-4:**

| Проблема (старый вариант) | Исправление |
|---------------------------|-------------|
| `url.startswith("postgresql")` | `is_postgres_url(url)` — ловит `postgres://` (C4) |
| `os.environ.get("SDD_DATABASE_URL")` | `resolve_pg_url()` — один owner (C5) |
| `psycopg2.connect()` raw, нет `search_path` | `open_db_connection()` — production seam (C1) |
| Schema `p_test_{uuid}` ≠ `SDD_PROJECT` конвенция | `SDD_PROJECT=test_{uuid}` + monkeypatch (C3) |
| `conn.cursor().execute()` — cursor leak | `with admin_conn.cursor() as cur:` |
| `yield (conn, schema)` | `yield (conn, schema, project_name)` |

### BC-40-5: dev-up script

```bash
#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
docker compose -f "$COMPOSE_FILE" up -d postgres

echo "Waiting for PostgreSQL..."
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_isready -U sdd -d sdd -q; do
    sleep 1
done

export SDD_DATABASE_URL="postgresql://sdd:sdd@localhost:5432/sdd"
echo "PG ready. SDD_DATABASE_URL=$SDD_DATABASE_URL"
echo "Run: SDD_DATABASE_URL=$SDD_DATABASE_URL pytest tests/integration/ -m pg -v"
```

**Makefile** — добавить 3 цели:

```makefile
pg-up:
	@./scripts/dev-up.sh

pg-down:
	docker compose down -v

ci-pg:
	pytest tests/integration/ -m pg -v --tb=short
```

### BC-40-6: pyproject.toml

```toml
[project.optional-dependencies]
dev = [
    # ... существующие ...
]
postgres = [
    "psycopg2-binary>=2.9",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "scripts"]   # добавить scripts для импорта migrate_duckdb_to_pg
addopts = "--tb=short --timeout=30"
markers = [
    "pg: marks tests requiring a live PostgreSQL (SDD_DATABASE_URL must be set)",
]
```

Note: `psycopg2-binary` ставится в CI через `pip install ... psycopg2-binary`, а не через core
dependencies — чтобы DuckDB-only окружение продолжало работать без PG.

### Dependencies

```text
BC-40-3 → BC-40-4 : pg_conn fixture
BC-40-4 → BC-40-0 : open_db_connection, is_postgres_url, resolve_pg_url
BC-40-3 → BC-32   : использует sdd init-project, migrate_duckdb_to_pg.py
BC-40-2 → BC-40-1 : одинаковый образ и credentials
BC-40-5 → BC-40-1 : docker compose up
BC-40-6 → BC-40-2 : pg marker для --tb=short
```

---

## 3. Domain Events

Новых domain events нет. Фаза — инфраструктурная + рефакторинг, не изменяет EventLog.

---

## 4. Types & Interfaces

Новые публичные функции в `sdd.db` (BC-40-0):

```python
# sdd.db  (re-exported from sdd.db.connection)
def is_postgres_url(url: str) -> bool: ...
def open_db_connection(
    db_url: str | None = None,
    project: str | None = None,
    schema: str | None = None,
) -> Any: ...
def resolve_pg_url() -> str | None: ...
```

**Deprecated (удалены из `sdd.db.connection`):**

```python
# REMOVED — open_sdd_connection в sdd.db.connection (multi-dialect)
# НЕ ТРОГАТЬ — open_sdd_connection в sdd.infra.db (DuckDB event store, 15+ callers)
```

Добавляется `extras_require` в `pyproject.toml`:

```toml
[project.optional-dependencies]
postgres = ["psycopg2-binary>=2.9"]
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-CI-PG-1 | CI pipeline MUST run `tests/integration/` with live PostgreSQL on every PR | 40 |
| I-CI-PG-2 | PG integration tests MUST use isolated per-test schema (`p_test_*`); MUST drop schema in teardown | 40 |
| I-CI-PG-3 | PG tests MUST `pytest.skip` (not FAIL) when `SDD_DATABASE_URL` is absent or not a PG URL | 40 |
| I-CI-PG-4 | `docker-compose.yml` MUST define healthcheck; CI MUST wait for healthy status before running tests | 40 |
| I-DB-SCHEMA-1 | Schema name MUST follow `p_{project_name}` convention; `project_name` MUST be the value of `SDD_PROJECT` env var in the current process | 40 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-DB-1 | `db_url` MUST be explicit non-empty str |
| I-DB-TEST-1 | Tests MUST NOT open production DB |
| I-DB-TEST-2 | In test context: `timeout_secs = 0.0` (fail-fast) |
| I-STATE-REBUILD-1 | `reduce(all_events) == IncrementalReducer().apply_delta_from_scratch(all_events)` |

---

## 6. Pre/Post Conditions

### CI Run

**Pre:**
- `docker-compose.yml` существует в корне репо
- `.github/workflows/ci.yml` содержит PG service
- `SDD_DATABASE_URL` установлен в CI environment

**Post:**
- `pytest tests/unit/ tests/test_db_connection.py -q` завершается exit 0 (job `unit`)
- `pytest tests/integration/ -m pg -v` завершается exit 0 (job `pg-integration`)
- Все ранее DEFERRED acceptance-тесты (T-3217 и другие PG-тесты) → PASS
- Coverage не падает ниже порога `testing.coverage_threshold`

### Local dev-up

**Pre:**
- Docker установлен и запущен
- Порт 5432 свободен

**Post:**
- `sdd show-state` работает против PostgreSQL
- `sdd init-project --name sdd` создаёт схему `p_sdd`
- `pytest tests/integration/ -m pg -q` проходит без skip

---

## 7. Use Cases

### UC-40-1: Разработчик запускает PG-тесты локально

**Actor:** Developer  
**Trigger:** `./scripts/dev-up.sh`  
**Pre:** Docker запущен  
**Steps:**
1. `docker compose up -d postgres` — поднимает контейнер
2. `scripts/dev-up.sh` ждёт healthcheck, печатает `SDD_DATABASE_URL`
3. `SDD_DATABASE_URL=... pytest tests/integration/ -m pg -v` — все PG-тесты PASS  
**Post:** полный тестовый прогон с реальным Postgres

### UC-40-2: PR проходит CI с PG

**Actor:** GitHub Actions  
**Trigger:** push / pull_request  
**Pre:** `.github/workflows/ci.yml` содержит два job'а  
**Steps:**
1. Job `unit`: lint + mypy + unit tests (без PG)
2. Job `pg-integration`: поднимает Postgres service container, ждёт healthcheck
3. Устанавливает `SDD_DATABASE_URL`
4. `pytest tests/integration/ -m pg -v --tb=short`  
**Post:** зелёный CI, PG acceptance-тесты PASS по матрице Python×PG

### UC-40-3: Unit-тесты без PG (offline)

**Actor:** Developer без Docker  
**Trigger:** `pytest tests/unit/ -q`  
**Pre:** `SDD_DATABASE_URL` не установлен  
**Steps:**
1. `pytest tests/unit/ tests/test_db_connection.py -q` — DuckDB unit-тесты работают
2. `pytest tests/integration/ -m pg -q` — PG-тесты помечены `skip` (I-CI-PG-3)  
**Post:** 954+ unit-тестов PASS, 0 FAIL, PG-тесты SKIP (не FAIL)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-32 (`open_sdd_connection` → `open_db_connection`) | this replaces | PG connection через `SDD_DATABASE_URL` |
| BC-32 (`sdd init-project`) | this → BC-32 | создание `p_sdd` схемы в тестах |
| BC-32 (`migrate_duckdb_to_pg.py --import`) | this → BC-32 | acceptance-тест T-3217 |
| BC-35 (test harness) | this → BC-35 | fixtures из `conftest.py` |
| `sdd.infra.db.open_sdd_connection` | **НЕТРОНУТ** | все 15+ DuckDB callers работают как прежде |

### Reducer Extensions

Нет — фаза не добавляет domain events и не затрагивает reducer.

---

## 9. Verification

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `from sdd.db import is_postgres_url, open_db_connection, resolve_pg_url` — импорт без ошибок | BC-40-0 |
| 2 | `python3 -c "from sdd.db.connection import open_sdd_connection"` → ImportError | C2 |
| 3 | `is_postgres_url("postgres://x")` → True; `is_postgres_url("duckdb://x")` → False | C4 |
| 4 | `pytest tests/unit/ tests/test_db_connection.py -q` → 0 FAIL | BC-40-0a |
| 5 | `pytest tests/integration/ -m pg -v` (без PG) → все SKIP, 0 FAIL | I-CI-PG-3 |
| 6 | `test_init_project_creates_schema` — schema в `information_schema.schemata` | I-CI-PG-2, I-DB-SCHEMA-1 |
| 7 | `test_search_path_set_correctly` — `SHOW search_path` содержит schema | C1 |
| 8 | `test_migration_round_trip` — `count(PG) == count(DuckDB)` | I-STATE-REBUILD-1 |
| 9 | `test_schema_dropped_in_teardown` — schema не существует после теста | I-CI-PG-2, I-DB-TEST-1 |
| 10 | CI: матрица Python 3.11×3.12 / PG 15×16 — все 4 комбинации зелёные | I-CI-PG-1, I-CI-PG-4 |

```bash
# Локальная верификация (полный порядок)

# 1. Новое API доступно
python3 -c "from sdd.db import is_postgres_url, open_db_connection, resolve_pg_url; print('OK')"

# 2. Старое имя удалено из multi-dialect модуля
python3 -c "from sdd.db.connection import open_sdd_connection" && echo FAIL || echo OK

# 3. Unit tests (без PG)
pytest tests/unit/ tests/test_db_connection.py -q

# 4. Integration skip без PG
pytest tests/integration/ -m pg -v  # → все SKIPPED, 0 FAILED

# 5. Lint + typecheck
ruff check src/ && mypy src/sdd/

# 6. Handler purity
make check-handler-purity

# 7. С живым PG
./scripts/dev-up.sh
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest tests/integration/ -m pg -v
```

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Kubernetes / Helm deployment | отдельный проект вне SDD |
| PG connection pooling (pgbouncer) | Phase 41+ при необходимости |
| PG backup / restore | ops-задача вне SDD |
| Multi-region / HA Postgres | Phase 41+ |
| DWH second project (`p_dwh`) тесты | Phase 41 или при появлении DWH проекта |
| Удаление DuckDB fallback из кода | только после полного перехода всех окружений |

---

## 11. Полный список файлов

| Файл | Действие |
|------|----------|
| `src/sdd/db/connection.py` | Modify — rename + 2 new functions (BC-40-0) |
| `src/sdd/db/__init__.py` | Modify — add exports (BC-40-0) |
| `src/sdd/commands/init_project.py` | Modify — rename import + call (BC-40-0a) |
| `src/sdd/commands/analytics_refresh.py` | Modify — rename import + call (BC-40-0a) |
| `scripts/migrate_duckdb_to_pg.py` | Modify — rename import + ~5 calls (BC-40-0a) |
| `tests/test_db_connection.py` | Modify — rename + new test classes (BC-40-0a) |
| `tests/unit/commands/test_init_project.py` | Modify — 5 patch target strings (BC-40-0a) |
| `tests/conftest.py` | Modify — add `pg_url` + `pg_conn` fixtures (BC-40-4) |
| `tests/integration/__init__.py` | Create (BC-40-3) |
| `tests/integration/test_pg_init_project.py` | Create (BC-40-3) |
| `tests/integration/test_pg_migration.py` | Create (BC-40-3) |
| `tests/integration/test_pg_rebuild_state.py` | Create (BC-40-3) |
| `docker-compose.yml` | Create (BC-40-1) |
| `.github/workflows/ci.yml` | Create (BC-40-2) |
| `scripts/dev-up.sh` | Create, chmod +x (BC-40-5) |
| `Makefile` | Modify — add 3 targets (BC-40-5) |
| `pyproject.toml` | Modify — postgres extra + pg marker + scripts pythonpath (BC-40-6) |
