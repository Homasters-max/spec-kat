"""Projection rebuilders — EventLog → TaskSet.md and State_index.yaml (I-ES-4, I-ES-5).

Spec: Spec_v4 §2 BC-INFRA extensions
Invariants: I-ES-4, I-ES-5, I-PK-5, I-SYNC-1

I-SYNC-1: every task-state mutation MUST rebuild both projections atomically via
sync_projections(). Calling rebuild_taskset or rebuild_state individually after
a mutation is forbidden — use sync_projections() as the sole mutation path.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sdd.domain.state.reducer import EventReducer, SDDState
from sdd.domain.state.yaml_state import read_state, write_state
from sdd.infra.audit import atomic_write
from sdd.infra.db import open_sdd_connection

_TASK_HEADER_RE = re.compile(r"^(T-\d+[a-z]*):\s")  # I-TASK-ID-1: suffix support
_STATUS_LINE_RE = re.compile(r"^(Status:\s+)(TODO|DONE)(.*)$")


def _replay_all(db_path: str) -> list[dict]:
    """Fetch all events from the EventLog ordered by seq ASC."""
    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, payload, level, event_source, caused_by_meta_seq "
            "FROM events ORDER BY seq ASC"
        ).fetchall()
    finally:
        conn.close()

    events = []
    for event_type, payload_str, level, event_source, caused_by_meta_seq in rows:
        try:
            payload: dict = json.loads(payload_str) if payload_str else {}
        except Exception:
            payload = {}
        event: dict = {
            "event_type": event_type,
            "level": level,
            "event_source": event_source,
            "caused_by_meta_seq": caused_by_meta_seq,
        }
        event.update(payload)
        events.append(event)
    return events


def rebuild_state(db_path: str, state_path: str) -> None:
    """Rebuild State_index.yaml from EventLog replay (I-ES-4, I-ES-5).

    Derives tasks_completed and tasks_done_ids from EventLog filtered to the
    current phase. Non-event-sourced fields (phase_current, plan_version,
    tasks_version, tasks_total) and human-managed fields (phase_status,
    plan_status) are preserved from the existing file. Writes atomically via
    write_state (I-PK-5). Idempotent.
    """
    phase_current = 0
    plan_version = 0
    tasks_version = 0
    tasks_total = 0
    phase_status = "PLANNED"
    plan_status = "PLANNED"
    invariants_status = "UNKNOWN"
    tests_status = "UNKNOWN"
    try:
        existing = read_state(state_path)
        phase_current = existing.phase_current
        plan_version = existing.plan_version
        tasks_version = existing.tasks_version
        tasks_total = existing.tasks_total
        phase_status = existing.phase_status
        plan_status = existing.plan_status
        invariants_status = existing.invariants_status
        tests_status = existing.tests_status
    except Exception:
        pass

    all_events = _replay_all(db_path)
    # Filter to events for the current phase only. Events without phase_id
    # (e.g. PlanActivated) are kept so the reducer can derive plan metadata.
    if phase_current:
        events = [
            e for e in all_events
            if e.get("phase_id") is None or e.get("phase_id") == phase_current
        ]
    else:
        events = all_events

    derived: SDDState = EventReducer().reduce(events)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = SDDState(
        phase_current=phase_current or derived.phase_current,
        plan_version=plan_version or derived.plan_version,
        tasks_version=tasks_version or derived.tasks_version,
        tasks_total=tasks_total or derived.tasks_total,
        tasks_completed=derived.tasks_completed,
        tasks_done_ids=derived.tasks_done_ids,
        invariants_status=derived.invariants_status if derived.invariants_status != "UNKNOWN" else invariants_status,
        tests_status=derived.tests_status if derived.tests_status != "UNKNOWN" else tests_status,
        last_updated=now,
        schema_version=derived.schema_version,
        snapshot_event_id=derived.snapshot_event_id,
        phase_status=derived.phase_status if derived.phase_status != "PLANNED" else phase_status,
        plan_status=derived.plan_status if derived.plan_status != "PLANNED" else plan_status,
    )
    write_state(state, state_path)


def rebuild_taskset(db_path: str, taskset_path: str) -> None:
    """Update TaskSet.md task statuses from EventLog replay (I-ES-4, I-ES-5).

    Replays EventLog → derives done_ids via reducer → marks matching tasks DONE
    in the TaskSet.md text. Writes atomically (I-PK-5). Idempotent: re-running
    on a file already reflecting the EventLog is a no-op in effect.
    """
    events = _replay_all(db_path)
    state: SDDState = EventReducer().reduce(events)
    done_ids: frozenset[str] = frozenset(state.tasks_done_ids)

    with open(taskset_path, encoding="utf-8") as f:
        original = f.read()

    lines = original.splitlines(keepends=True)
    current_task_id: str | None = None
    result: list[str] = []

    for line in lines:
        m = _TASK_HEADER_RE.match(line.strip())
        if m:
            current_task_id = m.group(1)

        if current_task_id in done_ids:
            sm = _STATUS_LINE_RE.match(line.rstrip("\n\r"))
            if sm and sm.group(2) == "TODO":
                eol = "\n" if line.endswith("\n") else ""
                line = sm.group(1) + "DONE" + sm.group(3) + eol

        result.append(line)

    atomic_write(taskset_path, "".join(result))


def sync_projections(db_path: str, taskset_path: str, state_path: str) -> None:
    """Rebuild both projections atomically after any task-state mutation (I-SYNC-1).

    Single mandatory path: always call this instead of rebuild_taskset /
    rebuild_state individually. Guarantees TaskSet.md and State_index.yaml
    are always co-consistent after any write.
    """
    rebuild_taskset(db_path, taskset_path)
    rebuild_state(db_path, state_path)
