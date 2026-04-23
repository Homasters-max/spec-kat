"""Tests for batch_id column — I-EL-12.

Invariants covered: I-EL-12
"""
from __future__ import annotations

from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventInput, sdd_append, sdd_append_batch
from sdd.infra.event_query import EventLogQuerier, QueryFilters


# ── helpers ───────────────────────────────────────────────────────────────────


def _fetch_batch_ids(db_path: str) -> list[str | None]:
    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT batch_id FROM events ORDER BY seq ASC"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def _column_names(db_path: str) -> list[str]:
    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'events'"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


# ── schema ────────────────────────────────────────────────────────────────────


def test_batch_id_column_exists(tmp_db_path: str) -> None:
    open_sdd_connection(tmp_db_path).close()
    assert "batch_id" in _column_names(tmp_db_path)


# ── sdd_append_batch stamps batch_id ─────────────────────────────────────────


def test_batch_id_set_on_batch_append(tmp_db_path: str) -> None:
    sdd_append_batch(
        [
            EventInput(event_type="TestEvent", payload={"n": 1}),
            EventInput(event_type="TestEvent", payload={"n": 2}),
        ],
        db_path=tmp_db_path,
    )
    ids = _fetch_batch_ids(tmp_db_path)
    assert all(bid is not None for bid in ids)


def test_batch_id_same_within_one_call(tmp_db_path: str) -> None:
    sdd_append_batch(
        [
            EventInput(event_type="TestEvent", payload={"n": 1}),
            EventInput(event_type="TestEvent", payload={"n": 2}),
            EventInput(event_type="TestEvent", payload={"n": 3}),
        ],
        db_path=tmp_db_path,
    )
    ids = _fetch_batch_ids(tmp_db_path)
    assert len(set(ids)) == 1


def test_batch_id_uuid_unique_per_call(tmp_db_path: str) -> None:
    sdd_append_batch(
        [EventInput(event_type="TestEvent", payload={"call": 1})],
        db_path=tmp_db_path,
    )
    sdd_append_batch(
        [EventInput(event_type="TestEvent", payload={"call": 2})],
        db_path=tmp_db_path,
    )
    ids = _fetch_batch_ids(tmp_db_path)
    assert ids[0] != ids[1]


# ── sdd_append sets batch_id NULL ────────────────────────────────────────────


def test_batch_id_null_on_single_append(tmp_db_path: str) -> None:
    sdd_append("TestEvent", {"x": 1}, db_path=tmp_db_path)
    ids = _fetch_batch_ids(tmp_db_path)
    assert ids == [None]


# ── QueryFilters batch_id / is_batched clauses ────────────────────────────────


def test_batch_id_filter_exact(tmp_db_path: str) -> None:
    sdd_append_batch(
        [EventInput(event_type="BatchedEvent", payload={"n": 1})],
        db_path=tmp_db_path,
    )
    sdd_append("SingleEvent", {"n": 2}, db_path=tmp_db_path)

    target_bid = _fetch_batch_ids(tmp_db_path)[0]
    assert target_bid is not None

    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(batch_id=target_bid))
    assert len(results) == 1
    assert results[0].event_type == "BatchedEvent"


def test_is_batched_true_filter(tmp_db_path: str) -> None:
    sdd_append_batch(
        [EventInput(event_type="BatchedEvent", payload={"n": 1})],
        db_path=tmp_db_path,
    )
    sdd_append("SingleEvent", {"n": 2}, db_path=tmp_db_path)

    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(is_batched=True))
    assert len(results) == 1
    assert results[0].event_type == "BatchedEvent"


def test_is_batched_false_filter(tmp_db_path: str) -> None:
    sdd_append_batch(
        [EventInput(event_type="BatchedEvent", payload={"n": 1})],
        db_path=tmp_db_path,
    )
    sdd_append("SingleEvent", {"n": 2}, db_path=tmp_db_path)

    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(is_batched=False))
    assert len(results) == 1
    assert results[0].event_type == "SingleEvent"


def test_is_batched_none_no_filter(tmp_db_path: str) -> None:
    sdd_append_batch(
        [EventInput(event_type="BatchedEvent", payload={"n": 1})],
        db_path=tmp_db_path,
    )
    sdd_append("SingleEvent", {"n": 2}, db_path=tmp_db_path)

    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters())
    assert len(results) == 2
