"""yaml_state — read_state and write_state for State_index.yaml — Spec_v2 §4.4."""

from __future__ import annotations

import datetime
import os
from typing import Any

import yaml

from sdd.core.errors import Inconsistency, MissingState
from sdd.domain.state.reducer import SDDState, compute_state_hash
from sdd.infra.audit import atomic_write

# Header comment block preserved on every write_state call.
_HEADER = """\
# SSOT Runtime State — projection derived from TaskSet + validation results.
#
# Model: TaskSet_vN.md is the source of truth for individual task statuses.
#        This file is a derived aggregate — always re-derivable via Sync State.
#
# Human MAY directly edit:
#   - phase.status  (PLANNED → ACTIVE only)
#   - plan.status   (PLANNED → ACTIVE only)
#
# Editing tasks.*, invariants.*, tests.* manually is INVALID.
# If done, immediately run "Sync State from TaskSet N" to re-align.
#
# LLM sets phase.status / plan.status ACTIVE → COMPLETE only via Check DoD
# (deterministic: all tasks done + invariants PASS + tests PASS).

"""


def read_state(path: str) -> SDDState:
    """Parse State_index.yaml → SDDState.

    Raises MissingState if file absent.
    tasks_done_ids: YAML list → tuple[str, ...].
    state_hash: recomputed from parsed fields and verified against stored value.
    Raises Inconsistency if stored hash != recomputed hash (I-ST-8).
    """
    if not os.path.exists(path):
        raise MissingState(f"State file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Extract stored state_hash from comment line.
    stored_hash: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("# state_hash:"):
            stored_hash = stripped.removeprefix("# state_hash:").strip()
            break

    data: dict[str, Any] = yaml.safe_load(raw) or {}

    phase = data.get("phase", {})
    plan = data.get("plan", {})
    tasks = data.get("tasks", {})
    inv = data.get("invariants", {})
    tests = data.get("tests", {})
    meta = data.get("meta", {})

    done_ids_raw = tasks.get("done_ids") or []
    tasks_done_ids: tuple[str, ...] = tuple(str(t) for t in done_ids_raw)

    state = SDDState(
        phase_current=int(phase.get("current", 0)),
        plan_version=int(plan.get("version", 0)),
        tasks_version=int(tasks.get("version", 0)),
        tasks_total=int(tasks.get("total", 0)),
        tasks_completed=int(tasks.get("completed", 0)),
        tasks_done_ids=tasks_done_ids,
        invariants_status=str(inv.get("status", "UNKNOWN")),
        tests_status=str(tests.get("status", "UNKNOWN")),
        last_updated=str(meta.get("last_updated", "")),
        schema_version=int(meta.get("schema_version", 1)),
        snapshot_event_id=_parse_optional_int(meta.get("snapshot_event_id")),
        phase_status=str(phase.get("status", "PLANNED")),
        plan_status=str(plan.get("status", "PLANNED")),
    )

    # Verify integrity: recompute hash and compare against stored comment (I-ST-8).
    if stored_hash is not None:
        recomputed = compute_state_hash(state)
        if recomputed != stored_hash:
            raise Inconsistency(
                f"state_hash mismatch: stored={stored_hash!r}, recomputed={recomputed!r}"
            )

    return state


def write_state(state: SDDState, path: str) -> None:
    """Serialise SDDState → State_index.yaml via atomic_write (I-PK-5).

    Preserves header comments. tasks_done_ids written as YAML list.
    state_hash written as a comment for human reference: # state_hash: <hex>
    """
    done_ids_list = list(state.tasks_done_ids)

    data: dict[str, Any] = {
        "phase": {
            "current": state.phase_current,
            "status": state.phase_status,
        },
        "plan": {
            "version": state.plan_version,
            "status": state.plan_status,
        },
        "tasks": {
            "version": state.tasks_version,
            "total": state.tasks_total,
            "completed": state.tasks_completed,
            "done_ids": done_ids_list,
        },
        "invariants": {
            "status": state.invariants_status,
        },
        "tests": {
            "status": state.tests_status,
        },
        "meta": {
            "last_updated": state.last_updated or _utcnow_iso(),
            "schema_version": state.schema_version,
            "snapshot_event_id": state.snapshot_event_id,
        },
    }

    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = _HEADER + yaml_body + f"\n# state_hash: {state.state_hash}\n"

    atomic_write(path, content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
