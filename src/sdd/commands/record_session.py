"""record-session — emits SessionDeclaredEvent (I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel, SessionDeclaredEvent


@dataclass(frozen=True)
class RecordSessionCommand:
    command_id: str
    command_type: str
    payload: Any            # dict: {session_type, task_id, phase_id, plan_hash}
    session_type: str
    task_id: str | None
    phase_id: int
    plan_hash: str


class RecordSessionHandler(CommandHandlerBase):
    """Pure handler: returns SessionDeclaredEvent (I-HANDLER-PURE-1)."""

    @error_event_boundary(source=__name__)
    def handle(self, cmd: Any) -> list[DomainEvent]:
        return [
            SessionDeclaredEvent(
                event_type=SessionDeclaredEvent.EVENT_TYPE,
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="runtime",
                caused_by_meta_seq=None,
                session_type=cmd.session_type,
                task_id=cmd.task_id,
                phase_id=cmd.phase_id,
                plan_hash=cmd.plan_hash,
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        ]
