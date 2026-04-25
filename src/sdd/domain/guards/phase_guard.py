"""PhaseGuard factory — Spec_v5 §4.5, I-GUARD-1, PG-1..PG-3."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from sdd.core.events import DomainEvent, EventLevel
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class _SDDEventRejectedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "SDDEventRejected"
    command: str
    rejection_reason: str
    phase_id: str
    failed_check: str
    timestamp: str


def make_phase_guard(command_str: str, task_id: str | None) -> Guard:
    """Return a Guard enforcing PG-1..PG-3 preconditions."""

    def phase_guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        s = ctx.state
        p = ctx.phase
        failed_check: str | None = None
        deny_reason: str | None = None

        if s.phase_current != p.phase_id:
            failed_check = "PG-1"
            deny_reason = f"phase_current ({s.phase_current}) != phase_id ({p.phase_id})"
        elif s.plan_version != p.phase_id or s.tasks_version != p.phase_id:
            failed_check = "PG-2"
            deny_reason = (
                f"plan_version ({s.plan_version}) or tasks_version ({s.tasks_version})"
                f" != phase_id ({p.phase_id})"
            )
        elif p.status != "ACTIVE":
            failed_check = "PG-3"
            deny_reason = f"phase.status ({p.status!r}) != 'ACTIVE'"

        if failed_check is not None:
            deny_result = GuardResult(
                outcome=GuardOutcome.DENY,
                guard_name="PhaseGuard",
                message=deny_reason,
                reason=f"GUARD_DENY.PhaseGuard.{failed_check}",
                norm_id=None,
                task_id=task_id,
            )
            audit_event = _SDDEventRejectedEvent(
                event_type="SDDEventRejected",
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="runtime",
                caused_by_meta_seq=None,
                command=command_str,
                rejection_reason=deny_reason,
                phase_id=str(s.phase_current),
                failed_check=failed_check,
                timestamp=ctx.now,
            )
            return deny_result, [audit_event]

        return (
            GuardResult(GuardOutcome.ALLOW, "PhaseGuard", "PG-1..PG-3 pass", None, task_id),
            [],
        )

    return phase_guard
