"""I-VR-STABLE-3: I-IDEM-1 — same command_id → duplicate INSERT silently skipped (P-7)."""
from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings

from sdd.infra.db import open_sdd_connection
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


def _event_count(db_path: str) -> int:
    conn = open_sdd_connection(db_path)
    try:
        row = conn.execute("SELECT count(*) FROM events").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


@given(cmds=valid_command_sequence())
@settings(max_examples=30, deadline=None)
def test_duplicate_run_same_state(cmds):
    """Running the same command sequence twice leaves state unchanged (I-IDEM-1)."""
    wrapped = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        _, state1 = execute_sequence(wrapped, db)
        _, state2 = execute_sequence(wrapped, db)
        assert state1 == state2


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None)
def test_duplicate_run_no_new_events(cmds):
    """Second run of the same sequence adds no new events (all duplicate-skipped)."""
    wrapped = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        execute_sequence(wrapped, db)
        count_after_first = _event_count(db)
        execute_sequence(wrapped, db)
        count_after_second = _event_count(db)
        assert count_after_second == count_after_first


@given(cmds=valid_command_sequence(max_cmds=5))
@settings(max_examples=20, deadline=None)
def test_triple_run_idempotent(cmds):
    """Three runs of the same sequence produce the same final state."""
    wrapped = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        _, s1 = execute_sequence(wrapped, db)
        _, s2 = execute_sequence(wrapped, db)
        _, s3 = execute_sequence(wrapped, db)
        assert s1 == s2 == s3
