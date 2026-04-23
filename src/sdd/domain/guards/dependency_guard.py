"""DependencyGuard — Spec_v4 §4.11 step 3, I-CMD-11, I-ES-3."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import ClassVar

from sdd.core.events import DomainEvent, EventLevel
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult


@dataclass(frozen=True)
class _DependencyDeniedEvent(DomainEvent):
    """Audit event emitted when DependencyGuard denies a command (I-CMD-11)."""
    EVENT_TYPE: ClassVar[str] = "SDDEventRejected"
    command:          str
    rejection_reason: str
    phase_id:         str
    failed_check:     str
    timestamp:        str


class DependencyGuard:
    """Pure guard: DENY if any declared dependency of task_id is not DONE (I-CMD-11).

    Returns (GuardResult, list[DomainEvent]) — no I/O, no mutations (I-ES-3).
    CommandRunner appends audit_events via EventStore on DENY.
    """

    @staticmethod
    def check(
        ctx: GuardContext,
        task_id: str,
    ) -> tuple[GuardResult, list[DomainEvent]]:
        """Check that all declared dependencies of task_id are DONE in the EventLog
        projection (ctx.state.tasks_done_ids).

        ALLOW → (GuardResult(ALLOW), [])
        DENY  → (GuardResult(DENY), [_DependencyDeniedEvent(...)])
        """
        deps = ctx.task_graph.dependencies(task_id)
        done_ids = set(ctx.state.tasks_done_ids)
        blocking = sorted(dep for dep in deps if dep not in done_ids)

        if blocking:
            reason = f"Dependencies not DONE: {', '.join(blocking)}"
            event = _DependencyDeniedEvent(
                event_type=_DependencyDeniedEvent.EVENT_TYPE,
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="runtime",
                caused_by_meta_seq=None,
                command=f"dependency check for {task_id}",
                rejection_reason=reason,
                phase_id=str(ctx.phase.phase_id),
                failed_check="I-CMD-11",
                timestamp=ctx.now,
            )
            return (
                GuardResult(
                    outcome=GuardOutcome.DENY,
                    guard_name="DependencyGuard",
                    message=reason,
                    norm_id="I-CMD-11",
                    task_id=task_id,
                ),
                [event],
            )

        return (
            GuardResult(
                outcome=GuardOutcome.ALLOW,
                guard_name="DependencyGuard",
                message="all dependencies DONE",
                norm_id=None,
                task_id=task_id,
            ),
            [],
        )
