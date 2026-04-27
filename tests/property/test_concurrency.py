"""I-VR-STABLE-4: optimistic lock — concurrent writes yield exactly one StaleStateError (P-8)."""
from __future__ import annotations

import tempfile
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from sdd.core.errors import StaleStateError
from sdd.infra.event_log import EventLog
from tests.harness.fixtures import make_minimal_event
from tests.harness.generators import valid_command_sequence
from tests.property import execute_sequence, wrap


def _seed_and_get_head(db_path: str) -> int:
    """Append one event and return the resulting head seq."""
    store = EventLog(db_path)
    store.append([make_minimal_event("_seed")], source="test_seed")
    head = store.max_seq()
    assert head is not None
    return head


@pytest.mark.parametrize("n_seed", [1, 3, 10])
def test_stale_head_raises_once(n_seed):
    """Second writer using stale head_seq gets StaleStateError (I-VR-STABLE-4)."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        store = EventLog(db)

        # Seed n_seed events to establish a non-None head
        for i in range(n_seed):
            store.append([make_minimal_event(f"_seed_{i}")], source="test", command_id=f"seed_{i:04d}")

        stale_head = store.max_seq()
        assert stale_head is not None

        # First writer: advances head
        store.append([make_minimal_event("_writer_a")], source="test", expected_head=stale_head)

        # Second writer: uses the now-stale head → StaleStateError
        with pytest.raises(StaleStateError):
            store.append([make_minimal_event("_writer_b")], source="test", expected_head=stale_head)


def test_only_one_stale_error_total():
    """P-8 acceptance: exactly one StaleStateError in the two-writer scenario."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        store = EventLog(db)
        store.append([make_minimal_event("_seed")], source="test", command_id="seed_0000")

        head = store.max_seq()
        errors = 0
        successes = 0

        for writer_id in ("A", "B"):
            try:
                store.append(
                    [make_minimal_event(f"_writer_{writer_id}")],
                    source="test",
                    expected_head=head,
                )
                successes += 1
            except StaleStateError:
                errors += 1

        assert successes == 1, f"Expected 1 success, got {successes}"
        assert errors == 1, f"Expected 1 StaleStateError, got {errors}"


@given(cmds=valid_command_sequence(max_cmds=3))
@settings(max_examples=20, deadline=None)
def test_stale_head_property(cmds):
    """Property: any sequence followed by a stale-head append yields StaleStateError."""
    wrapped = wrap(cmds)
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "db.duckdb")
        execute_sequence(wrapped, db)

        store = EventLog(db)
        head_after = store.max_seq()
        if head_after is None:
            return  # empty DB — optimistic lock not active for None head

        # Advance head by one more event
        store.append([make_minimal_event("_advance")], source="test", command_id="advance_0000")

        # Now head_after is stale → next append with expected_head=head_after must fail
        with pytest.raises(StaleStateError):
            store.append([make_minimal_event("_stale")], source="test", expected_head=head_after)
