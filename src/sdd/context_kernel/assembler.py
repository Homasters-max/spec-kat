"""ContextAssembler — deterministic truncation + document ordering (BC-36-3, §2.5).

Invariants enforced:
  I-CTX-MIGRATION-1:      NO import from context.build_context (DoD 6).
  I-CONTEXT-TRUNCATE-1:   nodes (hop ASC, -gis, node_id ASC); edges (hop ASC, -priority, edge_id ASC).
  I-CONTEXT-ORDER-1:      docs (node_rank, kind, sha256(content)).
  I-CONTEXT-LINEAGE-1:    context_id = sha256(graph_snapshot_hash + ":" + seed + ":" + intent)[:32];
                           SEARCH uses sha256(graph_snapshot_hash + ":SEARCH:" + sha256(query)[:16])[:32].
  I-CONTEXT-SEED-1:       seed node always present regardless of budget.
  I-CONTEXT-BUDGET-1:     len(nodes) <= max_nodes, len(edges) <= max_edges, sum(chars) <= max_chars.
  I-CONTEXT-DETERMINISM-1: identical (graph, query, budget) → identical AssembledContext.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sdd.context_kernel.documents import DocumentChunk, DocProvider
from sdd.context_kernel.intent import QueryIntent
from sdd.context_kernel.selection import RankedEdge, RankedNode, Selection
from sdd.graph.types import DeterministicGraph, Edge, Node
from sdd.policy import Budget


@dataclass
class AssembledContext:
    """Full assembled context — fact layer only. No LLM inference.

    Deterministic: AssembledContext = f(graph, selection, budget, doc_provider, intent).
    graph_snapshot_hash ties this context to its source SpatialIndex snapshot (I-CONTEXT-LINEAGE-1).
    context_id is a stable cache key for (snapshot, query, intent).
    """

    intent: QueryIntent
    effective_intent: QueryIntent
    intent_transform_reason: str | None
    nodes: list[Node]
    edges: list[Edge]
    documents: list[DocumentChunk]
    budget_used: dict[str, int]
    selection_exhausted: bool
    graph_snapshot_hash: str
    context_id: str


def _node_sort_key(ranked: RankedNode) -> tuple[int, float, str]:
    """(hop ASC, -global_importance_score, node_id ASC) — I-CONTEXT-TRUNCATE-1."""
    return (ranked.hop, -ranked.global_importance_score, ranked.node_id)


def _edge_sort_key(ranked: RankedEdge) -> tuple[int, float, str]:
    """(hop ASC, -priority, edge_id ASC) — I-CONTEXT-TRUNCATE-1."""
    return (ranked.hop, -ranked.priority, ranked.edge_id)


def _doc_sort_key(chunk: DocumentChunk, node_rank: dict[str, int], total_nodes: int) -> tuple[int, str, str]:
    """(node_rank, kind, sha256(content)) — I-CONTEXT-ORDER-1."""
    rank = node_rank.get(chunk.node_id, total_nodes)
    content_hash = hashlib.sha256(chunk.content.encode()).hexdigest()
    return (rank, chunk.kind, content_hash)


def _compute_context_id(
    graph_snapshot_hash: str,
    seed_node_id: str,
    intent: QueryIntent,
    raw_query: str | None,
) -> str:
    """Compute stable context_id per I-CONTEXT-LINEAGE-1.

    SEARCH:     sha256(graph_snapshot_hash + ":SEARCH:" + sha256(raw_query)[:16])[:32]
    otherwise:  sha256(graph_snapshot_hash + ":" + seed_node_id + ":" + intent.value)[:32]
    """
    if intent is QueryIntent.SEARCH and raw_query is not None:
        raw_query_hash = hashlib.sha256(raw_query.encode()).hexdigest()[:16]
        payload = f"{graph_snapshot_hash}:SEARCH:{raw_query_hash}"
    else:
        payload = f"{graph_snapshot_hash}:{seed_node_id}:{intent.value}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _build_edge_index(graph: DeterministicGraph) -> dict[str, Edge]:
    """Build edge_id → Edge lookup from graph (graph has no flat edge dict)."""
    return {
        e.edge_id: e
        for edges_list in graph.edges_out.values()
        for e in edges_list
    }


class ContextAssembler:
    """Assembles a deterministic, budget-bounded AssembledContext.

    Pure function: no I/O, no state, no side effects (I-CONTEXT-DETERMINISM-1).
    DocProvider is the single filesystem I/O point (I-DOC-FS-IO-1) — it is passed in,
    never created here.
    """

    def build(
        self,
        graph: DeterministicGraph,
        selection: Selection,
        budget: Budget,
        doc_provider: DocProvider,
        intent: QueryIntent = QueryIntent.SEARCH,
        effective_intent: QueryIntent | None = None,
        intent_transform_reason: str | None = None,
        raw_query: str | None = None,
    ) -> AssembledContext:
        """Build deterministically-ordered, budget-bounded context.

        Steps:
          1. Sort ranked nodes; take prefix up to max_nodes; seed always first (I-CONTEXT-SEED-1).
          2. Sort ranked edges; take prefix up to max_edges (max_edges=0 → no edges, I-SEARCH-MAX-EDGES-1).
          3. Fetch DocumentChunks for included node_ids via doc_provider.
          4. Sort docs by (node_rank, kind, sha256(content)); apply char budget prefix.
          5. Compute selection_exhausted and context_id; return AssembledContext.
        """
        if effective_intent is None:
            effective_intent = intent

        seed_id = selection.seed

        # ── Step 1: node ordering + budget ───────────────────────────────────
        sorted_ranked: list[RankedNode] = sorted(
            selection.nodes.values(), key=_node_sort_key
        )

        # Guarantee seed is at position 0 (I-CONTEXT-SEED-1).
        # Seed has hop=0, gis=1.0 so it naturally sorts first; this guard handles edge cases.
        seed_ranked = selection.nodes.get(seed_id)
        if seed_ranked and (not sorted_ranked or sorted_ranked[0].node_id != seed_id):
            others = [r for r in sorted_ranked if r.node_id != seed_id]
            sorted_ranked = [seed_ranked] + others

        # Take prefix up to max_nodes (seed always included since it is first).
        included_ranked = sorted_ranked[: budget.max_nodes]
        included_node_ids: list[str] = [r.node_id for r in included_ranked]
        included_node_id_set: frozenset[str] = frozenset(included_node_ids)

        # Resolve Node objects from graph (preserve sorted order).
        nodes: list[Node] = [
            graph.nodes[nid] for nid in included_node_ids if nid in graph.nodes
        ]

        # ── Step 2: edge ordering + budget ────────────────────────────────────
        edge_index = _build_edge_index(graph)
        edges: list[Edge] = []
        if budget.max_edges > 0:
            sorted_ranked_edges: list[RankedEdge] = sorted(
                selection.edges.values(), key=_edge_sort_key
            )
            for ranked_edge in sorted_ranked_edges:
                if len(edges) >= budget.max_edges:
                    break
                edge = edge_index.get(ranked_edge.edge_id)
                if edge is not None:
                    edges.append(edge)
        # max_edges == 0 → edges stays [] (I-SEARCH-MAX-EDGES-1)

        # ── Step 3–4: documents ───────────────────────────────────────────────
        node_rank: dict[str, int] = {nid: i for i, nid in enumerate(included_node_ids)}
        total_nodes = len(included_node_ids)

        raw_chunks = doc_provider.get_chunks(included_node_ids)
        sorted_chunks = sorted(
            raw_chunks,
            key=lambda c: _doc_sort_key(c, node_rank, total_nodes),
        )

        documents: list[DocumentChunk] = []
        chars_used = 0
        for chunk in sorted_chunks:
            if chars_used + chunk.char_count > budget.max_chars:
                break
            documents.append(chunk)
            chars_used += chunk.char_count

        # ── Step 5: metadata ──────────────────────────────────────────────────
        all_selected: frozenset[str] = frozenset(selection.nodes)
        selection_exhausted: bool = all(
            e.dst in all_selected
            for nid in all_selected
            for e in graph.edges_out.get(nid, [])
        )

        context_id = _compute_context_id(
            graph.source_snapshot_hash, seed_id, intent, raw_query
        )

        return AssembledContext(
            intent=intent,
            effective_intent=effective_intent,
            intent_transform_reason=intent_transform_reason,
            nodes=nodes,
            edges=edges,
            documents=documents,
            budget_used={
                "nodes": len(nodes),
                "edges": len(edges),
                "chars": chars_used,
            },
            selection_exhausted=selection_exhausted,
            graph_snapshot_hash=graph.source_snapshot_hash,
            context_id=context_id,
        )
