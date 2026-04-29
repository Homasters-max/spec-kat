"""Tests for _build_selection BFS core (T-5108)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Callable
from unittest.mock import MagicMock

import pytest

from sdd.context_kernel.selection import (
    RankedEdge,
    RankedNode,
    Selection,
    _build_selection,
    _global_importance,
)
from sdd.policy import BFS_OVERSELECT_FACTOR, Budget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edge(edge_id: str, src: str, dst: str, priority: float):
    """Return a minimal Edge-compatible SimpleNamespace."""
    return SimpleNamespace(edge_id=edge_id, src=src, dst=dst, priority=priority)


def _graph(edges_in: dict | None = None) -> MagicMock:
    """Return a DeterministicGraph mock with configurable edges_in."""
    g = MagicMock()
    g.edges_in = edges_in or {}
    return g


def _budget(max_nodes: int) -> Budget:
    return Budget(max_nodes=max_nodes, max_edges=max_nodes * 4, max_chars=max_nodes * 1000)


def _no_expand(graph, node_id, hop):
    """Expand function that yields no neighbours."""
    return []


# ---------------------------------------------------------------------------
# RankedNode / RankedEdge dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_ranked_node_frozen(self):
        n = RankedNode(node_id="a", hop=0, global_importance_score=1.0)
        with pytest.raises((AttributeError, TypeError)):
            n.hop = 99  # type: ignore[misc]

    def test_ranked_edge_frozen(self):
        e = RankedEdge(edge_id="e1", src="a", dst="b", hop=1, priority=0.5)
        with pytest.raises((AttributeError, TypeError)):
            e.priority = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _global_importance
# ---------------------------------------------------------------------------

class TestGlobalImportance:
    def test_single_incoming_edge(self):
        e = _edge("e1", "a", "b", 0.7)
        g = _graph({"b": [e]})
        assert _global_importance(g, "b", e) == pytest.approx(0.7)

    def test_max_over_multiple_incoming_edges(self):
        """I-RANKED-NODE-BP-1: max priority over ALL incoming edges, not just the current one."""
        e_low = _edge("e1", "x", "b", 0.3)
        e_high = _edge("e2", "y", "b", 0.9)
        e_mid = _edge("e3", "z", "b", 0.6)
        g = _graph({"b": [e_low, e_high, e_mid]})
        fallback = _edge("ef", "f", "b", 0.1)
        assert _global_importance(g, "b", fallback) == pytest.approx(0.9)

    def test_fallback_when_no_incoming(self):
        """Uses fallback_edge when dst not in edges_in."""
        fallback = _edge("ef", "x", "b", 0.55)
        g = _graph({})
        assert _global_importance(g, "b", fallback) == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# _build_selection — seed node
# ---------------------------------------------------------------------------

class TestSeedNode:
    def test_seed_always_in_selection(self):
        sel = _build_selection(_graph(), _budget(10), "seed", _no_expand)
        assert "seed" in sel.nodes

    def test_seed_hop_is_zero(self):
        sel = _build_selection(_graph(), _budget(10), "seed", _no_expand)
        assert sel.nodes["seed"].hop == 0

    def test_seed_importance_is_one(self):
        """I-CONTEXT-SEED-1: seed global_importance_score == 1.0."""
        sel = _build_selection(_graph(), _budget(10), "seed", _no_expand)
        assert sel.nodes["seed"].global_importance_score == pytest.approx(1.0)

    def test_seed_field_on_selection(self):
        sel = _build_selection(_graph(), _budget(10), "myseed", _no_expand)
        assert sel.seed == "myseed"

    def test_no_edges_for_isolated_seed(self):
        sel = _build_selection(_graph(), _budget(10), "seed", _no_expand)
        assert sel.edges == {}


# ---------------------------------------------------------------------------
# _build_selection — BFS traversal
# ---------------------------------------------------------------------------

class TestBFSTraversal:
    def _linear_expand(self, chain: list[str]) -> Callable:
        """Returns expand function that follows a linear chain seed→chain[0]→…"""
        def expand(graph, node_id, hop):
            idx = chain.index(node_id) if node_id in chain else -1
            if idx == -1:
                return []
            if idx + 1 >= len(chain):
                return []
            nxt = chain[idx + 1]
            return [_edge(f"e{idx}", node_id, nxt, 0.5)]
        return expand

    def test_single_hop(self):
        chain = ["seed", "a"]
        expand = self._linear_expand(chain)
        g = _graph()
        sel = _build_selection(g, _budget(10), "seed", expand)
        assert "a" in sel.nodes
        assert sel.nodes["a"].hop == 1

    def test_multi_hop(self):
        chain = ["seed", "a", "b", "c"]
        expand = self._linear_expand(chain)
        sel = _build_selection(_graph(), _budget(10), "seed", expand)
        assert sel.nodes["c"].hop == 3

    def test_edges_recorded(self):
        chain = ["seed", "a"]
        expand = self._linear_expand(chain)
        sel = _build_selection(_graph(), _budget(10), "seed", expand)
        assert len(sel.edges) == 1
        edge = next(iter(sel.edges.values()))
        assert edge.src == "seed"
        assert edge.dst == "a"

    def test_returns_selection_instance(self):
        sel = _build_selection(_graph(), _budget(5), "seed", _no_expand)
        assert isinstance(sel, Selection)


# ---------------------------------------------------------------------------
# _build_selection — BFS budget early-stop (I-BFS-BUDGET-1)
# ---------------------------------------------------------------------------

class TestBFSBudgetEarlyStop:
    def _chain_expand(self, total_length: int) -> Callable:
        """seed → c0 → c1 → … → c_{total_length-1} (linear chain)."""
        def expand(graph, node_id, hop):
            try:
                idx = int(node_id.lstrip("c")) if node_id.startswith("c") else -1
            except ValueError:
                idx = -1
            if node_id == "seed":
                return [_edge("e_seed", "seed", "c0", 0.5)]
            if node_id.startswith("c") and idx + 1 < total_length:
                nxt = f"c{idx + 1}"
                return [_edge(f"e{idx}", node_id, nxt, 0.5)]
            return []
        return expand

    def test_early_stop_limits_nodes(self):
        """I-BFS-BUDGET-1: guard fires at dequeue — chain cut to exactly limit nodes.

        Guard check: `len(nodes) >= max_nodes * BFS_OVERSELECT_FACTOR`.
        In a chain, each iteration adds one node, guard fires when len == limit,
        producing exactly `limit` nodes in the final selection.
        """
        max_nodes = 5
        limit = int(max_nodes * BFS_OVERSELECT_FACTOR)  # 15
        # chain of 50 is far longer than limit
        expand = self._chain_expand(total_length=50)
        sel = _build_selection(_graph(), _budget(max_nodes), "seed", expand)
        assert len(sel.nodes) == limit

    def test_no_early_stop_within_budget(self):
        """When total nodes fit within budget, all are included."""
        max_nodes = 20
        chain_len = 5  # seed + 5 chain nodes = 6, well under limit=60
        expand = self._chain_expand(total_length=chain_len)
        sel = _build_selection(_graph(), _budget(max_nodes), "seed", expand)
        # seed + chain_len nodes
        assert len(sel.nodes) == chain_len + 1

    def test_early_stop_with_mock_graph(self):
        """Use MagicMock DeterministicGraph; guard stops second-level expansion.

        Fan-out from seed: seed → n0..n{fan-1} (all added before guard fires).
        Guard fires when processing n0: len(nodes) >= limit → second level never expanded.
        """
        mock_graph = MagicMock()
        mock_graph.edges_in = {}

        fan = 50  # large fan-out so second level would be huge
        max_nodes = 5
        limit = int(max_nodes * BFS_OVERSELECT_FACTOR)

        second_level_expanded = {"visited": False}

        def counting_expand(graph, node_id, hop):
            if node_id == "seed":
                return [_edge(f"e{i}", "seed", f"n{i}", 0.1) for i in range(fan)]
            # second level — should never be called if guard works
            second_level_expanded["visited"] = True
            return []

        budget = _budget(max_nodes)
        sel = _build_selection(mock_graph, budget, "seed", counting_expand)

        # guard fires before second level is processed
        assert not second_level_expanded["visited"], (
            "BFS early-stop failed: second level was expanded past budget"
        )
        # seed + all fan children fit in one batch (guard fires only on dequeue of children)
        assert len(sel.nodes) == fan + 1


# ---------------------------------------------------------------------------
# _build_selection — global_importance_score uses ALL incoming edges (I-RANKED-NODE-BP-1)
# ---------------------------------------------------------------------------

class TestGlobalImportanceInSelection:
    def test_gis_uses_all_graph_incoming_edges(self):
        """GIS must reflect max priority over ALL graph.edges_in[dst], not just traversal edge."""
        # The edge from BFS traversal has priority=0.2, but graph.edges_in["b"] has a higher one.
        traversal_edge = _edge("e_trav", "seed", "b", 0.2)
        high_priority_edge = _edge("e_other", "x", "b", 0.95)

        g = _graph({"b": [traversal_edge, high_priority_edge]})

        def expand(graph, node_id, hop):
            if node_id == "seed":
                return [traversal_edge]
            return []

        sel = _build_selection(g, _budget(10), "seed", expand)
        assert "b" in sel.nodes
        # Must be 0.95, not 0.2 (traversal edge priority)
        assert sel.nodes["b"].global_importance_score == pytest.approx(0.95)

    def test_gis_fallback_when_not_in_graph(self):
        """When dst absent from graph.edges_in, fallback_edge priority is used."""
        traversal_edge = _edge("e_trav", "seed", "b", 0.42)
        g = _graph({})  # empty edges_in

        def expand(graph, node_id, hop):
            if node_id == "seed":
                return [traversal_edge]
            return []

        sel = _build_selection(g, _budget(10), "seed", expand)
        assert sel.nodes["b"].global_importance_score == pytest.approx(0.42)
