"""Task dataclass and TaskSet markdown parser — Spec_v2 §4.7, Spec_v3 §4.9."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdd.core.errors import MissingContext
from sdd.domain.tasks.navigation import TaskNavigationSpec


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    status: str
    spec_section: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    checks: tuple[str, ...]
    spec_refs: tuple[str, ...]
    produces_invariants: tuple[str, ...]
    requires_invariants: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    parallel_group: str | None = None
    navigation: TaskNavigationSpec | None = None


_HEADER_RE = re.compile(r"^(?:##\s+)?(T-\d+[a-z]*):\s*(.+)$")  # I-TASK-ID-1: suffix support
_FIELD_RE = re.compile(r"^(\w[\w\s]*):\s*(.*)$")


def _split_csv(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(v.strip() for v in value.split(",") if v.strip())


def parse_taskset(path: str) -> list[Task]:
    """Parse TaskSet_vN.md → list[Task]. Deterministic; raises MissingContext on absent
    file or missing ## T-NNN headers (I-TS-2, I-TS-3)."""
    p = Path(path)
    if not p.exists():
        raise MissingContext(f"TaskSet file not found: {path}")

    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()

    tasks: list[Task] = []
    current_id: str | None = None
    current_title: str | None = None
    current_fields: dict[str, str] = {}
    current_nav: dict[str, Any] = {}
    in_navigation: bool = False

    def _flush() -> None:
        if current_id is None:
            return
        f = current_fields
        raw_pg = f.get("Parallel group", "").strip() or f.get("parallel_group", "").strip()

        nav: TaskNavigationSpec | None = None
        if current_nav:
            raw: dict[str, Any] = dict(current_nav)
            if "resolve_keywords" in raw and isinstance(raw["resolve_keywords"], str):
                raw["resolve_keywords"] = [
                    k.strip() for k in raw["resolve_keywords"].split(",") if k.strip()
                ]
            nav = TaskNavigationSpec.parse(raw)

        tasks.append(Task(
            task_id=current_id,
            title=current_title or "",
            status=f.get("Status", "TODO").strip(),
            spec_section=f.get("Spec ref", "").strip(),
            inputs=_split_csv(f.get("Inputs", "")),
            outputs=_split_csv(f.get("Outputs", "")),
            checks=_split_csv(f.get("Checks", "")),
            spec_refs=_split_csv(f.get("spec_refs", "")),
            produces_invariants=_split_csv(f.get("produces_invariants", "")),
            requires_invariants=_split_csv(f.get("requires_invariants", "")),
            depends_on=_split_csv(f.get("Depends on", "") or f.get("depends_on", "")),
            parallel_group=raw_pg if raw_pg and raw_pg != "—" else None,
            navigation=nav,
        ))

    for line in lines:
        stripped = line.strip()

        m = _HEADER_RE.match(stripped)
        if m:
            _flush()
            current_id = m.group(1)
            current_title = m.group(2).strip()
            current_fields = {}
            current_nav = {}
            in_navigation = False
            continue

        if current_id is not None:
            if in_navigation:
                if line and (line[0] == " " or line[0] == "\t"):
                    fm = _FIELD_RE.match(stripped)
                    if fm:
                        current_nav[fm.group(1).strip()] = fm.group(2).strip()
                    continue
                else:
                    in_navigation = False

            fm = _FIELD_RE.match(stripped)
            if fm:
                key = fm.group(1).strip()
                value = fm.group(2).strip()
                if key == "Navigation":
                    in_navigation = True
                else:
                    current_fields[key] = value

    _flush()

    if not tasks:
        raise MissingContext(f"No ## T-NNN task headers found in: {path}")

    return tasks
