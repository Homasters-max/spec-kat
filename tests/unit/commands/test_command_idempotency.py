"""Command idempotency classification tests.

Invariants: I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1, I-DB-TEST-1, I-DB-TEST-2
"""
from __future__ import annotations

import dataclasses
import pathlib
import time
import uuid

import pytest

from sdd.commands.registry import REGISTRY
from sdd.core.errors import StaleStateError
from sdd.core.events import DomainEvent, EventLevel
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventLog


@dataclasses.dataclass(frozen=True)
class _TestEvent(DomainEvent):
    """Minimal concrete DomainEvent for EventLog-level tests."""


def _make_event() -> _TestEvent:
    return _TestEvent(
        event_type="TestStateEvent",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L1,
        event_source="test",
        caused_by_meta_seq=None,
    )


def _event_count(db: str) -> int:
    conn = open_sdd_connection(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_switch_phase_non_idempotent(tmp_path: pathlib.Path) -> None:
    """Two switch-phase calls (A→B) produce two distinct events in EventLog.

    switch-phase has idempotent=False → execute_command passes uuid4() as
    command_id → EventLog dedup never fires → two PhaseContextSwitched stored.
    I-CMD-IDEM-1, I-IDEM-SCHEMA-1.
    """
    assert not REGISTRY["switch-phase"].idempotent, (
        "switch-phase must have idempotent=False (I-CMD-IDEM-1)"
    )

    db = str(tmp_path / "test_sdd_events.duckdb")
    store = EventLog(db)

    # Simulate two switch-phase calls: each gets a fresh uuid4() command_id
    store.append([_make_event()], source="test", command_id=str(uuid.uuid4()))
    store.append([_make_event()], source="test", command_id=str(uuid.uuid4()))

    assert _event_count(db) == 2, (
        "Two navigation events with distinct uuid4 command_ids must both be stored"
    )


def test_complete_still_idempotent(tmp_path: pathlib.Path) -> None:
    """Two complete calls with identical payload store only one event.

    complete has idempotent=True → execute_command passes payload hash as
    command_id → EventLog dedup fires on second call → one TaskImplemented stored.
    I-IDEM-SCHEMA-1.
    """
    assert REGISTRY["complete"].idempotent, (
        "complete must have idempotent=True (I-IDEM-SCHEMA-1)"
    )

    db = str(tmp_path / "test_sdd_events.duckdb")
    store = EventLog(db)

    # Simulate two complete calls with the same payload hash command_id
    stable_command_id = "sha256-payload-hash-complete-T-2703"
    store.append([_make_event()], source="test", command_id=stable_command_id)
    store.append([_make_event()], source="test", command_id=stable_command_id)  # dedup

    assert _event_count(db) == 1, (
        "Second append with identical command_id must be silently deduplicated (I-IDEM-SCHEMA-1)"
    )


def test_switch_phase_optlock_preserved(tmp_path: pathlib.Path) -> None:
    """Optimistic lock (expected_head) is active even when idempotent=False.

    I-OPTLOCK-1: execute_command always passes expected_head to EventLog.append,
    regardless of spec.idempotent. StaleStateError raised when head has advanced.
    """
    db = str(tmp_path / "test_sdd_events.duckdb")
    store = EventLog(db)

    # Append first event and capture head
    store.append([_make_event()], source="test", command_id=str(uuid.uuid4()))
    stale_head = store.max_seq()

    # Advance the head (another write after stale_head was captured)
    store.append([_make_event()], source="test", command_id=str(uuid.uuid4()))

    # Non-idempotent call with stale expected_head must raise (I-OPTLOCK-1)
    with pytest.raises(StaleStateError):
        store.append(
            [_make_event()],
            source="test",
            command_id=str(uuid.uuid4()),   # uuid4 → idempotent=False style
            expected_head=stale_head,       # stale → must raise
        )


def test_command_spec_idempotent_default() -> None:
    """All REGISTRY entries have idempotent=True except switch-phase (idempotent=False).

    I-CMD-IDEM-1: CommandSpec.idempotent classification is correct for every command.
    """
    for name, spec in REGISTRY.items():
        if name == "switch-phase":
            assert not spec.idempotent, (
                "switch-phase must be idempotent=False (I-CMD-IDEM-1)"
            )
        else:
            assert spec.idempotent, (
                f"{name!r} must be idempotent=True (default); "
                f"only navigation commands may be False"
            )
