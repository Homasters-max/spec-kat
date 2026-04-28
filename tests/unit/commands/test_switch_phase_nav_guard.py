"""Tests for switch-phase navigation guard policy.

Invariants: I-GUARD-NAV-1, I-STDERR-1
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from sdd.commands.switch_phase import (
    _switch_phase_guard_factory,
    make_switch_phase_guard,
)
from sdd.domain.guards.context import GuardOutcome


def test_switch_phase_from_complete_phase_allowed() -> None:
    """Switching from a COMPLETE phase must be ALLOW.

    I-GUARD-NAV-1: make_phase_guard (PG-3) must not be in the pipeline; phase_status
    of the current phase is irrelevant to navigation.
    """
    ctx = MagicMock()
    ctx.state.phases_known = frozenset({1, 2})
    ctx.state.phase_current = 1
    ctx.state.phase_status = "COMPLETE"  # would have been blocked by PG-3 before fix

    guard = make_switch_phase_guard(phase_id=2)
    result, events = guard(ctx)

    assert result.outcome == GuardOutcome.ALLOW
    assert events == []


def test_switch_phase_guard_no_pg3() -> None:
    """_switch_phase_guard_factory must contain exactly SwitchPhaseGuard + NormGuard.

    I-GUARD-NAV-1: make_phase_guard (PG-1..PG-3) must be absent from the pipeline.
    """
    cmd = MagicMock()
    cmd.phase_id = 3

    _SWITCH = object()
    _NORM = object()

    with (
        patch("sdd.commands.switch_phase.make_switch_phase_guard", return_value=_SWITCH) as mock_sw,
        patch("sdd.commands.switch_phase.make_norm_guard", return_value=_NORM),
    ):
        guards = _switch_phase_guard_factory(cmd)

    assert len(guards) == 2, f"Expected 2 guards (nav only), got {len(guards)}"
    assert guards[0] is _SWITCH
    assert guards[1] is _NORM
    mock_sw.assert_called_once_with(3)


def test_switch_phase_stderr_on_error(capsys) -> None:
    """main() must emit JSON to stderr before returning 1 on SDDError.

    I-STDERR-1: silent `except SDDError: return 1` is forbidden.
    """
    from sdd.commands.switch_phase import main
    from sdd.core.errors import MissingContext

    err = MissingContext("I-PHASE-CONTEXT-2: phase 99 not in phases_known=[]")

    with (
        patch("sdd.commands.switch_phase.event_store_url", return_value="/fake/db.duckdb"),
        patch("sdd.infra.projections.get_current_state", side_effect=err),
    ):
        rc = main(["99"])

    assert rc == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error_type"] == "MissingContext"
    assert "phase" in payload["message"].lower()
