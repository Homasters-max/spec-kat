"""sdd.guards.phase — PhaseGuard CLI (migrated to src/ in Phase 8).

Invariants: PG-1..PG-3 (CLAUDE.md §R.4).
I-GUARD-REG-2: guards resolve tasks with suffixes (e.g. T-1007b) correctly.
Exit: 0 = allowed, 1 = rejected. JSON to stdout.
"""
from __future__ import annotations

import json
import re
import sys

from sdd.infra import paths as _paths

# Extracts a full Task ID (with optional suffix) from a command string.
_CMD_TASK_RE = re.compile(r"(T-\d+[a-z]*)")


def _extract_phase_from_task(task_id: str) -> int | None:
    """Extract phase_id from a Task ID (I-TASK-ID-1). Returns None for invalid IDs."""
    from sdd.guards.task import parse_task_id
    try:
        phase, _, _ = parse_task_id(task_id)
        return phase
    except ValueError:
        return None


def _extract_task_id(command: str) -> str | None:
    m = _CMD_TASK_RE.search(command)
    return m.group(1) if m else None


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print('Usage: phase_guard.py check --command "Implement T-NNN[s]" [--state path]')
        return 0

    if args[0] != "check":
        print(json.dumps({"error": f"Unknown subcommand: {args[0]}"}))
        return 1

    command = state_path = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--command" and i + 1 < len(args):
            command = args[i + 1]; i += 2
        elif a == "--state" and i + 1 < len(args):
            state_path = args[i + 1]; i += 2
        else:
            i += 1

    if not command:
        print(json.dumps({"error": "Missing --command"}))
        return 1

    sp = state_path or str(_paths.state_file())
    try:
        from sdd.domain.state.yaml_state import read_state
        state = read_state(sp)
    except FileNotFoundError as e:
        print(json.dumps({
            "allowed": False,
            "reason": f"MissingState — {e}",
            "violated_guard": "SG-0",
            "violated_norm": "NORM-PHASE-001",
            "sdd_event_rejected": None,
        }, indent=2))
        return 1

    phase_current = state.phase_current
    phase_status = state.phase_status
    plan_version = state.plan_version
    tasks_version = state.tasks_version

    def _reject(guard: str, reason: str) -> int:
        print(json.dumps({
            "allowed": False,
            "reason": reason,
            "violated_guard": guard,
            "violated_norm": "NORM-PHASE-001",
            "sdd_event_rejected": None,
        }, indent=2))
        return 1

    # PG-1: task must belong to the current active phase.
    # Two complementary checks (belt + suspenders):
    #   1. parse_task_id() — canonical ID grammar (I-TASK-ID-1, I-GUARD-REG-2)
    #   2. TaskSet membership — existence in the current phase's declared tasks
    task_id = _extract_task_id(command)
    if task_id is not None:
        phase_from_task = _extract_phase_from_task(task_id)
        if phase_from_task is not None and phase_current != phase_from_task:
            return _reject(
                "PG-1",
                f"PG-1 violated: task {task_id} belongs to phase {phase_from_task}, "
                f"but current phase is {phase_current}.",
            )

        from sdd.guards.task import _find_task_status
        taskset_path = str(_paths.taskset_file(tasks_version))
        if _find_task_status(taskset_path, task_id) is None:
            return _reject(
                "PG-1",
                f"PG-1 violated: task {task_id} not found in current phase {phase_current} "
                f"TaskSet ({taskset_path}).",
            )

    if not (phase_current == plan_version == tasks_version):
        return _reject(
            "PG-2",
            f"PG-2 violated: version mismatch — "
            f"phase.current={phase_current}, plan.version={plan_version}, "
            f"tasks.version={tasks_version}.",
        )

    if phase_status != "ACTIVE":
        return _reject(
            "PG-3",
            f"PG-3 violated: phase.status={phase_status!r}, expected ACTIVE. "
            f"Human must set phase.status=ACTIVE before execution.",
        )

    print(json.dumps({
        "allowed": True,
        "reason": f"PhaseGuard passed: phase={phase_current} ACTIVE, versions aligned.",
        "violated_guard": None,
        "violated_norm": None,
        "sdd_event_rejected": None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
