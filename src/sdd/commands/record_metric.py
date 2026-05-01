"""RecordMetricHandler — Spec_v56 §2 BC-56-A2.

Invariants: I-2, I-HANDLER-PURE-1, I-EREG-SCOPE-1
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import InvalidState
from sdd.core.events import DomainEvent, MetricRecorded, classify_event_level

_CONTEXT_MAX_LEN = 140


@dataclass(frozen=True)
class RecordMetricCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    metric_key:   str
    value:        float
    phase_id:     int
    task_id:      str
    context:      str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class RecordMetricHandler(CommandHandlerBase):
    """Emit MetricRecorded event into EventLog.
    Pure handler: returns events only, no I/O (I-HANDLER-PURE-1, BC-56-A2).
    Kernel (execute_command) is responsible for EventStore.append (I-SPEC-EXEC-1).
    """

    def __init__(self, db_path: str = "") -> None:
        super().__init__(db_path)

    @error_event_boundary(source=__name__)
    def handle(self, command: RecordMetricCommand) -> list[DomainEvent]:
        if not command.metric_key or not command.metric_key.strip():
            raise InvalidState("metric_key must be a non-empty string")

        context = command.context[:_CONTEXT_MAX_LEN] if command.context else ""
        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: F841

        return [MetricRecorded(
            event_type="MetricRecorded",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("MetricRecorded"),
            event_source="meta",
            caused_by_meta_seq=None,
            metric_key=command.metric_key,
            value=float(command.value),
            phase_id=command.phase_id,
            task_id=command.task_id,
            context=context,
        )]
