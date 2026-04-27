"""reconcile-bootstrap — EventLog backfill for bootstrap-completed tasks.

Reads bootstrap_manifest.json, emits TaskImplemented + TaskValidated(PASS) events
for each unreconciled entry, marks them reconciled, then rebuilds State projection.

I-BOOTSTRAP-1: EventLog consistency restored here, not in bootstrap-complete.
               Direct EventLog.append is authorized (maintenance path exception).
I-RECONCILE-1: reconcile-bootstrap MUST be idempotent.
I-RECONCILE-2: reconcile-bootstrap MUST only run when PhaseContextSwitch is stable.

PhaseContextSwitch became stable at end of Phase 24 — stub removed.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from sdd.core.events import DomainEvent, TaskImplementedEvent, TaskValidatedEvent, classify_event_level


@dataclass(frozen=True)
class _MetricRecordedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "MetricRecorded"
    metric_id: str
    value: float
    task_id: str | None
    phase_id: int | None


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    from sdd.infra.bootstrap_manifest import list_unreconciled, mark_reconciled
    from sdd.infra.event_log import EventLog
    from sdd.infra.paths import event_store_file, state_file, taskset_file
    from sdd.commands.registry import ProjectionType, project_all

    pending = list_unreconciled()

    if not pending:
        print(json.dumps({"status": "nothing_to_reconcile"}))
        return 0

    db_path = str(event_store_file())
    store = EventLog(db_path)

    reconciled_ids: list[str] = []
    last_task_id: str | None = None
    last_phase: int | None = None

    for entry in sorted(pending, key=lambda e: e["timestamp"]):
        task_id = entry["task_id"]
        phase = int(entry["phase"])
        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        events: list[DomainEvent] = [
            TaskImplementedEvent(
                event_type="TaskImplemented",
                event_id=str(uuid.uuid4()),
                appended_at=now_ms,
                level=classify_event_level("TaskImplemented"),
                event_source="runtime",
                caused_by_meta_seq=None,
                task_id=task_id,
                phase_id=phase,
                timestamp=now_iso,
            ),
            _MetricRecordedEvent(
                event_type="MetricRecorded",
                event_id=str(uuid.uuid4()),
                appended_at=now_ms,
                level=classify_event_level("MetricRecorded"),
                event_source="runtime",
                caused_by_meta_seq=None,
                metric_id="task.lead_time",
                value=0.0,
                task_id=task_id,
                phase_id=phase,
            ),
        ]
        # I-BOOTSTRAP-1: authorized direct EventLog write (maintenance path)
        store.append(events, source="runtime", allow_outside_kernel="bootstrap")
        mark_reconciled(task_id)
        reconciled_ids.append(task_id)
        last_task_id = task_id
        last_phase = phase

    # Emit TaskValidated(PASS) for final task to set invariants_status + tests_status
    if last_task_id is not None and last_phase is not None:
        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        validated_event = TaskValidatedEvent(
            event_type="TaskValidated",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("TaskValidated"),
            event_source="runtime",
            caused_by_meta_seq=None,
            task_id=last_task_id,
            phase_id=last_phase,
            result="PASS",
            timestamp=now_iso,
        )
        store.append([validated_event], source="runtime", allow_outside_kernel="bootstrap")

    # Rebuild State_index + TaskSet projections
    state_path = str(state_file())
    ts_path = str(taskset_file(last_phase)) if last_phase else None
    project_all(ProjectionType.FULL, db_path=db_path, state_path=state_path, taskset_path=ts_path)

    print(json.dumps({
        "status": "done",
        "reconciled": reconciled_ids,
        "validated": last_task_id,
    }))
    return 0
