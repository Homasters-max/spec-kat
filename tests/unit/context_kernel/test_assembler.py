"""Tests for ContextAssembler (T-5114).

Covers:
  - Sort order: nodes (hop ASC, -gis, node_id ASC) — I-CONTEXT-TRUNCATE-1
  - Sort order: edges (hop ASC, -priority, edge_id ASC) — I-CONTEXT-TRUNCATE-1
  - Sort order: docs (node_rank, kind, sha256(content)) — I-CONTEXT-ORDER-1
  - context_id determinism (I-CONTEXT-DETERMINISM-1, R-CONTEXT-ID-SEARCH)
  - Seed always present regardless of budget (I-CONTEXT-SEED-1)
  - Budget limits applied (I-CONTEXT-BUDGET-1)
  - I-CTX-MIGRATION-1: no build_context.py import in assembler.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from sdd.context_kernel.assembler import (
    AssembledContext,
    ContextAssembler,
    _compute_context_id,
    _doc_sort_key,
    _edge_sort_key,
    _node_sort_key,
)
from sdd.context_kernel.documents import DocumentChunk
from sdd.context_kernel.intent import QueryIntent
from sdd.context_kernel.selection import RankedEdge, RankedNode, Selection
from sdd.graph.types import DeterministicGraph, Edge, Node
from sdd.policy import Budget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id: str, kind: str = "FILE") -> Node:
    return Node(node_id=node_id, kind=kind, label=node_id, summary="", meta={})


def _edge(edge_id: str, src: str, dst: str, kind: str = "depends_on", priority: float = 0.7) -> Edge:
    return Edge(edge_id=edge_id, src=src, dst=dst, kind=kind, priority=priority, source="test", meta={})


def _ranked_node(node_id: str, hop: int, gis: float) -> RankedNode:
    return RankedNode(node_id=node_id, hop=hop, global_importance_score=gis)


def _ranked_edge(edge_id: str, src: str, dst: str, hop: int, priority: float) -> RankedEdge:
    return RankedEdge(edge_id=edge_id, src=src, dst=dst, hop=hop, priority=priority)


def _graph(nodes: dict[str, Node] | None = None, snapshot_hash: str = "abc123") -> DeterministicGraph:
    return DeterministicGraph(
        nodes=nodes or {},
        edges_out={},
        edges_in={},
        source_snapshot_hash=snapshot_hash,
    )


def _selection(seed: str, nodes: list[RankedNode], edges: list[RankedEdge] | None = None) -> Selection:
    return Selection(
        seed=seed,
        nodes={rn.node_id: rn for rn in nodes},
        edges={re.edge_id: re for re in (edges or [])},
    )


def _budget(max_nodes: int = 10, max_edges: int = 20, max_chars: int = 10_000) -> Budget:
    return Budget(max_nodes=max_nodes, max_edges=max_edges, max_chars=max_chars)


def _doc_provider(chunks: list[DocumentChunk] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get_chunks.return_value = chunks or []
    return mock


def _chunk(node_id: str, content: str, kind: str = "code") -> DocumentChunk:
    return DocumentChunk(
        node_id=node_id,
        content=content,
        kind=kind,
        char_count=len(content),
        meta={},
        references=[],
    )


# ---------------------------------------------------------------------------
# _node_sort_key
# ---------------------------------------------------------------------------

class TestNodeSortKey:
    def test_primary_sort_by_hop_asc(self):
        n0 = _ranked_node("a", hop=0, gis=0.5)
        n1 = _ranked_node("b", hop=1, gis=0.9)
        assert _node_sort_key(n0) < _node_sort_key(n1)

    def test_secondary_sort_by_gis_desc(self):
        """Higher gis → lower sort key (listed first)."""
        n_high = _ranked_node("a", hop=1, gis=0.9)
        n_low = _ranked_node("b", hop=1, gis=0.1)
        assert _node_sort_key(n_high) < _node_sort_key(n_low)

    def test_tertiary_sort_by_node_id_asc(self):
        n_a = _ranked_node("aaa", hop=1, gis=0.5)
        n_b = _ranked_node("bbb", hop=1, gis=0.5)
        assert _node_sort_key(n_a) < _node_sort_key(n_b)

    def test_sort_key_tuple_structure(self):
        n = _ranked_node("x", hop=2, gis=0.7)
        key = _node_sort_key(n)
        assert key == (2, -0.7, "x")


# ---------------------------------------------------------------------------
# _edge_sort_key
# ---------------------------------------------------------------------------

class TestEdgeSortKey:
    def test_primary_sort_by_hop_asc(self):
        e0 = _ranked_edge("e1", "a", "b", hop=0, priority=0.5)
        e1 = _ranked_edge("e2", "a", "c", hop=1, priority=0.9)
        assert _edge_sort_key(e0) < _edge_sort_key(e1)

    def test_secondary_sort_by_priority_desc(self):
        """Higher priority → lower sort key (listed first)."""
        e_high = _ranked_edge("e1", "a", "b", hop=1, priority=0.9)
        e_low = _ranked_edge("e2", "a", "c", hop=1, priority=0.3)
        assert _edge_sort_key(e_high) < _edge_sort_key(e_low)

    def test_tertiary_sort_by_edge_id_asc(self):
        e_a = _ranked_edge("aaa", "a", "b", hop=1, priority=0.5)
        e_b = _ranked_edge("bbb", "a", "c", hop=1, priority=0.5)
        assert _edge_sort_key(e_a) < _edge_sort_key(e_b)

    def test_sort_key_tuple_structure(self):
        e = _ranked_edge("eid", "a", "b", hop=3, priority=0.8)
        key = _edge_sort_key(e)
        assert key == (3, -0.8, "eid")


# ---------------------------------------------------------------------------
# _doc_sort_key
# ---------------------------------------------------------------------------

class TestDocSortKey:
    def test_sort_by_node_rank(self):
        """Chunks for higher-ranked (lower index) nodes sort first."""
        c0 = _chunk("n0", "content")
        c1 = _chunk("n1", "content")
        node_rank = {"n0": 0, "n1": 1}
        assert _doc_sort_key(c0, node_rank, 2) < _doc_sort_key(c1, node_rank, 2)

    def test_secondary_sort_by_kind(self):
        """Same node rank: 'code' < 'doc' < 'invariant' (lexicographic)."""
        rank = {"n0": 0}
        c_code = _chunk("n0", "same_content", kind="code")
        c_doc = _chunk("n0", "same_content", kind="doc")
        assert _doc_sort_key(c_code, rank, 1) < _doc_sort_key(c_doc, rank, 1)

    def test_tertiary_sort_by_content_hash(self):
        """Same node rank, same kind: sorted by sha256(content)."""
        rank = {"n0": 0}
        c_a = _chunk("n0", "aaa", kind="code")
        c_b = _chunk("n0", "bbb", kind="code")
        hash_a = hashlib.sha256(b"aaa").hexdigest()
        hash_b = hashlib.sha256(b"bbb").hexdigest()
        result = _doc_sort_key(c_a, rank, 1) < _doc_sort_key(c_b, rank, 1)
        expected = hash_a < hash_b
        assert result == expected

    def test_unknown_node_id_uses_total_nodes_as_rank(self):
        """Chunks for unknown node_ids sort after all known nodes."""
        c_known = _chunk("n0", "content")
        c_unknown = _chunk("unknown", "content")
        rank = {"n0": 0}
        assert _doc_sort_key(c_known, rank, 5) < _doc_sort_key(c_unknown, rank, 5)


# ---------------------------------------------------------------------------
# ContextAssembler — node ordering in build()
# ---------------------------------------------------------------------------

class TestBuildNodeOrdering:
    def _assemble(self, ranked_nodes: list[RankedNode], max_nodes: int = 10) -> list[Node]:
        nodes_dict = {rn.node_id: _node(rn.node_id) for rn in ranked_nodes}
        graph = _graph(nodes=nodes_dict)
        sel = _selection("seed", ranked_nodes)
        ctx = ContextAssembler().build(graph, sel, _budget(max_nodes=max_nodes), _doc_provider())
        return ctx.nodes

    def test_nodes_sorted_by_hop_then_gis_desc_then_id(self):
        """I-CONTEXT-TRUNCATE-1: deterministic node order (hop, -gis, node_id)."""
        rn_seed = _ranked_node("seed", hop=0, gis=1.0)
        rn_b = _ranked_node("b", hop=1, gis=0.9)
        rn_a = _ranked_node("a", hop=1, gis=0.5)
        rn_c = _ranked_node("c", hop=2, gis=0.8)
        nodes = self._assemble([rn_seed, rn_b, rn_a, rn_c])
        node_ids = [n.node_id for n in nodes]
        assert node_ids == ["seed", "b", "a", "c"]

    def test_nodes_same_hop_gis_sorted_by_id(self):
        """Tiebreak by node_id ASC."""
        rn_seed = _ranked_node("seed", hop=0, gis=1.0)
        rn_z = _ranked_node("zzz", hop=1, gis=0.5)
        rn_a = _ranked_node("aaa", hop=1, gis=0.5)
        nodes = self._assemble([rn_seed, rn_z, rn_a])
        node_ids = [n.node_id for n in nodes]
        assert node_ids == ["seed", "aaa", "zzz"]

    def test_max_nodes_budget_applied(self):
        """I-CONTEXT-BUDGET-1: at most max_nodes returned."""
        ranked = [_ranked_node("seed", hop=0, gis=1.0)] + [
            _ranked_node(f"n{i}", hop=1, gis=0.5) for i in range(10)
        ]
        nodes = self._assemble(ranked, max_nodes=3)
        assert len(nodes) <= 3


# ---------------------------------------------------------------------------
# ContextAssembler — edge ordering in build()
# ---------------------------------------------------------------------------

class TestBuildEdgeOrdering:
    def _assemble_edges(self, ranked_edges: list[RankedEdge], max_edges: int = 20) -> list[Edge]:
        seed_rn = _ranked_node("seed", hop=0, gis=1.0)
        nodes_dict: dict[str, Node] = {"seed": _node("seed")}
        # Add src/dst nodes
        for re_ in ranked_edges:
            for nid in [re_.src, re_.dst]:
                nodes_dict[nid] = _node(nid)
        graph_edges_out: dict[str, list[Edge]] = {}
        graph_edges_in: dict[str, list[Edge]] = {}
        real_edges: list[Edge] = []
        for re_ in ranked_edges:
            e = _edge(re_.edge_id, re_.src, re_.dst, priority=re_.priority)
            real_edges.append(e)
            graph_edges_out.setdefault(re_.src, []).append(e)
            graph_edges_in.setdefault(re_.dst, []).append(e)
        graph = DeterministicGraph(
            nodes=nodes_dict,
            edges_out=graph_edges_out,
            edges_in=graph_edges_in,
            source_snapshot_hash="snap",
        )
        sel = _selection("seed", [seed_rn], ranked_edges)
        ctx = ContextAssembler().build(
            graph, sel, _budget(max_nodes=50, max_edges=max_edges), _doc_provider()
        )
        return ctx.edges

    def test_edges_sorted_by_hop_then_priority_desc_then_id(self):
        """I-CONTEXT-TRUNCATE-1: edges ordered (hop ASC, -priority, edge_id ASC)."""
        re_high = _ranked_edge("eAAA", "seed", "b", hop=1, priority=0.9)
        re_low = _ranked_edge("eBBB", "seed", "c", hop=1, priority=0.3)
        re_hop2 = _ranked_edge("eHOP2", "seed", "d", hop=2, priority=0.9)
        edges = self._assemble_edges([re_hop2, re_low, re_high])
        edge_ids = [e.edge_id for e in edges]
        assert edge_ids == ["eAAA", "eBBB", "eHOP2"]

    def test_max_edges_budget_applied(self):
        """I-CONTEXT-BUDGET-1: at most max_edges returned."""
        ranked_edges = [
            _ranked_edge(f"e{i}", "seed", f"n{i}", hop=1, priority=0.5)
            for i in range(10)
        ]
        edges = self._assemble_edges(ranked_edges, max_edges=3)
        assert len(edges) <= 3

    def test_max_edges_zero_returns_no_edges(self):
        """I-SEARCH-MAX-EDGES-1: max_edges=0 → empty edges."""
        re = _ranked_edge("e1", "seed", "b", hop=1, priority=0.9)
        edges = self._assemble_edges([re], max_edges=0)
        assert edges == []


# ---------------------------------------------------------------------------
# ContextAssembler — document ordering in build()
# ---------------------------------------------------------------------------

class TestBuildDocOrdering:
    def _assemble_docs(self, node_ids: list[str], chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        ranked = [_ranked_node(nid, hop=i, gis=1.0 - i * 0.1) for i, nid in enumerate(node_ids)]
        sel = _selection(node_ids[0], ranked)
        graph = _graph(nodes={nid: _node(nid) for nid in node_ids})
        ctx = ContextAssembler().build(graph, sel, _budget(), _doc_provider(chunks))
        return ctx.documents

    def test_docs_sorted_by_node_rank(self):
        """I-CONTEXT-ORDER-1: docs sorted by node's position in assembled nodes list."""
        nids = ["seed", "b", "c"]
        chunks = [
            _chunk("c", "content_c"),
            _chunk("b", "content_b"),
            _chunk("seed", "content_seed"),
        ]
        docs = self._assemble_docs(nids, chunks)
        assert [d.node_id for d in docs] == ["seed", "b", "c"]

    def test_docs_secondary_sort_by_kind(self):
        """Same node rank: kind sorted lexicographically."""
        chunks = [
            _chunk("seed", "x", kind="invariant"),
            _chunk("seed", "x", kind="code"),
        ]
        docs = self._assemble_docs(["seed"], chunks)
        assert docs[0].kind == "code"
        assert docs[1].kind == "invariant"

    def test_max_chars_budget_applied(self):
        """I-CONTEXT-BUDGET-1: char budget enforced via prefix."""
        big_content = "x" * 5_000
        chunks = [
            _chunk("seed", big_content),
            _chunk("seed", big_content),
        ]
        budget = Budget(max_nodes=10, max_edges=20, max_chars=256)
        sel = _selection("seed", [_ranked_node("seed", 0, 1.0)])
        graph = _graph(nodes={"seed": _node("seed")})
        ctx = ContextAssembler().build(graph, sel, budget, _doc_provider(chunks))
        assert ctx.budget_used["chars"] <= budget.max_chars


# ---------------------------------------------------------------------------
# context_id determinism (R-CONTEXT-ID-SEARCH, I-CONTEXT-DETERMINISM-1)
# ---------------------------------------------------------------------------

class TestContextIdDeterministic:
    """DoD requirement R-CONTEXT-ID-SEARCH: context_id is deterministic."""

    def _build(
        self,
        snapshot_hash: str = "hash1",
        seed: str = "seed",
        intent: QueryIntent = QueryIntent.EXPLAIN,
        raw_query: str | None = None,
    ) -> str:
        graph = _graph(nodes={"seed": _node("seed")}, snapshot_hash=snapshot_hash)
        sel = _selection(seed, [_ranked_node(seed, 0, 1.0)])
        ctx = ContextAssembler().build(
            graph, sel, _budget(), _doc_provider(), intent=intent, raw_query=raw_query
        )
        return ctx.context_id

    def test_context_id_deterministic(self):
        """Same (graph, seed, intent, query) → identical context_id every call."""
        id1 = self._build(snapshot_hash="snap42", seed="seed", intent=QueryIntent.EXPLAIN)
        id2 = self._build(snapshot_hash="snap42", seed="seed", intent=QueryIntent.EXPLAIN)
        assert id1 == id2

    def test_context_id_changes_with_snapshot_hash(self):
        id1 = self._build(snapshot_hash="hashA")
        id2 = self._build(snapshot_hash="hashB")
        assert id1 != id2

    def test_context_id_changes_with_intent(self):
        id1 = self._build(intent=QueryIntent.EXPLAIN)
        id2 = self._build(intent=QueryIntent.TRACE)
        assert id1 != id2

    def test_context_id_search_uses_query_hash(self):
        """SEARCH intent: sha256(snapshot_hash + ':SEARCH:' + sha256(query)[:16])[:32]."""
        snap = "snap"
        raw_query = "what is the kernel?"
        expected_query_hash = hashlib.sha256(raw_query.encode()).hexdigest()[:16]
        expected_payload = f"{snap}:SEARCH:{expected_query_hash}"
        expected_id = hashlib.sha256(expected_payload.encode()).hexdigest()[:32]

        actual_id = self._build(snapshot_hash=snap, intent=QueryIntent.SEARCH, raw_query=raw_query)
        assert actual_id == expected_id

    def test_context_id_search_deterministic(self):
        """Two calls with same SEARCH query → same context_id."""
        id1 = self._build(intent=QueryIntent.SEARCH, raw_query="find reducer")
        id2 = self._build(intent=QueryIntent.SEARCH, raw_query="find reducer")
        assert id1 == id2

    def test_context_id_search_differs_by_query(self):
        id1 = self._build(intent=QueryIntent.SEARCH, raw_query="query A")
        id2 = self._build(intent=QueryIntent.SEARCH, raw_query="query B")
        assert id1 != id2

    def test_context_id_non_search_uses_seed_and_intent(self):
        """Non-SEARCH: sha256(snapshot_hash + ':' + seed + ':' + intent.value)[:32]."""
        snap = "snap"
        seed = "seed"
        intent = QueryIntent.EXPLAIN
        expected_payload = f"{snap}:{seed}:{intent.value}"
        expected_id = hashlib.sha256(expected_payload.encode()).hexdigest()[:32]

        actual_id = self._build(snapshot_hash=snap, seed=seed, intent=intent)
        assert actual_id == expected_id


# ---------------------------------------------------------------------------
# _compute_context_id (unit-level)
# ---------------------------------------------------------------------------

class TestComputeContextId:
    def test_search_with_raw_query(self):
        snap = "s1"
        query = "my query"
        q_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        payload = f"{snap}:SEARCH:{q_hash}"
        expected = hashlib.sha256(payload.encode()).hexdigest()[:32]
        assert _compute_context_id(snap, "seed", QueryIntent.SEARCH, query) == expected

    def test_non_search_uses_seed_and_intent(self):
        snap = "s2"
        seed = "my_seed"
        intent = QueryIntent.TRACE
        payload = f"{snap}:{seed}:{intent.value}"
        expected = hashlib.sha256(payload.encode()).hexdigest()[:32]
        assert _compute_context_id(snap, seed, intent, None) == expected

    def test_search_without_raw_query_falls_back_to_non_search_formula(self):
        """SEARCH + raw_query=None → falls through to non-SEARCH formula."""
        snap = "s3"
        seed = "seed"
        intent = QueryIntent.SEARCH
        payload = f"{snap}:{seed}:{intent.value}"
        expected = hashlib.sha256(payload.encode()).hexdigest()[:32]
        assert _compute_context_id(snap, seed, intent, None) == expected

    def test_result_is_32_chars(self):
        cid = _compute_context_id("h", "s", QueryIntent.EXPLAIN, None)
        assert len(cid) == 32


# ---------------------------------------------------------------------------
# Seed guarantee (I-CONTEXT-SEED-1)
# ---------------------------------------------------------------------------

class TestSeedGuarantee:
    def test_seed_always_present(self):
        """Seed must appear in assembled nodes even at max_nodes=1."""
        seed_rn = _ranked_node("seed", hop=0, gis=1.0)
        other = _ranked_node("other", hop=1, gis=0.9)
        graph = _graph(nodes={"seed": _node("seed"), "other": _node("other")})
        sel = _selection("seed", [seed_rn, other])
        ctx = ContextAssembler().build(graph, sel, _budget(max_nodes=1), _doc_provider())
        node_ids = [n.node_id for n in ctx.nodes]
        assert "seed" in node_ids

    def test_seed_is_first_node(self):
        """Seed sorts first: hop=0, gis=1.0 → always position 0."""
        seed_rn = _ranked_node("seed", hop=0, gis=1.0)
        other = _ranked_node("zzz", hop=0, gis=1.0)
        graph = _graph(nodes={"seed": _node("seed"), "zzz": _node("zzz")})
        sel = _selection("seed", [seed_rn, other])
        ctx = ContextAssembler().build(graph, sel, _budget(max_nodes=10), _doc_provider())
        assert ctx.nodes[0].node_id == "seed"


# ---------------------------------------------------------------------------
# AssembledContext fields
# ---------------------------------------------------------------------------

class TestAssembledContextFields:
    def _build_simple(self) -> AssembledContext:
        seed_rn = _ranked_node("seed", hop=0, gis=1.0)
        graph = _graph(nodes={"seed": _node("seed")})
        sel = _selection("seed", [seed_rn])
        return ContextAssembler().build(
            graph, sel, _budget(), _doc_provider(),
            intent=QueryIntent.EXPLAIN,
            effective_intent=QueryIntent.EXPLAIN,
            intent_transform_reason="none",
            raw_query=None,
        )

    def test_budget_used_keys(self):
        ctx = self._build_simple()
        assert set(ctx.budget_used.keys()) == {"nodes", "edges", "chars"}

    def test_intent_field(self):
        ctx = self._build_simple()
        assert ctx.intent == QueryIntent.EXPLAIN

    def test_graph_snapshot_hash_field(self):
        ctx = self._build_simple()
        assert ctx.graph_snapshot_hash == "abc123"

    def test_context_id_is_non_empty_string(self):
        ctx = self._build_simple()
        assert isinstance(ctx.context_id, str) and len(ctx.context_id) > 0


# ---------------------------------------------------------------------------
# I-CTX-MIGRATION-1: no build_context.py import in assembler.py
# ---------------------------------------------------------------------------

class TestImportConstraint:
    def test_no_build_context_import_in_assembler(self):
        """I-CTX-MIGRATION-1: assembler.py MUST NOT import from build_context."""
        result = subprocess.run(
            ["grep", "-nE", r"^(from|import).*build_context", "src/sdd/context_kernel/assembler.py"],
            capture_output=True, text=True, cwd="/root/project",
        )
        assert result.returncode != 0, (
            f"Found 'build_context' import statement in assembler.py:\n{result.stdout}"
        )
