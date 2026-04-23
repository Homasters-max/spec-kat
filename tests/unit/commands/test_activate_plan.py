"""Tests for ActivatePlanCommand + ActivatePlanHandler.

Invariants covered: I-ACT-1, I-CMD-1, I-DOMAIN-1
Spec ref: Spec_v5 §4.3, §9 Verification row 6
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.activate_plan import ActivatePlanCommand, ActivatePlanHandler
from sdd.core.errors import AlreadyActivated, InvalidActor
from sdd.core.events import PlanActivatedEvent
from sdd.infra.event_log import sdd_append


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd(
    command_id: str | None = None,
    plan_version: int = 5,
    actor: str = "human",
) -> ActivatePlanCommand:
    return ActivatePlanCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ActivatePlanCommand",
        payload={},
        plan_version=plan_version,
        actor=actor,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_activate_plan_emits_event(tmp_db_path: str) -> None:
    """ActivatePlanHandler emits a PlanActivatedEvent when plan is PLANNED (I-ACT-1)."""
    cmd = _cmd(actor="human")
    result = ActivatePlanHandler(tmp_db_path).handle(cmd)
    assert len(result) == 1
    evt = result[0]
    assert isinstance(evt, PlanActivatedEvent)
    assert evt.event_type == "PlanActivated"
    assert evt.actor == "human"
    assert evt.plan_version == 5


def test_activate_plan_command_idempotent(tmp_db_path: str) -> None:
    """Duplicate command_id returns [] without side effects (I-CMD-1 command-level idempotency)."""
    cmd_id = "cmd-activate-plan-idem"
    cmd = _cmd(command_id=cmd_id, plan_version=5, actor="human")

    # First call succeeds
    result = ActivatePlanHandler(tmp_db_path).handle(cmd)
    assert len(result) == 1

    # Simulate CommandRunner writing the event with command_id in payload
    sdd_append(
        "PlanActivated",
        {"command_id": cmd_id, "plan_version": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    # Second call with same command_id → idempotent → []
    result2 = ActivatePlanHandler(tmp_db_path).handle(cmd)
    assert result2 == []


def test_already_active_plan_raises(tmp_db_path: str) -> None:
    """Activating an already-ACTIVE plan raises AlreadyActivated — I-DOMAIN-1.

    A new command_id on an ACTIVE plan is a domain error, not a replay.
    """
    # Seed DB with a PlanActivated event (plan is now ACTIVE per reducer)
    sdd_append(
        "PlanActivated",
        {"plan_version": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    cmd = _cmd(command_id=str(uuid.uuid4()), plan_version=5, actor="human")
    with pytest.raises(AlreadyActivated):
        ActivatePlanHandler(tmp_db_path).handle(cmd)


def test_llm_actor_rejected_plan(tmp_db_path: str) -> None:
    """actor='llm' is rejected with InvalidActor — I-ACT-1 (plan activation is human-only)."""
    cmd = _cmd(actor="llm")
    with pytest.raises(InvalidActor):
        ActivatePlanHandler(tmp_db_path).handle(cmd)
