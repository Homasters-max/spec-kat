"""sdd.guards.task — TaskGuard CLI (I-GRD-5).

Checks that a task exists in the TaskSet and is TODO (not already DONE).
Exit: 0 = allowed, 1 = denied. JSON to stdout.

Invariant I-TASK-ID-1: TaskID := T-<phase_id><task_seq>[suffix?]
  where phase_id is 1..N digits, task_seq is exactly 2 digits, suffix is [a-z]?.
  Examples: T-901 (phase=9, seq=01), T-1001 (phase=10, seq=01), T-1007b (phase=10, seq=07).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_DEFAULT_STATE = ".sdd/runtime/State_index.yaml"

# Matches task ID headers in TaskSet markdown: "T-1007b: ..." or "## T-1007b: ..."
_TASK_HDR = re.compile(r"^(?:##\s+)?(T-\d+[a-z]*)\s*[:.]")
_STATUS_RE = re.compile(r"^\s*Status\s*:\s*(\S+)", re.IGNORECASE)

# I-TASK-ID-1: canonical Task ID grammar.
# (\d+) is greedy and consumes all but the last 2 digit positions (taken by \d{2}).
TASK_ID_RE = re.compile(r"^T-(\d+)(\d{2})([a-z]?)$")


def parse_task_id(task_id: str) -> tuple[int, int, str | None]:
    r"""Parse a Task ID into (phase_id, task_seq, suffix).

    Implements I-TASK-ID-1: T-<phase_id><task_seq>[suffix?]
    The greedy (\d+) captures phase digits; (\d{2}) captures the 2-digit sequence.

    >>> parse_task_id("T-1007b")
    (10, 7, 'b')
    >>> parse_task_id("T-1001")
    (10, 1, None)
    >>> parse_task_id("T-901")
    (9, 1, None)
    """
    m = TASK_ID_RE.match(task_id)
    if not m:
        raise ValueError(f"Invalid TaskID: {task_id!r} — expected T-<phase><2-digit-seq>[a-z?]")
    phase = int(m.group(1))
    seq = int(m.group(2))
    suffix = m.group(3) or None
    return phase, seq, suffix


def _find_task_status(taskset_path: str, task_id: str) -> str | None:
    """Return Status value for task_id in the TaskSet file, or None if not found."""
    try:
        content = Path(taskset_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    found = False
    for line in content.splitlines():
        m = _TASK_HDR.match(line)
        if m:
            if m.group(1) == task_id:
                found = True
            elif found:
                break  # entered next task's header — stop
            continue
        if found:
            s = _STATUS_RE.match(line)
            if s:
                return s.group(1).upper()
    return None


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: task_guard.py check --task T-NNN[s] [--taskset path]")
        return 0

    if args[0] != "check":
        print(json.dumps({"error": f"Unknown subcommand: {args[0]}"}))
        return 1

    task_id = taskset_path = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--task" and i + 1 < len(args):
            task_id = args[i + 1]; i += 2
        elif a == "--taskset" and i + 1 < len(args):
            taskset_path = args[i + 1]; i += 2
        else:
            i += 1

    if not task_id:
        print(json.dumps({"error": "Missing --task"}))
        return 1

    if taskset_path is None:
        try:
            from sdd.domain.state.yaml_state import read_state
            state = read_state(_DEFAULT_STATE)
            taskset_path = f".sdd/tasks/TaskSet_v{state.tasks_version}.md"
        except Exception as e:
            print(json.dumps({"error": f"Cannot resolve taskset path: {e}"}))
            return 1

    status = _find_task_status(taskset_path, task_id)
    if status is None:
        print(json.dumps({
            "allowed": False,
            "reason": f"Task {task_id} not found in {taskset_path}.",
            "task_id": task_id,
            "status": None,
        }))
        return 1

    if status == "DONE":
        print(json.dumps({
            "allowed": False,
            "reason": f"Task {task_id} is already DONE — duplicate execution blocked (I-GRD-5).",
            "task_id": task_id,
            "status": "DONE",
        }))
        return 1

    print(json.dumps({
        "allowed": True,
        "reason": f"Task {task_id} is {status} — allowed.",
        "task_id": task_id,
        "status": status,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
