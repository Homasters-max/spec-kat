"""Tests for ActivatePhaseCommand + ActivatePhaseHandler.

Invariants covered: I-ACT-1, I-HANDLER-BATCH-PURE-1, I-PHASE-EVENT-PAIR-1
Spec ref: Spec_v15 §2 BC-4; Phase_v15.5 §4; T-1514 acceptance
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.activate_phase import ActivatePhaseCommand, ActivatePhaseHandler
from sdd.core.errors import InvalidActor
from sdd.core.events import PhaseInitializedEvent, PhaseStartedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd(
    command_id: str | None = None,
    phase_id: int = 5,
    actor: str = "human",
    tasks_total: int = 3,
) -> ActivatePhaseCommand:
    return ActivatePhaseCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ActivatePhaseCommand",
        payload={},
        phase_id=phase_id,
        actor=actor,
        tasks_total=tasks_total,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_activate_phase_emits_atomic_pair(tmp_db_path: str) -> None:
    """ActivatePhaseHandler emits exactly [PhaseStarted, PhaseInitialized] (I-PHASE-EVENT-PAIR-1, I-ACT-1)."""
    cmd = _cmd(actor="human", tasks_total=7)
    result = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    assert len(result) == 2

    started = result[0]
    assert isinstance(started, PhaseStartedEvent)
    assert started.event_type == "PhaseStarted"
    assert started.phase_id == 5
    assert started.actor == "human"

    initialized = result[1]
    assert isinstance(initialized, PhaseInitializedEvent)
    assert initialized.event_type == "PhaseInitialized"
    assert initialized.phase_id == 5
    assert initialized.tasks_total == 7
    assert initialized.plan_version == 5

    # pair consistency (I-PHASE-EVENT-PAIR-1)
    assert started.phase_id == initialized.phase_id


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
