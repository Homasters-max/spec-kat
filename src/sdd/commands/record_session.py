"""record-session — emits SessionDeclaredEvent (I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1).

BC-48-D: dedup_policy wire-up lives here; REGISTRY["record-session"] picks it up.
BC-55-P8: writes current_session.json atomically (I-SESSION-CONTEXT-1).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel, SessionDeclaredEvent
from sdd.domain.session.policy import SessionDedupPolicy
from sdd.infra import paths as _infra_paths
from sdd.transcript.parser import latest_transcript, project_dir_from_cwd

# BC-48-D: canonical dedup policy for record-session; imported by REGISTRY.
DEDUP_POLICY: SessionDedupPolicy = SessionDedupPolicy()


def _current_session_path() -> Path:
    """Path to .sdd/runtime/current_session.json via paths.py (SDD-14)."""
    return Path(str(_infra_paths.state_file())).parent / "current_session.json"


def _resolve_transcript_anchor() -> tuple[str | None, int | None]:
    """Return (transcript_path, transcript_offset) for the active session.

    transcript_offset = file size in bytes at session start (BC-63-P2).
    Returns (None, None) if no transcript file exists (I-TRANSCRIPT-1 is soft).
    """
    try:
        project_dir = project_dir_from_cwd(os.getcwd())
        transcript = latest_transcript(project_dir)
        if transcript is None:
            return None, None
        return str(transcript), transcript.stat().st_size
    except Exception:
        return None, None


def _write_session_meta(
    task_id: str,
    session_id: str,
    transcript_path: str,
    transcript_offset: int | None,
) -> None:
    """Write per-task session anchor to .sdd/reports/<task_id>/session_meta.json."""
    meta_path = _infra_paths.get_sdd_root() / "reports" / task_id / "session_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({
            "session_id": session_id,
            "transcript_path": transcript_path,
            "transcript_offset": transcript_offset,
        }),
        encoding="utf-8",
    )


def _write_current_session(
    session_id: str, session_type: str, phase_id: int, declared_at: str,
    task_id: str | None = None,
) -> None:
    """Atomically write current_session.json (BC-55-P8, I-SESSION-CONTEXT-1, BC-63-P2)."""
    target = _current_session_path()
    transcript_path, transcript_offset = _resolve_transcript_anchor()
    data: dict[str, Any] = {
        "session_id": session_id,
        "session_type": session_type,
        "phase_id": phase_id,
        "declared_at": declared_at,
        "transcript_path": transcript_path,
        "transcript_offset": transcript_offset,
    }
    if session_type == "IMPLEMENT" and task_id is not None:
        data["task_id"] = task_id
    tmp_fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    # Also persist per-task anchor so enrich-trace can find the right transcript
    # even after current_session.json has been overwritten by a later session.
    if session_type == "IMPLEMENT" and task_id is not None and transcript_path:
        _write_session_meta(task_id, session_id, transcript_path, transcript_offset)
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = SessionDeclaredEvent(
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
            timestamp=timestamp,
        )
        _write_current_session(event.event_id, cmd.session_type, cmd.phase_id, timestamp, cmd.task_id)
        return [event]
