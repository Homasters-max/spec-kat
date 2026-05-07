"""Unit tests for sdd.tracing.trace_event — TraceEvent dataclass."""
from __future__ import annotations

import json

import pytest

from sdd.tracing.trace_event import VALID_TYPES, TraceEvent


class TestTraceEvent:

    def test_valid_types_set(self) -> None:
        assert VALID_TYPES == frozenset({"GRAPH_CALL", "FILE_READ", "FILE_WRITE", "COMMAND"})

    @pytest.mark.parametrize("event_type", ["GRAPH_CALL", "FILE_READ", "FILE_WRITE", "COMMAND"])
    def test_valid_type_accepted(self, event_type: str) -> None:
        e = TraceEvent(ts=1.0, type=event_type)
        assert e.type == event_type

    def test_invalid_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid TraceEvent.type"):
            TraceEvent(ts=1.0, type="UNKNOWN")

    def test_defaults(self) -> None:
        e = TraceEvent(ts=0.5, type="COMMAND")
        assert e.payload == {}
        assert e.session_id == ""
        assert e.task_id == ""

    def test_to_json_roundtrip(self) -> None:
        e = TraceEvent(ts=3.14, type="FILE_READ", payload={"path": "x.py"}, session_id="s1", task_id="T-001")
        data = json.loads(e.to_json())
        assert data["ts"] == 3.14
        assert data["type"] == "FILE_READ"
        assert data["payload"] == {"path": "x.py"}
        assert data["session_id"] == "s1"
        assert data["task_id"] == "T-001"

    def test_from_dict_full(self) -> None:
        d = {"ts": 2.0, "type": "GRAPH_CALL", "payload": {"cmd": "resolve"}, "session_id": "s2", "task_id": "T-002"}
        e = TraceEvent.from_dict(d)
        assert e.ts == 2.0
        assert e.type == "GRAPH_CALL"
        assert e.payload == {"cmd": "resolve"}
        assert e.session_id == "s2"
        assert e.task_id == "T-002"

    def test_from_dict_minimal(self) -> None:
        e = TraceEvent.from_dict({"ts": "1.5", "type": "COMMAND"})
        assert e.ts == 1.5
        assert e.payload == {}
        assert e.session_id == ""
        assert e.task_id == ""

    def test_to_json_then_from_dict(self) -> None:
        e = TraceEvent(ts=9.9, type="FILE_WRITE", payload={"path": "a/b.py"}, session_id="sx", task_id="T-099")
        restored = TraceEvent.from_dict(json.loads(e.to_json()))
        assert restored.ts == e.ts
        assert restored.type == e.type
        assert restored.payload == e.payload
        assert restored.session_id == e.session_id
        assert restored.task_id == e.task_id

    def test_to_json_no_ascii_escape(self) -> None:
        e = TraceEvent(ts=1.0, type="COMMAND", payload={"msg": "привет"})
        raw = e.to_json()
        assert "привет" in raw
