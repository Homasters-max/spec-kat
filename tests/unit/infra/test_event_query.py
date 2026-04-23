"""Tests for infra/event_query.py.

Invariants covered: I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2
"""
from __future__ import annotations

import json

from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import sdd_append
from sdd.infra.event_query import EventLogQuerier, QueryFilters


# ── helpers ───────────────────────────────────────────────────────────────────


def _insert(
    db_path: str,
    *,
    event_type: str = "TestEvent",
    payload: dict | None = None,
    event_source: str = "runtime",
    expired: bool = False,
    seq_override: int | None = None,
) -> None:
    """Insert one event directly — allows setting expired and seq for test control."""
    if payload is None:
        payload = {}
    import hashlib, time

    ts = int(time.time() * 1000)
    raw = (event_type + json.dumps(payload, sort_keys=True) + str(ts)).encode()
    event_id = hashlib.sha256(raw + str(seq_override or 0).encode()).hexdigest()
    # schema_version=3 prevents ensure_sdd_schema from re-running the
    # "ADD COLUMN IF NOT EXISTS expired" migration, which in DuckDB 1.5.x
    # resets all expired values to FALSE (the column default).
    conn = open_sdd_connection(db_path)
    try:
        seq_expr = str(seq_override) if seq_override is not None else "nextval('sdd_event_seq')"
        conn.execute(
            f"""
            INSERT INTO events
                (seq, event_id, event_type, payload, schema_version,
                 appended_at, level, event_source, caused_by_meta_seq, expired)
            VALUES
                ({seq_expr}, ?, ?, ?, 3, ?, NULL, ?, NULL, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [event_id, event_type, json.dumps(payload, sort_keys=True), ts, event_source, expired],
        )
    finally:
        conn.close()


# ── I-QE-1: ordering ──────────────────────────────────────────────────────────


def test_query_order_asc(tmp_db_path: str) -> None:
    for i in range(3):
        _insert(tmp_db_path, event_type=f"E{i}")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(order="ASC"))
    seqs = [r.seq for r in results]
    assert seqs == sorted(seqs), "I-QE-1: expected ascending seq order"


def test_query_order_desc(tmp_db_path: str) -> None:
    for i in range(3):
        _insert(tmp_db_path, event_type=f"E{i}")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(order="DESC"))
    seqs = [r.seq for r in results]
    assert seqs == sorted(seqs, reverse=True), "I-QE-1: expected descending seq order"


# ── I-QE-2: event_source exact match ─────────────────────────────────────────


def test_query_source_filter_meta(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_source="meta")
    _insert(tmp_db_path, event_source="runtime")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(event_source="meta"))
    assert len(results) == 1
    assert results[0].event_source == "meta", "I-QE-2: only meta events expected"


def test_query_source_filter_runtime(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_source="meta")
    _insert(tmp_db_path, event_source="runtime")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(event_source="runtime"))
    assert len(results) == 1
    assert results[0].event_source == "runtime", "I-QE-2: only runtime events expected"


def test_query_source_filter_none(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_source="meta")
    _insert(tmp_db_path, event_source="runtime")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(event_source=None))
    assert len(results) == 2, "I-QE-2: None filter should return all events"


# ── I-QE-3: expired exclusion ─────────────────────────────────────────────────


def test_query_excludes_expired_by_default(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_type="Active")
    _insert(tmp_db_path, event_type="Archived", expired=True)
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters())  # include_expired=False by default
    assert all(not r.expired for r in results), "I-QE-3: expired rows must be excluded by default"
    assert len(results) == 1


def test_query_includes_expired_when_flag_set(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_type="Active")
    _insert(tmp_db_path, event_type="Archived", expired=True)
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(include_expired=True))
    assert len(results) == 2, "I-QE-3: include_expired=True must include expired rows"


# ── I-QE-4: phase_id filter ───────────────────────────────────────────────────


def test_query_phase_id_filter(tmp_db_path: str) -> None:
    _insert(tmp_db_path, payload={"phase_id": 5})
    _insert(tmp_db_path, payload={"phase_id": 6})
    _insert(tmp_db_path, payload={"phase_id": 6})
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(phase_id=6))
    assert len(results) == 2, "I-QE-4: only phase_id=6 events expected"
    for r in results:
        assert json.loads(r.payload)["phase_id"] == 6


# ── limit ─────────────────────────────────────────────────────────────────────


def test_query_limit(tmp_db_path: str) -> None:
    for i in range(5):
        _insert(tmp_db_path, event_type=f"E{i}")
    querier = EventLogQuerier(tmp_db_path)
    results = querier.query(QueryFilters(limit=2))
    assert len(results) == 2, "limit=2 must return at most 2 rows"


# ── I-PROJ-CONST-1: determinism ───────────────────────────────────────────────


def test_query_deterministic(tmp_db_path: str) -> None:
    for i in range(3):
        _insert(tmp_db_path, event_type=f"E{i}")
    querier = EventLogQuerier(tmp_db_path)
    filters = QueryFilters(order="ASC")
    first = querier.query(filters)
    second = querier.query(filters)
    assert first == second, "I-PROJ-CONST-1: same filters must yield identical results"


# ── I-PROJ-CONST-2: no shared state ───────────────────────────────────────────


def test_querier_no_shared_state(tmp_db_path: str) -> None:
    _insert(tmp_db_path, event_source="meta")

    querier = EventLogQuerier(tmp_db_path)

    # First call — returns one event
    r1 = querier.query(QueryFilters(event_source="meta"))
    assert len(r1) == 1

    # Insert a second event after first call
    _insert(tmp_db_path, event_source="meta")

    # Second call must reflect new DB state — no cached result from first call
    r2 = querier.query(QueryFilters(event_source="meta"))
    assert len(r2) == 2, "I-PROJ-CONST-2: each query() call must read fresh state, no hidden cache"
