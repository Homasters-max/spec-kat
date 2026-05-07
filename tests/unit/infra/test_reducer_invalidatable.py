"""Tests for EventReducer.is_invalidatable and _AUDIT_ONLY_EVENTS.

Covers: I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1, I-INVALID-4.
"""
from __future__ import annotations

import pytest

from sdd.domain.state.reducer import EventReducer


# ---------------------------------------------------------------------------
# I-AUDIT-ONLY-SSOT-1
# ---------------------------------------------------------------------------

def test_audit_only_events_in_reducer_contains_session_declared() -> None:
    assert "SessionDeclared" in EventReducer._AUDIT_ONLY_EVENTS


# ---------------------------------------------------------------------------
# I-INVALIDATABLE-INTERFACE-1 + I-INVALID-AUDIT-ONLY-1
# ---------------------------------------------------------------------------

def test_is_invalidatable_returns_true_for_session_declared() -> None:
    assert EventReducer.is_invalidatable("SessionDeclared") is True


# ---------------------------------------------------------------------------
# I-INVALID-4: state-mutating events MUST NOT be invalidatable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event_type", [
    "PhaseInitialized",
    "TaskImplemented",
    "TaskValidated",
    "PhaseActivated",
    "PlanActivated",
    "PhaseCompleted",
    "PhaseContextSwitched",
    "PlanAmended",
    "TaskSetDefined",
])
def test_is_invalidatable_returns_false_for_state_mutating(event_type: str) -> None:
    assert EventReducer.is_invalidatable(event_type) is False


# ---------------------------------------------------------------------------
# I-INVALIDATABLE-INTERFACE-1: unknown types are invalidatable
# ---------------------------------------------------------------------------

def test_is_invalidatable_returns_true_for_unknown_type() -> None:
    assert EventReducer.is_invalidatable("NonExistentEvent_XYZ") is True
