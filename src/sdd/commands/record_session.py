"""record-session — emits SessionDeclaredEvent (I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1).

BC-48-D: dedup_policy wire-up lives here; REGISTRY["record-session"] picks it up.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel, SessionDeclaredEvent
from sdd.domain.session.policy import SessionDedupPolicy

# BC-48-D: canonical dedup policy for record-session; imported by REGISTRY.
DEDUP_POLICY: SessionDedupPolicy = SessionDedupPolicy()


def _utc_date_str() -> str:
    """Return today's UTC date as YYYY-MM-DD. Extracted for testability."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def stable_session_command_id(session_type: str, phase_id: int) -> str:
    """Deterministic command_id scoped to session_type + phase_id + UTC day.

    Same inputs on the same UTC day → same 32-hex hash.
    Different UTC day → different hash.
    Supports I-SESSION-DEDUP-1: same-day deduplication via exists_command.
    """
    raw = f"record-session:{session_type}:{phase_id}:{_utc_date_str()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


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
