"""Tests for infra/event_store.py — EventStore atomic write path.

Invariants covered: I-ES-1
Spec ref: Spec_v4 §9 Verification row 2a, §4.12
"""
from __future__ import annotations

from typing import Any

import pytest

import sdd.infra.event_store as _es_module
from sdd.core.events import TaskImplementedEvent
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventInput
from sdd.infra.event_store import EventStore, EventStoreError


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_task_event(task_id: str = "T-404", seq: int = 1) -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id=f"evt-{task_id}-{seq}",
        appended_at=1_700_000_000_000,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id=task_id,
        phase_id=4,
        timestamp="2026-04-22T00:00:00Z",
    )


# ── tests ─────────────────────────────────────────────────────────────────────


def test_append_is_atomic(tmp_db_path: str) -> None:
    """append() writes all events in one DB transaction: all land or none do (I-ES-1)."""
    events = [_make_task_event(f"T-40{i}") for i in range(3)]
    store = EventStore(db_path=tmp_db_path)
    store.append(events, source="test")

    conn = open_sdd_connection(tmp_db_path)
    rows = conn.execute("SELECT event_type FROM events ORDER BY seq").fetchall()
    conn.close()

    assert len(rows) == 3
    assert all(r[0] == "TaskImplemented" for r in rows)


def test_append_only_write_path(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """EventStore.append() delegates exclusively to sdd_append_batch — no other write path (I-ES-1)."""
    captured: list[EventInput] = []

    def _fake_batch(inputs: list[EventInput], db_path: str) -> None:
        captured.extend(inputs)

    monkeypatch.setattr(_es_module, "sdd_append_batch", _fake_batch)

    store = EventStore(db_path=tmp_db_path)
    store.append([_make_task_event("T-404")], source="test.module")

    assert len(captured) == 1
    assert captured[0].event_type == "TaskImplemented"
    assert captured[0].payload["_source"] == "test.module"


def test_crash_before_append_leaves_files_unchanged(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When sdd_append_batch raises, EventStoreError is re-raised and no DB file is created (I-ES-1)."""
    db_path = str(tmp_path / "crash_test.duckdb")

    def _failing_batch(inputs: list[EventInput], db_path: str) -> None:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(_es_module, "sdd_append_batch", _failing_batch)

    store = EventStore(db_path=db_path)
    with pytest.raises(EventStoreError, match="EventStore.append\\(\\) failed"):
        store.append([_make_task_event()], source="test")

    assert not (tmp_path / "crash_test.duckdb").exists()


def test_event_store_routes_through_infra_db(
    tmp_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EventStore.append() calls sdd_append_batch with the correct db_path — never duckdb.connect directly (I-ES-1)."""
    batch_calls: list[tuple[list[EventInput], str]] = []

    def _capture_batch(inputs: list[EventInput], db_path: str) -> None:
        batch_calls.append((inputs, db_path))

    monkeypatch.setattr(_es_module, "sdd_append_batch", _capture_batch)

    store = EventStore(db_path=tmp_db_path)
    store.append([_make_task_event("T-404", 99)], source="infra.test")

    assert len(batch_calls) == 1
    inputs, used_db_path = batch_calls[0]
    assert used_db_path == tmp_db_path
    assert len(inputs) == 1
    assert inputs[0].event_type == "TaskImplemented"
