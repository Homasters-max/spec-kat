"""Tests for sdd write CLI handler — I-TRACE-BEFORE-WRITE, I-TRACE-RELEVANCE-1."""
from __future__ import annotations

import json
from unittest.mock import patch

from sdd.graph_navigation.session_state import GraphSessionState


def _make_state(trace_path: list[str]) -> GraphSessionState:
    return GraphSessionState(
        session_id="test-session",
        phase_id=61,
        allowed_files=frozenset(["src/foo.py"]),
        trace_path=trace_path,
    )


class TestWriteGate:
    """I-TRACE-BEFORE-WRITE: write gated on non-empty trace_path."""

    def test_exits_0_when_trace_set(self, capsys) -> None:
        """Exit 0 when session has non-empty trace_path."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state(["FILE:src/foo.py"])
        with patch.object(write_gate, "_load_session", return_value=state):
            result = write_gate.run("src/foo.py", "test-session")
        assert result == 0

    def test_exits_1_when_trace_absent(self, capsys) -> None:
        """Exit 1 + JSON stderr when trace_path is empty (I-TRACE-BEFORE-WRITE violation)."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state([])
        with patch.object(write_gate, "_load_session", return_value=state):
            result = write_gate.run("src/foo.py", "test-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error"] == "I-TRACE-BEFORE-WRITE"
        assert "trace_path" in err["message"]

    def test_exits_1_when_session_not_found(self, capsys) -> None:
        """Exit 1 + JSON stderr when session does not exist."""
        from sdd.graph_navigation.cli import write_gate

        with patch.object(write_gate, "_load_session", return_value=None):
            result = write_gate.run("src/foo.py", "missing-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error_type"] == "NOT_FOUND"


class TestWriteGateTraceRelevance:
    """I-TRACE-RELEVANCE-1 (BC-62-G2): write_target must be in trace_path."""

    def test_exits_1_when_target_not_in_trace_path(self, capsys) -> None:
        """S9: exit 1 + I-TRACE-RELEVANCE-1 when file not in trace_path."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state(["FILE:src/other.py"])
        with patch.object(write_gate, "_load_session", return_value=state):
            result = write_gate.run("src/foo.py", "test-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error"] == "I-TRACE-RELEVANCE-1"
        assert "src/foo.py" in err["message"]

    def test_exits_0_when_target_in_trace_path(self, capsys) -> None:
        """S9 positive: exit 0 when file appears in trace_path as FILE: node."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state(["FILE:src/foo.py", "FILE:src/other.py"])
        with patch.object(write_gate, "_load_session", return_value=state):
            result = write_gate.run("src/foo.py", "test-session")
        assert result == 0

    def test_accepts_file_prefix_in_argument(self, capsys) -> None:
        """Exit 0 when file_path already has FILE: prefix matching trace_path."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state(["FILE:src/foo.py"])
        with patch.object(write_gate, "_load_session", return_value=state):
            result = write_gate.run("FILE:src/foo.py", "test-session")
        assert result == 0

    def test_trace_path_contains_error_details(self, capsys) -> None:
        """Error JSON includes trace_path for diagnostics."""
        from sdd.graph_navigation.cli import write_gate

        state = _make_state(["FILE:src/other.py"])
        with patch.object(write_gate, "_load_session", return_value=state):
            write_gate.run("src/foo.py", "test-session")
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert "trace_path" in err
        assert err["trace_path"] == ["FILE:src/other.py"]
