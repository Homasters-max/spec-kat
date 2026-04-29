"""SDDState, ReducerDiagnostics, EventReducer — Spec_v2 §4.1, §4.2, §4.3."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import ClassVar

from sdd.core.errors import Inconsistency, UnknownEventType
from sdd.core.events import V1_L1_EVENT_TYPES

# Pre-filter constants (I-REDUCER-1): only runtime L1 events are eligible for dispatch.
_REDUCER_REQUIRES_SOURCE: str = "runtime"
_REDUCER_REQUIRES_LEVEL: str = "L1"


# ---------------------------------------------------------------------------
# FrozenPhaseSnapshot (BC-PC-9)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrozenPhaseSnapshot:
    """Immutable per-phase state snapshot.

    Created by PhaseInitialized. Updated (via replace) by task events matching phase_id.
    Restored (not mutated) by PhaseContextSwitched.

    I-PHASE-SNAPSHOT-3: PhaseInitialized ALWAYS overwrites snapshot for phase_id.
    I-PHASE-SNAPSHOT-1: phases_snapshots MUST contain exactly one entry per phase in phases_known.
    """
    phase_id:          int
    phase_status:      str    # "PLANNED" | "ACTIVE" | "COMPLETE"
    plan_status:       str    # "PLANNED" | "ACTIVE" | "COMPLETE"
    tasks_total:       int
    tasks_completed:   int
    tasks_done_ids:    tuple[str, ...]
    plan_version:      int
    tasks_version:     int
    invariants_status: str    # "UNKNOWN" | "PASS" | "FAIL"
    tests_status:      str    # "UNKNOWN" | "PASS" | "FAIL"
    plan_hash:         str = ""   # BC-31-2: updated by PlanAmended; set by PhaseInitialized
    logical_type:      str | None = None  # BC-41-E: opaque; interpreted only by PhaseOrder
    anchor_phase_id:   int | None = None  # BC-41-E: opaque; interpreted only by PhaseOrder


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

    # --- Multi-phase fields (BC-PC-2, BC-PC-9) ---
    phases_known:     frozenset[int] = field(default_factory=frozenset)
    phases_snapshots: tuple[FrozenPhaseSnapshot, ...] = field(default_factory=tuple)

    state_hash: str = field(default="", init=False)  # computed in __post_init__ (I-ST-8)

    REDUCER_VERSION: ClassVar[int] = 2  # bump: adds phases_known + phases_snapshots

    # Human-managed fields excluded from state_hash (I-ST-11).
    # phases_known + phases_snapshots excluded until yaml_state.py serialises them (T-2405).
    _HUMAN_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "phase_status", "plan_status", "state_hash",
        "phases_known", "phases_snapshots",
    })

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
        phases_known=frozenset(), phases_snapshots=(),
    )


EMPTY_STATE: SDDState = _make_empty_state()


def _check_snapshot_coherence(state: SDDState) -> bool:
    """I-PHASE-SNAPSHOT-2: flat state MUST equal phases_snapshots[phase_current]."""
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    snap = snap_map.get(state.phase_current)
    if snap is None:
        return len(state.phases_snapshots) == 0  # empty state is coherent
    return (
        state.phase_status        == snap.phase_status
        and state.plan_status     == snap.plan_status
        and state.tasks_total     == snap.tasks_total
        and state.tasks_completed == snap.tasks_completed
        and set(state.tasks_done_ids) == set(snap.tasks_done_ids)
        and state.plan_version    == snap.plan_version
        and state.tasks_version   == snap.tasks_version
        and state.invariants_status == snap.invariants_status
        and state.tests_status    == snap.tests_status
    )


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

    # Minimal event schema registry: required payload fields per handled event type.
    # Declared first — _HANDLER_EVENTS and _KNOWN_NO_HANDLER are derived from this. (I-EREG-1)
    _EVENT_SCHEMA: ClassVar[dict[str, frozenset[str]]] = {
        "PhaseInitialized":  frozenset({"phase_id", "tasks_total", "plan_version", "actor", "timestamp"}),
        "TaskImplemented":   frozenset({"task_id", "phase_id"}),
        "TaskValidated":     frozenset({"task_id", "phase_id", "result"}),
        "PhaseActivated":    frozenset({"phase_id", "actor", "timestamp"}),  # I-REDUCER-LEGACY-1: kept for backward compat
        "PlanActivated":     frozenset({"plan_version", "actor", "timestamp"}),
        # Phase 15 handlers (I-PHASE-COMPLETE-1, I-PHASE-STARTED-1, I-PHASE-ORDER-1)
        "PhaseCompleted":         frozenset({"phase_id"}),
        "PhaseStarted":           frozenset({"phase_id", "actor"}),
        "TaskSetDefined":         frozenset({"phase_id", "tasks_total"}),
        # BC-PC-1: navigation event (not lifecycle); handler: restore snapshot for to_phase
        "PhaseContextSwitched":   frozenset({"from_phase", "to_phase", "actor", "timestamp"}),
        # Phase 29 — SessionDeclared: audit-only; logging.debug only, no state mutation (I-SESSION-DECLARED-1)
        "SessionDeclared":        frozenset({"session_type", "task_id", "phase_id", "plan_hash", "timestamp"}),
        # Phase 31 — PlanAmended: updates plan_hash in phases_snapshots[phase_id] (BC-31-2, T-3108)
        "PlanAmended":            frozenset({"phase_id", "new_plan_hash", "reason", "actor"}),
    }

    # I-EREG-1 (Spec_v39 BC-39-2): _KNOWN_NO_HANDLER is derived, not a static literal.
    # Adding a new no-handler event type: update only events.py (V1_L1_EVENT_TYPES).
    # reducer.py does NOT need to change. Verified by test_event_registry_consistency.py.
    _HANDLER_EVENTS: ClassVar[frozenset[str]] = frozenset(_EVENT_SCHEMA)
    _KNOWN_NO_HANDLER: frozenset[str] = V1_L1_EVENT_TYPES - _HANDLER_EVENTS

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

        # Multi-phase accumulators (BC-PC-9, I-PHASE-SNAPSHOT-1..3)
        phases_known_set: set[int] = set(base.phases_known)
        phases_snapshots_map: dict[int, FrozenPhaseSnapshot] = {
            s.phase_id: s for s in base.phases_snapshots
        }

        for event in filtered_events:
            event_type = event.get("event_type", "")

            if event_type in self._KNOWN_NO_HANDLER:
                events_known_no_handler += 1
                continue

            if event_type not in self._EVENT_SCHEMA:
                events_unknown_type += 1
                logging.debug("EventReducer: unknown event_type=%r — skipping (NO-OP)", event_type)
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
                # I-PHASE-AUTH-1: ЕДИНСТВЕННАЯ авторитетная точка для phase_current.
                raw_phase_id = event.get("phase_id", phase_current)
                if isinstance(raw_phase_id, int):
                    phase_current = raw_phase_id
                    phases_known_set.add(raw_phase_id)
                raw_tasks_total = event.get("tasks_total", tasks_total)
                if isinstance(raw_tasks_total, int):
                    tasks_total = raw_tasks_total
                raw_plan_version = event.get("plan_version", plan_version)
                if isinstance(raw_plan_version, int):
                    plan_version = raw_plan_version
                tasks_version = plan_version
                phase_status = "ACTIVE"
                plan_status = "ACTIVE"
                # D: backward-compat reset (I-PHASE-RESET-1) — prevents cross-phase task count bleed
                tasks_completed = 0
                tasks_done_ids_set = set()
                invariants_status = "UNKNOWN"
                tests_status = "UNKNOWN"
                # I-PHASE-SNAPSHOT-3: unconditional overwrite (re-activation resets snapshot)
                raw_plan_hash = event.get("plan_hash", "")
                raw_logical_type = event.get("logical_type")
                raw_anchor_phase_id = event.get("anchor_phase_id")
                if isinstance(raw_phase_id, int):
                    phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                        phase_id=raw_phase_id,
                        phase_status="ACTIVE",
                        plan_status="ACTIVE",
                        tasks_total=tasks_total,
                        tasks_completed=0,
                        tasks_done_ids=(),
                        plan_version=plan_version,
                        tasks_version=tasks_version,
                        invariants_status="UNKNOWN",
                        tests_status="UNKNOWN",
                        plan_hash=str(raw_plan_hash) if isinstance(raw_plan_hash, str) else "",
                        logical_type=str(raw_logical_type) if isinstance(raw_logical_type, str) else None,
                        anchor_phase_id=int(raw_anchor_phase_id) if isinstance(raw_anchor_phase_id, int) else None,
                    )
            elif event_type == "TaskImplemented":
                task_id = event.get("task_id")
                raw_phase_id = event.get("phase_id")
                if isinstance(task_id, str) and task_id not in tasks_done_ids_set:
                    tasks_done_ids_set.add(task_id)
                    tasks_completed += 1
                # Update snapshot for the event's phase_id (key fix for D-5)
                if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
                    snap = phases_snapshots_map[raw_phase_id]
                    if isinstance(task_id, str) and task_id not in snap.tasks_done_ids:
                        new_done = tuple(sorted(set(snap.tasks_done_ids) | {task_id}))
                        phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                            phase_id=raw_phase_id,
                            phase_status=snap.phase_status,
                            plan_status=snap.plan_status,
                            tasks_total=snap.tasks_total,
                            tasks_completed=snap.tasks_completed + 1,
                            tasks_done_ids=new_done,
                            plan_version=snap.plan_version,
                            tasks_version=snap.tasks_version,
                            invariants_status=snap.invariants_status,
                            tests_status=snap.tests_status,
                            plan_hash=snap.plan_hash,
                            logical_type=snap.logical_type,
                            anchor_phase_id=snap.anchor_phase_id,
                        )
            elif event_type == "TaskValidated":
                result = event.get("result", "")
                raw_phase_id = event.get("phase_id")
                if result in ("PASS", "FAIL") and isinstance(result, str):
                    tests_status = result
                    invariants_status = result
                if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
                    snap = phases_snapshots_map[raw_phase_id]
                    if result in ("PASS", "FAIL"):
                        phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                            phase_id=raw_phase_id,
                            phase_status=snap.phase_status,
                            plan_status=snap.plan_status,
                            tasks_total=snap.tasks_total,
                            tasks_completed=snap.tasks_completed,
                            tasks_done_ids=snap.tasks_done_ids,
                            plan_version=snap.plan_version,
                            tasks_version=snap.tasks_version,
                            invariants_status=result,
                            tests_status=result,
                            plan_hash=snap.plan_hash,
                            logical_type=snap.logical_type,
                            anchor_phase_id=snap.anchor_phase_id,
                        )
            elif event_type == "PhaseActivated":
                # I-REDUCER-2: accumulator updated, not base state mutated (Q1)
                phase_status = "ACTIVE"
            elif event_type == "PlanActivated":
                # I-REDUCER-2: accumulator updated, not base state mutated (Q1)
                plan_status = "ACTIVE"
            elif event_type == "PhaseCompleted":
                # I-PHASE-COMPLETE-1: terminal transition; I-PHASE-LIFECYCLE-2: COMPLETE is terminal
                raw_phase_id = event.get("phase_id")
                phase_status = "COMPLETE"
                plan_status = "COMPLETE"
                if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
                    snap = phases_snapshots_map[raw_phase_id]
                    phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                        phase_id=raw_phase_id,
                        phase_status="COMPLETE",
                        plan_status="COMPLETE",
                        tasks_total=snap.tasks_total,
                        tasks_completed=snap.tasks_completed,
                        tasks_done_ids=snap.tasks_done_ids,
                        plan_version=snap.plan_version,
                        tasks_version=snap.tasks_version,
                        invariants_status=snap.invariants_status,
                        tests_status=snap.tests_status,
                        plan_hash=snap.plan_hash,
                        logical_type=snap.logical_type,
                        anchor_phase_id=snap.anchor_phase_id,
                    )
            elif event_type == "PhaseContextSwitched":
                # BC-PC-1, I-PHASE-LIFECYCLE-1: restore snapshot for to_phase;
                # phase_status taken from snapshot — preserves COMPLETE, NOT forced ACTIVE.
                # I-PHASES-KNOWN-1: MUST NOT modify phases_known.
                # I-PHASE-SNAPSHOT-4: missing snapshot → Inconsistency (guard failure or corrupt log).
                raw_to_phase = event.get("to_phase")
                if isinstance(raw_to_phase, int):
                    if raw_to_phase not in phases_snapshots_map:
                        raise Inconsistency(
                            f"I-PHASE-SNAPSHOT-4: PhaseContextSwitched to_phase={raw_to_phase}"
                            f" has no snapshot; phases_known={sorted(phases_known_set)}."
                            f" EventLog may be corrupted."
                        )
                    snap = phases_snapshots_map[raw_to_phase]
                    phase_current      = snap.phase_id
                    phase_status       = snap.phase_status
                    plan_status        = snap.plan_status
                    tasks_total        = snap.tasks_total
                    tasks_completed    = snap.tasks_completed
                    tasks_done_ids_set = set(snap.tasks_done_ids)
                    plan_version       = snap.plan_version
                    tasks_version      = snap.tasks_version
                    invariants_status  = snap.invariants_status
                    tests_status       = snap.tests_status
            elif event_type == "PhaseStarted":
                # DO NOT ADD LOGIC HERE — I-PHASE-AUTH-1, I-PHASE-STARTED-1
                # PhaseStarted is an informational signal only; PhaseInitialized is authoritative.
                raw_phase_id = event.get("phase_id")
                if isinstance(raw_phase_id, int):
                    if raw_phase_id < phase_current:
                        logging.debug(
                            "EventReducer: PhaseStarted phase_id=%r < phase_current=%r"
                            " — regression replay, PhaseInitialized is authoritative"
                            " (I-PHASE-AUTH-1, I-PHASE-STARTED-1)",
                            raw_phase_id, phase_current,
                        )
                    elif raw_phase_id == phase_current:
                        logging.debug(
                            "EventReducer: PhaseStarted phase_id=%r == phase_current — normal replay, skip",
                            raw_phase_id,
                        )
                    else:
                        logging.debug(
                            "EventReducer: PhaseStarted phase_id=%r > phase_current=%r"
                            " — PhaseInitialized will follow and is authoritative (I-PHASE-AUTH-1)",
                            raw_phase_id, phase_current,
                        )
                # NO state mutations in any branch.
            elif event_type == "SessionDeclared":
                # DO NOT ADD LOGIC HERE — I-SESSION-DECLARED-1
                # SessionDeclared is an audit-only causal anchor; no state mutation permitted.
                logging.debug(
                    "EventReducer: SessionDeclared session_type=%r task_id=%r phase_id=%r"
                    " — audit event, no state mutation (I-SESSION-DECLARED-1)",
                    event.get("session_type"),
                    event.get("task_id"),
                    event.get("phase_id"),
                )
                # NO state mutations in any branch.
            elif event_type == "PlanAmended":
                # BC-31-2: update plan_hash in snapshot for event's phase_id.
                # I-PHASE-SNAPSHOT-4: absent snapshot → Inconsistency (corrupted log).
                raw_phase_id = event.get("phase_id")
                new_plan_hash = event.get("new_plan_hash", "")
                if isinstance(raw_phase_id, int):
                    if raw_phase_id not in phases_snapshots_map:
                        raise Inconsistency(
                            f"I-PHASE-SNAPSHOT-4: PlanAmended for phase_id={raw_phase_id}"
                            f" has no snapshot; phases_known={sorted(phases_known_set)}."
                            f" EventLog may be corrupted or event predates PhaseInitialized."
                        )
                    snap = phases_snapshots_map[raw_phase_id]
                    phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                        phase_id=snap.phase_id,
                        phase_status=snap.phase_status,
                        plan_status=snap.plan_status,
                        tasks_total=snap.tasks_total,
                        tasks_completed=snap.tasks_completed,
                        tasks_done_ids=snap.tasks_done_ids,
                        plan_version=snap.plan_version,
                        tasks_version=snap.tasks_version,
                        invariants_status=snap.invariants_status,
                        tests_status=snap.tests_status,
                        plan_hash=str(new_plan_hash) if isinstance(new_plan_hash, str) else "",
                        logical_type=snap.logical_type,
                        anchor_phase_id=snap.anchor_phase_id,
                    )
            elif event_type == "TaskSetDefined":
                # I-PHASE-ORDER-1: A-19 soft ordering guard — flat state only for current phase.
                # Snapshot is always updated for the target phase_id (fixes tasks_total drift).
                raw_phase_id = event.get("phase_id")
                raw_tasks_total = event.get("tasks_total")
                if isinstance(raw_phase_id, int) and raw_phase_id != phase_current:
                    logging.warning(
                        "EventReducer: TaskSetDefined phase_id=%r != phase_current=%r"
                        " — updating snapshot only, not flat state (A-19, I-PHASE-ORDER-1)",
                        raw_phase_id, phase_current,
                    )
                elif isinstance(raw_tasks_total, int):
                    tasks_total = raw_tasks_total
                # Always update snapshot.tasks_total for the target phase (prevents completed > total drift)
                if isinstance(raw_phase_id, int) and isinstance(raw_tasks_total, int):
                    if raw_phase_id in phases_snapshots_map:
                        snap = phases_snapshots_map[raw_phase_id]
                        phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                            phase_id=snap.phase_id,
                            phase_status=snap.phase_status,
                            plan_status=snap.plan_status,
                            tasks_total=raw_tasks_total,
                            tasks_completed=snap.tasks_completed,
                            tasks_done_ids=snap.tasks_done_ids,
                            plan_version=snap.plan_version,
                            tasks_version=snap.tasks_version,
                            invariants_status=snap.invariants_status,
                            tests_status=snap.tests_status,
                            plan_hash=snap.plan_hash,
                            logical_type=snap.logical_type,
                            anchor_phase_id=snap.anchor_phase_id,
                        )

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
            phases_known=frozenset(phases_known_set),
            phases_snapshots=tuple(phases_snapshots_map.values()),
        )
        # I-PHASE-SNAPSHOT-2: coherence check (enabled via SDD_DEBUG_INVARIANTS=1)
        if os.environ.get("SDD_DEBUG_INVARIANTS"):
            assert _check_snapshot_coherence(state), "I-PHASE-SNAPSHOT-2 violated"
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
