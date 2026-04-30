"""LightRAGExporter — idempotent KG export from DeterministicGraph to LightRAG.

I-RAG-EXPORT-FRESHNESS-1: skip if registry.has_kg(fingerprint) is True.
I-RAG-EXPORT-NOT-IN-QUERY-1: MUST NOT be imported from ContextEngine, ContextRuntime,
    or CLI query-handlers (resolve/explain/trace/invariant).
I-RAG-CHUNK-1: entities/relationships linked to chunks via source_id/file_path.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sdd.context_kernel.documents import DocumentChunk
from sdd.graph.types import DeterministicGraph

if TYPE_CHECKING:
    from sdd.context_kernel.rag_types import LightRAGClient
    from sdd.graph_navigation.rag.registry import LightRAGRegistry


class LightRAGExporter:
    """Idempotent LightRAG KG exporter.

    I-RAG-EXPORT-NOT-IN-QUERY-1: must only be called from sdd rag-export, never from query pipeline.
    """

    def export(
        self,
        graph: DeterministicGraph,
        docs: list[DocumentChunk],
        rag_client: "LightRAGClient",
        registry: "LightRAGRegistry",
        fingerprint: str,
    ) -> None:
        """Export graph to LightRAG KG. Idempotent: skips if KG already exists.

        I-RAG-EXPORT-FRESHNESS-1: registry.has_kg(fingerprint) → return immediately.
        I-RAG-CHUNK-1: each entity/relationship carries source_id matching a chunk.
        """
        if registry.has_kg(fingerprint):
            return

        doc_map: dict[str, DocumentChunk] = {d.node_id: d for d in docs}

        entities = [
            {
                "entity_name": node_id,
                "entity_type": node.kind,
                "description": node.summary or f"{node.kind}:{node_id}",
                "source_id": node_id,
                "file_path": str(doc_map[node_id].meta.get("path", "")) if node_id in doc_map else "",
            }
            for node_id, node in graph.nodes.items()
        ]

        relationships = [
            {
                "src_id": edge.src,
                "tgt_id": edge.dst,
                "description": edge.kind,
                "source_id": edge.src,
                "file_path": str(doc_map[edge.src].meta.get("path", "")) if edge.src in doc_map else "",
            }
            for edges in graph.edges_out.values()
            for edge in edges
        ]

        chunks = [
            {
                "content": doc.content,
                "source_id": doc.node_id,
                "file_path": str(doc.meta.get("path", "")),
            }
            for doc in docs
        ]

        kg_path = registry.get_path(fingerprint)
        kg_path.mkdir(parents=True, exist_ok=True)

        rag_client.insert_custom_kg({
            "entities": entities,
            "relationships": relationships,
            "chunks": chunks,
        })
