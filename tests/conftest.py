from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
from collections.abc import Generator
from typing import Any

import psycopg
import pytest

from sdd.db.connection import open_db_connection
from sdd.infra.paths import reset_sdd_root

# Read-only subdirs to symlink from project .sdd/ so tests can still find
# norm_catalog.yaml, project_profile.yaml etc. via SDD_HOME-based path functions.
_SDD_READONLY_SUBDIRS = ("norms", "config", "specs", "specs_draft", "plans",
                          "tasks", "templates", "docs", "contracts")
# Projection files copied (not symlinked) into runtime/ so commands like sdd show-state
# work but writes stay in the isolated copy and don't touch production files.
_SDD_RUNTIME_COPY_FILES = ("State_index.yaml", "audit_log.jsonl")


@pytest.fixture(autouse=True)
def _reset_sdd_root() -> Generator[None, None, None]:
    reset_sdd_root()
    yield
    reset_sdd_root()


@pytest.fixture(autouse=True)
def _isolate_sdd_home(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Prevent tests from touching the production DB via event_store_file().

    Creates a per-test SDD_HOME in a dedicated tmp dir (not in pytest's tmp_path,
    so os.listdir(tmp_path) is unaffected). Read-only config dirs (norms, config …)
    are symlinked from the project .sdd/ so subprocess tests still find config files.
    state/ and runtime/ are isolated empty dirs — the production DB is never reached.

    SDD_DATABASE_URL passthrough (BC-45-E, Путь A): if SDD_DATABASE_URL is set in the
    parent env (CI with PG), pass it through so event_store_url() resolves correctly.
    Unit tests without SDD_DATABASE_URL must use explicit db_path — event_store_url()
    will raise EnvironmentError after BC-45-A, which is the correct unit-test behaviour.
    """
    project_sdd = pathlib.Path(".sdd").resolve()
    with tempfile.TemporaryDirectory(prefix="sdd_test_home_") as tmpdir:
        sdd_dir = pathlib.Path(tmpdir) / ".sdd"
        sdd_dir.mkdir()
        for subdir in _SDD_READONLY_SUBDIRS:
            src = project_sdd / subdir
            if src.exists():
                (sdd_dir / subdir).symlink_to(src)
        (sdd_dir / "state").mkdir()
        runtime_dir = sdd_dir / "runtime"
        runtime_dir.mkdir()
        for fname in _SDD_RUNTIME_COPY_FILES:
            src = project_sdd / "runtime" / fname
            if src.exists():
                shutil.copy2(src, runtime_dir / fname)
        monkeypatch.setenv("SDD_HOME", str(sdd_dir))
        if db_url := os.environ.get("SDD_DATABASE_URL"):
            monkeypatch.setenv("SDD_DATABASE_URL", db_url)
        reset_sdd_root()
        yield
    reset_sdd_root()


@pytest.fixture(autouse=True)
def _test_postgres_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance (I-DB-TEST-1): PostgreSQL schema in tests MUST match p_test_*.

    Sets SDD_PROJECT=test_default so open_sdd_connection resolves schema=p_test_default.
    """
    monkeypatch.setenv("SDD_PROJECT", "test_default")


@pytest.fixture()
def sdd_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Generator[pathlib.Path, None, None]:
    sdd_dir = tmp_path / ".sdd"
    sdd_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("SDD_HOME", str(sdd_dir))
    reset_sdd_root()
    yield sdd_dir


@pytest.fixture()
def pg_url() -> str:
    """I-CI-PG-2: skip test when SDD_DATABASE_URL is not configured."""
    url = os.environ.get("SDD_DATABASE_URL", "")
    if not url:
        pytest.skip("SDD_DATABASE_URL not set — PostgreSQL tests skipped")
    return url


@pytest.fixture()
def pg_conn(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> Generator[object, None, None]:
    """I-CI-PG-3: isolated PostgreSQL connection using schema p_test_pg."""
    monkeypatch.setenv("SDD_PROJECT", "test_pg")
    conn = open_db_connection(pg_url)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def _require_sdd_database_url() -> str:
    """Fail-fast guard: skip PG tests if SDD_DATABASE_URL not set.

    FakeEventLog unit tests work without PG — only PG fixtures call this.
    """
    url = os.environ.get("SDD_DATABASE_URL")
    if not url:
        pytest.skip("SDD_DATABASE_URL not set — skipping PG integration tests")
    return url


def _apply_sdd_ddl(conn: Any, schema: str) -> None:
    """Apply event_log DDL to an existing schema (I-PG-DDL-1)."""
    from sdd.infra.event_log import _PG_DDL
    conn.execute(f"SET search_path = {schema}, public")
    for stmt in _PG_DDL:
        conn.execute(stmt)


@pytest.fixture(scope="session")
def _pg_shared_schema(_require_sdd_database_url: str) -> Generator[dict[str, str], None, None]:
    """Session-scoped schema: DDL applied once per test session (BC-47-D, I-TEST-TRUNCATE-1).

    Schema name includes PID so parallel workers (pytest-xdist) get distinct schemas.
    """
    schema = f"test_sdd_{os.getpid()}"
    base_url = _require_sdd_database_url
    test_url = f"{base_url}?options=-csearch_path%3D{schema}"

    conn = psycopg.connect(base_url)
    conn.execute(f"CREATE SCHEMA {schema}")
    _apply_sdd_ddl(conn, schema)
    conn.commit()
    conn.close()

    yield {"base_url": base_url, "schema": schema, "test_url": test_url}

    conn = psycopg.connect(base_url)
    conn.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture()
def pg_test_db(_pg_shared_schema: dict[str, str]) -> Generator[str, None, None]:
    """TRUNCATE-based per-test isolation (BC-47-D, I-TEST-TRUNCATE-1).

    Resets event_log and p_meta before each test — faster than per-test schema creation.
    Skip-safe: skipped when SDD_DATABASE_URL is not set (via _pg_shared_schema dependency).
    """
    base_url = _pg_shared_schema["base_url"]
    schema = _pg_shared_schema["schema"]
    test_url = _pg_shared_schema["test_url"]

    conn = psycopg.connect(base_url)
    conn.execute(f"SET search_path = {schema}, public")
    conn.execute("TRUNCATE event_log RESTART IDENTITY")
    conn.execute("DELETE FROM p_meta")
    conn.execute("INSERT INTO p_meta DEFAULT VALUES")
    conn.commit()
    conn.close()

    yield test_url


@pytest.fixture()
def tmp_db_path(pg_test_db: str) -> str:
    """PostgreSQL test schema URL (replaces DuckDB tmp_db_path — BC-46-E).

    Skip-safe: skipped when SDD_DATABASE_URL is not set.
    """
    return pg_test_db


@pytest.fixture()
def in_memory_db(pg_test_db: str) -> Generator[object, None, None]:
    """PostgreSQL test connection (replaces DuckDB in_memory_db — BC-46-E).

    Skip-safe: skipped when SDD_DATABASE_URL is not set.
    """
    conn = psycopg.connect(pg_test_db)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Enforcement tests (BC-46-F, BC-46-E)
# ---------------------------------------------------------------------------

def test_duckdb_not_in_dependencies() -> None:
    """I-NO-DUCKDB-1: duckdb must not appear in pyproject.toml."""
    pyproject = pathlib.Path("pyproject.toml").read_text()
    assert "duckdb" not in pyproject.lower(), "duckdb found in pyproject.toml"


@pytest.mark.pg
def test_pg_test_db_fixture_isolated(pg_test_db: str) -> None:
    """BC-46-E: pg_test_db uses a test schema (search_path contains test_ prefix)."""
    assert "test_" in pg_test_db
    with psycopg.connect(pg_test_db) as conn:
        row = conn.execute("SELECT current_schema()").fetchone()
        assert row is not None
        assert row[0].startswith("test_")


@pytest.mark.pg
def test_pg_test_db_truncate_isolation(pg_test_db: str) -> None:
    """BC-47-D: event_log is empty at the start of each test (TRUNCATE isolation)."""
    with psycopg.connect(pg_test_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()
        assert row is not None
        assert row[0] == 0, "event_log must be empty after TRUNCATE (I-TEST-TRUNCATE-1)"


@pytest.mark.pg
def test_postgres_event_log_append_via_kernel(pg_test_db: str) -> None:
    """BC-47-D: PostgresEventLog.append stores an event using the pg_test_db fixture."""
    import time
    import uuid
    from dataclasses import dataclass

    from sdd.core.events import DomainEvent, EventLevel
    from sdd.infra.event_log import EventLog

    @dataclass(frozen=True)
    class _ConfTestMinimalEvent(DomainEvent):
        """Stub event; unknown to reducer (EV-4 skip)."""

    event = _ConfTestMinimalEvent(
        event_type="_conftest_minimal",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L2,
        event_source="test",
        caused_by_meta_seq=None,
    )
    el = EventLog(pg_test_db)
    el.append([event], source="test", allow_outside_kernel="test")

    with psycopg.connect(pg_test_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()
        assert row is not None
        assert row[0] == 1, "expected 1 event in event_log after append"
