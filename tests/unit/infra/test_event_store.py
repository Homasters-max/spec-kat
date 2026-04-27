"""Tests for infra/event_store.py — EventStore write path + EventLog crash isolation.

Invariants covered: I-ES-1, I-EL-UNIFIED-2, I-DB-TEST-1
Spec ref: Spec_v4 §9 Verification row 2a, §4.12; Spec_v34 §9
"""
from __future__ import annotations

from typing import Any

import pytest

import sdd.infra.event_log as _el_module
import sdd.infra.event_store as _es_module
from sdd.core.events import TaskImplementedEvent
from sdd.infra.event_log import EventInput, EventLog
from sdd.infra.event_store import EventStore


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


def test_crash_before_append_leaves_files_unchanged(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When open_sdd_connection raises inside EventLog.append(), error propagates and no DB file is created (I-EL-UNIFIED-2, I-DB-TEST-1)."""
    db_path = str(tmp_path / "crash_test.duckdb")

    el = EventLog(db_path=db_path)

    def _failing_conn(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(_el_module, "open_sdd_connection", _failing_conn)

    with pytest.raises(Exception):
        el.append([_make_task_event()], source="test", allow_outside_kernel="test")

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
