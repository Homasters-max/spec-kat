"""BC-56-A1: GraphCallLog — typed API for graph navigation audit.

Invariants: I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from sdd.infra.audit import atomic_write
from sdd.infra.paths import graph_calls_file


@dataclass(frozen=True)
class GraphCallEntry:
    command: str
    args: dict[str, Any]
    session_id: str | None
    ts: str
    result_size: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "args": dict(self.args),
            "session_id": self.session_id,
            "ts": self.ts,
            "result_size": dict(self.result_size),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphCallEntry":
        return cls(
            command=data["command"],
            args=data["args"],
            session_id=data.get("session_id"),
            ts=data["ts"],
            result_size=data["result_size"],
        )


def log_graph_call(entry: GraphCallEntry, log_path: str | None = None) -> None:
    """Append GraphCallEntry to graph_calls.jsonl atomically (I-GRAPH-CALL-LOG-1)."""
    path = log_path if log_path is not None else str(graph_calls_file())
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    line = json.dumps(entry.to_dict(), sort_keys=True)
    new_content = existing + line + "\n" if existing else line + "\n"
    atomic_write(path, new_content)


def query_graph_calls(
    session_id: str | None = None,
    log_path: str | None = None,
) -> list[GraphCallEntry]:
    """Read graph_calls.jsonl, optionally filter by session_id.

    Returns [] if file absent (I-AUDIT-SESSION-1).
    Skips malformed lines silently.
    """
    path = log_path if log_path is not None else str(graph_calls_file())
    if not os.path.exists(path):
        return []
    entries: list[GraphCallEntry] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                entry = GraphCallEntry.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if session_id is not None and entry.session_id != session_id:
                continue
            entries.append(entry)
    return entries
