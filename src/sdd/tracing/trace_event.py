from __future__ import annotations

import json
from dataclasses import dataclass, field


VALID_TYPES = frozenset({"GRAPH_CALL", "FILE_READ", "FILE_WRITE", "COMMAND"})


@dataclass
class TraceEvent:
    ts: float
    type: str
    payload: dict = field(default_factory=dict)
    session_id: str = ""
    task_id: str = ""

    def __post_init__(self) -> None:
        if self.type not in VALID_TYPES:
            raise ValueError(f"Invalid TraceEvent.type: {self.type!r}; expected one of {VALID_TYPES}")

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": self.ts,
                "type": self.type,
                "payload": self.payload,
                "session_id": self.session_id,
                "task_id": self.task_id,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "TraceEvent":
        return cls(
            ts=float(data["ts"]),
            type=data["type"],
            payload=data.get("payload", {}),
            session_id=data.get("session_id", ""),
            task_id=data.get("task_id", ""),
        )
