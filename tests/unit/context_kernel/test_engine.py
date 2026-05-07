"""Integration-level tests for ContextEngine (T-5118, T-5504).

Covers:
  - DoD 3: ContextEngine instantiable with mocks
  - I-ENGINE-PURE-1: no SpatialIndex, GraphService, PolicyResolver imports in engine.py
  - I-CONTEXT-EXPLAIN-KIND-1: EXPLAIN with empty S1 → TRACE fallback + warning
  - I-SEARCH-AUTO-EXACT-1: SEARCH with single candidate → upgrade to RESOLVE_EXACT
  - I-SEARCH-NO-EMBED-1: fuzzy_score via BM25
  - I-CONTEXT-DETERMINISM-1: identical inputs → identical assembler call args
  - I-ENGINE-EDGE-FILTER-1: edge_types BFS filter applied inside expand, not as post-filter
"""
from __future__ import annotations

import pathlib
import warnings
from unittest.mock import MagicMock

import pytest

from sdd.context_kernel.assembler import AssembledContext, ContextAssembler
from sdd.context_kernel.documents import DocProvider
from sdd.context_kernel.engine import ContextEngine, _expand_trace
from sdd.context_kernel.intent import QueryIntent
from sdd.context_kernel.rag_types import LightRAGProjection, RAGResult
from sdd.context_kernel.selection import Selection
from sdd.graph.types import DeterministicGraph, Edge, Node
from sdd.policy import Budget, NavigationPolicy, RagMode

_PROJECT_ROOT = pathlib.Path(__file__).parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id: str, kind: str = "FILE", label: str = "", summary: str = "") -> Node:
    return Node(node_id=node_id, kind=kind, label=label or node_id, summary=summary, meta={})


def _graph(*node_ids: str, snapshot_hash: str = "testhash") -> DeterministicGraph:
    nodes = {nid: _node(nid) for nid in node_ids}
    return DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash=snapshot_hash)


def _policy(max_nodes: int = 10, rag_mode: RagMode = RagMode.OFF) -> NavigationPolicy:
    return NavigationPolicy(Budget(max_nodes=max_nodes, max_edges=20, max_chars=4096), rag_mode)


def _mock_assembled(intent: QueryIntent = QueryIntent.RESOLVE_EXACT) -> AssembledContext:
    return AssembledContext(
        intent=intent,
        effective_intent=intent,
        intent_transform_reason=None,
        nodes=[],
        edges=[],
        documents=[],
        budget_used={},
        selection_exhausted=False,
        graph_snapshot_hash="testhash",
        context_id="ctx123",
    )


def _make_engine(
    rag_projection: LightRAGProjection | None = None,
) -> tuple[ContextEngine, MagicMock]:
    assembler = MagicMock(spec=ContextAssembler)
    assembler.build.return_value = _mock_assembled()
    return ContextEngine(assembler=assembler, rag_projection=rag_projection), assembler


def _doc_provider() -> MagicMock:
    return MagicMock(spec=DocProvider)


# ---------------------------------------------------------------------------
# DoD 3: Instantiation
# ---------------------------------------------------------------------------

class TestEngineInstantiation:
    def test_instantiable_with_mock_assembler(self) -> None:
        """DoD 3: ContextEngine instantiable with injected assembler mock."""
        assembler = MagicMock(spec=ContextAssembler)
        engine = ContextEngine(assembler=assembler)
        assert engine is not None

    def test_rag_projection_defaults_to_none(self) -> None:
        assembler = MagicMock(spec=ContextAssembler)
        engine = ContextEngine(assembler=assembler)
        assert engine._rag_projection is None

    def test_rag_projection_injected(self) -> None:
        assembler = MagicMock(spec=ContextAssembler)
        rag = MagicMock(spec=LightRAGProjection)
        engine = ContextEngine(assembler=assembler, rag_projection=rag)
        assert engine._rag_projection is rag


# ---------------------------------------------------------------------------
# I-ENGINE-PURE-1: no forbidden imports in engine.py
# ---------------------------------------------------------------------------

def _imported_names(rel_path: str) -> set[str]:
    """Return all names referenced in import statements of the given source file."""
    import ast
    src = (_PROJECT_ROOT / rel_path).read_text()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return names


class TestEnginePurity:
    _SRC = "src/sdd/context_kernel/engine.py"

    def test_does_not_import_spatial_index(self) -> None:
        """I-ENGINE-PURE-1: engine.py must not import SpatialIndex."""
        assert "SpatialIndex" not in _imported_names(self._SRC)

    def test_does_not_import_graph_service(self) -> None:
        """I-ENGINE-PURE-1: engine.py must not import GraphService."""
        assert "GraphService" not in _imported_names(self._SRC)

    def test_does_not_import_policy_resolver(self) -> None:
        """I-ENGINE-PURE-1: engine.py must not import PolicyResolver."""
        assert "PolicyResolver" not in _imported_names(self._SRC)


# ---------------------------------------------------------------------------
# RESOLVE_EXACT pipeline
# ---------------------------------------------------------------------------

class TestResolveExact:
    def test_assembler_called_with_resolve_exact_intent(self) -> None:
        engine, assembler = _make_engine()
        graph = _graph("FILE:main")

        engine.query(graph, _policy(), _doc_provider(), "FILE:main", QueryIntent.RESOLVE_EXACT)

        kwargs = assembler.build.call_args.kwargs
        assert kwargs["intent"] is QueryIntent.RESOLVE_EXACT
        assert kwargs["effective_intent"] is QueryIntent.RESOLVE_EXACT
        assert kwargs["intent_transform_reason"] is None

    def test_response_context_is_assembled(self) -> None:
        engine, assembler = _make_engine()
        assembled = _mock_assembled()
        assembler.build.return_value = assembled
        graph = _graph("FILE:x")

        response = engine.query(graph, _policy(), _doc_provider(), "FILE:x")

        assert response.context is assembled
        assert response.rag_summary is None
        assert response.rag_mode is None
        assert response.candidates is None

    def test_assembler_receives_doc_provider(self) -> None:
        engine, assembler = _make_engine()
        graph = _graph("FILE:dp")
        dp = _doc_provider()

        engine.query(graph, _policy(), dp, "FILE:dp")

        assert assembler.build.call_args.kwargs["doc_provider"] is dp


# ---------------------------------------------------------------------------
# I-CONTEXT-EXPLAIN-KIND-1: EXPLAIN → TRACE fallback
# ---------------------------------------------------------------------------

class TestExplainFallback:
    def test_fallback_when_no_explain_edges(self) -> None:
        """I-CONTEXT-EXPLAIN-KIND-1: node with no EXPLAIN-kind out-edges → TRACE fallback."""
        engine, assembler = _make_engine()
        # Single node, no edges → S1 empty → fallback
        graph = _graph("FILE:no_edges")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine.query(graph, _policy(), _doc_provider(), "FILE:no_edges", QueryIntent.EXPLAIN)

        assert any(
            "EXPLAIN" in str(w.message) and "TRACE" in str(w.message) for w in caught
        ), "Expected EXPLAIN→TRACE fallback RuntimeWarning"

        kwargs = assembler.build.call_args.kwargs
        assert kwargs["effective_intent"] is QueryIntent.TRACE
        assert kwargs["intent_transform_reason"] == "EXPLAIN fallback to TRACE: S1 was empty"
        assert kwargs["intent"] is QueryIntent.EXPLAIN

    def test_no_fallback_when_explain_edge_present(self) -> None:
        """No fallback when seed node has EXPLAIN-kind out-edges (S1 non-empty)."""
        engine, assembler = _make_engine()
        edge = Edge(
            edge_id="e1", src="COMMAND:do", dst="EVENT:done",
            kind="emits", priority=0.95, source="test", meta={},
        )
        nodes = {
            "COMMAND:do": _node("COMMAND:do", kind="COMMAND"),
            "EVENT:done": _node("EVENT:done", kind="EVENT"),
        }
        graph = DeterministicGraph(
            nodes=nodes,
            edges_out={"COMMAND:do": [edge]},
            edges_in={"EVENT:done": [edge]},
            source_snapshot_hash="explain_hash",
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine.query(graph, _policy(), _doc_provider(), "COMMAND:do", QueryIntent.EXPLAIN)

        assert not any("TRACE" in str(w.message) for w in caught), \
            "Must not fall back to TRACE when S1 is non-empty"

        kwargs = assembler.build.call_args.kwargs
        assert kwargs["effective_intent"] is QueryIntent.EXPLAIN


# ---------------------------------------------------------------------------
# SEARCH pipeline (I-SEARCH-AUTO-EXACT-1, I-SEARCH-NO-EMBED-1)
# ---------------------------------------------------------------------------

class TestSearch:
    def _single_node_graph(self) -> DeterministicGraph:
        nodes = {
            "FILE:alpha": _node("FILE:alpha", label="alpha authentication", summary="login token handler"),
        }
        return DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash="single")

    def test_single_candidate_upgrades_to_resolve_exact(self) -> None:
        """I-SEARCH-AUTO-EXACT-1: single BM25 match → effective_intent = RESOLVE_EXACT."""
        engine, assembler = _make_engine()
        graph = self._single_node_graph()

        engine.query(graph, _policy(max_nodes=15), _doc_provider(), "authentication", QueryIntent.SEARCH)

        kwargs = assembler.build.call_args.kwargs
        assert kwargs["effective_intent"] is QueryIntent.RESOLVE_EXACT
        assert "auto-upgraded" in (kwargs["intent_transform_reason"] or "")
        assert kwargs["intent"] is QueryIntent.SEARCH

    def test_multi_candidate_returns_candidates_list(self) -> None:
        """Multiple BM25 matches → no upgrade, candidates returned in response."""
        engine, assembler = _make_engine()
        nodes = {
            "FILE:a": _node("FILE:a", label="login auth handler", summary="authentication token"),
            "FILE:b": _node("FILE:b", label="auth token store", summary="authentication cache"),
        }
        graph = DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash="multi")

        response = engine.query(graph, _policy(max_nodes=15), _doc_provider(), "authentication", QueryIntent.SEARCH)

        assert response.candidates is not None
        assert len(response.candidates) >= 2

    def test_no_match_returns_empty_candidates(self) -> None:
        """Zero BM25 matches → candidates == []."""
        engine, assembler = _make_engine()
        nodes = {"FILE:x": _node("FILE:x", label="database executor", summary="SQL query runner")}
        graph = DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash="nomatch")

        response = engine.query(graph, _policy(), _doc_provider(), "xyzzy_impossible_term_99", QueryIntent.SEARCH)

        assert response.candidates == []

    def test_candidates_sorted_by_bm25_score_descending(self) -> None:
        """I-SEARCH-NO-EMBED-1: candidates ordered by fuzzy_score DESC, deterministic."""
        engine, assembler = _make_engine()
        nodes = {
            "FILE:a": _node("FILE:a", label="core", summary="core module"),
            "FILE:b": _node("FILE:b", label="core core", summary="core core core"),
        }
        graph = DeterministicGraph(nodes=nodes, edges_out={}, edges_in={}, source_snapshot_hash="sorted")

        response = engine.query(graph, _policy(max_nodes=15), _doc_provider(), "core", QueryIntent.SEARCH)

        assert response.candidates is not None and len(response.candidates) >= 2
        scores = [c.fuzzy_score for c in response.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_search_node_id_used_as_raw_query(self) -> None:
        """For SEARCH, node_id parameter is treated as the free-text query string."""
        engine, assembler = _make_engine()
        graph = self._single_node_graph()

        engine.query(graph, _policy(max_nodes=15), _doc_provider(), "authentication", QueryIntent.SEARCH)

        kwargs = assembler.build.call_args.kwargs
        assert kwargs["raw_query"] == "authentication"


# ---------------------------------------------------------------------------
# I-CONTEXT-DETERMINISM-1
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_identical_calls_produce_identical_assembler_args(self) -> None:
        """I-CONTEXT-DETERMINISM-1: same (graph, policy, node_id) → same assembler.build() args."""
        engine, assembler = _make_engine()
        graph = _graph("FILE:det")
        policy = _policy()
        dp = _doc_provider()

        engine.query(graph, policy, dp, "FILE:det")
        first_call = assembler.build.call_args

        engine.query(graph, policy, dp, "FILE:det")
        second_call = assembler.build.call_args

        assert first_call == second_call


# ---------------------------------------------------------------------------
# RAG pipeline
# ---------------------------------------------------------------------------

class TestRagPipeline:
    def test_no_rag_when_projection_none(self) -> None:
        """rag_summary is None when rag_projection=None."""
        engine, _ = _make_engine(rag_projection=None)
        graph = _graph("FILE:r")

        response = engine.query(graph, _policy(rag_mode=RagMode.LOCAL), _doc_provider(), "FILE:r")

        assert response.rag_summary is None
        assert response.rag_mode is None

    def test_rag_called_when_projection_set_and_mode_not_off(self) -> None:
        """rag_projection.query() called and result surfaced in response."""
        rag_projection = MagicMock(spec=LightRAGProjection)
        rag_projection.query.return_value = RAGResult(summary="rag answer", rag_mode="LOCAL")
        engine, _ = _make_engine(rag_projection=rag_projection)
        graph = _graph("FILE:s")
        rag_client = MagicMock()

        response = engine.query(
            graph, _policy(rag_mode=RagMode.LOCAL), _doc_provider(), "FILE:s",
            rag_client=rag_client,
        )

        rag_projection.query.assert_called_once()
        assert response.rag_summary == "rag answer"
        assert response.rag_mode == "LOCAL"

    def test_rag_not_called_when_mode_off(self) -> None:
        """rag_projection.query() NOT called when rag_mode == OFF."""
        rag_projection = MagicMock(spec=LightRAGProjection)
        engine, _ = _make_engine(rag_projection=rag_projection)

        engine.query(_graph("FILE:t"), _policy(rag_mode=RagMode.OFF), _doc_provider(), "FILE:t")

        rag_projection.query.assert_not_called()


# ---------------------------------------------------------------------------
# I-ENGINE-EDGE-FILTER-1: edge_types BFS filter correctness (Spec_v55 §9 #1-4)
# ---------------------------------------------------------------------------

class TestEdgeTypesBFSFilter:
    """I-ENGINE-EDGE-FILTER-1: edge_types filter applied inside BFS expand functions."""

    def _graph_with_mixed_out_edges(self) -> DeterministicGraph:
        """CMD:A --emits--> EVT:B, CMD:A --uses--> FILE:C"""
        nodes = {
            "CMD:A": _node("CMD:A", kind="COMMAND"),
            "EVT:B": _node("EVT:B", kind="EVENT"),
            "FILE:C": _node("FILE:C", kind="FILE"),
        }
        e_emits = Edge(
            edge_id="e1", src="CMD:A", dst="EVT:B", kind="emits",
            priority=1.0, source="test", meta={},
        )
        e_uses = Edge(
            edge_id="e2", src="CMD:A", dst="FILE:C", kind="uses",
            priority=1.0, source="test", meta={},
        )
        return DeterministicGraph(
            nodes=nodes,
            edges_out={"CMD:A": [e_emits, e_uses]},
            edges_in={"EVT:B": [e_emits], "FILE:C": [e_uses]},
            source_snapshot_hash="mixed_hash",
        )

    def test_bfs_excludes_node_reachable_via_non_allowed_edge(self) -> None:
        """(Spec_v55 §9 #1) Hop=1 node reachable only via non-allowed edge is excluded from selection."""
        engine, assembler = _make_engine()
        graph = self._graph_with_mixed_out_edges()

        engine.query(
            graph, _policy(), _doc_provider(), "CMD:A",
            QueryIntent.EXPLAIN,
            edge_types=frozenset({"emits"}),
        )

        selection: Selection = assembler.build.call_args.kwargs["selection"]
        assert "EVT:B" in selection.nodes, "EVT:B reachable via allowed 'emits' must be included"
        assert "FILE:C" not in selection.nodes, "FILE:C via non-allowed 'uses' must be excluded"

    def test_backward_compat_edge_types_none_matches_default(self) -> None:
        """(Spec_v55 §9 #2) edge_types=None produces identical output to calling without edge_types."""
        nodes = {
            "CMD:do": _node("CMD:do", kind="COMMAND"),
            "EVT:done": _node("EVT:done", kind="EVENT"),
        }
        e = Edge(
            edge_id="e1", src="CMD:do", dst="EVT:done", kind="emits",
            priority=0.95, source="test", meta={},
        )
        graph = DeterministicGraph(
            nodes=nodes,
            edges_out={"CMD:do": [e]},
            edges_in={"EVT:done": [e]},
            source_snapshot_hash="compat_hash",
        )

        engine1, asm1 = _make_engine()
        engine1.query(graph, _policy(), _doc_provider(), "CMD:do", QueryIntent.EXPLAIN)
        sel_default: Selection = asm1.build.call_args.kwargs["selection"]

        engine2, asm2 = _make_engine()
        engine2.query(graph, _policy(), _doc_provider(), "CMD:do", QueryIntent.EXPLAIN, edge_types=None)
        sel_none: Selection = asm2.build.call_args.kwargs["selection"]

        assert set(sel_default.nodes.keys()) == set(sel_none.nodes.keys()), (
            "edge_types=None must produce the same node set as calling without edge_types"
        )

    def test_expand_trace_allowed_kinds_filters_in_edges(self) -> None:
        """(Spec_v55 §9 #3) _expand_trace with allowed_kinds returns only matching in-edges."""
        e_imports = Edge(
            edge_id="e1", src="FILE:a", dst="FILE:dst", kind="imports",
            priority=1.0, source="test", meta={},
        )
        e_uses = Edge(
            edge_id="e2", src="FILE:b", dst="FILE:dst", kind="uses",
            priority=1.0, source="test", meta={},
        )
        nodes = {
            "FILE:dst": _node("FILE:dst"),
            "FILE:a": _node("FILE:a"),
            "FILE:b": _node("FILE:b"),
        }
        graph = DeterministicGraph(
            nodes=nodes,
            edges_out={"FILE:a": [e_imports], "FILE:b": [e_uses]},
            edges_in={"FILE:dst": [e_imports, e_uses]},
            source_snapshot_hash="trace_filter_hash",
        )

        result = _expand_trace(graph, "FILE:dst", 0, allowed_kinds=frozenset({"imports"}))

        assert len(result) == 1, f"Expected 1 edge, got {len(result)}"
        assert result[0].kind == "imports", "Only 'imports' in-edges must be returned"
