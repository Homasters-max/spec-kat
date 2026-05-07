"""Tests for T-4602: record-session deduplication (I-SESSION-DEDUP-1)."""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.record_session import (
    RecordSessionCommand,
    RecordSessionHandler,
    stable_session_command_id,
)


def _make_cmd(
    session_type: str = "IMPLEMENT",
    phase_id: int = 46,
    task_id: str | None = "T-4602",
    plan_hash: str = "",
) -> RecordSessionCommand:
    return RecordSessionCommand(
        command_id=str(uuid.uuid4()),
        command_type="RecordSession",
        payload={"session_type": session_type, "task_id": task_id, "phase_id": phase_id, "plan_hash": plan_hash},
        session_type=session_type,
        task_id=task_id,
        phase_id=phase_id,
        plan_hash=plan_hash,
    )


def _store_events(db_path: str, events: list) -> None:
    """Write events to test DB (simulate execute_command append)."""
    from sdd.infra.event_log import EventLog
    EventLog(db_path).append(events, source="runtime", allow_outside_kernel="test")


# ---------------------------------------------------------------------------
# test_session_dedup_same_utc_day
# ---------------------------------------------------------------------------

def test_session_dedup_same_utc_day(tmp_db_path: str) -> None:
    """BC-49-C / I-HANDLER-SESSION-PURE-1: handler is pure and always returns [SessionDeclaredEvent].

    Dedup is exclusively the kernel's responsibility (Step 2.5, I-DEDUP-KERNEL-AUTHORITY-1).
    Second handle() call MUST return an event — not [] — regardless of existing DB state.
    """
    handler = RecordSessionHandler(db_path=tmp_db_path)
    cmd = _make_cmd()

    # First call: event emitted
    events1 = handler.handle(cmd)
    assert len(events1) == 1
    assert events1[0].event_type == "SessionDeclared"

    # Persist the event (simulate execute_command)
    _store_events(tmp_db_path, events1)

    # Second call: handler is pure — always emits; kernel (Step 2.5) handles dedup
    events2 = handler.handle(cmd)
    assert len(events2) == 1
    assert events2[0].event_type == "SessionDeclared"


# ---------------------------------------------------------------------------
# test_session_dedup_different_utc_day
# ---------------------------------------------------------------------------

def test_session_dedup_different_utc_day(
    tmp_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-SESSION-DEDUP-1: calls on different UTC days each emit a new SessionDeclared."""
    import sdd.commands.record_session as rs_mod

    monkeypatch.setattr(rs_mod, "_utc_date_str", lambda: "2026-01-01")
    handler = RecordSessionHandler(db_path=tmp_db_path)
    cmd = _make_cmd()

    # Day 1: emit and persist
    events1 = handler.handle(cmd)
    assert len(events1) == 1
    _store_events(tmp_db_path, events1)

    # Day 2: dedup query uses new date → no match → new event
    monkeypatch.setattr(rs_mod, "_utc_date_str", lambda: "2026-01-02")
    events2 = handler.handle(cmd)
    assert len(events2) == 1
    assert events2[0].event_type == "SessionDeclared"


# ---------------------------------------------------------------------------
# test_stable_command_id_uses_utc
# ---------------------------------------------------------------------------

def test_stable_command_id_uses_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    """I-SESSION-DEDUP-1: stable_session_command_id is deterministic within same UTC day."""
    import sdd.commands.record_session as rs_mod

    monkeypatch.setattr(rs_mod, "_utc_date_str", lambda: "2026-04-28")
    id1 = stable_session_command_id("IMPLEMENT", 46)
    id2 = stable_session_command_id("IMPLEMENT", 46)
    assert id1 == id2, "same day → same command_id"

    monkeypatch.setattr(rs_mod, "_utc_date_str", lambda: "2026-04-29")
    id3 = stable_session_command_id("IMPLEMENT", 46)
    assert id3 != id1, "different day → different command_id"

    # Different session_type or phase_id → different id even on same day
    monkeypatch.setattr(rs_mod, "_utc_date_str", lambda: "2026-04-28")
    id4 = stable_session_command_id("VALIDATE", 46)
    id5 = stable_session_command_id("IMPLEMENT", 47)
    assert id4 != id1
    assert id5 != id1
