"""SDDState, ReducerDiagnostics, EventReducer — Spec_v2 §4.1, §4.2, §4.3."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import ClassVar

from sdd.core.errors import UnknownEventType
from sdd.core.events import V1_L1_EVENT_TYPES

# Pre-filter constants (I-REDUCER-1): only runtime L1 events are eligible for dispatch.
_REDUCER_REQUIRES_SOURCE: str = "runtime"
_REDUCER_REQUIRES_LEVEL: str = "L1"


# ---------------------------------------------------------------------------
# SDDState
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SDDState:
    # --- Derived fields: authoritative source = EventLog via reduce() ---
    phase_current: int
    plan_version: int
    tasks_version: int
    tasks_total: int
    tasks_completed: int
    tasks_done_ids: tuple[str, ...]
    invariants_status: str          # "UNKNOWN" | "PASS" | "FAIL"
    tests_status: str               # "UNKNOWN" | "PASS" | "FAIL"
    last_updated: str               # ISO8601 UTC
    schema_version: int             # = 1
    snapshot_event_id: int | None   # seq of last event folded into base (None = full replay)

    # --- Human-managed fields: YAML-only; NOT included in state_hash (I-ST-11) ---
    phase_status: str               # "PLANNED" | "ACTIVE" | "COMPLETE"
    plan_status: str                # "PLANNED" | "ACTIVE" | "COMPLETE"

    state_hash: str = field(default="", init=False)  # computed in __post_init__ (I-ST-8)

    REDUCER_VERSION: ClassVar[int] = 1

    # Human-managed fields excluded from state_hash (I-ST-11).
    _HUMAN_FIELDS: ClassVar[frozenset[str]] = frozenset({"phase_status", "plan_status", "state_hash"})

    def __post_init__(self) -> None:
        data = {k: v for k, v in asdict(self).items() if k not in self._HUMAN_FIELDS}
        data["reducer_version"] = self.REDUCER_VERSION
        h = hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()
        object.__setattr__(self, "state_hash", h)


def _make_empty_state() -> SDDState:
    return SDDState(
        phase_current=0, plan_version=0, tasks_version=0,
        tasks_total=0, tasks_completed=0, tasks_done_ids=(),
        invariants_status="UNKNOWN", tests_status="UNKNOWN",
        last_updated="", schema_version=1, snapshot_event_id=None,
        phase_status="PLANNED", plan_status="PLANNED",
    )


EMPTY_STATE: SDDState = _make_empty_state()


def compute_state_hash(state: SDDState) -> str:
    """Re-derive hash from derived fields only (for verification in read_state). Pure function."""
    data = {k: v for k, v in asdict(state).items() if k not in SDDState._HUMAN_FIELDS}
    data["reducer_version"] = SDDState.REDUCER_VERSION
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# ReducerDiagnostics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReducerDiagnostics:
    events_total: int
    events_filtered_source: int     # skipped: event_source != "runtime"
    events_filtered_level: int      # skipped: level != "L1"
    events_processed: int           # actually handled by a registered handler
    events_known_no_handler: int    # L1 runtime events with no registered handler
    events_unknown_type: int        # I-ST-7: unrecognised event_type


# ---------------------------------------------------------------------------
# EventReducer
# ---------------------------------------------------------------------------

class EventReducer:
    """Pure stateless reducer. No I/O, no side effects (I-ST-2).
    All public methods are pure functions of their arguments.
    """

    # Known L1 types intentionally without a handler (not unknown — I-ST-10).
    _KNOWN_NO_HANDLER: frozenset[str] = frozenset({
        "StateDerivationCompleted",
        "DecisionRecorded", "SpecApproved", "SDDEventRejected",
        "ExecutionWrapperAccepted", "ExecutionWrapperRejected",
        "TestRunCompleted", "TaskRetryScheduled", "TaskFailed",
        "NormViolated", "TaskStartGuardRejected",
        "PhaseCompleted",
        # Hook events registered for C-1 compliance (T-611); written as L2/L3 meta events.
        "ToolUseStarted", "ToolUseCompleted", "HookError",
    })

    # Minimal event schema registry: required payload fields per handled event type.
    _EVENT_SCHEMA: ClassVar[dict[str, frozenset[str]]] = {
        "PhaseInitialized":  frozenset({"phase_id", "tasks_total", "plan_version", "actor", "timestamp"}),
        "TaskImplemented":   frozenset({"task_id", "phase_id"}),
        "TaskValidated":     frozenset({"task_id", "phase_id", "result"}),
        "PhaseActivated":    frozenset({"phase_id", "actor", "timestamp"}),
        "PlanActivated":     frozenset({"plan_version", "actor", "timestamp"}),
    }

    # Completeness identity (I-ST-10): every V1_L1_EVENT_TYPE must be classified.
    # Verified at class definition time so any gap is caught at import.
    assert _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES, (
        "I-ST-10 violation: not all V1_L1_EVENT_TYPES are classified in EventReducer. "
        f"Missing: {V1_L1_EVENT_TYPES - (_KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()))}"
    )

    def _pre_filter(
        self,
        events: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], int, int]:
        """Pre-filter to runtime L1 events before dispatch (I-REDUCER-1).
        Returns (filtered_events, source_skipped, level_skipped).
        """
        filtered: list[dict[str, object]] = []
        source_skipped = 0
        level_skipped = 0
        for event in events:
            if event.get("event_source") != _REDUCER_REQUIRES_SOURCE:
                source_skipped += 1
            elif event.get("level") != _REDUCER_REQUIRES_LEVEL:
                level_skipped += 1
            else:
                filtered.append(event)
        return filtered, source_skipped, level_skipped

    def reduce(
        self,
        events: list[dict[str, object]],
        strict_mode: bool = False,
    ) -> SDDState:
        """Fold events onto EMPTY_STATE.
        Filter: event_source == "runtime" AND level == "L1" (I-EL-3).
        Precondition: events MUST be sorted by seq ASC (I-EL-13).
        Unknown event_type: counted in diagnostics; raises UnknownEventType if strict_mode=True (I-ST-7).
        """
        state, _ = self._fold(EMPTY_STATE, events, strict_mode=strict_mode)
        return state

    def reduce_incremental(
        self,
        base: SDDState,
        events: list[dict[str, object]],
        strict_mode: bool = False,
    ) -> SDDState:
        """Apply new events on top of an existing base state (optimisation path).
        Same filter rules as reduce() (I-EL-3).
        Satisfies I-ST-9: reduce(all) == reduce_incremental(EMPTY_STATE, all).
        """
        state, _ = self._fold(base, events, strict_mode=strict_mode)
        return state

    def reduce_with_diagnostics(
        self,
        events: list[dict[str, object]],
        strict_mode: bool = False,
    ) -> tuple[SDDState, ReducerDiagnostics]:
        """Same as reduce() but also returns ReducerDiagnostics."""
        return self._fold(EMPTY_STATE, events, strict_mode=strict_mode)

    def _fold(
        self,
        base: SDDState,
        events: list[dict[str, object]],
        strict_mode: bool,
    ) -> tuple[SDDState, ReducerDiagnostics]:
        events_total = len(events)
        # I-EL-3: pre-filter to runtime L1 events before any dispatch.
        filtered_events, events_filtered_source, events_filtered_level = self._pre_filter(events)
        events_processed = 0
        events_known_no_handler = 0
        events_unknown_type = 0

        # Mutable accumulators for derived fields.
        phase_current = base.phase_current
        plan_version = base.plan_version
        tasks_version = base.tasks_version
        tasks_total = base.tasks_total
        tasks_completed = base.tasks_completed
        tasks_done_ids_set: set[str] = set(base.tasks_done_ids)
        invariants_status = base.invariants_status
        tests_status = base.tests_status
        last_updated = base.last_updated
        schema_version = base.schema_version
        snapshot_event_id = base.snapshot_event_id
        phase_status = base.phase_status
        plan_status = base.plan_status

        for event in filtered_events:
            event_type = event.get("event_type", "")

            if event_type in self._KNOWN_NO_HANDLER:
                events_known_no_handler += 1
                continue

            if event_type not in self._EVENT_SCHEMA:
                events_unknown_type += 1
                logging.warning("EventReducer: unknown event_type=%r — skipping (NO-OP)", event_type)
                if strict_mode:
                    raise UnknownEventType(event_type)
                continue

            # Schema validation fires before handler dispatch (§4.3).
            if strict_mode:
                required = self._EVENT_SCHEMA[event_type]
                missing = required - event.keys()
                if missing:
                    raise UnknownEventType(
                        f"Missing required fields {missing} for event_type {event_type!r}"
                    )

            # Handler dispatch.
            events_processed += 1
            if event_type == "PhaseInitialized":
                raw_phase_id = event.get("phase_id", phase_current)
                if isinstance(raw_phase_id, int):
                    phase_current = raw_phase_id
                raw_tasks_total = event.get("tasks_total", tasks_total)
                if isinstance(raw_tasks_total, int):
                    tasks_total = raw_tasks_total
                raw_plan_version = event.get("plan_version", plan_version)
                if isinstance(raw_plan_version, int):
                    plan_version = raw_plan_version
                tasks_version = plan_version
                phase_status = "ACTIVE"
            elif event_type == "TaskImplemented":
                task_id = event.get("task_id")
                if isinstance(task_id, str) and task_id not in tasks_done_ids_set:
                    tasks_done_ids_set.add(task_id)
                    tasks_completed += 1
            elif event_type == "TaskValidated":
                result = event.get("result", "")
                if result in ("PASS", "FAIL") and isinstance(result, str):
                    tests_status = result
                    invariants_status = result
            elif event_type == "PhaseActivated":
                # I-REDUCER-2: accumulator updated, not base state mutated (Q1)
                phase_status = "ACTIVE"
            elif event_type == "PlanActivated":
                # I-REDUCER-2: accumulator updated, not base state mutated (Q1)
                plan_status = "ACTIVE"

        state = SDDState(
            phase_current=phase_current,
            plan_version=plan_version,
            tasks_version=tasks_version,
            tasks_total=tasks_total,
            tasks_completed=tasks_completed,
            tasks_done_ids=tuple(sorted(tasks_done_ids_set)),
            invariants_status=invariants_status,
            tests_status=tests_status,
            last_updated=last_updated,
            schema_version=schema_version,
            snapshot_event_id=snapshot_event_id,
            phase_status=phase_status,
            plan_status=plan_status,
        )
        diagnostics = ReducerDiagnostics(
            events_total=events_total,
            events_filtered_source=events_filtered_source,
            events_filtered_level=events_filtered_level,
            events_processed=events_processed,
            events_known_no_handler=events_known_no_handler,
            events_unknown_type=events_unknown_type,
        )
        return state, diagnostics


# ---------------------------------------------------------------------------
# Module-level convenience functions (preferred API)
# ---------------------------------------------------------------------------

def reduce(events: list[dict[str, object]], strict_mode: bool = False) -> SDDState:
    return EventReducer().reduce(events, strict_mode=strict_mode)


def reduce_with_diagnostics(
    events: list[dict[str, object]], strict_mode: bool = False
) -> tuple[SDDState, ReducerDiagnostics]:
    return EventReducer().reduce_with_diagnostics(events, strict_mode=strict_mode)
