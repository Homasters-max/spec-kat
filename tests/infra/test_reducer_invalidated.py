"""Test that _replay_from_event_log emits DEBUG (not WARNING) for invalidated seqs.

Invariant: I-INVALIDATE-PG-1 (replay safety — skipped seqs are logged at DEBUG only).
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import pytest

from sdd.infra.db import open_sdd_connection
from sdd.infra.projections import _get_invalidated_seqs, _replay_from_event_log


def _seed_event(db_url: str, event_type: str, payload: dict, level: str = "L1") -> int:
    """Insert an event into event_log; return its sequence_id."""
    conn = open_sdd_connection(db_url)
    try:
        event_id = str(uuid.uuid4())
        payload_json = json.dumps(payload, sort_keys=True)
        conn.execute(
            "INSERT INTO event_log "
            "(event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired) "
            "VALUES (%s, %s, %s::jsonb, %s, 'runtime', NULL, FALSE)",
            [event_id, event_type, payload_json, level],
        )
        conn.commit()
        row = conn.execute("SELECT MAX(sequence_id) FROM event_log").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def test_reducer_debug_for_invalidated_seq(
    tmp_db_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Replay skips invalidated seq with DEBUG only — no WARNING (I-INVALIDATE-PG-1)."""
    target_seq = _seed_event(tmp_db_path, "SomeObsoleteEvent", {"data": "obsolete"})
    _seed_event(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": target_seq, "reason": "test invalidation", "invalidated_by_phase": 46},
    )

    with caplog.at_level(logging.DEBUG):
        _replay_from_event_log(tmp_db_path)

    debug_msgs = [
        r for r in caplog.records
        if r.levelno == logging.DEBUG and str(target_seq) in r.message
    ]
    assert debug_msgs, (
        f"Expected DEBUG log mentioning seq={target_seq}, got records: "
        f"{[(r.levelname, r.message) for r in caplog.records]}"
    )

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, (
        f"Expected no WARNING during replay, got: {[(r.levelname, r.message) for r in warnings]}"
    )


def test_get_invalidated_seqs_accessible() -> None:
    """_get_invalidated_seqs is importable from projections (I-INVALIDATE-PG-1)."""
    assert callable(_get_invalidated_seqs), "_get_invalidated_seqs must be callable"
