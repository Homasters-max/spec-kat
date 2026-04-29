"""Tests for InvalidateEventHandler — Spec_v28 §2 BC-WG-5.

Invariants: I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1,
            I-INVALID-AUDIT-ONLY-1
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from sdd.commands.invalidate_event import (
    InvalidateEventCommand,
    InvalidateEventHandler,
)
from sdd.core.errors import InvariantViolationError
from sdd.core.events import compute_command_id
from sdd.infra.db import open_sdd_connection


def _cmd(
    target_seq: int = 1,
    reason: str = "test invalidation",
    phase_id: int = 28,
    command_id: str | None = None,
) -> InvalidateEventCommand:
    return InvalidateEventCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="InvalidateEvent",
        payload={"target_seq": target_seq},
        target_seq=target_seq,
        reason=reason,
        phase_id=phase_id,
    )


def _seed_raw(db_path: str, event_type: str, payload: dict, level: str = "L1") -> int:
    """Insert event directly via SQL."""
    conn = open_sdd_connection(db_path)
    try:
        import json as _json
        payload_json = _json.dumps(payload, sort_keys=True)
        event_id_val = str(uuid.uuid4())
        ts = int(time.time() * 1000)
        conn.execute(
            """INSERT INTO event_log
                (event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired)
            VALUES (%s, %s, %s::jsonb, %s, 'runtime', NULL, FALSE)""",
            [event_id_val, event_type, payload_json, level],
        )
        conn.commit()
        row = conn.execute("SELECT MAX(sequence_id) FROM event_log").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# test_invalidate_nonexistent_seq_raises
# ---------------------------------------------------------------------------

def test_invalidate_nonexistent_seq_raises(tmp_db_path: str) -> None:
    """I-INVALID-1: invalidating a non-existent seq raises InvariantViolationError."""
    handler = InvalidateEventHandler(db_path=tmp_db_path)
    with pytest.raises(InvariantViolationError, match="I-INVALID-1"):
        handler.handle(_cmd(target_seq=99999))


# ---------------------------------------------------------------------------
# test_invalidate_invalidated_raises
# ---------------------------------------------------------------------------

def test_invalidate_invalidated_raises(tmp_db_path: str) -> None:
    """I-INVALID-3: trying to invalidate an EventInvalidated event raises."""
    seq = _seed_raw(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": 1, "reason": "prior", "invalidated_by_phase": 28},
    )
    handler = InvalidateEventHandler(db_path=tmp_db_path)
    with pytest.raises(InvariantViolationError, match="I-INVALID-3"):
        handler.handle(_cmd(target_seq=seq))


# ---------------------------------------------------------------------------
# test_invalidate_state_event_raises
# ---------------------------------------------------------------------------

def test_invalidate_state_event_raises(tmp_db_path: str) -> None:
    """I-INVALID-4: invalidating a state-mutating event (in EventReducer._EVENT_SCHEMA) raises."""
    seq = _seed_raw(
        tmp_db_path,
        "TaskImplemented",
        {"task_id": "T-9999", "phase_id": 28, "timestamp": "2026-01-01T00:00:00Z"},
    )
    handler = InvalidateEventHandler(db_path=tmp_db_path)
    with pytest.raises(InvariantViolationError, match="I-INVALID-4"):
        handler.handle(_cmd(target_seq=seq))


# ---------------------------------------------------------------------------
# test_invalidate_idempotent
# ---------------------------------------------------------------------------

def test_invalidate_idempotent(tmp_db_path: str) -> None:
    """I-INVALID-IDEM-1: second call for already-invalidated seq returns [] (noop)."""
    # Seed a non-state L2 event as the target
    target_seq = _seed_raw(tmp_db_path, "ErrorOccurred", {"msg": "test"}, level="L2")

    # Seed an existing EventInvalidated pointing to target_seq (simulate prior invalidation)
    _seed_raw(
        tmp_db_path,
        "EventInvalidated",
        {"target_seq": target_seq, "reason": "already done", "invalidated_by_phase": 28},
    )

    handler = InvalidateEventHandler(db_path=tmp_db_path)
    # Different reason and command_id — still noop because target_seq is already invalidated
    events = handler.handle(_cmd(target_seq=target_seq, reason="retry attempt"))
    assert events == []


# ---------------------------------------------------------------------------
# test_invalidate_emits_correct_fields
# ---------------------------------------------------------------------------

def test_invalidate_emits_correct_fields(tmp_db_path: str) -> None:
    """Emitted EventInvalidatedEvent carries all required fields."""
    target_seq = _seed_raw(tmp_db_path, "ErrorOccurred", {"msg": "diag"}, level="L2")

    handler = InvalidateEventHandler(db_path=tmp_db_path)
    events = handler.handle(_cmd(target_seq=target_seq, reason="test reason", phase_id=28))

    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "EventInvalidated"
    assert ev.target_seq == target_seq        # type: ignore[attr-defined]
    assert ev.reason == "test reason"         # type: ignore[attr-defined]
    assert ev.invalidated_by_phase == 28      # type: ignore[attr-defined]
    assert ev.level == "L1"
    assert ev.event_source == "runtime"


# ---------------------------------------------------------------------------
# test_payload_hash_unique_per_target_seq  (AC1, I-INVALID-IDEM-1)
# ---------------------------------------------------------------------------

def test_payload_hash_unique_per_target_seq() -> None:
    """AC1: compute_command_id must differ for different target_seq values.

    Ensures idempotency keys are unique across distinct invalidation targets so
    EventStore._append_locked does not silently skip events for a new target_seq
    that shares a command_id with a prior invalidation.
    """
    cmd_a = _cmd(target_seq=100)
    cmd_b = _cmd(target_seq=101)
    assert compute_command_id(cmd_a) != compute_command_id(cmd_b)


# ---------------------------------------------------------------------------
# test_cmd_idem2_spec_is_idempotent  (I-CMD-IDEM-2)
# ---------------------------------------------------------------------------

def test_cmd_idem2_spec_is_idempotent() -> None:
    """I-CMD-IDEM-2: invalidate-event CommandSpec.idempotent must be True.

    Handler-level noop (I-INVALID-IDEM-1) is only permitted when the spec
    declares idempotent=True; False would contradict the handler's noop return.
    """
    from sdd.commands.registry import REGISTRY
    spec = REGISTRY["invalidate-event"]
    assert spec.idempotent is True


# ---------------------------------------------------------------------------
# test_invalidate_session_declared_succeeds  (I-INVALID-AUDIT-ONLY-1)
# ---------------------------------------------------------------------------

def test_invalidate_session_declared_succeeds(tmp_db_path: str) -> None:
    """I-INVALID-AUDIT-ONLY-1: SessionDeclared is audit-only → invalidation succeeds.

    SessionDeclared is in _AUDIT_ONLY_EVENTS, so is_invalidatable returns True
    and the handler emits EventInvalidated without raising I-INVALID-4.
    """
    target_seq = _seed_raw(
        tmp_db_path,
        "SessionDeclared",
        {
            "session_type": "IMPLEMENT",
            "task_id": "T-4907",
            "phase_id": 49,
            "plan_hash": "abc123",
            "timestamp": "2026-04-29T00:00:00Z",
        },
    )

    handler = InvalidateEventHandler(db_path=tmp_db_path)
    events = handler.handle(_cmd(target_seq=target_seq, reason="duplicate session"))

    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "EventInvalidated"
    assert ev.target_seq == target_seq          # type: ignore[attr-defined]
    assert ev.reason == "duplicate session"     # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# test_invalidate_state_mutating_still_blocked  (I-INVALID-4 regression)
# ---------------------------------------------------------------------------

def test_invalidate_state_mutating_still_blocked(tmp_db_path: str) -> None:
    """I-INVALID-4: state-mutating events remain blocked after audit-only exception.

    Regression guard: adding SessionDeclared to _AUDIT_ONLY_EVENTS must not open
    the gate for state-mutating events like PhaseInitialized.
    """
    target_seq = _seed_raw(
        tmp_db_path,
        "PhaseInitialized",
        {
            "phase_id": 49,
            "tasks_total": 10,
            "plan_version": 49,
            "actor": "human",
            "timestamp": "2026-04-29T00:00:00Z",
        },
    )

    handler = InvalidateEventHandler(db_path=tmp_db_path)
    with pytest.raises(InvariantViolationError, match="I-INVALID-4"):
        handler.handle(_cmd(target_seq=target_seq))
