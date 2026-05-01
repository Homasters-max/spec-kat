"""Tests for sdd graph-guard CLI handler — I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from sdd.graph_navigation.session_state import GraphSessionState


def _make_state(
    allowed_files: list[str] | None = None,
    trace_path: list[str] | None = None,
    traversal_depth_max: int = 2,
    fallback_used: bool = False,
    depth_justification: str = "",
    write_targets: list[str] | None = None,
    explain_nodes: list[str] | None = None,
) -> GraphSessionState:
    return GraphSessionState(
        session_id="test-session",
        phase_id=61,
        allowed_files=frozenset(["src/foo.py"] if allowed_files is None else allowed_files),
        trace_path=["FILE:src/foo.py"] if trace_path is None else trace_path,
        traversal_depth_max=traversal_depth_max,
        fallback_used=fallback_used,
        depth_justification=depth_justification,
        write_targets=frozenset(write_targets or []),
        explain_nodes=frozenset(explain_nodes or []),
    )


class TestCheckProtocol:
    """Unit tests for _check_protocol logic (I-GRAPH-PROTOCOL-1)."""

    def test_valid_state_no_violations(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(["src/foo.py"], ["FILE:src/foo.py"])
        assert _check_protocol(state) == []

    def test_empty_allowed_files_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state([], ["FILE:src/foo.py"])
        violations = _check_protocol(state)
        assert len(violations) == 1
        assert "allowed_files empty" in violations[0]

    def test_empty_trace_path_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(["src/foo.py"], [])
        violations = _check_protocol(state)
        assert len(violations) == 1
        assert "trace_path empty" in violations[0]

    def test_both_empty_two_violations(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state([], [])
        violations = _check_protocol(state)
        assert len(violations) == 2


class TestRunGraphGuard:
    """Integration-style tests for graph_guard.run()."""

    def test_exits_0_when_session_valid(self, capsys) -> None:
        """Exit 0 when session satisfies I-GRAPH-PROTOCOL-1."""
        from sdd.graph_navigation.cli import graph_guard

        state = _make_state(["src/foo.py"], ["FILE:src/foo.py"])
        with patch.object(graph_guard, "_load_session", return_value=state):
            result = graph_guard.run("test-session")
        assert result == 0

    def test_exits_1_when_session_not_found(self, capsys) -> None:
        """Exit 1 + NOT_FOUND JSON when session file missing."""
        from sdd.graph_navigation.cli import graph_guard

        with patch.object(graph_guard, "_load_session", return_value=None):
            result = graph_guard.run("missing-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.out or captured.err)
        assert err["error_type"] == "NOT_FOUND"

    def test_exits_1_on_protocol_violation(self, capsys) -> None:
        """Exit 1 + GRAPH_PROTOCOL_VIOLATION when I-GRAPH-PROTOCOL-1 violated."""
        from sdd.graph_navigation.cli import graph_guard

        state = _make_state([], [])
        with patch.object(graph_guard, "_load_session", return_value=state):
            result = graph_guard.run("bad-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error"] == "GRAPH_PROTOCOL_VIOLATION"
        assert len(err["violations"]) == 2

    def test_exits_1_on_partial_violation_trace_missing(self, capsys) -> None:
        """Exit 1 when only trace_path is empty."""
        from sdd.graph_navigation.cli import graph_guard

        state = _make_state(["src/foo.py"], [])
        with patch.object(graph_guard, "_load_session", return_value=state):
            result = graph_guard.run("partial-session")
        assert result == 1
        captured = capsys.readouterr()
        err = json.loads(captured.err)
        assert err["error"] == "GRAPH_PROTOCOL_VIOLATION"
        assert len(err["violations"]) == 1


class TestLoadSessionFromDisk:
    """Tests that exercise the actual file-loading path in _load_session."""

    def test_load_session_from_real_file(self, tmp_path) -> None:
        """_load_session reads a real JSON file and returns GraphSessionState."""
        from sdd.graph_navigation.cli.graph_guard import _load_session

        session_data = {
            "session_id": "test-real",
            "phase_id": 61,
            "allowed_files": ["src/foo.py"],
            "trace_path": ["FILE:src/foo.py"],
        }
        sessions_dir = tmp_path / "runtime" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "test-real.json").write_text(json.dumps(session_data))

        with patch("sdd.graph_navigation.cli.graph_guard.get_sdd_root", return_value=tmp_path):
            state = _load_session("test-real")

        assert state is not None
        assert state.session_id == "test-real"
        assert "src/foo.py" in state.allowed_files

    def test_load_session_missing_file_returns_none(self, tmp_path) -> None:
        """_load_session returns None when session file does not exist."""
        from sdd.graph_navigation.cli.graph_guard import _load_session

        with patch("sdd.graph_navigation.cli.graph_guard.get_sdd_root", return_value=tmp_path):
            state = _load_session("nonexistent-session")

        assert state is None


class TestFallbackStrictInvariant:
    """Tests for I-FALLBACK-STRICT-1: fallback_used + allowed_files empty → exit 1."""

    def test_fallback_with_empty_files_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(allowed_files=[], fallback_used=True)
        violations = _check_protocol(state)
        assert any("I-FALLBACK-STRICT-1" in v for v in violations)

    def test_fallback_with_files_resolved_no_fallback_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(allowed_files=["src/foo.py"], fallback_used=True)
        violations = _check_protocol(state)
        assert not any("I-FALLBACK-STRICT-1" in v for v in violations)

    def test_no_fallback_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(fallback_used=False)
        violations = _check_protocol(state)
        assert not any("I-FALLBACK-STRICT-1" in v for v in violations)


class TestGraphDepthInvariant:
    """Tests for I-GRAPH-DEPTH-1: depth_max < 2 AND no justification → exit 1."""

    def test_depth_1_no_justification_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(traversal_depth_max=1, depth_justification="")
        violations = _check_protocol(state)
        assert any("I-GRAPH-DEPTH-1" in v for v in violations)

    def test_depth_0_no_justification_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(traversal_depth_max=0, depth_justification="")
        violations = _check_protocol(state)
        assert any("I-GRAPH-DEPTH-1" in v for v in violations)

    def test_depth_2_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(traversal_depth_max=2)
        violations = _check_protocol(state)
        assert not any("I-GRAPH-DEPTH-1" in v for v in violations)

    def test_depth_1_with_justification_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(traversal_depth_max=1, depth_justification="shallow traversal sufficient for this task")
        violations = _check_protocol(state)
        assert not any("I-GRAPH-DEPTH-1" in v for v in violations)

    def test_depth_3_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(traversal_depth_max=3)
        violations = _check_protocol(state)
        assert not any("I-GRAPH-DEPTH-1" in v for v in violations)


class TestGraphCoverageReq:
    """Tests for I-GRAPH-COVERAGE-REQ-1 (S12): write_target ∉ trace_path ∪ explain_nodes → exit 1."""

    def test_write_target_in_trace_path_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/foo.py"],
            write_targets=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert not any("I-GRAPH-COVERAGE-REQ-1" in v for v in violations)

    def test_write_target_in_explain_nodes_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/bar.py"],
            explain_nodes=["FILE:src/foo.py"],
            write_targets=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert not any("I-GRAPH-COVERAGE-REQ-1" in v for v in violations)

    def test_write_target_missing_from_both_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/bar.py"],
            explain_nodes=["FILE:src/bar.py"],
            write_targets=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert any("I-GRAPH-COVERAGE-REQ-1" in v and "src/foo.py" in v for v in violations)

    def test_no_write_targets_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(write_targets=[])
        violations = _check_protocol(state)
        assert not any("I-GRAPH-COVERAGE-REQ-1" in v for v in violations)

    def test_multiple_write_targets_partial_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py", "src/baz.py"],
            trace_path=["FILE:src/foo.py"],
            write_targets=["FILE:src/foo.py", "FILE:src/baz.py"],
        )
        violations = _check_protocol(state)
        coverage_violations = [v for v in violations if "I-GRAPH-COVERAGE-REQ-1" in v]
        assert len(coverage_violations) == 1
        assert "src/baz.py" in coverage_violations[0]


class TestExplainUsage:
    """Tests for I-EXPLAIN-USAGE-1 (S13): explain_node ∉ trace_path ∪ write_targets → exit 1."""

    def test_explain_node_in_trace_path_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/foo.py"],
            explain_nodes=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert not any("I-EXPLAIN-USAGE-1" in v for v in violations)

    def test_explain_node_in_write_targets_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/bar.py"],
            explain_nodes=["FILE:src/foo.py"],
            write_targets=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert not any("I-EXPLAIN-USAGE-1" in v for v in violations)

    def test_explain_node_missing_from_both_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/bar.py"],
            write_targets=["FILE:src/bar.py"],
            explain_nodes=["FILE:src/foo.py"],
        )
        violations = _check_protocol(state)
        assert any("I-EXPLAIN-USAGE-1" in v and "src/foo.py" in v for v in violations)

    def test_no_explain_nodes_no_violation(self) -> None:
        from sdd.graph_navigation.cli.graph_guard import _check_protocol

        state = _make_state(explain_nodes=[])
        violations = _check_protocol(state)
        assert not any("I-EXPLAIN-USAGE-1" in v for v in violations)


class TestS14PositiveScenario:
    """S14: all new invariants satisfied simultaneously → exit 0."""

    def test_all_invariants_satisfied_exit_0(self, capsys) -> None:
        from sdd.graph_navigation.cli import graph_guard

        state = _make_state(
            allowed_files=["src/foo.py"],
            trace_path=["FILE:src/foo.py"],
            traversal_depth_max=2,
            explain_nodes=["FILE:src/foo.py"],
            write_targets=["FILE:src/foo.py"],
        )
        with patch.object(graph_guard, "_load_session", return_value=state):
            result = graph_guard.run("s14-session")
        assert result == 0

    def test_write_in_explain_explain_in_trace_exit_0(self, capsys) -> None:
        from sdd.graph_navigation.cli import graph_guard

        state = _make_state(
            allowed_files=["src/foo.py", "src/bar.py"],
            trace_path=["FILE:src/foo.py", "FILE:src/bar.py"],
            traversal_depth_max=2,
            explain_nodes=["FILE:src/foo.py"],
            write_targets=["FILE:src/bar.py"],
        )
        with patch.object(graph_guard, "_load_session", return_value=state):
            result = graph_guard.run("s14-mixed-session")
        assert result == 0


class TestGraphSessionStateMethods:
    """Tests for is_allowed() and with_trace() methods on GraphSessionState."""

    def test_is_allowed_true(self) -> None:
        state = GraphSessionState(
            session_id="s",
            phase_id=61,
            allowed_files=frozenset(["src/foo.py"]),
            trace_path=[],
        )
        assert state.is_allowed("src/foo.py") is True

    def test_is_allowed_false(self) -> None:
        state = GraphSessionState(
            session_id="s",
            phase_id=61,
            allowed_files=frozenset(["src/foo.py"]),
            trace_path=[],
        )
        assert state.is_allowed("src/bar.py") is False

    def test_with_trace_appends_node(self) -> None:
        state = GraphSessionState(
            session_id="s",
            phase_id=61,
            allowed_files=frozenset(["src/foo.py"]),
            trace_path=["FILE:src/foo.py"],
        )
        new_state = state.with_trace("FILE:src/bar.py")
        assert "FILE:src/bar.py" in new_state.trace_path
        assert len(new_state.trace_path) == 2
        assert new_state.session_id == state.session_id
