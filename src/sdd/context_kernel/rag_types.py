"""LightRAGClient (Protocol), RAGResult, NavigationResponse, LightRAGProjection — BC-36-3 RAG types.

I-LIGHTRAG-CANONICAL-1: LightRAGProjection is defined exactly once in this file.
Phase 52 extends via __init__(registry) injection only — no new class.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sdd.context_kernel.context_types import Context
from sdd.context_kernel.documents import DocumentChunk
from sdd.context_kernel.intent import SearchCandidate
from sdd.policy import RagMode

if TYPE_CHECKING:
    pass


class LightRAGClient(Protocol):
    """Structural typing — no `import lightrag` required (R-LIGHTRAG-COUPLING fix)."""

    def query(self, question: str, context: list[DocumentChunk], mode: str) -> str: ...

    def insert_custom_kg(self, kg: dict[str, object]) -> None: ...


@dataclass
class RAGResult:
    """Result of a LightRAG query. Isolated from Context (I-NAV-RESPONSE-1)."""

    summary: str
    rag_mode: str  # actual mode used: "LOCAL" | "GLOBAL" | "HYBRID"


@dataclass
class NavigationResponse:
    """Full query response. Explicit boundary between fact (context) and inference (rag_summary)."""

    context: Context
    rag_summary: str | None          # None when RAG=OFF
    rag_mode: str | None             # "LOCAL" | "HYBRID" | "GLOBAL" | None; actual mode
    candidates: list[SearchCandidate] | None  # non-None only for QueryIntent.SEARCH (I-SEARCH-RESPONSE-1)


class LightRAGProjection:
    """Canonical LightRAG integration stub (Phase 51).

    I-LIGHTRAG-CANONICAL-1: single definition in sdd.context_kernel.rag_types.
    Phase 52 extends via __init__(registry) injection; query() signature is immutable.
    """

    def __init__(self, registry: "LightRAGRegistry | None" = None) -> None:  # type: ignore[name-defined]
        # registry=None: stub/Phase-51 mode; Phase 52 passes LightRAGRegistry.
        self._registry = registry

    def query(
        self,
        question: str,
        context: Context,
        rag_mode: RagMode,
        rag_client: LightRAGClient | None,
    ) -> RAGResult | None:
        """Return None for graceful degradation when rag_client is None (I-RAG-DEGRADE-LOCAL-1)."""
        if rag_client is None:
            logging.warning("LightRAGProjection: rag_client is None; degrading to OFF")
            return None

        # I-RAG-DEGRADE-LOCAL-1: GLOBAL/HYBRID without KG → LOCAL (not OFF)
        if rag_mode in (RagMode.GLOBAL, RagMode.HYBRID) and self._registry is not None:
            fingerprint: str = getattr(context, "graph_snapshot_hash", "")
            if not self._registry.has_kg(fingerprint):
                logging.warning(
                    "LightRAGProjection: KG not found for fingerprint %r; degrading to LOCAL",
                    fingerprint,
                )
                rag_mode = RagMode.LOCAL

        documents: list[DocumentChunk] = getattr(context, "documents", [])
        summary = rag_client.query(question, documents, rag_mode.value.lower())
        return RAGResult(summary=summary, rag_mode=rag_mode.value)
