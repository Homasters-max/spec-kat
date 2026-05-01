"""Payload dataclasses, registry, and factory for Command envelope — Spec_v9 §2."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final

from sdd.core.types import Command


@dataclass(frozen=True)
class CompleteTaskPayload:
    task_id:      str
    phase_id:     int
    taskset_path: str
    state_path:   str


@dataclass(frozen=True)
class ValidateTaskPayload:
    task_id:      str | None
    phase_id:     int
    result:       str | None
    check_dod:    bool
    taskset_path: str
    state_path:   str


@dataclass(frozen=True)
class SyncStatePayload:
    phase_id:             int
    taskset_path:         str
    state_path:           str
    current_tasks_total:  int = 0


@dataclass(frozen=True)
class CheckDoDPayload:
    phase_id:   int
    state_path: str


@dataclass(frozen=True)
class ReportErrorPayload:
    error_type:  str
    message:     str
    source:      str
    recoverable: bool


@dataclass(frozen=True)
class ValidateInvariantsPayload:
    phase_id:      int
    task_id:       str | None
    config_path:   str
    cwd:           str
    env_whitelist: tuple[str, ...]


@dataclass(frozen=True)
class ActivatePhasePayload:
    phase_id: int
    actor:    str


@dataclass(frozen=True)
class ActivatePlanPayload:
    plan_version: int
    actor:        str


@dataclass(frozen=True)
class MetricsReportPayload:
    phase_id:    int
    output_path: str | None


@dataclass(frozen=True)
class RecordDecisionPayload:
    decision_id: str
    title:       str
    summary:     str
    phase_id:    int


COMMAND_REGISTRY: Final[dict[str, type[Any]]] = {
    "CompleteTask":       CompleteTaskPayload,
    "ValidateTask":       ValidateTaskPayload,
    "SyncState":          SyncStatePayload,
    "CheckDoD":           CheckDoDPayload,
    "ReportError":        ReportErrorPayload,
    "ValidateInvariants": ValidateInvariantsPayload,
    "ActivatePhase":      ActivatePhasePayload,
    "ActivatePlan":       ActivatePlanPayload,
    "MetricsReport":      MetricsReportPayload,
    "RecordDecision":     RecordDecisionPayload,
}


def build_command(command_type: str, **kwargs: Any) -> Command:
    """Single entry point for Command creation with runtime payload validation.

    Raises:
        KeyError:  unknown command_type (not in COMMAND_REGISTRY)
        TypeError: wrong or missing fields for the payload dataclass
    """
    schema = COMMAND_REGISTRY[command_type]
    payload_obj = schema(**kwargs)
    return Command(
        command_id=str(uuid.uuid4()),
        command_type=command_type,
        payload=asdict(payload_obj),
    )


def _unpack_payload(command_type: str, raw: Mapping[str, Any]) -> Any:
    """Testing/debug utility only — NOT for use in handler runtime path."""
    schema = COMMAND_REGISTRY[command_type]
    return schema(**raw)
