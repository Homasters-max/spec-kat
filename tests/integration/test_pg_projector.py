"""Integration tests: Projector against live PostgreSQL.

Invariants: I-PROJ-1, I-PROJ-NOOP-1, I-TABLE-SEP-1, I-EVENT-PURE-1
Skipped when SDD_DATABASE_URL is not set (pg_url fixture calls pytest.skip).
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from sdd.core.events import TaskImplementedEvent
from sdd.db.connection import open_db_connection
from sdd.infra.projector import Projector

pytestmark = pytest.mark.pg

_SCHEMA = "p_test_projector"


def _task_event(task_id: str) -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id=f"test-impl-{task_id}",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id=task_id,
        phase_id=43,
        timestamp="2026-01-01T00:00:00Z",
    )


@pytest.fixture()
def _pg_projector_schema(
    pg_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[str, None, None]:
    """Create an isolated schema for Projector tests; drop on teardown."""
    monkeypatch.setenv("SDD_PROJECT", "test_projector")

    import psycopg

    conn = psycopg.connect(pg_url)
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
        conn.execute("CREATE SCHEMA IF NOT EXISTS shared")
        conn.commit()
    finally:
        conn.close()

    yield pg_url

    conn = psycopg.connect(pg_url)
    try:
        conn.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.commit()
    finally:
        conn.close()


def _query_task(pg_url: str, task_id: str) -> Any:
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT task_id, phase_id, status FROM p_tasks WHERE task_id = %s",
            (task_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


@pytest.mark.usefixtures("_pg_projector_schema")
def test_pg_projector_apply_task_implemented(pg_url: str) -> None:
    """I-PROJ-1: TaskImplemented event → p_tasks row with status='DONE'."""
    task_id = "T-PROJ-IMPL-001"
    event = _task_event(task_id)

    with Projector(pg_url) as projector:
        projector.apply(event)

    row = _query_task(pg_url, task_id)
    assert row is not None, f"Expected row for task_id={task_id!r} in p_tasks"
    assert row[0] == task_id
    assert row[1] == 43
    assert row[2] == "DONE"


@pytest.mark.usefixtures("_pg_projector_schema")
def test_pg_projector_idempotent(pg_url: str) -> None:
    """I-PROJ-1: applying the same TaskImplemented event twice → exactly one row in p_tasks."""
    task_id = "T-PROJ-IDEM-001"
    event = _task_event(task_id)

    with Projector(pg_url) as p1:
        p1.apply(event)

    with Projector(pg_url) as p2:
        p2.apply(event)  # idempotent: ON CONFLICT DO UPDATE

    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM p_tasks WHERE task_id = %s", (task_id,))
        count = cur.fetchone()[0]
    finally:
        conn.close()

    assert count == 1, f"Expected exactly 1 row, got {count} (idempotency violation)"


@pytest.mark.usefixtures("_pg_projector_schema")
def test_pg_execute_and_project_full_pipeline(pg_url: str) -> None:
    """I-FAIL-1, I-PROJ-1: full pipeline — PostgresEventLog TX1 + Projector TX2 (BC-43-F).

    Tests that after TX1 (event_log INSERT) and TX2 (_apply_projector_safe),
    the event is in event_log and p_tasks is updated.
    """
    from sdd.commands.registry import _apply_projector_safe
    from sdd.infra.event_log import PostgresEventLog

    task_id = "T-PIPELINE-FULL-001"
    event = _task_event(task_id)

    # TX1: append event to PostgreSQL event_log
    pg_el = PostgresEventLog(pg_url)
    pg_el.append([event], source="test", allow_outside_kernel="test")

    # Verify TX1 committed
    assert pg_el.max_seq() is not None

    # TX2: apply to p_* via Projector
    with Projector(pg_url) as projector:
        _apply_projector_safe(projector, [event])

    # Verify p_tasks updated (TX2 committed)
    row = _query_task(pg_url, task_id)
    assert row is not None, f"Expected row for task_id={task_id!r} in p_tasks after TX2"
    assert row[2] == "DONE"


@pytest.mark.usefixtures("_pg_projector_schema")
def test_pg_projector_failure_does_not_rollback_event_log(pg_url: str) -> None:
    """I-FAIL-1, I-PROJ-SAFE-1: Projector failure in TX2 must not rollback event_log TX1."""
    from unittest.mock import patch

    from sdd.commands.registry import _apply_projector_safe
    from sdd.infra.event_log import PostgresEventLog

    task_id = "T-ROLLBACK-GUARD-001"
    event = _task_event(task_id)

    # TX1: append event to event_log
    pg_el = PostgresEventLog(pg_url)
    pg_el.append([event], source="test", allow_outside_kernel="test")
    seq_before = pg_el.max_seq()
    assert seq_before is not None

    # TX2: Projector.apply() raises — must not propagate or rollback TX1
    with Projector(pg_url) as projector:
        with patch.object(projector, "apply", side_effect=RuntimeError("simulated DB failure")):
            _apply_projector_safe(projector, [event])  # must not raise

    # Verify event_log TX1 is intact
    seq_after = pg_el.max_seq()
    assert seq_after == seq_before, (
        f"event_log was modified by Projector failure: seq before={seq_before}, after={seq_after}"
    )

    events_in_log = pg_el.replay()
    task_events = [e for e in events_in_log if e.get("event_type") == "TaskImplemented"]
    assert task_events, "event_log must contain TaskImplemented after Projector failure (I-PROJ-SAFE-1)"
