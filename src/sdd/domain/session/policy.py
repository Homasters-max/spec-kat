"""BC-48-A: Session deduplication policy (pure domain, no IO).

Invariants: I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1,
            I-SESSION-INVALIDATION-1, I-GUARD-PURE-1
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sdd.infra.projector import SessionsView


@dataclass(frozen=True)
class SessionDedupPolicy:
    """Pure domain policy: decide whether to emit SessionDeclared.

    Stateless frozen dataclass — no IO, no DB access.
    Consumes a pre-built SessionsView snapshot built by execute_command Step 0.
    """

    def should_emit(self, sessions_view: SessionsView | None, cmd: Any) -> bool:
        """Return True iff a new SessionDeclared event should be emitted.

        False iff sessions_view contains a non-invalidated session with
        matching (session_type, phase_id).
        """
        if sessions_view is None:
            return True
        session_type = getattr(cmd, "session_type", None)
        phase_id = getattr(cmd, "phase_id", None)
        if session_type is None:
            return True
        return sessions_view.get_last(cast(str, session_type), phase_id) is None
