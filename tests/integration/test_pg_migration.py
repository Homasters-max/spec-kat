"""Integration tests for DuckDB → PostgreSQL migration script.

Invariants: I-CI-PG-1, I-CI-PG-3, I-STATE-REBUILD-1
Skipped when SDD_DATABASE_URL is not set (I-CI-PG-3 via pg_url fixture).
"""
from __future__ import annotations

import json
import pathlib
import sys

import duckdb
import pytest

from sdd.commands.init_project import InitProjectHandler
from sdd.db.connection import open_db_connection

# Allow importing the migration script without installing it as a package.
_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from migrate_duckdb_to_pg import cmd_import  # noqa: E402

_EVENT_COUNT = 5


class _Cmd:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


@pytest.fixture()
def _pg_schema(pg_url: str, tmp_db_path: str) -> str:
    """Create an isolated PG schema for the migration test; drop it on teardown."""
    name = "migration_rt"
    schema = f"p_{name}"
    handler = InitProjectHandler(tmp_db_path)
    handler.handle(_Cmd({"name": name, "db_url": pg_url}))
    yield schema
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def duck_source(tmp_path: pathlib.Path) -> str:
    """Temporary DuckDB file with a small events table (_EVENT_COUNT rows)."""
    db_path = str(tmp_path / "source.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE events (
            seq                BIGINT PRIMARY KEY,
            partition_key      VARCHAR NOT NULL DEFAULT 'default',
            event_id           VARCHAR NOT NULL,
            event_type         VARCHAR NOT NULL,
            payload            TEXT    NOT NULL,
            schema_version     INTEGER NOT NULL DEFAULT 1,
            appended_at        BIGINT  NOT NULL,
            level              VARCHAR,
            expired            BOOLEAN NOT NULL DEFAULT FALSE,
            event_source       VARCHAR NOT NULL DEFAULT 'runtime',
            caused_by_meta_seq BIGINT,
            batch_id           VARCHAR
        )
    """)
    rows = [
        (
            i,
            "default",
            f"evt-{i:04d}",
            "TestEvent",
            json.dumps({"idx": i, "data": f"payload-{i}"}),
            1,
            1_700_000_000 + i,
            None,
            False,
            "runtime",
            None,
            None,
        )
        for i in range(1, _EVENT_COUNT + 1)
    ]
    conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.close()
    return db_path


@pytest.mark.pg
def test_migration_round_trip(
    duck_source: str,
    pg_url: str,
    _pg_schema: str,
) -> None:
    """I-CI-PG-1, I-CI-PG-3, I-STATE-REBUILD-1: event count matches before/after migration.

    SKIP when SDD_DATABASE_URL is unset (pg_url fixture calls pytest.skip).
    """
    # Confirm source count in DuckDB
    duck_conn = duckdb.connect(duck_source)
    source_count: int = duck_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    duck_conn.close()
    assert source_count == _EVENT_COUNT

    # Run migration (cmd_import returns normally on success; exits 1 on failure)
    cmd_import(duckdb_url=duck_source, pg_url=pg_url, pg_schema=_pg_schema)

    # Verify count in PostgreSQL
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(f"SET search_path = {_pg_schema}, shared")
        cur.execute("SELECT COUNT(*) FROM events")
        pg_count: int = cur.fetchone()[0]
    finally:
        conn.close()

    assert pg_count == source_count, (
        f"Count mismatch after migration: DuckDB={source_count}, PostgreSQL={pg_count}"
    )
