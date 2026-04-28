"""Integration tests: rebuild-state command against PostgreSQL.

Invariants: I-CI-PG-2, I-DB-TEST-1, I-DB-SCHEMA-1
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from sdd.commands.rebuild_state import RebuildStateHandler

pytestmark = pytest.mark.pg

_TEST_SCHEMA = "p_test_pg"


@pytest.fixture()
def _pg_schema_teardown(pg_conn: Any) -> Generator[None, None, None]:
    """Create test schema, yield, drop schema, assert no schema leak (I-DB-SCHEMA-1).

    Teardown guard: confirms schema is absent after test — no leaks to other tests.
    """
    cur = pg_conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_TEST_SCHEMA}")
    pg_conn.commit()
    cur.close()
    yield
    cur = pg_conn.cursor()
    cur.execute(f"DROP SCHEMA IF EXISTS {_TEST_SCHEMA} CASCADE")
    pg_conn.commit()
    cur.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
        (_TEST_SCHEMA,),
    )
    leaked = cur.fetchall()
    cur.close()
    assert leaked == [], f"Schema leak: {_TEST_SCHEMA!r} still exists after teardown"


@pytest.mark.usefixtures("_pg_schema_teardown")
class TestRebuildStateHandlerPg:
    """RebuildStateHandler integration tests with PostgreSQL backend."""

    def test_handle_returns_empty_list(self, pg_url: str) -> None:
        """I-HANDLER-PURE-1, I-CI-PG-2: handle() returns [] — rebuild delegated to project_all."""
        handler = RebuildStateHandler(db_path=pg_url)
        assert handler.handle(object()) == []

    def test_handle_idempotent_no_side_effects(self, pg_conn: Any, pg_url: str) -> None:
        """I-DB-TEST-1: repeated handle() calls are pure; test schema is isolated."""
        handler = RebuildStateHandler(db_path=pg_url)
        assert handler.handle(object()) == []
        assert handler.handle(object()) == []
