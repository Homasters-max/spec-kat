"""show_task — sdd show-task T-NNN [--phase N].

Reads TaskSet_vN.md and renders a structured markdown summary for a single task.

Invariants: I-CLI-READ-1, I-CLI-READ-2, I-CLI-SCHEMA-1, I-CLI-SCHEMA-2,
            I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-CLI-SSOT-1, I-CLI-SSOT-2,
            I-SCOPE-CLI-1, I-SCOPE-CLI-2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sdd.infra.paths import state_file, taskset_file

# Matches task-header lines: "T-1410: ..." or "## T-1410: ..."
_TASK_HDR = re.compile(r"^(?:##\s+)?(T-\d+[a-z]*)\s*[:.]")
_FIELD_RE = re.compile(r"^\s*(\w[\w\s]*?)\s*:\s*(.*)", re.IGNORECASE)


def _json_error(error_type: str, message: str, exit_code: int) -> None:
    """Write I-CLI-API-1 structured error to stderr."""
    json.dump({"error_type": error_type, "message": message, "exit_code": exit_code},
              sys.stderr)
    sys.stderr.write("\n")


def _detect_phase() -> int:
    """Auto-detect phase from State_index.yaml (tasks.version)."""
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(Path(state_file()).read_text(encoding="utf-8"))
        return int(data["tasks"]["version"])
    except Exception as exc:
        raise RuntimeError(f"Cannot detect phase from State_index.yaml: {exc}") from exc


def _parse_taskset(content: str, task_id: str) -> dict[str, object] | None:
    """Extract field dict for task_id from TaskSet markdown, or None if not found.

    Navigation block sub-fields are stored under key "_navigation" as a nested dict.
    """
    lines = content.splitlines()
    in_task = False
    in_navigation = False
    fields: dict[str, object] = {}
    nav_fields: dict[str, str] = {}

    def _flush_nav() -> None:
        if nav_fields:
            fields["_navigation"] = dict(nav_fields)

    for line in lines:
        m = _TASK_HDR.match(line)
        if m:
            if m.group(1) == task_id:
                in_task = True
                fields = {}
                nav_fields = {}
                in_navigation = False
            elif in_task:
                _flush_nav()
                break
            continue

        if line.strip() == "---":
            if in_task:
                _flush_nav()
                break
            continue

        if in_task:
            if in_navigation:
                if line and line[0] in (" ", "\t"):
                    fm = _FIELD_RE.match(line)
                    if fm:
                        nav_fields[fm.group(1).strip().lower()] = fm.group(2).strip()
                    continue
                else:
                    _flush_nav()
                    in_navigation = False

            fm = _FIELD_RE.match(line)
            if fm:
                key = fm.group(1).strip().lower()
                if key == "navigation":
                    in_navigation = True
                    nav_fields = {}
                else:
                    fields[key] = fm.group(2).strip()

    if in_task:
        _flush_nav()

    return fields if (in_task and fields) else None


def _bullets(raw: str) -> list[str]:
    """Split a comma-separated field value into a list of stripped items."""
    if not raw or raw.startswith("(none") or raw == "—":
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _render(task_id: str, fields: dict[str, object]) -> str:
    status = str(fields.get("status", "UNKNOWN"))
    spec_ref = str(fields.get("spec ref", "")).strip()
    inputs = _bullets(str(fields.get("inputs", "")))
    outputs = _bullets(str(fields.get("outputs", "")))
    invariants = _bullets(str(fields.get("invariants", "")))
    spec_refs = str(fields.get("spec_refs", "")).strip()
    produces = str(fields.get("produces_invariants", "")).strip()
    requires = str(fields.get("requires_invariants", "")).strip()
    acceptance = str(fields.get("acceptance", "")).strip()
    depends_on = str(fields.get("depends on", "")).strip()
    nav = fields.get("_navigation")

    lines: list[str] = []
    lines.append(f"## Task: {task_id}")
    lines.append(f"Status: {status}")
    if spec_ref:
        lines.append(f"Spec ref: {spec_ref}")
    if depends_on and depends_on != "—":
        lines.append(f"Depends on: {depends_on}")
    lines.append("")

    lines.append("### Inputs")
    if inputs:
        lines.extend(f"- {p}" for p in inputs)
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("### Outputs")
    if outputs:
        lines.extend(f"- {p}" for p in outputs)
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("### Invariants Covered")
    if invariants:
        lines.extend(f"- {inv}" for inv in invariants)
    else:
        lines.append("- (none)")
    if produces:
        lines.append(f"Produces: {produces}")
    if requires:
        lines.append(f"Requires: {requires}")
    if spec_refs:
        lines.append(f"Spec refs: {spec_refs}")
    lines.append("")

    lines.append("### Acceptance Criteria")
    lines.append(acceptance)
    lines.append("")

    if nav and isinstance(nav, dict):
        lines.append("### Navigation")
        for k, v in nav.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    return "\n".join(lines)


def show_task(task_id: str, phase: int | None = None) -> int:
    """Render task definition to stdout. Returns exit code."""
    try:
        resolved_phase = phase if phase is not None else _detect_phase()
    except Exception as exc:
        _json_error("MissingState", str(exc), 1)
        return 1

    ts_path = taskset_file(resolved_phase)
    if not ts_path.exists():
        _json_error(
            "TaskNotFound",
            f"TaskSet not found for phase {resolved_phase}: {ts_path}",
            1,
        )
        return 1

    try:
        content = ts_path.read_text(encoding="utf-8")
    except OSError as exc:
        _json_error("TaskNotFound", f"Cannot read TaskSet: {exc}", 1)
        return 1

    fields = _parse_taskset(content, task_id)
    if fields is None:
        _json_error(
            "TaskNotFound",
            f"Task {task_id} not found in TaskSet_v{resolved_phase}.md",
            1,
        )
        return 1

    print(_render(task_id, fields), end="")
    return 0


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="sdd show-task",
                                     description="Show task definition from TaskSet")
    parser.add_argument("task_id", help="Task ID, e.g. T-1410")
    parser.add_argument("--phase", type=int, default=None,
                        help="Phase number (auto-detected from State_index.yaml if omitted)")
    try:
        parsed = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1

    try:
        return show_task(parsed.task_id, parsed.phase)
    except Exception as exc:
        _json_error("InternalError", str(exc), 2)
        return 2
