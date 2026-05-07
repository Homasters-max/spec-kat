"""S2: Enforcement check — graph-guard exits 1 for incomplete session. I-GRAPH-GUARD-1.

BC-61-T4 (S2): negative enforcement scenario. ScenarioResult.status = PASS when
enforcement correctly blocks a protocol violation (exit_code == 1 is the expected outcome).
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


def _make_incomplete_session(guard: EvalGuardCheck) -> GraphSessionState:
    return GraphSessionState(
        session_id=guard.session_id,
        phase_id=61,
        allowed_files=frozenset(),  # no graph steps performed
        trace_path=[],              # no trace performed
    )


class TestS2EnforcementCheck:
    """S2: enforcement blocks protocol violation → ScenarioResult.status = PASS."""

    def test_s2_graph_guard_exits_1_for_incomplete_session(self, capsys) -> None:
        """I-GRAPH-GUARD-1: graph-guard exits 1 when no graph steps performed."""
        from sdd.graph_navigation.cli import graph_guard

        guard_fixture = EvalGuardCheck.incomplete()  # resolved=False, empty explained/traced
        state = _make_incomplete_session(guard_fixture)

        with patch.object(graph_guard, "_load_session", return_value=state):
            rc = graph_guard.run(guard_fixture.session_id)

        captured = capsys.readouterr()
        # Enforcement correctly blocked: exit 1 is the expected outcome
        enforcement_worked = rc == 1
        result = ScenarioResult(
            scenario_id="S2",
            status="PASS" if enforcement_worked else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", f"S2 enforcement did not block: expected exit 1, got {rc}"
        assert result.exit_code == 1

        err = json.loads(captured.err)
        assert err["error"] == "GRAPH_PROTOCOL_VIOLATION"
        assert len(err["violations"]) > 0

    def test_s2_violations_include_allowed_files_and_trace(self, capsys) -> None:
        """I-GRAPH-PROTOCOL-1: violation message covers missing allowed_files and trace_path."""
        from sdd.graph_navigation.cli import graph_guard

        guard_fixture = EvalGuardCheck.incomplete()
        state = _make_incomplete_session(guard_fixture)

        with patch.object(graph_guard, "_load_session", return_value=state):
            graph_guard.run(guard_fixture.session_id)

        err = json.loads(capsys.readouterr().err)
        violation_text = " ".join(err["violations"])
        assert "allowed_files" in violation_text or "graph navigation" in violation_text
        assert "trace_path" in violation_text or "trace" in violation_text

    def test_s2_deterministic_anchor_resolve(self) -> None:
        """R-4: resolve --node-id works for anchor even when session protocol fails."""
        from sdd.graph_navigation.cli import resolve

        fixture = EvalFixtureTarget.default()
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=None, node_id=fixture.node_id)

        if rc == 1 and "NOT_FOUND" in err.getvalue():
            pytest.skip("eval_fixtures node not in graph")
        assert rc == 0, f"S2 anchor resolve failed: {err.getvalue()!r}"
