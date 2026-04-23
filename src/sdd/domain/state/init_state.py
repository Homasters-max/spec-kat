"""init_state — initialise fresh State_index.yaml for a new phase — Spec_v2 §4.6."""

from __future__ import annotations

import datetime
import os
import uuid
import warnings
from collections.abc import Callable

from sdd.core.errors import InvalidState
from sdd.core.events import (
    DomainEvent,
    PhaseInitializedEvent,
    StateDerivationCompletedEvent,
)
from sdd.domain.state.reducer import SDDState
from sdd.domain.state.yaml_state import write_state
from sdd.domain.tasks.parser import parse_taskset


def init_state(
    phase_id: int,
    taskset_path: str,
    state_path: str,
    emit: Callable[[DomainEvent], None],
) -> SDDState:
    """Create fresh State_index.yaml for a new phase (§K.1 Init State N).

    Precondition: state_path MUST NOT exist — raises InvalidState if present.
    Does not call sdd_replay: EventLog is empty for a new phase (I-EL-9).

    Emits PhaseInitializedEvent then StateDerivationCompletedEvent(derived_from="initial")
    exactly once each.
    """
    if os.path.exists(state_path):
        raise InvalidState(f"State file already exists: {state_path}")

    tasks = parse_taskset(taskset_path)
    tasks_total = len(tasks)
    done_ids = tuple(sorted(t.task_id for t in tasks if t.status == "DONE"))
    tasks_completed = len(done_ids)

    now = _utcnow_iso()
    now_ms = _utcnow_ms()

    state = SDDState(
        phase_current=phase_id,
        plan_version=phase_id,
        tasks_version=phase_id,
        tasks_total=tasks_total,
        tasks_completed=tasks_completed,
        tasks_done_ids=done_ids,
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated=now,
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )

    warnings.warn(
        "Direct YAML write in init_state is deprecated; use EventLog replay path.",
        DeprecationWarning,
        stacklevel=2,
    )
    write_state(state, state_path)

    emit(PhaseInitializedEvent(
        event_type=PhaseInitializedEvent.EVENT_TYPE,
        event_id=str(uuid.uuid4()),
        appended_at=now_ms,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=str(phase_id),
        tasks_total=tasks_total,
        plan_version=phase_id,
        actor="llm",
        timestamp=now,
    ))

    emit(StateDerivationCompletedEvent(
        event_type=StateDerivationCompletedEvent.EVENT_TYPE,
        event_id=str(uuid.uuid4()),
        appended_at=now_ms,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        phase_id=str(phase_id),
        tasks_total=tasks_total,
        tasks_completed=tasks_completed,
        derived_from="initial",
        timestamp=now,
    ))

    return state


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utcnow_ms() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)
