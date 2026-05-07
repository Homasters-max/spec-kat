"""amend-plan — emits PlanAmended event (BC-31-2, I-HANDLER-PURE-1).

Handler is pure: reads Plan_vN.md to compute hash; no EventStore/projection calls.
Guard: raises InvalidState if phase_status == PLANNED (I-PLAN-IMMUTABLE-AFTER-ACTIVATE).
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import InvalidState, MissingContext
from sdd.core.events import DomainEvent, EventLevel, PlanAmended
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard
from sdd.infra.paths import plan_file


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_amend_plan_guard(phase_id: int) -> Guard:
    """Guard: rejects amend-plan if phase has not been activated (I-PLAN-IMMUTABLE-AFTER-ACTIVATE)."""

    def amend_plan_guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        if ctx.state.phase_status == "PLANNED":
            raise InvalidState(
                f"I-PLAN-IMMUTABLE-AFTER-ACTIVATE: phase {phase_id} has not been activated"
                f" (phase_status=PLANNED); run 'sdd activate-phase {phase_id}' first"
            )
        return (
            GuardResult(
                outcome=GuardOutcome.ALLOW,
                guard_name="AmendPlanGuard",
                message="phase is activated — amendment allowed",
                norm_id=None,
                task_id=None,
            ),
            [],
        )

    return amend_plan_guard


def _amend_plan_guard_factory(cmd: Any) -> list[Guard]:
    from sdd.domain.guards.norm_guard import make_norm_guard

    phase_id: int = getattr(cmd, "phase_id", 0)
    return [
        _make_amend_plan_guard(phase_id),
        make_norm_guard("human", "amend_plan", None),
    ]


class AmendPlanHandler(CommandHandlerBase):
    """Pure handler: returns [PlanAmended] without side-effects (I-HANDLER-PURE-1).

    Guard: raises MissingContext if Plan_vN.md does not exist.
    Phase activation check is enforced by the guard pipeline (_make_amend_plan_guard).
    """

    @error_event_boundary(source=__name__)
    def handle(self, cmd: Any) -> list[DomainEvent]:
        phase_id: int = cmd.phase_id
        reason: str = getattr(cmd, "reason", "")
        actor: str = getattr(cmd, "actor", "human")

        plan_path = plan_file(phase_id)

        if not plan_path.exists():
            raise MissingContext(
                f"Plan_v{phase_id}.md not found in plans/ — plan must exist before amendment"
            )

        new_plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()[:16]

        return [
            PlanAmended(
                event_type="PlanAmended",
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="runtime",
                caused_by_meta_seq=None,
                phase_id=phase_id,
                new_plan_hash=new_plan_hash,
                reason=reason,
                actor=actor,
            )
        ]


def _build_amend_plan_spec() -> Any:
    """Deferred import to avoid circular dependency with registry.py."""
    from sdd.commands.registry import CommandSpec, ProjectionType

    return CommandSpec(
        name="amend-plan",
        handler_class=AmendPlanHandler,
        actor="human",
        action="amend_plan",
        projection=ProjectionType.NONE,
        uses_task_id=False,
        requires_active_phase=False,  # custom guard allows ACTIVE and COMPLETE (not only ACTIVE)
        guard_factory=_amend_plan_guard_factory,
        event_schema=(PlanAmended,),
        preconditions=(
            "Plan_vN.md exists in plans/",
            "phase_status != PLANNED (phase must be activated)",
        ),
        postconditions=(
            "PlanAmended in EventLog",
        ),
        description="Record plan amendment after post-activation edit (BC-31-2)",
    )


amend_plan_spec = _build_amend_plan_spec()
