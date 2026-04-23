"""Domain events, EventLevel, and classify_event_level — Spec_v1 §3, §4.3."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar


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
    phase_id: str
    tasks_total: int
    plan_version: int
    actor: str
    timestamp: str


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
class DecisionRecordedEvent(DomainEvent):
    EVENT_TYPE:  ClassVar[str] = "DecisionRecorded"
    decision_id: str
    title:       str
    summary:     str   # ≤ 500 chars
    phase_id:    int
    timestamp:   str


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
    # Hook events — written with explicit level="L2"/"L3" by log_tool.py (I-HOOK-3);
    # registered here for C-1 completeness; reducer places them in _KNOWN_NO_HANDLER.
    "ToolUseStarted",
    "ToolUseCompleted",
    "HookError",
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


# Module-level C-1 check (I-C1-MODE-1: replaces bare import-time assert)
_check_c1_consistency()
