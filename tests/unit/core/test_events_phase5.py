"""Phase 5 event dataclass tests — Spec_v5 §9 Verification row 1.

Invariants covered: C-1, I-SCHEMA-1
"""
from __future__ import annotations

import dataclasses

import pytest

from sdd.core.events import (
    PhaseActivatedEvent,
    PlanActivatedEvent,
    V1_L1_EVENT_TYPES,
)
from sdd.domain.state.reducer import EventReducer, reduce


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {
        "event_type": event_type,
        "event_source": "runtime",
        "level": "L1",
        **payload,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_phase_activated_event_is_frozen() -> None:
    """PhaseActivatedEvent must be a frozen dataclass (I-SCHEMA-1 — hashable, immutable)."""
    evt = PhaseActivatedEvent(
        event_type="PhaseActivated",
        event_id="e-1",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=5,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
    )
    assert dataclasses.is_dataclass(evt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.phase_id = 99  # type: ignore[misc]


def test_plan_activated_event_is_frozen() -> None:
    """PlanActivatedEvent must be a frozen dataclass (I-SCHEMA-1)."""
    evt = PlanActivatedEvent(
        event_type="PlanActivated",
        event_id="e-2",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        plan_version=5,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
    )
    assert dataclasses.is_dataclass(evt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.plan_version = 99  # type: ignore[misc]


def test_c1_assert_phase5_import() -> None:
    """Importing events.py must not raise AssertionError — C-1 compliance for Phase 5.

    C-1 is enforced by an assert at class-definition time in EventReducer:
    _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES.
    If PhaseActivated or PlanActivated are missing from either set, AssertionError is raised.
    """
    import sdd.core.events  # noqa: F401
    import sdd.domain.state.reducer  # noqa: F401


def test_phase_activated_in_v1_l1_types() -> None:
    """'PhaseActivated' must be in V1_L1_EVENT_TYPES (C-1 — L1 catalog membership)."""
    assert "PhaseActivated" in V1_L1_EVENT_TYPES


def test_reducer_handles_phase_activated() -> None:
    """PhaseActivated event is handled by the reducer: sets phase_status='ACTIVE'."""
    event = _runtime_l1(
        "PhaseActivated",
        phase_id=5,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
    )
    state = reduce([event])
    assert state.phase_status == "ACTIVE"


def test_reducer_handles_plan_activated() -> None:
    """PlanActivated event is handled by the reducer: sets plan_status='ACTIVE'."""
    event = _runtime_l1(
        "PlanActivated",
        plan_version=5,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
    )
    state = reduce([event])
    assert state.plan_status == "ACTIVE"
