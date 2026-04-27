"""ShowState — reads State_index.yaml, applies State Guard, renders markdown table.

Invariants: I-CLI-2, I-SHOW-STATE-1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from sdd.core.errors import Inconsistency, MissingState, SDDError
from sdd.domain.phase_order import PhaseOrder
from sdd.domain.state.reducer import FrozenPhaseSnapshot
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


def _parse_snapshots(s: dict) -> list[FrozenPhaseSnapshot]:
    raw = s.get("phases_snapshots") or []
    result = []
    for entry in raw:
        result.append(FrozenPhaseSnapshot(
            phase_id=entry["phase_id"],
            phase_status=entry["phase_status"],
            plan_status=entry.get("plan_status", "UNKNOWN"),
            tasks_total=entry.get("tasks_total", 0),
            tasks_completed=entry.get("tasks_completed", 0),
            tasks_done_ids=tuple(entry.get("tasks_done_ids") or []),
            plan_version=entry.get("plan_version", 0),
            tasks_version=entry.get("tasks_version", 0),
            invariants_status=entry.get("invariants_status", "UNKNOWN"),
            tests_status=entry.get("tests_status", "UNKNOWN"),
            plan_hash=entry.get("plan_hash", ""),
            logical_type=entry.get("logical_type"),
            anchor_phase_id=entry.get("anchor_phase_id"),
        ))
    return result


def _latest_completed(snapshots: list[FrozenPhaseSnapshot]) -> int | None:
    completed = [s.phase_id for s in snapshots if s.phase_status == "COMPLETE"]
    return max(completed) if completed else None


def _render(s: dict) -> str:
    done_ids = s["tasks"].get("done_ids") or []
    done_str = ", ".join(sorted(str(d) for d in done_ids)) if done_ids else "—"

    snapshots = _parse_snapshots(s)
    latest_completed = _latest_completed(snapshots)
    latest_completed_str = str(latest_completed) if latest_completed is not None else "—"

    rows = [
        ("phase.current", s["phase"]["current"]),
        ("phase.status", s["phase"]["status"]),
        ("phase.latest_completed", latest_completed_str),
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

    if snapshots:
        sorted_entries = PhaseOrder.sort(snapshots)
        snap_map = {s.phase_id: s for s in snapshots}
        lines += ["", "| Phase | Type | Status |", "|---|---|---|"]
        for entry in sorted_entries:
            snap = snap_map[entry.phase_id]
            lt = entry.logical_type if entry.logical_type is not None else "—"
            lines.append(f"| {entry.phase_id} | {lt} | {snap.phase_status} |")

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
