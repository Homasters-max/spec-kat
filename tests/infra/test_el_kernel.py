"""Tests for EventLogKernel (BC-46-A, I-EL-KERNEL-WIRED-1)."""
from __future__ import annotations

import pytest

from sdd.core.errors import StaleStateError
from sdd.infra.el_kernel import EventLogKernel


@pytest.fixture
def kernel() -> EventLogKernel:
    return EventLogKernel()


# ---------------------------------------------------------------------------
# resolve_batch_id
# ---------------------------------------------------------------------------

def test_el_kernel_resolve_batch_id(kernel: EventLogKernel) -> None:
    single = kernel.resolve_batch_id(["e1"])
    assert single is None, "single event → None"

    multi = kernel.resolve_batch_id(["e1", "e2"])
    assert multi is not None, "multi event → UUID str"
    assert len(multi) == 36  # UUID4 canonical form: 8-4-4-4-12

    # Two consecutive calls produce different UUIDs
    other = kernel.resolve_batch_id(["e1", "e2"])
    assert multi != other

    # Empty list → None (no multi-event batch)
    assert kernel.resolve_batch_id([]) is None


# ---------------------------------------------------------------------------
# check_optimistic_lock
# ---------------------------------------------------------------------------

def test_el_kernel_check_optimistic_lock(kernel: EventLogKernel) -> None:
    # expected_head=None → always skip (no constraint)
    kernel.check_optimistic_lock(None, None)
    kernel.check_optimistic_lock(10, None)
    kernel.check_optimistic_lock(None, None)

    # Matching values → no exception
    kernel.check_optimistic_lock(10, 10)
    kernel.check_optimistic_lock(0, 0)

    # Mismatch → StaleStateError
    with pytest.raises(StaleStateError):
        kernel.check_optimistic_lock(10, 9)

    with pytest.raises(StaleStateError):
        kernel.check_optimistic_lock(None, 5)

    with pytest.raises(StaleStateError):
        kernel.check_optimistic_lock(5, 10)


# ---------------------------------------------------------------------------
# filter_duplicates
# ---------------------------------------------------------------------------

def test_el_kernel_filter_duplicates(kernel: EventLogKernel) -> None:
    events = [
        {"command_id": "abc", "event_index": 0, "data": "first"},
        {"command_id": "abc", "event_index": 1, "data": "second"},
        {"command_id": "abc", "event_index": 2, "data": "third"},
    ]

    # No existing pairs → all go to to_insert
    to_insert, skipped = kernel.filter_duplicates(events, set())
    assert len(to_insert) == 3
    assert len(skipped) == 0

    # First event already exists → skipped
    existing = {("abc", 0)}
    to_insert, skipped = kernel.filter_duplicates(events, existing)
    assert len(to_insert) == 2
    assert len(skipped) == 1
    assert skipped[0]["event_index"] == 0
    assert to_insert[0]["event_index"] == 1

    # All pairs exist → everything skipped
    all_existing = {("abc", 0), ("abc", 1), ("abc", 2)}
    to_insert, skipped = kernel.filter_duplicates(events, all_existing)
    assert len(to_insert) == 0
    assert len(skipped) == 3

    # Events without command_id are never duplicates regardless of existing_pairs
    no_cmd_events = [{"event_index": 0}, {"event_index": 1}]
    to_insert, skipped = kernel.filter_duplicates(no_cmd_events, {(None, 0)})
    assert len(to_insert) == 2
    assert len(skipped) == 0

    # dict identity preserved (same objects returned)
    to_insert, _ = kernel.filter_duplicates(events[:2], set())
    assert to_insert[0] is events[0]
    assert to_insert[1] is events[1]
