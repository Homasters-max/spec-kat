"""S9–S15: Graph Semantic Hardening — enforcement and positive-path scenarios.

BC-62-G6: Eval scenarios covering I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1,
I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_FILE = "FILE:src/sdd/eval/eval_fixtures.py"
_DEEP_FILE = "FILE:src/sdd/eval/eval_deep.py"


def _guard_result(scenario_id: str, state: GraphSessionState, capsys) -> ScenarioResult:
    from sdd.graph_navigation.cli import graph_guard

    with patch.object(graph_guard, "_load_session", return_value=state):
        rc = graph_guard.run(state.session_id)

    captured = capsys.readouterr()
    return ScenarioResult(
        scenario_id=scenario_id,
        status="PASS" if rc == 0 else "FAIL",
        stdout=captured.out,
        stderr=captured.err,
        exit_code=rc,
    )


def _write_gate_result(
    scenario_id: str, state: GraphSessionState, file_path: str, capsys
) -> ScenarioResult:
    from sdd.graph_navigation.cli import write_gate

    with patch.object(write_gate, "_load_session", return_value=state):
        rc = write_gate.run(file_path, state.session_id)

    captured = capsys.readouterr()
    return ScenarioResult(
        scenario_id=scenario_id,
        status="PASS" if rc == 0 else "FAIL",
        stdout=captured.out,
        stderr=captured.err,
        exit_code=rc,
    )


# ---------------------------------------------------------------------------
# S9 — I-TRACE-RELEVANCE-1 (negative): write_target ∉ trace_path → exit 1
# ---------------------------------------------------------------------------

class TestS9TraceRelevance:
    """S9: write_gate rejects write when target not in trace_path."""

    def test_s9_write_gate_exits_1_when_target_not_in_trace(self, capsys) -> None:
        """I-TRACE-RELEVANCE-1: write blocked when file_path ∉ trace_path."""
        state = GraphSessionState(
            session_id="eval-s9-trace-relevance",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),
            trace_path=[_FIXTURE_FILE],  # only eval_fixtures.py in trace
        )
        # attempt to write eval_deep.py which is NOT in trace_path
        result = _write_gate_result("S9", state, "src/sdd/eval/eval_deep.py", capsys)

        assert result.exit_code == 1, f"S9: write gate should exit 1, got 0; stderr={result.stderr!r}"
        err = json.loads(result.stderr) if result.stderr.strip() else {}
        assert err.get("error") == "I-TRACE-RELEVANCE-1", (
            f"S9: expected I-TRACE-RELEVANCE-1 error, got {err!r}"
        )


# ---------------------------------------------------------------------------
# S10 — I-FALLBACK-STRICT-1 (negative): fallback_used + allowed_files empty → exit 1
# ---------------------------------------------------------------------------

class TestS10FallbackStrict:
    """S10: graph-guard rejects when fallback used but allowed_files is empty."""

    def test_s10_guard_exits_1_fallback_without_files(self, capsys) -> None:
        """I-FALLBACK-STRICT-1: fallback_used=True with empty allowed_files → exit 1."""
        state = GraphSessionState(
            session_id="eval-s10-fallback-strict",
            phase_id=62,
            allowed_files=frozenset(),  # no task_inputs set
            trace_path=[_FIXTURE_FILE],
            traversal_depth_max=2,
            fallback_used=True,
        )
        result = _guard_result("S10", state, capsys)

        assert result.exit_code == 1, f"S10: guard should exit 1; stderr={result.stderr!r}"
        err = json.loads(result.stderr) if result.stderr.strip() else {}
        violations = err.get("violations", [])
        assert any("I-FALLBACK-STRICT-1" in v for v in violations), (
            f"S10: expected I-FALLBACK-STRICT-1 in violations; got {violations!r}"
        )


# ---------------------------------------------------------------------------
# S11 — I-GRAPH-DEPTH-1 (negative): depth_max=1 + no justification → exit 1
# ---------------------------------------------------------------------------

class TestS11GraphDepth:
    """S11: graph-guard rejects when traversal depth < 2 with no justification."""

    def test_s11_guard_exits_1_shallow_depth_no_justification(self, capsys) -> None:
        """I-GRAPH-DEPTH-1: traversal_depth_max=1 and depth_justification="" → exit 1."""
        state = GraphSessionState(
            session_id="eval-s11-depth",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),
            trace_path=[_FIXTURE_FILE],
            traversal_depth_max=1,
            depth_justification="",  # no justification provided
            fallback_used=False,
        )
        result = _guard_result("S11", state, capsys)

        assert result.exit_code == 1, f"S11: guard should exit 1; stderr={result.stderr!r}"
        err = json.loads(result.stderr) if result.stderr.strip() else {}
        violations = err.get("violations", [])
        assert any("I-GRAPH-DEPTH-1" in v for v in violations), (
            f"S11: expected I-GRAPH-DEPTH-1 in violations; got {violations!r}"
        )


# ---------------------------------------------------------------------------
# S12 — I-GRAPH-COVERAGE-REQ-1 (negative): write_target ∉ trace_path ∪ explain_nodes → exit 1
# ---------------------------------------------------------------------------

class TestS12GraphCoverageReq:
    """S12: graph-guard rejects when write_target not covered by trace or explain."""

    def test_s12_guard_exits_1_uncovered_write_target(self, capsys) -> None:
        """I-GRAPH-COVERAGE-REQ-1: write_target not in trace_path ∪ explain_nodes → exit 1."""
        state = GraphSessionState(
            session_id="eval-s12-coverage",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),
            trace_path=[_FIXTURE_FILE],  # only eval_fixtures in trace
            traversal_depth_max=2,
            explain_nodes=frozenset(),  # no explain nodes
            write_targets=frozenset([_DEEP_FILE]),  # eval_deep not in trace ∪ explain
            fallback_used=False,
        )
        result = _guard_result("S12", state, capsys)

        assert result.exit_code == 1, f"S12: guard should exit 1; stderr={result.stderr!r}"
        err = json.loads(result.stderr) if result.stderr.strip() else {}
        violations = err.get("violations", [])
        assert any("I-GRAPH-COVERAGE-REQ-1" in v for v in violations), (
            f"S12: expected I-GRAPH-COVERAGE-REQ-1 in violations; got {violations!r}"
        )


# ---------------------------------------------------------------------------
# S13 — I-EXPLAIN-USAGE-1 (negative): explain_node ∉ trace_path ∪ write_targets → exit 1
# ---------------------------------------------------------------------------

class TestS13ExplainUsage:
    """S13: graph-guard rejects when explain_node not referenced in trace or write_targets."""

    def test_s13_guard_exits_1_orphaned_explain_node(self, capsys) -> None:
        """I-EXPLAIN-USAGE-1: explain_node not in trace_path ∪ write_targets → exit 1."""
        state = GraphSessionState(
            session_id="eval-s13-explain-usage",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),
            trace_path=[_FIXTURE_FILE],
            traversal_depth_max=2,
            explain_nodes=frozenset([_DEEP_FILE]),  # eval_deep explained but not in trace/write
            write_targets=frozenset([_FIXTURE_FILE]),  # write target IS in trace → no S12 violation
            fallback_used=False,
        )
        result = _guard_result("S13", state, capsys)

        assert result.exit_code == 1, f"S13: guard should exit 1; stderr={result.stderr!r}"
        err = json.loads(result.stderr) if result.stderr.strip() else {}
        violations = err.get("violations", [])
        assert any("I-EXPLAIN-USAGE-1" in v for v in violations), (
            f"S13: expected I-EXPLAIN-USAGE-1 in violations; got {violations!r}"
        )


# ---------------------------------------------------------------------------
# S14 — positive: all invariants satisfied → exit 0
# ---------------------------------------------------------------------------

class TestS14AllInvariantsSatisfied:
    """S14: graph-guard exits 0 when all invariants pass (depth=2, targets covered, explain used)."""

    def test_s14_guard_exits_0_full_correct_protocol(self, capsys) -> None:
        """S14: depth=2, write_target in trace, explain_node in trace, no fallback → exit 0."""
        state = GraphSessionState(
            session_id="eval-s14-full-correct",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),
            trace_path=[_FIXTURE_FILE],
            traversal_depth_max=2,
            fallback_used=False,
            explain_nodes=frozenset([_FIXTURE_FILE]),  # explain node IS in trace_path
            write_targets=frozenset([_FIXTURE_FILE]),  # write target IS in trace_path
            depth_justification="",
        )
        result = _guard_result("S14", state, capsys)

        assert result.exit_code == 0, (
            f"S14: guard should exit 0 (all invariants satisfied); stderr={result.stderr!r}"
        )
        assert result.status == "PASS"


# ---------------------------------------------------------------------------
# S15 — I-FALLBACK-STRICT-1 (positive): fallback_used + task_inputs set → exit 0
# ---------------------------------------------------------------------------

class TestS15FallbackWithTaskInputs:
    """S15: graph-guard exits 0 when fallback used but task_inputs (allowed_files) are set."""

    def test_s15_guard_exits_0_fallback_with_files(self, capsys) -> None:
        """I-FALLBACK-STRICT-1 positive: fallback_used=True but allowed_files non-empty → exit 0."""
        state = GraphSessionState(
            session_id="eval-s15-fallback-ok",
            phase_id=62,
            allowed_files=frozenset([_FIXTURE_FILE]),  # task_inputs set → fallback allowed
            trace_path=[_FIXTURE_FILE],
            traversal_depth_max=2,
            fallback_used=True,  # fallback used, but allowed_files non-empty → OK
            write_targets=frozenset(),
            explain_nodes=frozenset(),
        )
        result = _guard_result("S15", state, capsys)

        assert result.exit_code == 0, (
            f"S15: guard should exit 0 (fallback with task_inputs is allowed); stderr={result.stderr!r}"
        )
        assert result.status == "PASS"
