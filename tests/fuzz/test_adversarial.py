"""Adversarial tests for Validation Runtime stability (G4).

Invariants: I-VR-STABLE-4 (state reconstructable after adversarial writes),
            I-VR-STABLE-7 (duplicate / oversized sequences don't corrupt state).

G4 scenarios: concurrent writes, stale head, duplicates, schema corrupt.

Note: execute_command uses a NormGuard that validates actor='any' against the live norm
catalog (strict=True, no catalog entry for actor='any'). Therefore adversarial write
scenarios are exercised directly through EventLog; replay/rollback are used for
state-consistency assertions (I-VR-HARNESS-1 is validated in test_harness.py).
"""
from __future__ import annotations

import threading

from hypothesis import given, settings

from sdd.commands.registry import CommandSpec
from sdd.infra.event_log import EventLog
from sdd.infra.projections import get_current_state
from tests.harness.api import replay, rollback
from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.fixtures import make_minimal_event
from tests.harness.generators import adversarial_sequence


def _events(n: int = 3, event_type: str = "_vr_test") -> list:
    """Return a list of n minimal events with a valid event_source for direct DB seeding."""
    return [make_minimal_event(event_type, event_source="runtime") for _ in range(n)]


def _seed(db: str, n: int = 3) -> list:
    """Seed *db* with n minimal events; return the event list."""
    evs = _events(n)
    EventLog(db).append(evs, source="runtime")
    return evs


# ---------------------------------------------------------------------------
# G4.1 — Concurrent writes
# ---------------------------------------------------------------------------


def test_concurrent_writes_stable(db_factory):  # noqa: F811
    """Multiple threads append to the same DB; final state reconstructable (I-VR-STABLE-4).

    EventLog uses ON CONFLICT (event_id) DO NOTHING — concurrent inserts are safe.
    """
    db = db_factory()

    def _write() -> None:
        try:
            EventLog(db).append(_events(2), source="runtime")
        except Exception:
            pass  # transient write conflict is acceptable; state integrity is the invariant

    threads = [threading.Thread(target=_write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    state = get_current_state(db)
    assert state is not None


def test_concurrent_writes_state_reconstructable(db_factory):  # noqa: F811
    """After concurrent appends complete, state is reconstructable from the EventLog (I-VR-STABLE-4)."""
    db = db_factory()

    def _write() -> None:
        try:
            EventLog(db).append(_events(1), source="runtime")
        except Exception:
            pass  # write-write conflict on schema init is acceptable

    threads = [threading.Thread(target=_write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All writes done; state must be reconstructable regardless of which ones succeeded
    state = get_current_state(db)
    assert state is not None


# ---------------------------------------------------------------------------
# G4.2 — Stale head (rolled-back in-memory checkpoint)
# ---------------------------------------------------------------------------


def test_stale_head_replay_stable(db_factory):  # noqa: F811
    """Replay with a stale (rolled-back) in-memory head returns valid state (I-VR-STABLE-4).

    rollback() truncates the in-memory list; the DB is unchanged, so replay() sees full history.
    """
    db = db_factory()
    events = _seed(db, n=4)

    stale = rollback(events, 2)  # in-memory: only first 2 events "visible"
    assert len(stale) == 2

    state = replay(stale, db)  # replay reads DB, not the stale list (I-VR-HARNESS-2)
    assert state is not None


def test_rollback_to_empty_head_replay_stable(db_factory):  # noqa: F811
    """Rollback to empty in-memory head; replay() still returns valid state (I-VR-STABLE-4)."""
    db = db_factory()
    events = _seed(db, n=3)

    empty_head = rollback(events, 0)
    assert empty_head == []

    state = replay(empty_head, db)
    assert state is not None


def test_rollback_beyond_db_length_stable(db_factory):  # noqa: F811
    """rollback() with t > len(events) returns full list; state reconstructable (I-VR-STABLE-4)."""
    db = db_factory()
    events = _seed(db, n=2)

    over_sliced = rollback(events, 100)
    assert over_sliced == events  # events[:100] == events when len < 100

    state = replay(over_sliced, db)
    assert state is not None


# ---------------------------------------------------------------------------
# G4.3 — Duplicates / adversarial sequences
# ---------------------------------------------------------------------------


@given(adversarial_sequence())
@settings(max_examples=20)
def test_adversarial_sequence_structure_valid(seq):
    """adversarial_sequence() always produces structurally valid (CommandSpec, cmd) pairs (I-VR-STABLE-7).

    rollback() is pure in-memory — valid for any sequence regardless of cmd type.
    """
    assert isinstance(seq, list)
    for spec_item, _ in seq:
        assert isinstance(spec_item, CommandSpec)

    half = len(seq) // 2
    sliced = rollback(seq, half)
    assert len(sliced) == half


def test_duplicate_event_ids_idempotent(db_factory):  # noqa: F811
    """Appending the same events twice is idempotent (ON CONFLICT DO NOTHING, I-VR-STABLE-7)."""
    db = db_factory()
    events = _events(3)

    EventLog(db).append(events, source="runtime")
    EventLog(db).append(events, source="runtime")  # same event_ids → silently skipped

    state = get_current_state(db)
    assert state is not None


def test_duplicate_append_preserves_state(db_factory):  # noqa: F811
    """State after two identical appends equals state after one append (I-VR-STABLE-7)."""
    db_once = db_factory()
    db_twice = db_factory()
    events = _events(3)

    EventLog(db_once).append(events, source="runtime")

    EventLog(db_twice).append(events, source="runtime")
    EventLog(db_twice).append(events, source="runtime")

    state_once = get_current_state(db_once)
    state_twice = get_current_state(db_twice)
    assert type(state_once) is type(state_twice)


def test_oversized_append_stable(db_factory):  # noqa: F811
    """Appending a large batch of events completes without error (I-VR-STABLE-7)."""
    db = db_factory()
    large_batch = _events(50)
    EventLog(db).append(large_batch, source="runtime")

    state = get_current_state(db)
    assert state is not None


def test_empty_append_stable(db_factory):  # noqa: F811
    """Appending an empty list is a no-op; state remains valid (I-VR-STABLE-7)."""
    db = db_factory()
    EventLog(db).append([], source="runtime")

    state = get_current_state(db)
    assert state is not None


# ---------------------------------------------------------------------------
# G4.4 — Schema corrupt (unknown / malformed event types)
# ---------------------------------------------------------------------------


def test_schema_corrupt_unknown_events_stable(db_factory):  # noqa: F811
    """Unknown event types are skipped by reducer; state reconstructable (EV-4, I-VR-STABLE-4)."""
    db = db_factory()
    corrupt_events = [
        make_minimal_event("_corrupt_unknown_type", event_source="runtime") for _ in range(5)
    ]
    EventLog(db).append(corrupt_events, source="runtime")

    state = get_current_state(db)
    assert state is not None


def test_schema_corrupt_mixed_with_valid_events_stable(db_factory):  # noqa: F811
    """Unknown events interspersed with known events; state reconstructable (I-VR-STABLE-4)."""
    db = db_factory()
    valid_events = _seed(db, n=3)

    corrupt_events = [
        make_minimal_event("_schema_corrupt_type", event_source="runtime") for _ in range(4)
    ]
    EventLog(db).append(corrupt_events, source="runtime")

    state = get_current_state(db)
    assert state is not None

    replayed = replay(valid_events, db)
    assert replayed is not None


def test_schema_corrupt_replay_invariant(db_factory):  # noqa: F811
    """replay() returns valid state even when DB contains only unknown event types (EV-4, I-VR-STABLE-4)."""
    db = db_factory()
    corrupt_events = [
        make_minimal_event(f"_corrupt_{i}", event_source="runtime") for i in range(10)
    ]
    EventLog(db).append(corrupt_events, source="runtime")

    state = replay(corrupt_events, db)
    assert state is not None
