"""Tests for EventStore replay pre-filter and cache invalidation.

Invariants: I-INVALID-2, I-INVALID-CACHE-1
Spec: Spec_v28_WriteKernelGuard.md §2 BC-WG-2, §5
"""
from __future__ import annotations

import logging

import pytest

from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventInput, sdd_append_batch
from sdd.infra.event_store import EventStore


def _insert_event(db_path: str, event_type: str, payload: dict) -> int:
    """Insert a single event and return its seq."""
    sdd_append_batch(
        [EventInput(event_type=event_type, payload=payload)],
        db_path=db_path,
    )
    conn = open_sdd_connection(db_path)
    try:
        row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
        return int(row[0])
    finally:
        conn.close()


def test_replay_skips_invalidated_seq(tmp_db_path: str) -> None:
    """I-INVALID-2: EventStore.replay() must exclude events whose seq is invalidated."""
    # Insert a normal event and capture its seq
    target_seq = _insert_event(tmp_db_path, "TaskImplemented", {"task_id": "T-0001"})

    # Insert a second normal event (should appear in replay)
    other_seq = _insert_event(tmp_db_path, "TaskImplemented", {"task_id": "T-0002"})

    # Invalidate the first event
    _insert_event(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": target_seq, "reason": "test invalidation", "invalidated_by_phase": 28},
    )

    store = EventStore(tmp_db_path)
    result = store.replay()

    seqs = {e["seq"] for e in result}
    assert target_seq not in seqs, (
        f"Invalidated seq={target_seq} must not appear in replay result"
    )
    assert other_seq in seqs, (
        f"Non-invalidated seq={other_seq} must appear in replay result"
    )


def test_replay_no_warning_for_invalidated(
    tmp_db_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    """I-INVALID-2: filtering invalidated events must log DEBUG only, never WARNING."""
    target_seq = _insert_event(tmp_db_path, "TaskImplemented", {"task_id": "T-0001"})
    _insert_event(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": target_seq, "reason": "test", "invalidated_by_phase": 28},
    )

    store = EventStore(tmp_db_path)
    with caplog.at_level(logging.DEBUG, logger="sdd.infra.event_store"):
        result = store.replay()

    warning_records = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and str(target_seq) in r.getMessage()
    ]
    assert not warning_records, (
        f"Expected no WARNING for invalidated seq={target_seq}, got: {warning_records}"
    )

    debug_records = [
        r for r in caplog.records
        if r.levelno == logging.DEBUG and "skipping invalidated" in r.getMessage()
    ]
    assert debug_records, "Expected at least one DEBUG log for skipped invalidated seq"

    seqs = {e["seq"] for e in result}
    assert target_seq not in seqs


def test_cache_invalidated_after_append(tmp_db_path: str) -> None:
    """I-INVALID-CACHE-1: _invalidated_cache must be reset to None on every append()."""
    _insert_event(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": 999, "reason": "test", "invalidated_by_phase": 28},
    )

    store = EventStore(tmp_db_path)

    # Populate the cache
    seqs = store._get_invalidated_seqs()
    assert 999 in seqs
    assert store._invalidated_cache is not None

    # Any append() must reset the cache
    store.append(
        events=[],
        source="test",
    )
    assert store._invalidated_cache is None, (
        "I-INVALID-CACHE-1: _invalidated_cache must be None after append()"
    )
