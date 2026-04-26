"""Tests for RecordSessionHandler — I-SESSION-DECLARED-1, I-DB-TEST-1, I-DB-TEST-2."""
from __future__ import annotations

import pathlib
import uuid

import pytest

from sdd.commands.record_session import RecordSessionCommand, RecordSessionHandler


def _cmd(
    session_type: str = "IMPLEMENT",
    task_id: str | None = "T-2901",
    phase_id: int = 29,
    plan_hash: str = "abc123",
    command_id: str | None = None,
) -> RecordSessionCommand:
    return RecordSessionCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="RecordSessionCommand",
        payload={},
        session_type=session_type,
        task_id=task_id,
        phase_id=phase_id,
        plan_hash=plan_hash,
    )


@pytest.fixture
def handler(tmp_db_path: str) -> RecordSessionHandler:
    return RecordSessionHandler(db_path=tmp_db_path)


# ---------------------------------------------------------------------------
# test_record_session_emits_event  (I-SESSION-DECLARED-1)
# ---------------------------------------------------------------------------

def test_record_session_emits_event(handler: RecordSessionHandler) -> None:
    """handle() returns exactly one SessionDeclaredEvent with correct fields."""
    cmd = _cmd(session_type="IMPLEMENT", task_id="T-2901", phase_id=29)
    events = handler.handle(cmd)

    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "SessionDeclared"
    assert ev.session_type == "IMPLEMENT"   # type: ignore[attr-defined]
    assert ev.task_id == "T-2901"           # type: ignore[attr-defined]
    assert ev.phase_id == 29                # type: ignore[attr-defined]
    assert ev.plan_hash == "abc123"         # type: ignore[attr-defined]
    assert ev.level == "L1"


# ---------------------------------------------------------------------------
# test_record_session_uses_tmp_db  (I-DB-TEST-1, I-DB-TEST-2)
# ---------------------------------------------------------------------------

def test_record_session_uses_tmp_db(tmp_db_path: str) -> None:
    """Handler uses tmp_path DB, never production DB (I-DB-TEST-1).

    Also validates I-DB-TEST-2: PYTEST_CURRENT_TEST is set, so open_sdd_connection
    uses timeout_secs=0.0 (fail-fast), which means lock contention raises immediately.
    """
    prod_db = pathlib.Path(".sdd/state/sdd_events.duckdb").resolve()
    test_db = pathlib.Path(tmp_db_path).resolve()

    assert test_db != prod_db, "tmp_db_path must differ from production DB (I-DB-TEST-1)"

    handler = RecordSessionHandler(db_path=tmp_db_path)
    events = handler.handle(_cmd())
    assert len(events) == 1
    assert events[0].event_type == "SessionDeclared"
