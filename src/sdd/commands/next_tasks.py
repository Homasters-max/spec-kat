from __future__ import annotations

from dataclasses import dataclass

from sdd.commands._base import CommandHandlerBase
from sdd.core.events import DomainEvent
from sdd.domain.guards.context import DAG, load_dag
from sdd.domain.tasks.parser import Task, parse_taskset
from sdd.infra.paths import event_store_file, taskset_file
from sdd.infra.projections import get_current_state

# Single source of truth for task done status (I-CMD-IDEM-1, I-CMD-IDEM-2)
EVENT_TASK_DONE = "DONE"


@dataclass
class NextTasksCommand:
    phase_id: int
    db_path: str | None = None


def next_tasks(cmd: NextTasksCommand) -> list[Task]:
    """Return TODO tasks whose dependencies are all fulfilled.

    Read-only; bypasses Write Kernel (I-READ-ONLY-EXCEPTION-1).
    """
    db = cmd.db_path or str(event_store_file())
    state = get_current_state(db)
    ts_path = str(taskset_file(cmd.phase_id))
    tasks = parse_taskset(ts_path)
    dag: DAG = load_dag(ts_path)
    done_ids: frozenset[str] = frozenset(state.done_ids or [])
    return [
        t for t in tasks
        if t.task_id not in done_ids
        and all(dep in done_ids for dep in dag.deps.get(t.task_id, []))
    ]


class NextTasksHandler(CommandHandlerBase):
    """REGISTRY stub for next-tasks; actual query via next_tasks() (I-READ-ONLY-EXCEPTION-1)."""

    def __init__(self, db_path: str | None = None):
        self._db = db_path

    def handle(self, cmd: NextTasksCommand) -> list[DomainEvent]:  # type: ignore[override]
        return []
