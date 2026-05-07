"""S1: Normal path — resolve→explain→trace→write. I-GRAPH-PROTOCOL-1 satisfied.

BC-61-T4 (S1): positive scenario verifying that the full graph-guided protocol
succeeds — graph-guard exits 0 and write gate exits 0 when session is complete.
"""
from __future__ import annotations

import contextlib
import io
import json
from unittest.mock import patch

import pytest

from sdd.eval.eval_fixtures import EvalFixtureTarget, EvalGuardCheck
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


def _make_complete_session(guard: EvalGuardCheck, fixture: EvalFixtureTarget) -> GraphSessionState:
    return GraphSessionState(
        session_id=guard.session_id,
        phase_id=61,
        allowed_files=frozenset([fixture.file_path]),
        trace_path=list(guard.traced),
        explain_nodes=guard.explained,   # I-EXPLAIN-USAGE-1: must be in trace_path ∪ write_targets
        traversal_depth_max=2,           # I-GRAPH-DEPTH-1: ≥2 required when no depth_justification
    )


class TestS1NormalPath:
    """S1: full protocol — resolve→explain→trace→write → protocol_satisfied=True."""

    def test_s1_deterministic_anchor_resolve(self) -> None:
        """R-4: sdd resolve --node-id → deterministic exit 0 for eval fixture node."""
        from sdd.graph_navigation.cli import resolve

        fixture = EvalFixtureTarget.default()
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=None, node_id=fixture.node_id)

        if rc == 1 and "NOT_FOUND" in err.getvalue():
            pytest.skip("eval_fixtures node not in graph — graph may need rebuild")
        assert rc == 0, f"S1 resolve --node-id failed: {err.getvalue()!r}"

    def test_s1_graph_guard_exits_0(self, capsys) -> None:
        """I-GRAPH-GUARD-1: graph-guard exits 0 when protocol is satisfied."""
        from sdd.graph_navigation.cli import graph_guard

        fixture = EvalFixtureTarget.default()
        guard_fixture = EvalGuardCheck.complete()
        state = _make_complete_session(guard_fixture, fixture)

        with patch.object(graph_guard, "_load_session", return_value=state):
            rc = graph_guard.run(guard_fixture.session_id)

        captured = capsys.readouterr()
        result = ScenarioResult(
            scenario_id="S1",
            status="PASS" if rc == 0 else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", f"S1 graph-guard failed: {captured.err!r}"
        assert result.exit_code == 0

    def test_s1_write_gate_exits_0(self, capsys) -> None:
        """I-TRACE-BEFORE-WRITE: write gate exits 0 when trace_path is set."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()
        guard_fixture = EvalGuardCheck.complete()
        state = _make_complete_session(guard_fixture, fixture)

        with patch.object(write_gate, "_load_session", return_value=state):
            rc = write_gate.run(fixture.file_path, guard_fixture.session_id)

        captured = capsys.readouterr()
        result = ScenarioResult(
            scenario_id="S1",
            status="PASS" if rc == 0 else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", f"S1 write gate failed: {captured.err!r}"
        assert result.exit_code == 0
