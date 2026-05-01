"""_check_deps guard-lite for sdd complete — BC-32-6, I-CMD-IDEM-2.

Lightweight dependency pre-check using the taskset projection. The authoritative
DependencyGuard still runs inside execute_and_project.

_run_trace_summary: BC-62-L5 — informational trace-summary step before complete.
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


def _run_trace_summary(task_id: str) -> None:
    """Run enrich-trace then trace-summary as informational pre-steps for sdd complete.

    enrich-trace runs first (I-TRACE-CMD-1, BC-63-P3); trace-summary follows (BC-62-L5).
    Neither raises — complete is never blocked (I-BEHAV-NONBLOCK-1).
    """
    try:
        from sdd.commands.enrich_trace import main as _enrich_main
        _enrich_main([task_id])
    except Exception:
        pass
    try:
        from sdd.commands.trace_summary import main as _trace_main
        _trace_main([task_id])
    except Exception:
        pass
