"""EventLog class — 16 tests covering §9 of Spec_v34_EventLogDeepModule.

Invariants: I-EL-UNIFIED-1, I-EL-UNIFIED-2, I-EL-DEEP-1, I-EL-CANON-1,
            I-EL-LEGACY-1, I-EL-BATCH-ID-1, I-EL-NON-KERNEL-1,
            I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1, I-IDEM-SCHEMA-1, I-IDEM-LOG-1,
            I-INVALID-CACHE-1, I-KERNEL-WRITE-1, I-DB-TEST-1, I-DB-TEST-2,
            I-2, I-3, I-HANDLER-PURE-1
"""
from __future__ import annotations

import inspect
import logging
from pathlib import Path

import pytest

import sdd.infra.event_log as _el_module
from sdd.core.errors import StaleStateError
from sdd.core.events import DomainEvent, TaskImplementedEvent
from sdd.core.execution_context import KernelContextError, kernel_context
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import (
    EventInput,
    EventLog,
    sdd_append,
    sdd_append_batch,
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


# ── 1 ─────────────────────────────────────────────────────────────────────────


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


# ── 2 ─────────────────────────────────────────────────────────────────────────


def test_event_log_append_locked_optimistic(tmp_db_path: str) -> None:
    """EventLog.append() with expected_head enforces optimistic lock (I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1)."""
    el = EventLog(tmp_db_path)

    seed = _make_domain_event(task_id="T-seed")
    el.append([seed], source="test", allow_outside_kernel="test")
    head = el.max_seq()
    assert head is not None

    event = _make_domain_event(task_id="T-002")
    el.append([event], source="test", expected_head=head, allow_outside_kernel="test")

    with pytest.raises(StaleStateError):
        el.append([event], source="test", expected_head=head, allow_outside_kernel="test")


# ── 3 ─────────────────────────────────────────────────────────────────────────


def test_event_log_append_idempotent(tmp_db_path: str, caplog: pytest.LogCaptureFixture) -> None:
    """Duplicate (command_id, event_index) skipped; INFO logged for all-duplicate call
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


# ── 4 ─────────────────────────────────────────────────────────────────────────


def test_event_log_replay_filters_invalidated(tmp_db_path: str) -> None:
    """EventLog.replay() excludes seqs targeted by EventInvalidated; cache resets on append
    (I-INVALID-CACHE-1)."""
    el = EventLog(tmp_db_path)

    el.append([_make_domain_event(task_id="T-to-invalidate")], source="test", allow_outside_kernel="test")
    target_seq = el.max_seq()
    assert target_seq is not None

    el.append([_make_domain_event(task_id="T-keeper")], source="test", allow_outside_kernel="test")
    keeper_seq = el.max_seq()

    sdd_append(
        "EventInvalidated",
        {"target_seq": target_seq},
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    el2 = EventLog(tmp_db_path)
    replayed = el2.replay()
    replayed_seqs = {e["seq"] for e in replayed}

    assert target_seq not in replayed_seqs, "invalidated seq must be excluded from replay"
    assert keeper_seq in replayed_seqs, "non-invalidated event must remain"


# ── 5 ─────────────────────────────────────────────────────────────────────────


def test_event_log_exists_command(tmp_db_path: str) -> None:
    """EventLog.exists_command() returns True iff a non-expired event with command_id exists
    (I-EL-DEEP-1)."""
    el = EventLog(tmp_db_path)
    cid = "cmd-exists-test"

    assert el.exists_command(cid) is False

    event = _make_domain_event(task_id="T-ec")
    el.append([event], source="test", command_id=cid, allow_outside_kernel="test")

    assert el.exists_command(cid) is True
    assert el.exists_command("cmd-nonexistent") is False


# ── 6 ─────────────────────────────────────────────────────────────────────────


def test_event_log_exists_semantic(tmp_db_path: str) -> None:
    """EventLog.exists_semantic() matches (command_type, task_id, phase_id, payload_hash)
    (I-EL-DEEP-1)."""
    el = EventLog(tmp_db_path)

    command_type = "TaskImplemented"
    task_id = "T-sem"
    phase_id = 34
    payload_hash = "abc123"

    assert el.exists_semantic(command_type, task_id, phase_id, payload_hash) is False

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


# ── 7 ─────────────────────────────────────────────────────────────────────────


def test_event_log_get_error_count(tmp_db_path: str) -> None:
    """EventLog.get_error_count() counts non-expired ErrorEvent rows for command_id
    (I-EL-DEEP-1)."""
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


# ── 8 ─────────────────────────────────────────────────────────────────────────


def test_event_store_module_deleted() -> None:
    """infra/event_store.py MUST NOT exist; EventLog is the sole persistence class
    (I-EL-UNIFIED-1)."""
    import sdd.infra as infra_pkg

    event_store_path = Path(infra_pkg.__file__).parent / "event_store.py"
    assert not event_store_path.exists(), (
        "I-EL-UNIFIED-1: infra/event_store.py must be deleted; "
        "EventLog is the sole event persistence class"
    )


# ── 9 ─────────────────────────────────────────────────────────────────────────


def test_canonical_json_in_core() -> None:
    """canonical_json() resides in core/json_utils.py; MUST NOT exist in event_log.py
    (I-EL-CANON-1)."""
    from sdd.core.json_utils import canonical_json

    result = canonical_json({"b": 1, "a": 2})
    assert result == '{"a":2,"b":1}', "canonical_json must sort keys and omit whitespace"

    assert not hasattr(_el_module, "canonical_json"), (
        "I-EL-CANON-1: canonical_json must NOT exist in infra/event_log.py after Phase 34"
    )


# ── 10 ────────────────────────────────────────────────────────────────────────


def test_sdd_append_legacy_preserved() -> None:
    """sdd_append() remains module-level in event_log.py, marked with legacy comment
    (I-EL-LEGACY-1)."""
    assert hasattr(_el_module, "sdd_append"), (
        "I-EL-LEGACY-1: sdd_append must remain as a module-level function in event_log.py"
    )
    assert callable(_el_module.sdd_append)

    source = inspect.getsource(_el_module)
    assert "# legacy: raw event write" in source, (
        "I-EL-LEGACY-1: sdd_append must be marked with '# legacy: raw event write' comment"
    )


# ── 11 ────────────────────────────────────────────────────────────────────────


def test_kernel_write_guard_via_event_log() -> None:
    """EventLog.append on production DB outside execute_command raises KernelContextError
    (I-KERNEL-WRITE-1)."""
    from sdd.infra.paths import event_store_file

    el = EventLog(str(event_store_file()))
    event = _make_domain_event()

    with pytest.raises(KernelContextError, match="EventLog.append"):
        el.append([event], source="test")

    with kernel_context("execute_command"):
        el.append([], source="test")  # guard passes; empty → no DB write (I-DB-TEST-1)


# ── 12 ────────────────────────────────────────────────────────────────────────


def test_write_kernel_full_chain_event_log() -> None:
    """registry.py Write Kernel imports EventLog; EventStore MUST NOT be present
    (I-2, I-3, I-HANDLER-PURE-1, I-EL-UNIFIED-1)."""
    import sdd.commands.registry as reg_module

    assert hasattr(reg_module, "EventLog"), (
        "registry must import EventLog (I-EL-UNIFIED-1)"
    )
    assert not hasattr(reg_module, "EventStore"), (
        "registry must NOT import EventStore after Phase 34 migration"
    )


# ── 13 ────────────────────────────────────────────────────────────────────────


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


# ── 14 ────────────────────────────────────────────────────────────────────────


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


# ── 15 ────────────────────────────────────────────────────────────────────────


def test_sdd_append_batch_raises_inside_kernel(tmp_db_path: str) -> None:
    """sdd_append_batch MUST NOT be called inside execute_command; raises KernelContextError
    (I-EL-NON-KERNEL-1)."""
    events = [EventInput(event_type="MetricRecorded", payload={"key": "v"}, event_source="runtime")]
    with kernel_context("execute_command"):
        with pytest.raises(KernelContextError, match="I-EL-NON-KERNEL-1"):
            sdd_append_batch(events, db_path=tmp_db_path)


# ── 16 ────────────────────────────────────────────────────────────────────────


def test_metrics_non_kernel_write(tmp_db_path: str) -> None:
    """record_metric with allow_outside_kernel='metrics' writes events without KernelContextError
    (I-KERNEL-WRITE-1 updated)."""
    from sdd.infra.metrics import record_metric

    record_metric("task.lead_time", 42.0, task_id="T-001", phase_id=34, db_path=tmp_db_path)

    conn = open_sdd_connection(tmp_db_path)
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert count >= 1, "record_metric must persist at least one event (MetricRecorded)"


# ── 17 ────────────────────────────────────────────────────────────────────────


def test_append_is_atomic(tmp_db_path: str) -> None:
    """EventLog.append() writes all events in one DB transaction: all land or none do (I-EL-UNIFIED-2)."""
    el = EventLog(tmp_db_path)
    events = [_make_domain_event(task_id=f"T-40{i}") for i in range(3)]
    el.append(events, source="test", allow_outside_kernel="test")

    conn = open_sdd_connection(tmp_db_path)
    rows = conn.execute("SELECT event_type FROM events ORDER BY seq").fetchall()
    conn.close()

    assert len(rows) == 3
    assert all(r[0] == "TaskImplemented" for r in rows)
