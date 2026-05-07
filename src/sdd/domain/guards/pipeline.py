"""Generic guard pipeline executor — Spec_v5 §4.11, I-GUARD-1, I-GUARD-2."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sdd.domain.guards.context import GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard

if TYPE_CHECKING:
    from sdd.core.events import DomainEvent
    from sdd.domain.guards.context import GuardContext


def run_guard_pipeline(
    ctx: "GuardContext",
    guards: list[Guard],
    stop_on_deny: bool = True,
) -> "tuple[GuardResult, list[DomainEvent]]":
    """Pure orchestrator: call each Guard(ctx) in order, merge events.

    Integrity guards (raise on violation) propagate exceptions naturally.
    Policy guards return (DENY, events) — collected and returned to caller.
    """
    all_events: list[Any] = []
    last_result = GuardResult(GuardOutcome.ALLOW, "pipeline", "no guards run", None, None)

    for guard in guards:
        result, events = guard(ctx)
        all_events.extend(events)
        last_result = result
        if result.outcome is GuardOutcome.DENY and stop_on_deny:
            return result, all_events

    return last_result, all_events
