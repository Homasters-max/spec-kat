"""NormGuard factory — Spec_v5 §4.5, I-GUARD-1, I-CMD-12."""
from __future__ import annotations

import time
import uuid

from sdd.core.events import DomainEvent, EventLevel, NormViolatedEvent
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard


def make_norm_guard(actor: str, action: str, task_id: str | None) -> Guard:
    """Return a Guard that checks actor/action against the norm catalog (I-CMD-12)."""

    def norm_guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        if ctx.norms.is_allowed(actor, action):
            return (
                GuardResult(GuardOutcome.ALLOW, "NormGuard", "actor permitted", None, task_id),
                [],
            )

        violated_norm_id = ""
        for entry in ctx.norms.entries:
            if (
                (entry.actor == actor or entry.actor == "any")
                and entry.action == action
                and entry.result == "forbidden"
            ):
                violated_norm_id = entry.norm_id
                break

        norm_reason = (
            f"actor={actor!r} not permitted for action={action!r}"
            f" (norm: {violated_norm_id})"
        )
        deny_result = GuardResult(
            outcome=GuardOutcome.DENY,
            guard_name="NormGuard",
            message=norm_reason,
            norm_id=violated_norm_id,
            task_id=task_id,
            reason=f"GUARD_DENY.NormGuard.{violated_norm_id or 'UNLISTED'}",
            human_reason=norm_reason[:140],
        )
        norm_event = NormViolatedEvent(
            event_type="NormViolated",
            event_id=str(uuid.uuid4()),
            appended_at=int(time.time() * 1000),
            level=EventLevel.L1,
            event_source="runtime",
            caused_by_meta_seq=None,
            actor=actor,
            action=action,
            norm_id=violated_norm_id,
            task_id=task_id,
            timestamp=ctx.now,
        )
        return deny_result, [norm_event]

    return norm_guard
