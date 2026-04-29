"""Tests for infra/event_log.py — PostgreSQL-backed EventLog.

Invariants covered: I-TEST-TRUNCATE-1
"""
from __future__ import annotations

import psycopg
import pytest


@pytest.mark.pg
def test_pg_test_db_truncate_isolation(pg_test_db: str) -> None:
    """I-TEST-TRUNCATE-1: event_log is empty at the start of each test (TRUNCATE isolation).

    Verifies that the pg_test_db fixture correctly resets the event_log table
    via TRUNCATE RESTART IDENTITY before each test, so tests are fully isolated.
    """
    with psycopg.connect(pg_test_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()
        assert row is not None
        assert row[0] == 0, "event_log must be empty after TRUNCATE (I-TEST-TRUNCATE-1)"
