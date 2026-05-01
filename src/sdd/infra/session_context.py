"""BC-INFRA session context — get/set current SDD session state.

Invariants: I-SESSION-CONTEXT-1
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sdd.infra.audit import atomic_write
from sdd.infra.paths import get_sdd_root


def _default_session_file() -> str:
    return str(get_sdd_root() / "runtime" / "current_session.json")


def get_current_session_id(session_file: str | None = None) -> str | None:
    """Return session_id from current_session.json, or None if absent or malformed."""
    path = session_file if session_file is not None else _default_session_file()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("session_id")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def set_current_session(
    session_id: str,
    session_type: str,
    phase_id: int,
    session_file: str | None = None,
) -> None:
    """Write current session context atomically.

    Schema: {session_id, session_type, phase_id, declared_at} (ISO 8601).
    """
    path = session_file if session_file is not None else _default_session_file()
    payload: dict[str, Any] = {
        "session_id": session_id,
        "session_type": session_type,
        "phase_id": phase_id,
        "declared_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    atomic_write(path, json.dumps(payload, indent=2))
