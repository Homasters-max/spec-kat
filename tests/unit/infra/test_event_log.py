"""Tests for infra/event_log.py.

Invariants covered: I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7,
                    I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12,
                    I-EL-UNIFIED-2, I-EL-BATCH-ID-1, I-OPTLOCK-1,
                    I-OPTLOCK-ATOMIC-1, I-IDEM-SCHEMA-1, I-IDEM-LOG-1,
                    I-INVALID-CACHE-1, I-KERNEL-WRITE-1, I-EL-NON-KERNEL-1
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import duckdb
import pytest

import sdd.infra.event_log as _el_module
from sdd.core.errors import StaleStateError
from sdd.core.events import DomainEvent, TaskImplementedEvent, TaskValidatedEvent
from sdd.core.execution_context import KernelContextError, kernel_context
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import (
    EventInput,
    EventLog,
    _make_event_id,
    archive_expired_l3,
    meta_context,
    sdd_append,
    sdd_append_batch,
    sdd_replay,
)


def _make_domain_event(task_id: str = "T-001", phase_id: int = 34) -> DomainEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id="test-id",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id=task_id,
        phase_id=phase_id,
        timestamp="2026-01-01T00:00:00Z",
    )


# ── helper ────────────────────────────────────────────────────────────────────


class _FailingConnWrapper:
    """Wraps a real DuckDB connection; raises RuntimeError on the N-th INSERT into events."""

    def __init__(self, real: Any, fail_on_nth_insert: int = 2) -> None:
        self._real = real
        self._fail_on = fail_on_nth_insert
        self._insert_count = 0

    def begin(self) -> None:
        self._real.begin()

    def commit(self) -> None:
        self._real.commit()

    def rollback(self) -> None:
        self._real.rollback()

    def execute(self, sql: str, params: list[Any] | None = None) -> Any:
        if "INSERT INTO events" in sql:
            self._insert_count += 1
            if self._insert_count >= self._fail_on:
                raise RuntimeError("simulated mid-batch DB failure")
        if params is not None:
            return self._real.execute(sql, params)
        return self._real.execute(sql)

    def close(self) -> None:
        self._real.close()


# ── tests ─────────────────────────────────────────────────────────────────────


def test_sdd_append_idempotent(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Duplicate event_id → ON CONFLICT DO NOTHING; only 1 row stored (I-PK-2)."""
    fixed_id = "fixed-event-id-idempotency-test"
    monkeypatch.setattr(_el_module, "_make_event_id", lambda *_: fixed_id)

    sdd_append("TaskImplemented", {"task": "T-001"}, db_path=tmp_db_path, level="L1")
    sdd_append("TaskImplemented", {"task": "T-001"}, db_path=tmp_db_path, level="L1")

    conn = open_sdd_connection(tmp_db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_id = ?", [fixed_id]
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_replay_ordered_by_seq(tmp_db_path: str) -> None:
    """sdd_replay returns events in strictly ascending seq order (I-PK-3)."""
    for i in range(3):
        sdd_append(
            "TaskImplemented",
            {"task": f"T-{i:03d}"},
            db_path=tmp_db_path,
            level="L1",
            event_source="runtime",
        )

    events = sdd_replay(db_path=tmp_db_path, level="L1", source="runtime")
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(seqs) == 3


def test_replay_filters_level_source(tmp_db_path: str) -> None:
    """sdd_replay filters by level and source; non-matching events excluded (I-EL-10)."""
    sdd_append("TaskImplemented", {"x": 1}, db_path=tmp_db_path, level="L1", event_source="runtime")
    sdd_append("MetricRecorded", {"x": 2}, db_path=tmp_db_path, level="L2", event_source="runtime")
    sdd_append("ToolUseStarted", {"x": 3}, db_path=tmp_db_path, level="L3", event_source="meta")

    l1_events = sdd_replay(db_path=tmp_db_path, level="L1", source="runtime")
    assert len(l1_events) == 1
    assert l1_events[0]["event_type"] == "TaskImplemented"


def test_l3_archived_not_deleted(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """archive_expired_l3 sets expired=TRUE without deleting rows (I-EL-7).

    DuckDB 1.5.x does not auto-commit DML on close() when DDL ran on the same
    connection (open_sdd_connection runs CREATE OR REPLACE SEQUENCE). We patch
    open_sdd_connection to wrap DML in explicit begin/commit so the UPDATE
    actually persists — letting us verify the expired flag in a new connection.
    """
    _real_open = _el_module.open_sdd_connection

    class _CommitOnDML:
        """Wraps a DuckDB connection; wraps UPDATE/INSERT/DELETE in begin/commit."""

        _DML = ("UPDATE ", "INSERT ", "DELETE ")

        def __init__(self, conn: Any) -> None:
            self._c = conn

        def _is_dml(self, sql: str) -> bool:
            s = sql.strip().upper()
            return any(s.startswith(p) for p in self._DML)

        def execute(self, sql: str, params: list[Any] | None = None) -> Any:
            dml = self._is_dml(sql)
            if dml:
                self._c.begin()
            result = self._c.execute(sql, params) if params is not None else self._c.execute(sql)
            if dml:
                self._c.commit()
            return result

        def begin(self) -> None:
            self._c.begin()

        def commit(self) -> None:
            self._c.commit()

        def rollback(self) -> None:
            self._c.rollback()

        def close(self) -> None:
            self._c.close()

    def _committing_open(db_path: str = tmp_db_path) -> _CommitOnDML:
        return _CommitOnDML(_real_open(db_path))

    monkeypatch.setattr(_el_module, "open_sdd_connection", _committing_open)

    sdd_append("ToolUseStarted", {"x": 1}, db_path=tmp_db_path, level="L3", event_source="runtime")
    cutoff_ms = int(time.time() * 1000) + 60_000
    count = archive_expired_l3(cutoff_ms=cutoff_ms, db_path=tmp_db_path)
    assert count >= 1

    # Verify using raw duckdb.connect — open_sdd_connection runs ensure_sdd_schema which
    # triggers a DuckDB 1.5.x bug that reverts committed DML when DDL runs on the same file.
    conn = duckdb.connect(tmp_db_path)
    row = conn.execute(
        "SELECT expired FROM events WHERE event_type = 'ToolUseStarted'"
    ).fetchone()
    total = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'ToolUseStarted'"
    ).fetchone()[0]
    conn.close()

    assert row is not None and row[0] is True  # expired flag set
    assert total == 1  # row not deleted


def test_batch_atomic(tmp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """sdd_append_batch rolls back completely if an error occurs mid-batch (I-EL-11)."""
    # Initialise schema
    conn_init = open_sdd_connection(tmp_db_path)
    conn_init.close()

    real_open = _el_module.open_sdd_connection

    def patched_open(db_path: str = tmp_db_path) -> _FailingConnWrapper:
        real_conn = real_open(db_path)
        return _FailingConnWrapper(real_conn, fail_on_nth_insert=2)

    monkeypatch.setattr(_el_module, "open_sdd_connection", patched_open)

    # Provide explicit level to avoid calling classify_event_level().value in event_log.py
    events = [
        EventInput(event_type="TaskImplemented", payload={"task": "T-A"}, level="L1"),
        EventInput(event_type="TaskValidated", payload={"task": "T-B"}, level="L1"),
    ]

    with pytest.raises(RuntimeError, match="mid-batch"):
        sdd_append_batch(events, db_path=tmp_db_path)

    # Restore and verify rollback — no events in DB
    monkeypatch.undo()
    conn2 = open_sdd_connection(tmp_db_path)
    count = conn2.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn2.close()
    assert count == 0


def test_i_el_9_no_direct_connect() -> None:
    """event_log.py must not call duckdb.connect directly (I-EL-9)."""
    event_log_path = Path(_el_module.__file__)
    result = subprocess.run(
        ["grep", "-n", "duckdb.connect", str(event_log_path)],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", (
        f"duckdb.connect found in event_log.py:\n{result.stdout}"
    )


def test_replay_defaults(tmp_db_path: str) -> None:
    """sdd_replay() defaults to level='L1' source='runtime' (I-EL-10)."""
    sdd_append("TaskImplemented", {"d": 1}, db_path=tmp_db_path, level="L1", event_source="runtime")
    sdd_append("MetricRecorded", {"d": 2}, db_path=tmp_db_path, level="L2", event_source="runtime")

    events = sdd_replay(db_path=tmp_db_path)  # defaults: level=L1, source=runtime
    types = {e["event_type"] for e in events}
    assert "TaskImplemented" in types
    assert "MetricRecorded" not in types


def test_meta_context_sets_caused_by(tmp_db_path: str) -> None:
    """Within meta_context(N), sdd_append stores caused_by_meta_seq=N (I-EL-8a)."""
    meta_seq = 42
    with meta_context(meta_seq):
        sdd_append(
            "TaskImplemented",
            {"task": "T-meta"},
            db_path=tmp_db_path,
            level="L1",
            event_source="runtime",
        )

    conn = open_sdd_connection(tmp_db_path)
    row = conn.execute(
        "SELECT caused_by_meta_seq FROM events WHERE event_type = 'TaskImplemented'"
    ).fetchone()
    conn.close()
    assert row is not None and row[0] == meta_seq


def test_event_id_deterministic() -> None:
    """Same (event_type, payload, timestamp_ms) always yields same event_id (I-EL-12)."""
    event_type = "TaskImplemented"
    payload = {"task": "T-999", "phase": 1}
    ts = 1_700_000_000_000

    id1 = _make_event_id(event_type, payload, ts)
    id2 = _make_event_id(event_type, payload, ts)
    assert id1 == id2
    assert len(id1) == 64  # SHA-256 hex


def test_sdd_append_invalid_source_raises(tmp_db_path: str) -> None:
    """sdd_append with invalid event_source raises ValueError (I-EL-1)."""
    with pytest.raises(ValueError, match="event_source"):
        sdd_append("TaskImplemented", {}, db_path=tmp_db_path, event_source="invalid")


# ── EventLog class tests (T-3404 acceptance criteria) ─────────────────────────


def test_event_log_append_simple(tmp_db_path: str) -> None:
    """EventLog.append() without locking writes event to DB (I-EL-UNIFIED-2, I-ES-1)."""
    el = EventLog(tmp_db_path)
    event = _make_domain_event(task_id="T-001")
    el.append([event], source="test_module", allow_outside_kernel="test")

    conn = open_sdd_connection(tmp_db_path)
    rows = conn.execute(
        "SELECT event_type FROM events WHERE event_type = 'TaskImplemented'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_event_log_append_locked_optimistic(tmp_db_path: str) -> None:
    """EventLog.append() with expected_head enforces optimistic lock (I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1)."""
    el = EventLog(tmp_db_path)

    # Seed one event
    seed = _make_domain_event(task_id="T-seed")
    el.append([seed], source="test", allow_outside_kernel="test")
    head = el.max_seq()
    assert head is not None

    # Correct head → succeeds
    event = _make_domain_event(task_id="T-002")
    el.append([event], source="test", expected_head=head, allow_outside_kernel="test")

    # Stale head → StaleStateError
    with pytest.raises(StaleStateError):
        el.append([event], source="test", expected_head=head, allow_outside_kernel="test")


def test_event_log_append_idempotent(tmp_db_path: str, caplog: pytest.LogCaptureFixture) -> None:
    """Duplicate (command_id, event_index) is skipped; INFO logged when rows_inserted == 0
    (I-IDEM-SCHEMA-1, I-IDEM-LOG-1)."""
    el = EventLog(tmp_db_path)
    cid = "test-command-id-idempotent"
    event = _make_domain_event(task_id="T-003")

    el.append([event], source="test", command_id=cid, allow_outside_kernel="test")

    with caplog.at_level(logging.INFO, logger="sdd.infra.event_log"):
        el.append([event], source="test", command_id=cid, allow_outside_kernel="test")

    assert any("idempotent no-op" in r.message for r in caplog.records)

    conn = open_sdd_connection(tmp_db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'TaskImplemented'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_event_log_append_batch_id_multi(tmp_db_path: str) -> None:
    """Multi-event append with batch_id=None auto-generates UUID4; all rows share it
    (I-EL-BATCH-ID-1)."""
    el = EventLog(tmp_db_path)
    events = [
        _make_domain_event(task_id="T-A"),
        _make_domain_event(task_id="T-B"),
    ]
    el.append(events, source="test", allow_outside_kernel="test")

    conn = open_sdd_connection(tmp_db_path)
    rows = conn.execute(
        "SELECT batch_id FROM events WHERE event_type = 'TaskImplemented' ORDER BY seq"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    batch_ids = [r[0] for r in rows]
    assert all(b is not None for b in batch_ids), "batch_id must not be NULL for multi-event"
    assert batch_ids[0] == batch_ids[1], "all events in call must share the same batch_id"


def test_event_log_append_batch_id_single_null(tmp_db_path: str) -> None:
    """Single-event append with batch_id=None writes batch_id=NULL (I-EL-BATCH-ID-1)."""
    el = EventLog(tmp_db_path)
    event = _make_domain_event(task_id="T-single")
    el.append([event], source="test", allow_outside_kernel="test")

    conn = open_sdd_connection(tmp_db_path)
    row = conn.execute(
        "SELECT batch_id FROM events WHERE event_type = 'TaskImplemented'"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] is None, "single-event append must write batch_id=NULL"


# ── EventLog.replay() + max_seq() tests (T-3405 acceptance criteria) ──────────


def test_event_log_replay_filters_invalidated(tmp_db_path: str) -> None:
    """EventLog.replay() excludes events whose seq is targeted by EventInvalidated (I-INVALID-CACHE-1, I-ES-1)."""
    el = EventLog(tmp_db_path)

    # Append two domain events
    el.append([_make_domain_event(task_id="T-to-invalidate")], source="test", allow_outside_kernel="test")
    target_seq = el.max_seq()
    assert target_seq is not None

    el.append([_make_domain_event(task_id="T-keeper")], source="test", allow_outside_kernel="test")
    keeper_seq = el.max_seq()

    # Mark the first event as invalidated
    sdd_append(
        "EventInvalidated",
        {"target_seq": target_seq},
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    # Fresh instance — no cache primed
    el2 = EventLog(tmp_db_path)
    replayed = el2.replay()
    replayed_seqs = {e["seq"] for e in replayed}

    assert target_seq not in replayed_seqs, "invalidated seq must be excluded from replay"
    assert keeper_seq in replayed_seqs, "non-invalidated event must remain in replay"


def test_event_log_max_seq_empty(tmp_db_path: str) -> None:
    """`EventLog.max_seq()` returns None when the EventLog is empty (I-ES-1)."""
    el = EventLog(tmp_db_path)
    # Initialise schema without inserting any events
    open_sdd_connection(tmp_db_path).close()
    assert el.max_seq() is None


# ── EventLog.exists_command / exists_semantic / get_error_count (T-3406) ──────


def test_event_log_exists_command(tmp_db_path: str) -> None:
    """EventLog.exists_command() returns True iff a non-expired event with that command_id exists (I-EL-DEEP-1)."""
    el = EventLog(tmp_db_path)
    cid = "cmd-exists-test"

    assert el.exists_command(cid) is False

    event = _make_domain_event(task_id="T-ec")
    el.append([event], source="test", command_id=cid, allow_outside_kernel="test")

    assert el.exists_command(cid) is True
    assert el.exists_command("cmd-nonexistent") is False


def test_event_log_exists_semantic(tmp_db_path: str) -> None:
    """EventLog.exists_semantic() matches on (command_type, task_id, phase_id, payload_hash) (I-EL-DEEP-1)."""
    el = EventLog(tmp_db_path)

    command_type = "TaskImplemented"
    task_id = "T-sem"
    phase_id = 34
    payload_hash = "abc123"

    assert el.exists_semantic(command_type, task_id, phase_id, payload_hash) is False

    # Append a raw event with matching payload fields
    sdd_append(
        command_type,
        {
            "_source": "test",
            "task_id": task_id,
            "phase_id": phase_id,
            "payload_hash": payload_hash,
        },
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    assert el.exists_semantic(command_type, task_id, phase_id, payload_hash) is True
    assert el.exists_semantic(command_type, "T-other", phase_id, payload_hash) is False
    assert el.exists_semantic(command_type, task_id, phase_id, "wronghash") is False


def test_event_log_get_error_count(tmp_db_path: str) -> None:
    """EventLog.get_error_count() counts non-expired ErrorEvent rows for command_id (I-EL-DEEP-1)."""
    el = EventLog(tmp_db_path)
    cid = "cmd-error-count"

    assert el.get_error_count(cid) == 0

    for _ in range(2):
        sdd_append(
            "ErrorEvent",
            {"command_id": cid, "error_type": "ValueError", "message": "oops"},
            db_path=tmp_db_path,
            level="L2",
            event_source="runtime",
        )

    assert el.get_error_count(cid) == 2
    assert el.get_error_count("cmd-other") == 0


def test_sdd_append_batch_raises_inside_kernel(tmp_db_path: str) -> None:
    """I-EL-NON-KERNEL-1: sdd_append_batch MUST NOT be called inside execute_command."""
    events = [EventInput(event_type="MetricRecorded", payload={"key": "v"}, event_source="runtime")]
    with kernel_context("execute_command"):
        with pytest.raises(KernelContextError, match="I-EL-NON-KERNEL-1"):
            sdd_append_batch(events, db_path=tmp_db_path)


# ── T-3408: EventStore → EventLog migration in registry.py ───────────────────


def test_write_kernel_full_chain_event_log() -> None:
    """registry.py Write Kernel imports EventLog and has no reference to EventStore.

    Invariants: I-KERNEL-WRITE-1, I-EL-UNIFIED-1, I-2, I-3
    """
    import sdd.commands.registry as reg_module

    assert hasattr(reg_module, "EventLog"), "registry must import EventLog (migration T-3408)"
    assert not hasattr(reg_module, "EventStore"), (
        "registry must NOT import EventStore after migration T-3408"
    )


def test_kernel_write_guard_via_event_log() -> None:
    """EventLog.append on production DB outside execute_command raises KernelContextError (I-KERNEL-WRITE-1).

    Mirrors the EventStore guard test but verifies the guard is enforced
    through EventLog after migration T-3408.
    """
    from sdd.infra.paths import event_store_file

    el = EventLog(str(event_store_file()))
    event = _make_domain_event()

    with pytest.raises(KernelContextError, match="EventLog.append"):
        el.append([event], source="test")

    # Inside kernel_context: guard passes; empty list → no DB write (I-DB-TEST-1)
    with kernel_context("execute_command"):
        el.append([], source="test")
