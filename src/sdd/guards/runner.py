"""Guard pipeline runner — EmitFn, GuardContext, GuardOutcome, GuardResult,
run_guard_pipeline — Spec_v5 §2.3 (I-GRD-4).

GuardContext re-exported from canonical location: sdd.domain.guards.context.
Phase 3 guards (TaskGuard, PhaseGuard, ScopeGuard, NormGuard, TaskStartGuard) removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

from sdd.domain.guards.context import GuardContext  # canonical (Spec_v5 §2.3)

if TYPE_CHECKING:
    from sdd.core.events import DomainEvent

EmitFn = Callable[["DomainEvent"], None]


class GuardOutcome(Enum):
    ALLOW = "allow"
    DENY  = "deny"


@dataclass(frozen=True)
class GuardResult:
    outcome:    GuardOutcome
    guard_name: str
    message:    str
    norm_id:    str | None
    task_id:    str | None


def run_guard_pipeline(
    guards: list[Callable[[], GuardResult]],
    stop_on_deny: bool = True,
) -> list[GuardResult]:
    """Run a list of zero-argument guard callables in order.

    stop_on_deny=True (default): stop at first DENY, return [that result].
    stop_on_deny=False: run all guards regardless, return all results in order.

    Pure orchestration — does not inspect or interpret guard logic (I-GRD-4).
    Returns [] if guards list is empty.
    """
    results: list[GuardResult] = []
    for guard in guards:
        result = guard()
        results.append(result)
        if stop_on_deny and result.outcome is GuardOutcome.DENY:
            break
    return results
