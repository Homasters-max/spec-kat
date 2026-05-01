"""CLI handler: sdd write <file> --session-id <id> — BC-61-E3.

I-TRACE-BEFORE-WRITE: write is only permitted when trace_path is non-empty in session.
I-TRACE-RELEVANCE-1: write_target must appear in session trace_path (BC-62-G2).
"""
from __future__ import annotations

import json
import sys

from sdd.graph_navigation.cli.formatting import emit_error
from sdd.graph_navigation.session_state import GraphSessionState
from sdd.infra.paths import get_sdd_root


def _load_session(session_id: str) -> GraphSessionState | None:
    path = get_sdd_root() / "runtime" / "sessions" / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return GraphSessionState(
        session_id=data["session_id"],
        phase_id=data["phase_id"],
        allowed_files=frozenset(data.get("allowed_files", [])),
        trace_path=data.get("trace_path", []),
    )


def run(file_path: str, session_id: str) -> int:
    """Gate write access to file_path based on session trace. Returns exit code (0 = pass, 1 = violation)."""
    state = _load_session(session_id)
    if state is None:
        emit_error("NOT_FOUND", f"Session not found: {session_id!r}")
        return 1

    if not state.trace_path:
        json.dump(
            {
                "error": "I-TRACE-BEFORE-WRITE",
                "message": "Write gate blocked: trace_path is empty. Run sdd trace before writing.",
                "session_id": session_id,
                "file_path": file_path,
            },
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1

    node_id = file_path if file_path.startswith("FILE:") else f"FILE:{file_path}"
    if node_id not in state.trace_path:
        json.dump(
            {
                "error": "I-TRACE-RELEVANCE-1",
                "message": (
                    f"Write gate blocked: {file_path!r} not found in trace_path. "
                    "Run sdd trace for this target file first."
                ),
                "session_id": session_id,
                "file_path": file_path,
                "trace_path": state.trace_path,
            },
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1

    return 0
