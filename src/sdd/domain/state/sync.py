"""sync_state — Spec_v2 §4.5, §6 — EventLog-authoritative projection (I-ST-4, I-ST-6)."""

from __future__ import annotations

import datetime
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from sdd.core.errors import Inconsistency, MissingState
from sdd.core.events import StateDerivationCompletedEvent
from sdd.domain.state.reducer import SDDState, reduce
from sdd.domain.state.yaml_state import read_state, write_state
from sdd.domain.tasks.parser import parse_taskset
from sdd.infra.event_log import sdd_replay as _default_replay


def sync_state(
    taskset_path: str,
    state_path: str,
    emit: Callable[[StateDerivationCompletedEvent], None],
    replay_fn: Callable[[], list[dict[str, Any]]] = _default_replay,
) -> SDDState:
    """Refresh YAML projection from EventLog + TaskSet (I-ST-6).

    tasks_completed and tasks_done_ids are derived solely from reduce(replay_fn()).
    TaskSet is used only for tasks_total and cross-validation (I-ST-4).
    Raises Inconsistency if TaskSet DONE count diverges from EventLog tasks_completed.
    No direct duckdb.connect calls (I-EL-9).
    """
    # Step 1: EventLog is the sole authoritative source for task counts (I-ST-4, I-ST-6).
    events = replay_fn()
    authoritative = reduce(events)

    # Step 2: TaskSet provides tasks_total and DONE count for cross-validation only.
    tasks = parse_taskset(taskset_path)
    tasks_total = len(tasks)
    taskset_done_count = sum(1 for t in tasks if t.status == "DONE")

    # Step 3: Cross-validate — divergence means manual YAML edit without a TaskImplemented event.
    if taskset_done_count != authoritative.tasks_completed:
        raise Inconsistency(
            f"TaskSet DONE count ({taskset_done_count}) diverges from "
            f"EventLog tasks_completed ({authoritative.tasks_completed})"
        )

    # Step 4: Preserve human-managed fields from existing YAML; fall back to reducer defaults.
    try:
        existing = read_state(state_path)
        phase_status = existing.phase_status
        plan_status = existing.plan_status
    except MissingState:
        phase_status = authoritative.phase_status
        plan_status = authoritative.plan_status

    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_state = SDDState(
        phase_current=authoritative.phase_current,
        plan_version=authoritative.plan_version,
        tasks_version=authoritative.tasks_version,
        tasks_total=tasks_total,
        tasks_completed=authoritative.tasks_completed,
        tasks_done_ids=authoritative.tasks_done_ids,
        invariants_status=authoritative.invariants_status,
        tests_status=authoritative.tests_status,
        last_updated=now,
        schema_version=authoritative.schema_version,
        snapshot_event_id=authoritative.snapshot_event_id,
        phase_status=phase_status,
        plan_status=plan_status,
    )

    # Step 5: Persist projection.
    write_state(new_state, state_path)

    # Step 6: Emit exactly once (I-EL-9 — no duckdb.connect here).
    timestamp_ms = int(time.time() * 1000)
    payload = {
        "phase_id": str(new_state.phase_current),
        "tasks_total": new_state.tasks_total,
        "tasks_completed": new_state.tasks_completed,
        "derived_from": "eventlog",
        "timestamp": now,
    }
    raw = ("StateDerivationCompleted" + json.dumps(payload, sort_keys=True) + str(timestamp_ms)).encode()
    event_id = hashlib.sha256(raw).hexdigest()

    event = StateDerivationCompletedEvent(
        event_type="StateDerivationCompleted",
        event_id=event_id,
        appended_at=timestamp_ms,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=str(new_state.phase_current),
        tasks_total=new_state.tasks_total,
        tasks_completed=new_state.tasks_completed,
        derived_from="eventlog",
        timestamp=now,
    )
    emit(event)

    return new_state
