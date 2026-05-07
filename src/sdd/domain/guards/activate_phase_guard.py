"""ActivatePhaseGuard — Spec_v24 BC-PC-4, I-PHASE-SEQ-1."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sdd.core.errors import Inconsistency
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard

if TYPE_CHECKING:
    from sdd.core.events import DomainEvent


def make_activate_phase_guard(phase_id: int) -> Guard:
    """I-PHASE-SEQ-1: phase_id MUST equal current + 1."""

    def guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        current = ctx.state.phase_current
        if phase_id != current + 1:
            raise Inconsistency(
                f"I-PHASE-SEQ-1: activate-phase requires phase_id == current+1;"
                f" got phase_id={phase_id}, current={current}."
                f" Use 'sdd switch-phase {phase_id}' to return to a previously activated phase."
            )
        return GuardResult(GuardOutcome.ALLOW, "ActivatePhaseGuard", "I-PHASE-SEQ-1 pass", None, None), []

    return guard
