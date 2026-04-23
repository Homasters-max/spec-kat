"""RecordDecisionHandler — Spec_v4 §4.10.

Invariants: I-CMD-1, I-CMD-9
"""
from __future__ import annotations

import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import InvalidState
from sdd.core.events import DecisionRecordedEvent, DomainEvent, classify_event_level
from sdd.infra.event_store import EventStore

_DECISION_ID_RE = re.compile(r'^D-\d+$')
_SUMMARY_MAX_LEN = 500


@dataclass(frozen=True)
class RecordDecisionCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    decision_id:  str
    title:        str
    summary:      str
    phase_id:     int

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class _DecisionRecordedWithCmd(DecisionRecordedEvent):
    command_id: str


class RecordDecisionHandler(CommandHandlerBase):
    """Persist a design decision in the EventLog as DecisionRecordedEvent.
    Used to record D-* entries from sdd_plan.md into the immutable event log.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: RecordDecisionCommand) -> list[DomainEvent]:
        if self._check_idempotent(command):
            return []

        if not _DECISION_ID_RE.match(command.decision_id):
            raise InvalidState(
                f"decision_id {command.decision_id!r} must match D-<number> pattern"
            )

        if len(command.summary) > _SUMMARY_MAX_LEN:
            raise InvalidState(
                f"summary length {len(command.summary)} exceeds maximum {_SUMMARY_MAX_LEN} chars"
            )

        now_ms = int(time.time() * 1000)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        event = _DecisionRecordedWithCmd(
            event_type="DecisionRecorded",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("DecisionRecorded"),
            event_source="meta",
            caused_by_meta_seq=None,
            decision_id=command.decision_id,
            title=command.title,
            summary=command.summary,
            phase_id=command.phase_id,
            timestamp=now_iso,
            command_id=command.command_id,
        )

        EventStore(self._db_path).append([event], source=__name__)
        return [event]
