"""TaskGuard factory — Spec_v5 §4.5, I-GUARD-1, I-GRD-5."""
from __future__ import annotations

from sdd.core.errors import InvalidState, MissingContext
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.types import Guard


def make_task_guard(task_id: str) -> Guard:
    """Return an integrity Guard that raises when task is missing or already DONE."""

    def task_guard(ctx: GuardContext) -> tuple[GuardResult, list]:
        task = ctx.task
        if task is None:
            raise MissingContext(f"Task {task_id!r} not found in taskset")
        if task.status == "DONE":
            raise InvalidState(
                f"Task {task_id!r} is already DONE — duplicate execution blocked (I-GRD-5)"
            )
        return GuardResult(GuardOutcome.ALLOW, "TaskGuard", "task is TODO", None, task_id), []

    return task_guard
