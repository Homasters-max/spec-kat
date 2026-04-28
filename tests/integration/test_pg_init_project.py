"""Integration tests for InitProjectHandler against live PostgreSQL.

Invariants: I-CI-PG-1, I-CI-PG-2, I-DB-SCHEMA-1
Skipped when SDD_DATABASE_URL is not set (I-CI-PG-3 via pg_url fixture).
"""
from __future__ import annotations

import pytest

from sdd.commands.init_project import InitProjectHandler
from sdd.db.connection import open_db_connection


class _Cmd:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


@pytest.fixture()
def _pg_cleanup(pg_url: str):
    """Drop project schemas created during a test."""
    to_drop: list[str] = []
    yield to_drop
    if not to_drop:
        return
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        for schema in to_drop:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.pg
def test_init_project_creates_schemas(pg_url: str, _pg_cleanup: list, tmp_db_path: str) -> None:
    """I-DB-SCHEMA-1: handler creates shared schema and p_{name} schema."""
    name = "ci_init_a"
    _pg_cleanup.append(f"p_{name}")

    handler = InitProjectHandler(tmp_db_path)
    events = handler.handle(_Cmd({"name": name, "db_url": pg_url}))

    assert len(events) == 1
    ev = events[0]
    assert ev.project_name == name
    assert ev.db_schema == f"p_{name}"

    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata"
            " WHERE schema_name IN (%s, %s)",
            (f"p_{name}", "shared"),
        )
        found = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    assert f"p_{name}" in found, "project schema was not created"
    assert "shared" in found, "shared schema was not created"


@pytest.mark.pg
def test_init_project_registers_in_shared_projects(pg_url: str, _pg_cleanup: list, tmp_db_path: str) -> None:
    """I-DB-SCHEMA-1: handler inserts a row into shared.projects."""
    name = "ci_init_b"
    _pg_cleanup.append(f"p_{name}")

    handler = InitProjectHandler(tmp_db_path)
    events = handler.handle(_Cmd({"name": name, "db_url": pg_url}))
    project_id = events[0].project_id

    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, db_schema FROM shared.projects WHERE name = %s",
            (name,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, "no row in shared.projects after init-project"
    assert row[0] == project_id
    assert row[1] == f"p_{name}"


@pytest.mark.pg
def test_open_db_connection_sets_search_path(
    pg_url: str, _pg_cleanup: list, monkeypatch: pytest.MonkeyPatch, tmp_db_path: str
) -> None:
    """I-CI-PG-1: open_db_connection sets search_path to p_{project}, shared."""
    name = "ci_init_c"
    _pg_cleanup.append(f"p_{name}")

    # Create the schema so SET search_path doesn't fail
    handler = InitProjectHandler(tmp_db_path)
    handler.handle(_Cmd({"name": name, "db_url": pg_url}))

    monkeypatch.setenv("SDD_PROJECT", name)
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("SHOW search_path")
        search_path: str = cur.fetchone()[0]
    finally:
        conn.close()

    assert f"p_{name}" in search_path, f"p_{name} not in search_path: {search_path!r}"
    assert "shared" in search_path, f"shared not in search_path: {search_path!r}"
