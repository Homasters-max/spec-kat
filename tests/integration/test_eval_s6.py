"""S6: Multi-hop — BFS depth ≥2 traversal via eval fixture chain.

BC-61-T4 (S6): positive scenario verifying that the eval fixture chain encodes
a 2-hop imports graph: __init__.py →(imports)→ eval_fixtures.py →(imports)→ eval_deep.py.
EvalDeepAnchor.hop_depth == 2 and a session built after 2-hop BFS passes graph-guard.
"""
from __future__ import annotations

import contextlib
import io
from unittest.mock import patch

import pytest

from sdd.eval.eval_deep import EvalDeepAnchor
from sdd.eval.eval_fixtures import EvalMultiHop
from sdd.eval.eval_harness import ScenarioResult
from sdd.graph_navigation.session_state import GraphSessionState


class TestS6MultiHop:
    """S6: 2-hop graph traversal fixture encodes BFS depth ≥2; session passes guard."""

    def test_s6_hop_depth_is_at_least_2(self) -> None:
        """S6 fixture: EvalDeepAnchor.hop_depth must be ≥2."""
        anchor = EvalDeepAnchor()
        assert anchor.hop_depth >= 2, (
            f"S6: hop_depth must be ≥2 for multi-hop scenario, got {anchor.hop_depth}"
        )

    def test_s6_multi_hop_fixture_encodes_two_hops(self) -> None:
        """S6 fixture: EvalMultiHop.hop1_nodes and hop2_nodes are non-empty."""
        mh = EvalMultiHop.default()
        assert len(mh.hop1_nodes) >= 1, "S6: hop1_nodes must be non-empty"
        assert len(mh.hop2_nodes) >= 1, "S6: hop2_nodes must be non-empty"
        # hop2 nodes are NOT directly reachable from anchor (require 2 hops)
        assert not (frozenset(mh.hop2_nodes) & frozenset(mh.hop1_nodes)), (
            "S6: hop2_nodes must be disjoint from hop1_nodes — otherwise depth < 2"
        )

    def test_s6_deep_anchor_is_in_hop2(self) -> None:
        """S6: eval_deep.py appears only at hop2, not hop1."""
        anchor = EvalDeepAnchor()
        mh = anchor.multi_hop
        assert anchor.node_id in mh.hop2_nodes, (
            f"S6: {anchor.node_id!r} must be in hop2_nodes, got {mh.hop2_nodes}"
        )
        assert anchor.node_id not in mh.hop1_nodes, (
            f"S6: {anchor.node_id!r} must NOT be in hop1_nodes (would mean depth=1)"
        )

    def test_s6_session_with_multihop_scope_passes_guard(self, capsys) -> None:
        """S6: session built from 2-hop BFS scope satisfies graph-guard (exit 0)."""
        from sdd.graph_navigation.cli import graph_guard

        anchor = EvalDeepAnchor()
        mh = anchor.multi_hop
        # Session includes all nodes reachable via 2-hop BFS
        all_hop_files = {n.replace("FILE:", "") for n in (*mh.hop1_nodes, *mh.hop2_nodes)}
        state = GraphSessionState(
            session_id="eval-s6-multihop",
            phase_id=61,
            allowed_files=frozenset(all_hop_files),
            trace_path=list(mh.hop1_nodes) + list(mh.hop2_nodes),
        )

        with patch.object(graph_guard, "_load_session", return_value=state):
            rc = graph_guard.run("eval-s6-multihop")

        captured = capsys.readouterr()
        result = ScenarioResult(
            scenario_id="S6",
            status="PASS" if rc == 0 else "FAIL",
            stdout="",
            stderr=captured.err,
            exit_code=rc,
        )
        assert result.status == "PASS", (
            f"S6: graph-guard failed for multi-hop session: {captured.err!r}"
        )
        assert result.exit_code == 0

    def test_s6_deterministic_anchor_resolve_for_hop1(self) -> None:
        """R-4: resolve --node-id for hop1 node → deterministic exit."""
        from sdd.graph_navigation.cli import resolve

        mh = EvalMultiHop.default()
        hop1_node = mh.hop1_nodes[0]

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = resolve.run(query=None, node_id=hop1_node)

        if rc == 1 and "NOT_FOUND" in err.getvalue():
            pytest.skip(f"S6: hop1 node {hop1_node!r} not in graph — may need rebuild")
        assert rc == 0, f"S6: hop1 anchor resolve failed: {err.getvalue()!r}"
