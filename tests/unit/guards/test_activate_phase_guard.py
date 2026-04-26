"""Tests for ActivatePhaseGuard — I-PHASE-SEQ-1, I-PHASE-CONTEXT-1, I-PHASE-CONTEXT-2."""
from unittest.mock import MagicMock

import pytest

from sdd.core.errors import Inconsistency
from sdd.domain.guards.activate_phase_guard import make_activate_phase_guard
from sdd.domain.guards.context import GuardOutcome


def _ctx(phase_current: int) -> MagicMock:
    ctx = MagicMock()
    ctx.state.phase_current = phase_current
    return ctx


def test_allow_sequential_activation():
    # I-PHASE-SEQ-1: phase_id == current + 1 → ALLOW, no events
    guard = make_activate_phase_guard(phase_id=19)
    result, events = guard(_ctx(phase_current=18))
    assert result.outcome == GuardOutcome.ALLOW
    assert events == []


def test_deny_skip_forward():
    # I-PHASE-SEQ-1: phase_id > current + 1 → Inconsistency; message names switch-phase
    guard = make_activate_phase_guard(phase_id=20)
    with pytest.raises(Inconsistency, match="switch-phase 20"):
        guard(_ctx(phase_current=18))


def test_deny_regression():
    # I-PHASE-SEQ-1: phase_id < current → Inconsistency; message names switch-phase
    guard = make_activate_phase_guard(phase_id=17)
    with pytest.raises(Inconsistency, match="switch-phase 17"):
        guard(_ctx(phase_current=18))


def test_integration_context_navigation_scenario():
    # I-PHASE-CONTEXT-1,2: D-3 fix — activate-phase cannot be used for context navigation.
    # Returning to phase 18 while current=23 must be rejected, directing to switch-phase.
    guard = make_activate_phase_guard(phase_id=18)
    with pytest.raises(Inconsistency) as exc_info:
        guard(_ctx(phase_current=23))
    msg = str(exc_info.value)
    assert "switch-phase 18" in msg
    assert "I-PHASE-SEQ-1" in msg
