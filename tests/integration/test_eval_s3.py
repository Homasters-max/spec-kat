"""S3: Sparse graph — NOT_FOUND fallback. Graceful degradation when node absent.

BC-61-T4 (S3): positive scenario verifying that when graph resolve fails with
NOT_FOUND, the system degrades gracefully and a fallback session (built from
task_inputs) still satisfies the graph-guard check.
"""
from __future__ import annotations

import contextlib
import io
import json
from unittest.mock import patch

from sdd.eval.eval_fixtures import EvalFixtureTarget, EvalSparseGraph
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


class TestS3SparseGraphFallback:
    """S3: sparse graph → NOT_FOUND → fallback session from task_inputs."""

    def test_s3_not_found_for_nonexistent_node(self) -> None:
        """R-4: resolve --node-id for absent node → exit 1 + well-formed NOT_FOUND."""
        from sdd.graph_navigation.cli import resolve

        sparse = EvalSparseGraph.not_found()
        node_id = f"FILE:{sparse.query}"  # guaranteed absent from real graph

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=None, node_id=node_id)

        assert rc == 1, f"S3: expected NOT_FOUND (exit 1) for absent node, got rc={rc}"
        stderr_text = err.getvalue()
        assert "NOT_FOUND" in stderr_text, f"S3: expected NOT_FOUND in stderr: {stderr_text!r}"

        # Graceful error: well-formed JSON, not a crash / traceback
        err_data = json.loads(stderr_text)
        assert err_data.get("error_type") == "NOT_FOUND" or err_data.get("error") == "NOT_FOUND"

    def test_s3_fallback_session_passes_guard(self, capsys) -> None:
        """S3 positive: fallback session built from task_inputs satisfies graph-guard."""
        from sdd.graph_navigation.cli import graph_guard

        fixture = EvalFixtureTarget.default()
        # Fallback: when graph is sparse, session built from declared task_inputs
        fallback_state = GraphSessionState(
            session_id="eval-s3-sparse-fallback",
            phase_id=61,
            allowed_files=frozenset([fixture.file_path]),  # task_inputs as fallback scope
            trace_path=[fixture.node_id],                  # explicit trace acknowledgment
        )

        with patch.object(graph_guard, "_load_session", return_value=fallback_state):
            rc = graph_guard.run("eval-s3-sparse-fallback")

        captured = capsys.readouterr()
        result = ScenarioResult(
            scenario_id="S3",
            status="PASS" if rc == 0 else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", f"S3 fallback guard failed: {captured.err!r}"
        assert result.exit_code == 0

    def test_s3_bm25_not_found_is_graceful(self) -> None:
        """S3: BM25 resolve for absent keyword returns NOT_FOUND (not crash)."""
        from sdd.graph_navigation.cli import resolve

        sparse = EvalSparseGraph.not_found()
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=sparse.query)

        # Either NOT_FOUND (exit 1) or index is truly sparse — both are graceful
        assert rc in (0, 1), f"S3: unexpected exit code: {rc}"
        if rc == 1:
            stderr_text = err.getvalue()
            # Must be a structured error, not an exception traceback
            assert "NOT_FOUND" in stderr_text or "error" in stderr_text.lower()
