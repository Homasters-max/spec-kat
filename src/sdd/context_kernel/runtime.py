"""ContextRuntime — lifecycle orchestrator for Context Kernel (BC-36-3, §2.8).

I-RUNTIME-BOUNDARY-1:  CLI MUST call ContextRuntime.query(), NOT ContextEngine.query() directly.
                        ContextRuntime MUST NOT import GraphService (grep-enforced; R-RUNTIME-CONTRADICTION fix).
I-RUNTIME-ORCHESTRATOR-1: Single entry point for all external runtimes (CLI, HTTP, agent).
"""
from __future__ import annotations

from typing import Callable

from sdd.context_kernel.documents import DefaultContentMapper, DocProvider
from sdd.context_kernel.engine import ContextEngine
from sdd.context_kernel.rag_types import LightRAGClient, NavigationResponse
from sdd.graph.types import DeterministicGraph
from sdd.policy import NavigationPolicy
from sdd.spatial.index import SpatialIndex

# Module-level default; allows Phase 52 CLI to instantiate ContextRuntime without custom wiring.
_default_doc_provider_factory: Callable[[SpatialIndex], DocProvider] = (
    lambda index: DocProvider(index, DefaultContentMapper())
)


class ContextRuntime:
    """Entry point to Context Kernel.

    Creates DocProvider from SpatialIndex on each query().
    Does NOT hold GraphService — graph is built by caller before query() is invoked.
    Holds rag_client — injected at construction, not per-query.
    """

    def __init__(
        self,
        engine: ContextEngine,
        doc_provider_factory: Callable[[SpatialIndex], DocProvider] = _default_doc_provider_factory,
        rag_client: LightRAGClient | None = None,
    ) -> None:
        self._engine = engine
        self._doc_provider_factory = doc_provider_factory
        self._rag_client = rag_client

    def query(
        self,
        graph: DeterministicGraph,
        policy: NavigationPolicy,
        index: SpatialIndex,
        node_id: str,
        edge_types: frozenset[str] | None = None,
    ) -> NavigationResponse:
        """Execute full context pipeline.

        graph and policy are pre-built by the caller (Graph Subsystem + Policy Layer).
        DocProvider is created here from index (I-ENGINE-INPUTS-1: ContextEngine receives
        DocProvider ready, never SpatialIndex directly).
        LightRAGProjection degrades to OFF (returns None) when self._rag_client is None (DoD 4).
        edge_types: when provided, forwarded to ContextEngine.query() to filter edge kinds
                    for EXPLAIN/TRACE BFS traversal (I-ENGINE-EDGE-FILTER-1).
        """
        if edge_types is not None and len(edge_types) == 0:
            raise ValueError(
                "edge_types must not be empty frozenset; pass None to use strategy defaults"
            )
        doc_provider = self._doc_provider_factory(index)
        return self._engine.query(
            graph,
            policy,
            doc_provider,
            node_id,
            rag_client=self._rag_client,
            edge_types=edge_types,
        )
