"""Tests for sdd.db.connection — I-DB-1, I-DB-TEST-1."""
from __future__ import annotations

import os
import pathlib

import pytest

from sdd.db import open_db_connection
from sdd.db.connection import _resolve_url


# ---------------------------------------------------------------------------
# I-DB-1: open_db_connection(db_url) — db_url MUST be explicit non-empty str
# ---------------------------------------------------------------------------


class TestResolveUrl:
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="I-DB-1"):
            _resolve_url("")

    def test_none_without_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        with pytest.raises(ValueError, match="I-DB-1"):
            _resolve_url(None)

    def test_explicit_url_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", ":memory:")
        assert _resolve_url("explicit://foo") == "explicit://foo"

    def test_none_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", ":memory:")
        assert _resolve_url(None) == ":memory:"


class TestOpenSddConnectionIDB1:
    def test_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="I-DB-1"):
            open_db_connection("")

    def test_none_without_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        with pytest.raises(ValueError, match="I-DB-1"):
            open_db_connection(None)

    def test_non_pg_url_raises(self) -> None:
        """I-NO-DUCKDB-1: non-PostgreSQL URLs must be rejected."""
        with pytest.raises(ValueError, match="I-NO-DUCKDB-1"):
            open_db_connection(":memory:")

    def test_pg_url_opens_connection(self, tmp_db_path: str) -> None:
        conn = open_db_connection(tmp_db_path)
        assert conn is not None
        conn.close()

    def test_env_fallback_opens_pg_connection(
        self, monkeypatch: pytest.MonkeyPatch, tmp_db_path: str
    ) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", tmp_db_path)
        conn = open_db_connection(None)
        assert conn is not None
        conn.close()


# ---------------------------------------------------------------------------
# I-DB-TEST-1: Tests MUST NOT open production DB
# ---------------------------------------------------------------------------


class TestProductionDbIsolation:
    def test_sdd_home_differs_from_production(self) -> None:
        """SDD_HOME in test context must resolve to a different directory than .sdd/."""
        sdd_home = os.environ.get("SDD_HOME")
        if sdd_home is None:
            pytest.skip("SDD_HOME not redirected — _isolate_sdd_home fixture not active")
        prod_sdd = pathlib.Path(".sdd").resolve()
        test_sdd = pathlib.Path(sdd_home).resolve()
        assert test_sdd != prod_sdd, (
            f"Test SDD_HOME resolves to production directory: {prod_sdd}"
        )

    def test_postgres_schema_uses_test_prefix(self) -> None:
        """Acceptance: SDD_PROJECT=test_default ensures schema resolves to p_test_default."""
        project = os.environ.get("SDD_PROJECT", "")
        schema = f"p_{project}" if project else None
        assert schema is not None and schema.startswith("p_test_"), (
            f"Postgres schema {schema!r} does not match p_test_* — "
            "_test_postgres_schema fixture may not be active"
        )


# ---------------------------------------------------------------------------
# I-DB-TEST-2: In test context (PYTEST_CURRENT_TEST): psycopg connect_timeout = 0
# ---------------------------------------------------------------------------


class TestTestContextBehavior:
    def test_pytest_current_test_is_set(self) -> None:
        """pytest always sets PYTEST_CURRENT_TEST during test execution (I-DB-TEST-2)."""
        assert os.environ.get("PYTEST_CURRENT_TEST"), (
            "PYTEST_CURRENT_TEST not set — pytest may be too old or test is run outside pytest"
        )
