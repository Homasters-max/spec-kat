"""bootstrap-complete — bootstrap execution mode for circular dependency resolution.

I-BOOTSTRAP-1: Does NOT write to EventLog.
I-BOOTSTRAP-2: Tasks marked here are PRE-RESOLVED; sdd complete skips event emission.

Bootstrap guards (BG-1..BG-3):
  BG-1: task_id must exist in TaskSet_vN.md (N derived from task_id)
  BG-2: task.status must be TODO (not already DONE)
  BG-3: all task.depends_on entries must be DONE in TaskSet

Usage: sdd bootstrap-complete T-NNN
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


_TASK_HEADER_RE = re.compile(r"^(T-\d+[a-z]*):\s")
_STATUS_LINE_RE = re.compile(r"^(Status:\s+)(TODO|DONE)(.*)$")


def _mark_done_in_file(taskset_path: str, task_id: str) -> None:
    """Write task_id TODO→DONE in TaskSet file. Atomic via temp-file replace."""
    p = Path(taskset_path)
    original = p.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    current: str | None = None
    result = []
    for line in lines:
        m = _TASK_HEADER_RE.match(line.strip())
        if m:
            current = m.group(1)
        if current == task_id:
            sm = _STATUS_LINE_RE.match(line.rstrip("\n\r"))
            if sm and sm.group(2) == "TODO":
                eol = "\n" if line.endswith("\n") else ""
                line = sm.group(1) + "DONE" + sm.group(3) + eol
        result.append(line)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("".join(result), encoding="utf-8")
    tmp.replace(p)


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print("Usage: sdd bootstrap-complete T-NNN")
        return 0

    task_id = args[0]

    from sdd.guards.task import parse_task_id
    from sdd.infra.bootstrap_manifest import add_entry, contains
    from sdd.infra.paths import taskset_file
    from sdd.domain.tasks.parser import parse_taskset

    # BG-0: parse phase from task_id
    try:
        phase, _, _ = parse_task_id(task_id)
    except ValueError as exc:
        print(json.dumps({"error_type": "InvalidTaskId", "message": str(exc)}), file=sys.stderr)
        return 1

    # Idempotent: already in manifest
    if contains(task_id):
        print(json.dumps({"status": "noop", "task_id": task_id, "reason": "already in bootstrap manifest"}))
        return 0

    ts_path = taskset_file(phase)
    if not ts_path.exists():
        print(json.dumps({
            "error_type": "MissingTaskSet",
            "message": f"TaskSet_v{phase}.md not found",
        }), file=sys.stderr)
        return 1

    tasks = parse_taskset(str(ts_path))
    task = next((t for t in tasks if t.task_id == task_id), None)

    # BG-1: task must exist
    if task is None:
        print(json.dumps({
            "error_type": "TaskNotFound",
            "message": f"Task {task_id} not found in TaskSet_v{phase}.md",
            "violated_guard": "BG-1",
        }), file=sys.stderr)
        return 1

    # BG-2: task must be TODO (idempotent if already DONE)
    if task.status == "DONE":
        print(json.dumps({"status": "noop", "task_id": task_id, "reason": "already DONE in TaskSet"}))
        return 0

    # BG-3: dependencies must be DONE
    task_map = {t.task_id: t for t in tasks}
    for dep_id in (task.depends_on or ()):
        dep = task_map.get(dep_id)
        if dep is None or dep.status != "DONE":
            print(json.dumps({
                "error_type": "DependencyNotDone",
                "message": f"Dependency {dep_id} is not DONE — bootstrap guard BG-3 violated",
                "violated_guard": "BG-3",
                "dependency": dep_id,
            }), file=sys.stderr)
            return 1

    # Action: update TaskSet file (no EventLog write — I-BOOTSTRAP-1)
    _mark_done_in_file(str(ts_path), task_id)

    # Record in manifest for reconcile-bootstrap pass
    add_entry(task_id, phase)

    print(json.dumps({"status": "done", "task_id": task_id, "mode": "bootstrap", "phase": phase}))
    return 0
