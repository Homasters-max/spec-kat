"""Tests for commands/query_events.py.

Invariants covered: I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2, I-CLI-DB-RESOLUTION-1
"""
from __future__ import annotations

import json
import hashlib
import time

import unittest.mock

import pytest

from sdd.infra.db import open_sdd_connection
from sdd.infra.event_query import QueryFilters
from sdd.commands.query_events import (
    QueryEventsCommand,
    QueryEventsHandler,
    QueryEventsResult,
    QueryHandler,
)


# ── test_query_events_argparse_no_eager_eval ─────────────────────────────────


def test_query_events_argparse_no_eager_eval(tmp_db_path: str) -> None:
    """event_store_url must NOT be called when --db is explicit (I-CLI-DB-RESOLUTION-1).

    With eager eval (default=str(event_store_url())), the function is called at
    add_argument() time — even when --db is provided on the CLI.
    With lazy eval (default=None + post-parse resolution), it is never called when
    --db is explicit.
    """
    from sdd.commands import query_events
    with unittest.mock.patch("sdd.commands.query_events.event_store_url") as mock_url:
        query_events.main(["--db", tmp_db_path, "--list-types"])
    mock_url.assert_not_called()


# ── helpers ───────────────────────────────────────────────────────────────────


def _insert(
    db_path: str,
    *,
    event_type: str = "TestEvent",
    payload: dict | None = None,
    event_source: str = "runtime",
    expired: bool = False,
) -> None:
    if payload is None:
        payload = {}
    ts = int(time.time() * 1000)
    raw = (event_type + json.dumps(payload, sort_keys=True) + str(ts)).encode()
    event_id = hashlib.sha256(raw).hexdigest()
    conn = open_sdd_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO events
                (seq, event_id, event_type, payload, schema_version,
                 appended_at, level, event_source, caused_by_meta_seq, expired)
            VALUES
                (nextval('sdd_event_seq'), ?, ?, ?, 3, ?, NULL, ?, NULL, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [event_id, event_type, json.dumps(payload, sort_keys=True), ts, event_source, expired],
        )
    finally:
        conn.close()


# ── test_execute_returns_result ───────────────────────────────────────────────


def test_execute_returns_result(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_type="TaskImplemented", payload={"phase_id": 6})
    _insert(tmp_db_path, event_type="TaskValidated", payload={"phase_id": 6})

    handler = QueryEventsHandler(tmp_db_path)
    result = handler.execute(QueryEventsCommand(filters=QueryFilters(phase_id=6)))

    assert isinstance(result, QueryEventsResult)
    assert result.total == len(result.events)
    assert result.total == 2
    event_types = {e.event_type for e in result.events}
    assert event_types == {"TaskImplemented", "TaskValidated"}


# ── test_no_db_write_on_query ─────────────────────────────────────────────────


def test_no_db_write_on_query(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_type="BeforeQuery")

    def _count(db_path: str) -> int:
        conn = open_sdd_connection(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()

    before = _count(tmp_db_path)
    handler = QueryEventsHandler(tmp_db_path)
    handler.execute(QueryEventsCommand(filters=QueryFilters()))
    after = _count(tmp_db_path)

    assert before == after, "I-PROJ-CONST-1: execute() must not write to DB"


# ── test_handler_conforms_to_query_handler_protocol ──────────────────────────


def test_handler_conforms_to_query_handler_protocol(tmp_db_path: str) -> None:
    handler = QueryEventsHandler(tmp_db_path)

    # Runtime check: QueryEventsHandler must satisfy QueryHandler Protocol
    assert hasattr(handler, "execute"), "QueryEventsHandler must have execute()"

    # isinstance check via Protocol (runtime_checkable not required — duck-type check)
    cmd = QueryEventsCommand(filters=QueryFilters())
    result = handler.execute(cmd)
    assert isinstance(result, QueryEventsResult)

    # Verify it does NOT expose CommandHandler attributes (no last_result side-channel)
    assert not hasattr(handler, "last_result"), (
        "QueryEventsHandler must NOT be a CommandHandler (no last_result side-channel)"
    )
    assert not hasattr(handler, "run"), (
        "QueryEventsHandler must NOT be a CommandHandler (no run() method)"
    )
