"""S4: Hidden dependency — trace before write, explicit acknowledgment.

BC-61-T4 (S4): positive scenario verifying that after tracing a hidden dependency
(eval_deep.py → eval_fixtures.py via imports edge), the write gate permits writing
the hidden dep file. Without trace, the write gate must block.
"""
from __future__ import annotations

import contextlib
import io
import json
from unittest.mock import patch

import pytest

from sdd.eval.eval_fixtures import EvalFixtureTarget, EvalHiddenDep
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


class TestS4HiddenDependency:
    """S4: trace reveals hidden dep → write permitted only after explicit trace."""

    def test_s4_fixture_encodes_trace_path(self) -> None:
        """S4 fixture: hidden dep is reachable via trace_path from source to dep."""
        dep = EvalHiddenDep.default()
        assert dep.source_node == "FILE:src/sdd/eval/eval_deep.py"
        assert dep.hidden_dep_node == "FILE:src/sdd/eval/eval_fixtures.py"
        assert dep.hidden_dep_node in dep.trace_path

    def test_s4_write_gate_exits_0_after_trace(self, capsys) -> None:
        """I-TRACE-BEFORE-WRITE: write permitted after tracing hidden dep."""
        from sdd.graph_navigation.cli import write_gate

        dep = EvalHiddenDep.default()
        state = GraphSessionState(
            session_id="eval-s4-hidden-dep",
            phase_id=61,
            allowed_files=frozenset(dep.trace_path),  # trace revealed the allowed scope
            trace_path=list(dep.trace_path),
        )
        hidden_dep_path = dep.hidden_dep_node.replace("FILE:", "")

        with patch.object(write_gate, "_load_session", return_value=state):
            rc = write_gate.run(hidden_dep_path, "eval-s4-hidden-dep")

        captured = capsys.readouterr()
        result = ScenarioResult(
            scenario_id="S4",
            status="PASS" if rc == 0 else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", f"S4 write gate failed after trace: {captured.err!r}"
        assert result.exit_code == 0

    def test_s4_write_blocked_before_trace(self, capsys) -> None:
        """S4 contrast: without trace, write gate blocks the hidden dep write."""
        from sdd.graph_navigation.cli import write_gate

        dep = EvalHiddenDep.default()
        state_no_trace = GraphSessionState(
            session_id="eval-s4-no-trace",
            phase_id=61,
            allowed_files=frozenset(dep.trace_path),
            trace_path=[],  # trace not performed — hidden dep unacknowledged
        )
        hidden_dep_path = dep.hidden_dep_node.replace("FILE:", "")

        with patch.object(write_gate, "_load_session", return_value=state_no_trace):
            rc = write_gate.run(hidden_dep_path, "eval-s4-no-trace")

        assert rc == 1, f"S4: write must be blocked when trace absent, got rc={rc}"
        err_data = json.loads(capsys.readouterr().err)
        assert err_data["error"] == "I-TRACE-BEFORE-WRITE"

    def test_s4_deterministic_anchor_resolve(self) -> None:
        """R-4: resolve --node-id for hidden dep source → deterministic anchor."""
        from sdd.graph_navigation.cli import resolve

        dep = EvalHiddenDep.default()
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=None, node_id=dep.source_node)

        if rc == 1 and "NOT_FOUND" in err.getvalue():
            pytest.skip("eval_deep node not in graph — may need rebuild")
        assert rc == 0, f"S4 anchor resolve failed: {err.getvalue()!r}"
