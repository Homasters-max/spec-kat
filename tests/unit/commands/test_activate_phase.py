"""Tests for ActivatePhaseCommand + ActivatePhaseHandler.

Invariants covered: I-ACT-1, I-CMD-1, I-DOMAIN-1
Spec ref: Spec_v5 §4.2, §9 Verification row 5
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.activate_phase import ActivatePhaseCommand, ActivatePhaseHandler
from sdd.core.errors import AlreadyActivated, InvalidActor
from sdd.core.events import PhaseActivatedEvent
from sdd.infra.event_log import sdd_append


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd(
    command_id: str | None = None,
    phase_id: int = 5,
    actor: str = "human",
) -> ActivatePhaseCommand:
    return ActivatePhaseCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ActivatePhaseCommand",
        payload={},
        phase_id=phase_id,
        actor=actor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_activate_phase_emits_event(tmp_db_path: str) -> None:
    """ActivatePhaseHandler emits a PhaseActivatedEvent when phase is PLANNED (I-ACT-1)."""
    cmd = _cmd(actor="human")
    result = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    assert len(result) == 1
    evt = result[0]
    assert isinstance(evt, PhaseActivatedEvent)
    assert evt.event_type == "PhaseActivated"
    assert evt.actor == "human"
    assert evt.phase_id == 5


def test_activate_phase_command_idempotent(tmp_db_path: str) -> None:
    """Duplicate command_id returns [] without side effects (I-CMD-1 command-level idempotency)."""
    cmd_id = "cmd-activate-idem"
    cmd = _cmd(command_id=cmd_id, phase_id=5, actor="human")

    # First call succeeds
    result = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    assert len(result) == 1

    # Simulate CommandRunner writing the event with command_id in payload
    sdd_append(
        "PhaseActivated",
        {"command_id": cmd_id, "phase_id": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    # Second call with same command_id → idempotent → []
    result2 = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    assert result2 == []


def test_already_active_raises(tmp_db_path: str) -> None:
    """Activating an already-ACTIVE phase raises AlreadyActivated — I-DOMAIN-1.

    Command-level idempotency (I-CMD-1) only guards replay of the same command_id.
    A new command_id on an ACTIVE phase is a domain error, not a replay.
    """
    # Seed DB with a PhaseActivated event (phase is now ACTIVE per reducer)
    sdd_append(
        "PhaseActivated",
        {"phase_id": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    # New command_id (not a replay) — domain guard must catch the already-ACTIVE state
    cmd = _cmd(command_id=str(uuid.uuid4()), phase_id=5, actor="human")
    with pytest.raises(AlreadyActivated):
        ActivatePhaseHandler(tmp_db_path).handle(cmd)


def test_llm_actor_rejected(tmp_db_path: str) -> None:
    """actor='llm' is rejected with InvalidActor — I-ACT-1 (phase activation is human-only)."""
    cmd = _cmd(actor="llm")
    with pytest.raises(InvalidActor):
        ActivatePhaseHandler(tmp_db_path).handle(cmd)


def test_invalid_actor_raises(tmp_db_path: str) -> None:
    """Any non-'human' actor is rejected with InvalidActor — I-ACT-1."""
    cmd = _cmd(actor="robot")
    with pytest.raises(InvalidActor):
        ActivatePhaseHandler(tmp_db_path).handle(cmd)
