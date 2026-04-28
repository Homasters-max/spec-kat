from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
from collections.abc import Generator

import pytest

from sdd.db.connection import open_db_connection
from sdd.infra.db import open_sdd_connection
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
def _guard_production_db() -> Generator[None, None, None]:
    prod_db = pathlib.Path(".sdd/state/sdd_events.duckdb").resolve()
    mtime_before = prod_db.stat().st_mtime_ns if prod_db.exists() else None
    yield
    if prod_db.exists() and mtime_before is not None:
        mtime_after = prod_db.stat().st_mtime_ns
        assert mtime_after == mtime_before, f"Test modified production DB: {prod_db}"


@pytest.fixture()
def sdd_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Generator[pathlib.Path, None, None]:
    sdd_dir = tmp_path / ".sdd"
    sdd_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("SDD_HOME", str(sdd_dir))
    reset_sdd_root()
    yield sdd_dir


@pytest.fixture()
def in_memory_db() -> Generator[object, None, None]:
    conn = open_sdd_connection(":memory:")
    yield conn
    conn.close()


@pytest.fixture()
def tmp_db_path(tmp_path: pathlib.Path) -> str:
    return str(tmp_path / "test_sdd_events.duckdb")


@pytest.fixture(autouse=True)
def _test_postgres_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance (I-DB-TEST-1): PostgreSQL schema in tests MUST match p_test_*.

    Sets SDD_PROJECT=test_default so open_sdd_connection resolves schema=p_test_default.
    """
    monkeypatch.setenv("SDD_PROJECT", "test_default")


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


@pytest.fixture(autouse=True)
def _duckdb_fail_fast(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """I-DB-TEST-2: In test context (PYTEST_CURRENT_TEST), timeout_secs=0.0 (fail-fast).

    Signals fail-fast intent via SDD_DB_TIMEOUT_SECS=0.0.  The production layer
    may read this env var to configure DuckDB busy/lock timeout accordingly.
    """
    monkeypatch.setenv("SDD_DB_TIMEOUT_SECS", "0.0")
    yield
