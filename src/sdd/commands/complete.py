"""_check_deps guard-lite for sdd complete — BC-32-6, I-CMD-IDEM-2.

Lightweight dependency pre-check using the taskset projection. The authoritative
DependencyGuard still runs inside execute_and_project.
"""
from __future__ import annotations

from sdd.core.errors import DependencyNotMet
from sdd.domain.guards.context import DAG


def _check_deps(task_id: str, done_ids: frozenset[str], dag: DAG) -> None:
    """Raise DependencyNotMet if any declared dependency of task_id is not DONE."""
    deps = dag.dependencies(task_id)
    blocking = sorted(dep for dep in deps if dep not in done_ids)
    if blocking:
        raise DependencyNotMet(f"Dependencies not DONE: {', '.join(blocking)}")
