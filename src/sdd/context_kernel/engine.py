"""ContextEngine — pure pipeline (BC-36-3, §2.7).

Invariants enforced:
  I-ENGINE-PURE-1:    query() MUST NOT call IndexBuilder, GraphService, GraphCache,
                      PolicyResolver, or any filesystem API.
  I-ENGINE-INPUTS-1:  ContextEngine MUST NOT import SpatialIndex; DocProvider is injected.
  I-ENGINE-POLICY-1:  policy.budget → ContextAssembler; policy.rag_mode → LightRAGProjection.
  I-CONTEXT-EXPLAIN-KIND-1: EXPLAIN with empty S1 → TRACE fallback + warning.
  I-SEARCH-AUTO-EXACT-1:   SEARCH with single candidate → upgrade to RESOLVE_EXACT.
  I-SEARCH-NO-EMBED-1:     fuzzy_score via BM25 over (label + summary) corpus.
"""
from __future__ import annotations

import math
import warnings
from collections import Counter

from sdd.context_kernel.assembler import ContextAssembler
from sdd.context_kernel.documents import DocProvider
from sdd.context_kernel.intent import QueryIntent, SearchCandidate
from sdd.context_kernel.rag_types import LightRAGClient, LightRAGProjection, NavigationResponse
from sdd.context_kernel.selection import RankedNode, Selection, _build_selection
from sdd.graph.types import DeterministicGraph, Edge
from sdd.policy import NavigationPolicy

# ── Edge-kind allowlists per strategy ────────────────────────────────────────

_EXPLAIN_OUT_KINDS: frozenset[str] = frozenset({"emits", "guards", "implements", "tested_by"})
_EXPLAIN_TASK_IN_KINDS: frozenset[str] = frozenset({"depends_on"})
_INVARIANT_OUT_KINDS: frozenset[str] = frozenset({"verified_by", "introduced_in"})


# ── Strategy expand functions ────────────────────────────────────────────────

def _expand_resolve_exact(graph: DeterministicGraph, node_id: str, hop: int) -> list[Edge]:
    """Seed + all out-edges + in-edges at hop=0 only."""
    if hop > 0:
        return []
    return list(graph.edges_out.get(node_id, [])) + list(graph.edges_in.get(node_id, []))


def _expand_explain(graph: DeterministicGraph, node_id: str, hop: int) -> list[Edge]:
    """Out-edges in {emits, guards, implements, tested_by}; TASK seed also in-edges {depends_on}."""
    edges: list[Edge] = [
        e for e in graph.edges_out.get(node_id, []) if e.kind in _EXPLAIN_OUT_KINDS
    ]
    if hop == 0:
        seed = graph.nodes.get(node_id)
        if seed and seed.kind == "TASK":
            edges += [e for e in graph.edges_in.get(node_id, []) if e.kind in _EXPLAIN_TASK_IN_KINDS]
    return edges


def _expand_trace(graph: DeterministicGraph, node_id: str, hop: int) -> list[Edge]:
    """Reverse neighbors (in-edges) up to hop ≤ 2."""
    if hop >= 2:
        return []
    return list(graph.edges_in.get(node_id, []))


def _expand_invariant(graph: DeterministicGraph, node_id: str, hop: int) -> list[Edge]:
    """Out-edges in {verified_by, introduced_in}."""
    return [e for e in graph.edges_out.get(node_id, []) if e.kind in _INVARIANT_OUT_KINDS]


_STRATEGY_EXPAND = {
    QueryIntent.RESOLVE_EXACT: _expand_resolve_exact,
    QueryIntent.EXPLAIN: _expand_explain,
    QueryIntent.TRACE: _expand_trace,
    QueryIntent.INVARIANT: _expand_invariant,
}


# ── BM25 (I-SEARCH-NO-EMBED-1) ───────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_search(
    query: str,
    graph: DeterministicGraph,
    max_results: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[SearchCandidate]:
    """BM25 over (label + ' ' + summary) corpus (I-SEARCH-NO-EMBED-1).

    Deterministic tie-breaking: (-score, node_id ASC).
    """
    nodes = graph.nodes
    if not nodes:
        return []

    corpus: list[tuple[str, list[str]]] = []
    for nid, node in nodes.items():
        corpus.append((nid, _tokenize(f"{node.label} {node.summary}")))

    N = len(corpus)
    avg_dl = sum(len(tokens) for _, tokens in corpus) / N

    df: Counter[str] = Counter()
    for _, tokens in corpus:
        df.update(set(tokens))
    idf: dict[str, float] = {
        term: math.log((N - count + 0.5) / (count + 0.5) + 1)
        for term, count in df.items()
    }

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[float, str]] = []
    for nid, tokens in corpus:
        dl = len(tokens)
        tf: Counter[str] = Counter(tokens)
        denom = k1 * (1 - b + b * dl / avg_dl) if avg_dl > 0 else k1
        score = sum(
            idf.get(qt, 0.0) * tf.get(qt, 0) * (k1 + 1) / (tf.get(qt, 0) + denom)
            for qt in query_tokens
        )
        if score > 0.0:
            scored.append((score, nid))

    scored.sort(key=lambda x: (-x[0], x[1]))  # deterministic: -score then node_id ASC

    result: list[SearchCandidate] = []
    for score, nid in scored[:max_results]:
        node = nodes[nid]
        result.append(SearchCandidate(
            node_id=nid,
            kind=node.kind,
            label=node.label,
            summary=node.summary,
            fuzzy_score=score,
        ))
    return result


def _search_selection(graph: DeterministicGraph, candidates: list[SearchCandidate]) -> Selection:
    """Minimal seed-only selection for multi-candidate SEARCH (I-SEARCH-RESPONSE-1)."""
    if not candidates:
        return Selection(seed="", nodes={}, edges={})
    seed = candidates[0].node_id
    nodes = {}
    if seed in graph.nodes:
        nodes[seed] = RankedNode(node_id=seed, hop=0, global_importance_score=1.0)
    return Selection(seed=seed, nodes=nodes, edges={})


# ── ContextEngine ─────────────────────────────────────────────────────────────

class ContextEngine:
    """Pure pipeline: (DeterministicGraph, NavigationPolicy, DocProvider) → NavigationResponse.

    No I/O, no SpatialIndex, no GraphService, no PolicyResolver (I-ENGINE-PURE-1).
    DocProvider is injected; all inputs arrive pre-built (I-ENGINE-INPUTS-1).
    """

    def __init__(
        self,
        assembler: ContextAssembler,
        rag_projection: LightRAGProjection | None = None,
    ) -> None:
        self._assembler = assembler
        self._rag_projection = rag_projection

    def query(
        self,
        graph: DeterministicGraph,
        policy: NavigationPolicy,
        doc_provider: DocProvider,
        node_id: str,
        intent: QueryIntent = QueryIntent.RESOLVE_EXACT,
        rag_client: LightRAGClient | None = None,
    ) -> NavigationResponse:
        """Execute the pure context pipeline (I-ENGINE-PURE-1).

        node_id: graph node identifier for all intents except SEARCH.
                 For SEARCH, node_id is treated as the raw free-text query.
        intent:  defaults to RESOLVE_EXACT; caller is responsible for resolving
                 via parse_query_intent() + PolicyResolver before invoking engine.
        """
        candidates: list[SearchCandidate] | None = None
        effective_intent = intent
        intent_transform_reason: str | None = None
        raw_query: str | None = None

        if intent is QueryIntent.SEARCH:
            raw_query = node_id
            search_candidates = _bm25_search(raw_query, graph, policy.budget.max_nodes)
            candidates = search_candidates

            if len(search_candidates) == 1:
                # I-SEARCH-AUTO-EXACT-1: single candidate → upgrade to RESOLVE_EXACT
                upgraded_id = search_candidates[0].node_id
                selection = _build_selection(
                    graph, policy.budget, upgraded_id, _expand_resolve_exact
                )
                effective_intent = QueryIntent.RESOLVE_EXACT
                intent_transform_reason = (
                    "SEARCH auto-upgraded to RESOLVE_EXACT (single candidate)"
                )
            else:
                selection = _search_selection(graph, search_candidates)
        else:
            expand = _STRATEGY_EXPAND[intent]
            selection = _build_selection(graph, policy.budget, node_id, expand)

            # I-CONTEXT-EXPLAIN-KIND-1: EXPLAIN with empty S1 → TRACE fallback
            if intent is QueryIntent.EXPLAIN and len(selection.nodes) <= 1:
                warnings.warn(
                    f"EXPLAIN: empty S1 for node {node_id!r}; falling back to TRACE",
                    RuntimeWarning,
                    stacklevel=2,
                )
                selection = _build_selection(graph, policy.budget, node_id, _expand_trace)
                effective_intent = QueryIntent.TRACE
                intent_transform_reason = "EXPLAIN fallback to TRACE: S1 was empty"

        assembled = self._assembler.build(
            graph=graph,
            selection=selection,
            budget=policy.budget,
            doc_provider=doc_provider,
            intent=intent,
            effective_intent=effective_intent,
            intent_transform_reason=intent_transform_reason,
            raw_query=raw_query,
        )

        rag_result = None
        if self._rag_projection is not None and policy.rag_mode.value != "OFF":
            rag_result = self._rag_projection.query(
                node_id, assembled, policy.rag_mode, rag_client  # type: ignore[arg-type]
            )

        return NavigationResponse(
            context=assembled,  # type: ignore[arg-type]  # AssembledContext satisfies Context duck-type
            rag_summary=rag_result.summary if rag_result else None,
            rag_mode=rag_result.rag_mode if rag_result else None,
            candidates=candidates,
        )
