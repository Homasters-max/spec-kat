"""I-VR-STABLE-8: evolution safety — unknown events skipped; replay stable (P-9)."""
from __future__ import annotations

import os
import tempfile

import pytest
from hypothesis import given, settings

from sdd.infra.event_store import EventStore
from sdd.infra.projections import get_current_state
from tests.harness.fixtures import make_minimal_event
from tests.harness.generators import adversarial_sequence, valid_command_sequence
from tests.property import execute_sequence, wrap


def _seed_unknown_events(db_path: str, n: int = 5) -> None:
    """Insert n events with unknown types into db_path."""
    store = EventStore(db_path)
    events = [make_minimal_event(f"_unknown_future_v2_{i}") for i in range(n)]
    store.append(events, source="test_evolution", command_id="unk_seed_0000")


@given(cmds=valid_command_sequence())
@settings(max_examples=25, deadline=None)
def test_unknown_events_do_not_crash_replay(cmds):
    """Reducer skips unknown event types — replay must not raise (EV-4)."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        execute_sequence(wrap(cmds), db)
        _seed_unknown_events(db)
        # Must not raise
        state = get_current_state(db)
        assert state is not None


@given(cmds=valid_command_sequence())
@settings(max_examples=20, deadline=None)
def test_unknown_events_do_not_alter_state(cmds):
    """State built from [known_events] equals state from [known_events + unknown_events]."""
    wrapped = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        db_clean = os.path.join(d, "clean.duckdb")
        db_mixed = os.path.join(d, "mixed.duckdb")

        _, state_clean = execute_sequence(wrapped, db_clean)

        execute_sequence(wrapped, db_mixed)
        _seed_unknown_events(db_mixed)
        state_mixed = get_current_state(db_mixed)

        assert state_clean == state_mixed


@given(cmds=adversarial_sequence())
@settings(max_examples=20, deadline=None)
def test_adversarial_plus_unknown_safe(cmds):
    """Adversarial sequence with injected unknown events does not crash."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        execute_sequence(wrap(cmds), db)
        _seed_unknown_events(db, n=10)
        state = get_current_state(db)
        assert state is not None


def test_future_event_type_safe():
    """Synthetic future V2 event injected mid-log: replay must not crash (I-EVOLUTION-FORWARD-1)."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        store = EventStore(db)

        # Seed some known events
        store.append(
            [make_minimal_event("_seed_v1") for _ in range(5)],
            source="test",
            command_id="v1_seed_0000",
        )

        # Inject a synthetic future V2 event
        store.append(
            [make_minimal_event("FutureV2Event")],
            source="test",
            command_id="v2_synthetic_0000",
        )

        # Seed more known events after the future event
        store.append(
            [make_minimal_event("_seed_v1_post") for _ in range(3)],
            source="test",
            command_id="v1_post_0000",
        )

        state = get_current_state(db)
        assert state is not None
