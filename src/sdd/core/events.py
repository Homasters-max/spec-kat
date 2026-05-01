"""Domain events, EventLevel, and classify_event_level — Spec_v1 §3, §4.3."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from sdd.core.types import Command


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    event_id: str
    appended_at: int           # Unix ms
    level: str                 # "L1" | "L2" | "L3"
    event_source: str          # "meta" | "runtime"
    caused_by_meta_seq: int | None  # I-EL-8


@dataclass(frozen=True)
class ErrorEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "ErrorOccurred"
    error_type: str
    source: str
    recoverable: bool
    retry_count: int
    context: tuple[tuple[str, Any], ...]  # tuple-of-pairs for hashability


@dataclass(frozen=True)
class CommandEvent(DomainEvent):
    command_id: str
    command_type: str


@dataclass(frozen=True)
class NormViolatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "NormViolated"
    actor: str
    action: str
    norm_id: str
    task_id: str | None
    timestamp: str


@dataclass(frozen=True)
class TaskStartGuardRejectedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskStartGuardRejected"
    task_id: str
    missing_invariant: str
    required_ids: tuple[str, ...]
    timestamp: str


@dataclass(frozen=True)
class PhaseInitializedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseInitialized"
    phase_id: int
    tasks_total: int
    plan_version: int
    actor: str
    timestamp: str
    plan_hash: str = ""
    executed_by: str = ""
    logical_type: str | None = None
    anchor_phase_id: int | None = None


@dataclass(frozen=True)
class StateDerivationCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "StateDerivationCompleted"
    phase_id: str
    tasks_total: int
    tasks_completed: int
    derived_from: str
    timestamp: str


@dataclass(frozen=True)
class TaskImplementedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskImplemented"
    task_id:   str
    phase_id:  int
    timestamp: str


@dataclass(frozen=True)
class TaskValidatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskValidated"
    task_id:   str
    phase_id:  int
    result:    str    # "PASS" | "FAIL"
    timestamp: str


@dataclass(frozen=True)
class PhaseCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseCompleted"
    phase_id:    int
    total_tasks: int
    timestamp:   str


@dataclass(frozen=True)
class PhaseActivatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseActivated"
    phase_id:   int
    actor:      str
    timestamp:  str


@dataclass(frozen=True)
class PlanActivatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PlanActivated"
    plan_version: int
    actor:        str
    timestamp:    str


@dataclass(frozen=True)
class PhaseStartedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "PhaseStarted"
    phase_id: int
    actor: str  # "human"


@dataclass(frozen=True)
class TaskSetDefinedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TaskSetDefined"
    phase_id: int
    tasks_total: int


@dataclass(frozen=True)
class DecisionRecordedEvent(DomainEvent):
    EVENT_TYPE:  ClassVar[str] = "DecisionRecorded"
    decision_id: str
    title:       str
    summary:     str   # ≤ 500 chars
    phase_id:    int
    timestamp:   str


@dataclass(frozen=True)
class PhaseContextSwitchedEvent(DomainEvent):
    """Signals an explicit context switch between phases (Spec_v24 §3 BC-PC-1).

    Emitted by sdd switch-phase (T-2407+). Reducer handler added in T-2404+.
    I-PHASE-CONTEXT-1: from_phase MUST differ from to_phase.
    """
    EVENT_TYPE: ClassVar[str] = "PhaseContextSwitched"
    from_phase:  int
    to_phase:    int
    actor:       str
    timestamp:   str


@dataclass(frozen=True)
class SessionDeclaredEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "SessionDeclared"
    event_type: str = "SessionDeclared"
    event_id: str = ""
    appended_at: int = 0
    level: str = "L1"
    event_source: str = "runtime"
    caused_by_meta_seq: int | None = None
    session_type: str = ""  # e.g. "IMPLEMENT", "VALIDATE", "PLAN", etc.
    task_id: str | None = None
    phase_id: int | None = None  # I-SESSION-PHASE-NULL-1: None for DRAFT_SPEC (pre-phase sentinel)
    plan_hash: str = ""     # I-SESSION-PLAN-HASH-1
    timestamp: str = ""


@dataclass(frozen=True)
class SpecApproved(DomainEvent):
    """BC-31-1: emitted by sdd approve-spec. Write Kernel moves spec_draft → specs post-append."""
    event_type: str = "SpecApproved"
    event_id: str = ""
    appended_at: int = 0
    level: str = "L1"
    event_source: str = "runtime"
    caused_by_meta_seq: int | None = None
    phase_id: int = 0
    spec_hash: str = ""   # sha256(Spec_vN.md)[:16]
    actor: str = "human"
    spec_path: str = ""   # relative path in .sdd/specs/


@dataclass(frozen=True)
class PlanAmended(DomainEvent):
    """BC-31-2: emitted by sdd amend-plan. Records post-activation plan edits."""
    event_type: str = "PlanAmended"
    event_id: str = ""
    appended_at: int = 0
    level: str = "L1"
    event_source: str = "runtime"
    caused_by_meta_seq: int | None = None
    phase_id: int = 0
    new_plan_hash: str = ""  # sha256(Plan_vN.md)[:16] after amendment
    reason: str = ""
    actor: str = "human"


@dataclass(frozen=True)
class ToolUseStartedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "ToolUseStarted"
    tool_name:    str
    extra:        tuple[tuple[str, str], ...]  # key-value pairs per CLAUDE.md §0.12 taxonomy
    timestamp_ms: int                          # Unix ms


@dataclass(frozen=True)
class ToolUseCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "ToolUseCompleted"
    tool_name:     str
    output_len:    int
    interrupted:   bool
    error_snippet: str    # "" if no error; first 200 chars otherwise
    timestamp_ms:  int


@dataclass(frozen=True)
class HookErrorEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "HookError"
    hook_name:    str    # "log_tool"
    error_type:   str    # exception class name
    error_msg:    str    # first 300 chars of str(exc)
    timestamp_ms: int


@dataclass(frozen=True)
class TaskDefined(DomainEvent):
    """Phase 32: emitted when a task is defined in the DB schema (I-HANDLER-PURE-1)."""
    EVENT_TYPE: ClassVar[str] = "TaskDefined"
    task_id:   str
    phase_id:  int
    title:     str
    timestamp: str


@dataclass(frozen=True)
class InvariantRegistered(DomainEvent):
    """Phase 32: emitted when an invariant is registered in shared.invariants (I-HANDLER-PURE-1)."""
    EVENT_TYPE: ClassVar[str] = "InvariantRegistered"
    invariant_id: str
    phase_id:     int
    statement:    str
    timestamp:    str


@dataclass(frozen=True)
class MetricRecorded(DomainEvent):
    """Phase 56: domain metric event emitted by sdd record-metric (BC-56-A2)."""
    EVENT_TYPE: ClassVar[str] = "MetricRecorded"
    metric_key: str
    value:      float
    phase_id:   int
    task_id:    str
    context:    str   # free-text reason (≤140 chars)


class EventLevel:
    L1 = "L1"  # domain truth — replay forever
    L2 = "L2"  # operational — 90 days
    L3 = "L3"  # debug — archive after TTL


V1_L1_EVENT_TYPES: frozenset[str] = frozenset({
    "TaskImplemented",
    "TaskValidated",
    "PhaseCompleted",
    "TestRunCompleted",
    "StateDerivationCompleted",
    "ExecutionWrapperAccepted",
    "ExecutionWrapperRejected",
    "SDDEventRejected",
    "DecisionRecorded",
    "SpecApproved",
    "PhaseActivated",
    "PlanActivated",
    "PhaseInitialized",
    "TaskFailed",
    "TaskRetryScheduled",
    "NormViolated",
    "TaskStartGuardRejected",
    # Phase 15 — canonical phase-lifecycle events (I-PHASE-STARTED-1, I-PHASE-COMPLETE-1)
    "PhaseStarted",
    "TaskSetDefined",
    # Hook events — written with explicit level="L2"/"L3" by log_tool.py (I-HOOK-3);
    # registered here for C-1 completeness; reducer places them in _KNOWN_NO_HANDLER.
    "ToolUseStarted",
    "ToolUseCompleted",
    "HookError",
    # Phase 15 — ErrorEvent L2 observability sentinel (I-ERROR-L2-1); reducer ignores via _KNOWN_NO_HANDLER
    "ErrorOccurred",
    # Phase 24 — PhaseContextSwitch (Spec_v24 §3 BC-PC-1; I-PHASE-CONTEXT-1)
    "PhaseContextSwitched",
    # Phase 28 — EventInvalidated: Write Kernel guard rejection sentinel (I-EL-6; C-1)
    "EventInvalidated",
    # Phase 29 — SessionDeclared: session declaration audit event (I-SESSION-DECLARED-1)
    "SessionDeclared",
    # Phase 31 — governance events (BC-31-1, BC-31-2)
    "PlanAmended",
    # Phase 32 — DB schema events (PostgresMigration)
    "TaskDefined",
    "InvariantRegistered",
    # Phase 56 — domain metric event (BC-56-A2)
    "MetricRecorded",
})

V2_L1_EVENT_TYPES: frozenset[str] = V1_L1_EVENT_TYPES  # must be identical (I-EL-6)

_L3_EVENT_TYPES: frozenset[str] = frozenset({
    "BashCommandStarted",
    "BashCommandCompleted",
})

# C-1 registries: _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
_EVENT_SCHEMA: dict[str, Callable[..., Any]] = {}
_KNOWN_NO_HANDLER: frozenset[str] = frozenset(V1_L1_EVENT_TYPES)


def _check_c1_consistency() -> None:
    """I-C1-MODE-1: replaces bare import-time assert.

    Mode from SDD_C1_MODE env var: "strict" (AssertionError) | "warn" (logging.warning).
    Tests set SDD_C1_MODE=strict via conftest fixture or pytest.ini.
    """
    ok = _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
    if ok:
        return
    msg = (
        f"C-1 violated: registered={_KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys())!r}"
        f" != V1_L1_EVENT_TYPES={V1_L1_EVENT_TYPES!r}"
    )
    mode = os.environ.get("SDD_C1_MODE", "warn")  # "strict" | "warn"
    if mode == "strict":
        raise AssertionError(msg)
    logging.warning(msg)


def register_l1_event_type(
    event_type: str,
    handler: Callable[..., Any] | None = None,
) -> None:
    """I-REG-1 / I-REG-STATIC-1: sole registration path for new L1 event types.

    MUST be called only at module import time (module top-level or inside
    __init_subclass__ / decorator evaluation). Dynamic registration after
    EventLog replay has started is FORBIDDEN (I-REG-STATIC-1).

    handler=None  → event_type goes into _KNOWN_NO_HANDLER (reducer ignores)
    handler=fn    → event_type goes into _EVENT_SCHEMA (reducer processes)
    """
    global V1_L1_EVENT_TYPES, V2_L1_EVENT_TYPES, _KNOWN_NO_HANDLER
    if event_type in V1_L1_EVENT_TYPES:
        raise ValueError(f"Duplicate registration: {event_type!r} already in V1_L1_EVENT_TYPES")
    V1_L1_EVENT_TYPES = V1_L1_EVENT_TYPES | frozenset({event_type})
    V2_L1_EVENT_TYPES = V1_L1_EVENT_TYPES  # I-EL-6: must be identical
    if handler is None:
        _KNOWN_NO_HANDLER = _KNOWN_NO_HANDLER | frozenset({event_type})
    else:
        _EVENT_SCHEMA[event_type] = handler
    _check_c1_consistency()


def classify_event_level(event_type: str) -> str:
    """Pure total function (I-PK-4): returns L1 | L2 | L3, no side effects."""
    if event_type in V2_L1_EVENT_TYPES:
        return EventLevel.L1
    if event_type in _L3_EVENT_TYPES:
        return EventLevel.L3
    return EventLevel.L2


def compute_command_id(cmd: Command) -> str:
    """Stable idempotency key — deterministic via dataclasses.asdict, 32 hex chars.
    Invariant under retry and EventLog state (A-7, A-13, A-22, I-IDEM-1).
    Uses dataclasses.asdict for recursive deterministic serialization (not str()) —
    immune to __repr__ variations, new fields, frozenset ordering."""
    payload_dict = (
        dataclasses.asdict(cmd.payload)
        if dataclasses.is_dataclass(cmd.payload)
        else {"raw": repr(cmd.payload)}
    )
    serialized = json.dumps(
        {"cmd": cmd.command_type, "payload": payload_dict},
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]


def compute_trace_id(cmd: Command, head_seq: int | None) -> str:
    """Deterministic correlation ID — 16 hex chars (diagnostic; collisions tolerable).
    head_seq = MAX(seq) before step 1; None when EventStore unavailable (A-9 fallback).
    Fallback hash is less unique but always computable and non-None (I-TRACE-FALLBACK-1)."""
    if head_seq is not None:
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload), "head": head_seq},
            sort_keys=True,
        )
    else:
        payload = json.dumps(
            {"cmd": cmd.command_type, "payload": str(cmd.payload)},
            sort_keys=True,
        )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# Module-level C-1 check (I-C1-MODE-1: replaces bare import-time assert)
_check_c1_consistency()
