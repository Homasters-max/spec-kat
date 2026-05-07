"""I-VR-STABLE-8: evolution safety — unknown events skipped; replay stable (P-9)."""
from __future__ import annotations

import dataclasses

import pytest
from hypothesis import HealthCheck, given, settings

from sdd.infra.event_log import EventLog
from sdd.infra.projections import get_current_state
from tests.harness.fixtures import db_factory, make_minimal_event  # noqa: F401
from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap

_META_FIELDS: frozenset[str] = frozenset({"snapshot_event_id", "state_hash"})


def _domain_equal(s1, s2) -> bool:
    """Compare domain state excluding DB-position meta fields."""
    d1 = {k: v for k, v in dataclasses.asdict(s1).items() if k not in _META_FIELDS}
    d2 = {k: v for k, v in dataclasses.asdict(s2).items() if k not in _META_FIELDS}
    return d1 == d2


def _seed_unknown_events(db_path: str, n: int = 5) -> None:
    """Insert n events with unknown types into db_path."""
    store = EventLog(db_path)
    events = [make_minimal_event(f"_unknown_future_v2_{i}") for i in range(n)]
    store.append(events, source="test_evolution", command_id="unk_seed_0000")


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_unknown_events_do_not_crash_replay(db_factory, cmds):
    """Reducer skips unknown event types — replay must not raise (EV-4)."""
    db = db_factory()
    execute_sequence(wrap(cmds), db)
    _seed_unknown_events(db)
    state = get_current_state(db)
    assert state is not None


@given(cmds=valid_command_sequence())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_unknown_events_do_not_alter_state(db_factory, cmds):
    """State built from [known_events] equals state from [known_events + unknown_events]."""
    wrapped = wrap(cmds)
    db_clean = db_factory()
    db_mixed = db_factory()

    _, state_clean = execute_sequence(wrapped, db_clean)

    execute_sequence(wrapped, db_mixed)
    _seed_unknown_events(db_mixed)
    state_mixed = get_current_state(db_mixed)

    assert _domain_equal(state_clean, state_mixed)


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_adversarial_plus_unknown_safe(db_factory, cmds):
    """Adversarial sequence with injected unknown events does not crash."""
    db = db_factory()
    execute_sequence(wrap(cmds), db)
    _seed_unknown_events(db, n=10)
    state = get_current_state(db)
    assert state is not None


def test_future_event_type_safe(db_factory):
    """Synthetic future V2 event injected mid-log: replay must not crash (I-EVOLUTION-FORWARD-1)."""
    db = db_factory()
    store = EventLog(db)

    store.append(
        [make_minimal_event("_seed_v1") for _ in range(5)],
        source="test",
        command_id="v1_seed_0000",
    )

    store.append(
        [make_minimal_event("FutureV2Event")],
        source="test",
        command_id="v2_synthetic_0000",
    )

    store.append(
        [make_minimal_event("_seed_v1_post") for _ in range(3)],
        source="test",
        command_id="v1_post_0000",
    )

    state = get_current_state(db)
    assert state is not None
