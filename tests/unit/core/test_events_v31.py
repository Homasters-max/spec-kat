"""Unit tests for Phase-31 governance events — Spec_v31 §9 #5, #6 (BC-31-1, BC-31-2).

Invariants covered: I-SESSION-PHASE-NULL-1, I-HANDLER-PURE-1
"""
from __future__ import annotations

import dataclasses

import pytest

from sdd.core.events import (
    PlanAmended,
    SessionDeclaredEvent,
    SpecApproved,
    V1_L1_EVENT_TYPES,
)
from sdd.domain.state.reducer import reduce


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
# §9 #5 — I-SESSION-PHASE-NULL-1: DRAFT_SPEC carries phase_id=None
# ---------------------------------------------------------------------------


def test_session_declared_draft_spec_phase_id_is_none() -> None:
    """§9 #5 / I-SESSION-PHASE-NULL-1: DRAFT_SPEC session must carry phase_id=None sentinel."""
    evt = SessionDeclaredEvent(session_type="DRAFT_SPEC")
    assert evt.phase_id is None


def test_session_declared_phase_id_none_is_default() -> None:
    """phase_id defaults to None — pre-phase sentinel value (I-SESSION-PHASE-NULL-1)."""
    evt = SessionDeclaredEvent()
    assert evt.phase_id is None


def test_session_declared_real_session_carries_real_phase_id() -> None:
    """Non-DRAFT_SPEC sessions carry a real (non-None) phase_id."""
    evt = SessionDeclaredEvent(session_type="IMPLEMENT", phase_id=31)
    assert evt.phase_id == 31


def test_session_declared_is_frozen() -> None:
    """SessionDeclaredEvent must be immutable (frozen dataclass) — I-HANDLER-PURE-1 support."""
    evt = SessionDeclaredEvent(session_type="DRAFT_SPEC")
    assert dataclasses.is_dataclass(evt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.phase_id = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# §9 #6 — replay with phase_id=None must not mutate state (I-SESSION-PHASE-NULL-1)
# ---------------------------------------------------------------------------


def test_session_declared_none_phase_id_noop_on_replay() -> None:
    """§9 #6: reduce([SessionDeclared(DRAFT_SPEC)]) leaves phase_current unchanged.

    I-SESSION-PHASE-NULL-1: Reducer MUST treat phase_id=None in SessionDeclared as no-op.
    """
    baseline = reduce([])
    event = _runtime_l1(
        "SessionDeclared",
        session_type="DRAFT_SPEC",
        phase_id=None,
        task_id=None,
        plan_hash="",
        timestamp="2026-04-27T00:00:00Z",
    )
    after = reduce([event])
    assert after.phase_current == baseline.phase_current


# ---------------------------------------------------------------------------
# frozen=True — BC-31-1 SpecApproved, BC-31-2 PlanAmended
# ---------------------------------------------------------------------------


def test_spec_approved_is_frozen() -> None:
    """BC-31-1: SpecApproved must be an immutable frozen dataclass."""
    evt = SpecApproved(
        event_type="SpecApproved",
        event_id="sa-001",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=31,
        spec_hash="abc12345",
        actor="human",
        spec_path=".sdd/specs/Spec_v31.md",
    )
    assert dataclasses.is_dataclass(evt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.phase_id = 99  # type: ignore[misc]


def test_plan_amended_is_frozen() -> None:
    """BC-31-2: PlanAmended must be an immutable frozen dataclass."""
    evt = PlanAmended(
        event_type="PlanAmended",
        event_id="pa-001",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=31,
        new_plan_hash="def45678",
        reason="Clarified task scope",
        actor="human",
    )
    assert dataclasses.is_dataclass(evt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.phase_id = 99  # type: ignore[misc]


def test_spec_approved_fields_accessible() -> None:
    """BC-31-1: SpecApproved fields are correctly stored after construction."""
    evt = SpecApproved(
        event_type="SpecApproved",
        event_id="sa-002",
        appended_at=1000,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=31,
        spec_hash="deadbeef",
        actor="human",
        spec_path=".sdd/specs/Spec_v31.md",
    )
    assert evt.phase_id == 31
    assert evt.actor == "human"
    assert evt.spec_hash == "deadbeef"
    assert evt.spec_path == ".sdd/specs/Spec_v31.md"


def test_plan_amended_fields_accessible() -> None:
    """BC-31-2: PlanAmended fields are correctly stored after construction."""
    evt = PlanAmended(
        event_type="PlanAmended",
        event_id="pa-002",
        appended_at=1000,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=31,
        new_plan_hash="cafebabe",
        reason="Added missing acceptance criteria",
        actor="human",
    )
    assert evt.phase_id == 31
    assert evt.reason == "Added missing acceptance criteria"
    assert evt.new_plan_hash == "cafebabe"


# ---------------------------------------------------------------------------
# C-1 catalog membership
# ---------------------------------------------------------------------------


def test_spec_approved_in_v1_l1_types() -> None:
    """BC-31-1: 'SpecApproved' must be registered in V1_L1_EVENT_TYPES (C-1)."""
    assert "SpecApproved" in V1_L1_EVENT_TYPES


def test_plan_amended_in_v1_l1_types() -> None:
    """BC-31-2: 'PlanAmended' must be registered in V1_L1_EVENT_TYPES (C-1)."""
    assert "PlanAmended" in V1_L1_EVENT_TYPES


def test_session_declared_in_v1_l1_types() -> None:
    """'SessionDeclared' must be registered in V1_L1_EVENT_TYPES (C-1)."""
    assert "SessionDeclared" in V1_L1_EVENT_TYPES


def test_c1_consistency_on_import() -> None:
    """Importing events.py and reducer must not raise — C-1 compliance for Phase 31."""
    import sdd.core.events  # noqa: F401
    import sdd.domain.state.reducer  # noqa: F401
