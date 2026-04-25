"""Phase 4 GuardContext + supporting types — Spec_v4 §4.13, I-CMD-11, I-CMD-12."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from sdd.domain.tasks.parser import Task, parse_taskset

if TYPE_CHECKING:
    from sdd.domain.norms.catalog import NormCatalog
    from sdd.domain.state.reducer import SDDState


class GuardOutcome(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class GuardResult:
    outcome:             GuardOutcome
    guard_name:          str
    message:             str
    norm_id:             str | None
    task_id:             str | None
    reason:              str | None = None   # GUARD_DENY.<guard>.<rule_id> (I-GUARD-REASON-1)
    human_reason:        str | None = None   # ≤140 chars, no internal IDs (I-HUMAN-REASON-1)
    violated_invariant:  str | None = None   # I-* if applicable (I-GUARD-REASON-1)


@dataclass(frozen=True)
class PhaseState:
    phase_id: int
    status:   str  # "PLANNED" | "ACTIVE" | "COMPLETE"


@dataclass(frozen=True)
class EventLogView:
    """Read-only pointer to the EventLog DB — passed to guards for raw event queries."""
    db_path: str


@dataclass(frozen=True)
class DAG:
    """Immutable task dependency graph: task_id → declared dependency ids."""
    deps: dict[str, frozenset[str]]

    def dependencies(self, task_id: str) -> frozenset[str]:
        """Return declared dependency task_ids; empty set if task_id is unknown."""
        return self.deps.get(task_id, frozenset())


@dataclass(frozen=True)
class GuardContext:
    """Immutable snapshot passed to every Phase 4 guard (I-ES-3).

    Guards are pure functions over GuardContext — they inspect fields and
    return (GuardResult, list[DomainEvent]) without mutating anything.

    state is ALWAYS built from EventLog replay, never from State_index.yaml (I-CMD-11).
    """
    state:      "SDDState"
    phase:      PhaseState
    task:       Task | None
    norms:      "NormCatalog"        # default = DENY (I-CMD-12)
    event_log:  EventLogView         # read-only projection of EventLog
    task_graph: DAG                  # dependency graph for DependencyGuard (I-CMD-11)
    now:        str                  # ISO8601 UTC — injected for determinism


_SENTINEL_DEPS: frozenset[str] = frozenset({"—", "-", ""})


def load_dag(taskset_path: str) -> DAG:
    """Parse TaskSet_vN.md and build a DAG from declared depends_on fields.

    Pure: reads file once, returns immutable DAG. No side effects.
    Raises MissingContext if taskset_path is absent.
    """
    tasks = parse_taskset(taskset_path)
    deps: dict[str, frozenset[str]] = {}
    for task in tasks:
        if task.depends_on:
            real_deps = frozenset(d for d in task.depends_on if d not in _SENTINEL_DEPS)
            if real_deps:
                deps[task.task_id] = real_deps
    return DAG(deps=deps)
