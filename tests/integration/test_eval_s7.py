"""S7: Write without graph — sdd write exits 1 when protocol not followed.

BC-61-T4 (S7): negative enforcement scenario. I-TRACE-BEFORE-WRITE: write_gate
must exit 1 when the session has no trace_path (graph navigation protocol not
followed). ScenarioResult.status = PASS when enforcement correctly blocks the write.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sdd.eval.eval_fixtures import EvalFixtureTarget, EvalGuardCheck
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


class TestS7WriteWithoutGraph:
    """S7: write_gate blocks write when trace_path is empty (no graph navigation)."""

    def _make_no_trace_session(self) -> GraphSessionState:
        """Session with no trace — simulates agent skipping graph navigation."""
        return GraphSessionState(
            session_id="eval-s7-no-graph",
            phase_id=61,
            allowed_files=frozenset(["src/sdd/eval/eval_fixtures.py"]),
            trace_path=[],  # no trace performed — I-TRACE-BEFORE-WRITE violated
        )

    def test_s7_write_gate_exits_1_without_trace(self, capsys) -> None:
        """I-TRACE-BEFORE-WRITE: write_gate exits 1 when trace_path is empty."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()
        state = self._make_no_trace_session()

        with patch.object(write_gate, "_load_session", return_value=state):
            rc = write_gate.run(fixture.file_path, "eval-s7-no-graph")

        captured = capsys.readouterr()
        enforcement_worked = rc == 1
        result = ScenarioResult(
            scenario_id="S7",
            status="PASS" if enforcement_worked else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", (
            f"S7 enforcement did not block write without trace: expected exit 1, got {rc}"
        )
        assert result.exit_code == 1

    def test_s7_stderr_contains_trace_before_write_error(self, capsys) -> None:
        """S7: JSON stderr must contain I-TRACE-BEFORE-WRITE error type."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()
        state = self._make_no_trace_session()

        with patch.object(write_gate, "_load_session", return_value=state):
            write_gate.run(fixture.file_path, "eval-s7-no-graph")

        err_text = capsys.readouterr().err
        err_data = json.loads(err_text)
        assert err_data["error"] == "I-TRACE-BEFORE-WRITE", (
            f"S7: expected 'I-TRACE-BEFORE-WRITE' in error, got {err_data!r}"
        )

    def test_s7_stderr_includes_session_and_file(self, capsys) -> None:
        """S7: error payload must include session_id and file_path for traceability."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()
        state = self._make_no_trace_session()

        with patch.object(write_gate, "_load_session", return_value=state):
            write_gate.run(fixture.file_path, "eval-s7-no-graph")

        err_data = json.loads(capsys.readouterr().err)
        assert "session_id" in err_data, "S7: error must include session_id"
        assert "file_path" in err_data, "S7: error must include file_path"
        assert err_data["session_id"] == "eval-s7-no-graph"
        assert err_data["file_path"] == fixture.file_path

    def test_s7_write_permitted_when_trace_present(self, capsys) -> None:
        """S7 contrast: write_gate exits 0 when trace_path is non-empty."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()
        guard_fixture = EvalGuardCheck.complete()
        state_with_trace = GraphSessionState(
            session_id="eval-s7-with-trace",
            phase_id=61,
            allowed_files=frozenset([fixture.file_path]),
            trace_path=[fixture.node_id],
        )

        with patch.object(write_gate, "_load_session", return_value=state_with_trace):
            rc = write_gate.run(fixture.file_path, "eval-s7-with-trace")

        captured = capsys.readouterr()
        assert rc == 0, (
            f"S7 contrast: write should be permitted when trace is present, got rc={rc}, "
            f"stderr={captured.err!r}"
        )

    def test_s7_session_not_found_exits_1(self, capsys) -> None:
        """S7: missing session → write_gate exits 1 (NOT_FOUND)."""
        from sdd.graph_navigation.cli import write_gate

        fixture = EvalFixtureTarget.default()

        with patch.object(write_gate, "_load_session", return_value=None):
            rc = write_gate.run(fixture.file_path, "eval-s7-missing")

        assert rc == 1, "S7: missing session must produce exit 1"
        err_data = json.loads(capsys.readouterr().err)
        assert "NOT_FOUND" in err_data.get("error", "") or "NOT_FOUND" in err_data.get("error_type", "")
