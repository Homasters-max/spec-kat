"""ShowState — reads State_index.yaml, applies State Guard, renders markdown table.

Invariants: I-CLI-2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from sdd.core.errors import Inconsistency, MissingState, SDDError
from sdd.infra.paths import event_store_file, state_file


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise MissingState(f"State_index.yaml not found: {path}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _guard(s: dict) -> None:
    phase_current = s["phase"]["current"]
    plan_version = s["plan"]["version"]
    tasks_version = s["tasks"]["version"]
    tasks_completed = s["tasks"]["completed"]
    tasks_total = s["tasks"]["total"]
    done_ids = s["tasks"].get("done_ids") or []

    if phase_current != plan_version:
        raise Inconsistency(
            f"phase.current ({phase_current}) != plan.version ({plan_version})"
        )
    if plan_version != tasks_version:
        raise Inconsistency(
            f"plan.version ({plan_version}) != tasks.version ({tasks_version})"
        )
    if tasks_completed > tasks_total:
        raise Inconsistency(
            f"tasks.completed ({tasks_completed}) > tasks.total ({tasks_total})"
        )
    if len(done_ids) != tasks_completed:
        raise Inconsistency(
            f"len(done_ids) ({len(done_ids)}) != tasks.completed ({tasks_completed})"
        )


def _render(s: dict) -> str:
    done_ids = s["tasks"].get("done_ids") or []
    done_str = ", ".join(sorted(str(d) for d in done_ids)) if done_ids else "—"
    rows = [
        ("phase.current", s["phase"]["current"]),
        ("phase.status", s["phase"]["status"]),
        ("plan.version", s["plan"]["version"]),
        ("plan.status", s["plan"]["status"]),
        ("tasks.version", s["tasks"]["version"]),
        ("tasks.total", s["tasks"]["total"]),
        ("tasks.completed", s["tasks"]["completed"]),
        ("done_ids", done_str),
        ("invariants.status", s["invariants"]["status"]),
        ("tests.status", s["tests"]["status"]),
    ]
    lines = ["| Field | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines) + "\n"


def main(args: list[str] | None = None) -> int:
    """Reads State_index.yaml, renders as markdown table to stdout.

    Applies State Guard before rendering.
    Returns 0 on success, 1 on MissingState or Inconsistency.
    """
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(description="Show SDD runtime state")
    parser.add_argument("--state", default=None, help="Path to State_index.yaml")
    parsed = parser.parse_args(args)
    state_path = parsed.state or str(state_file())
    try:
        from sdd.infra.projections import rebuild_state  # noqa: PLC0415
        rebuild_state(str(event_store_file()), state_path)
    except Exception:
        pass  # best-effort rebuild; State Guard will catch staleness below
    try:
        s = _load(state_path)
        _guard(s)
        print(_render(s), end="")
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
