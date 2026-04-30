from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

MIN_CONTEXT_SIZE: int = 256
BFS_OVERSELECT_FACTOR: int = 3


class QueryIntent(Enum):
    RESOLVE_EXACT = "RESOLVE_EXACT"
    SEARCH = "SEARCH"
    EXPLAIN = "EXPLAIN"
    TRACE = "TRACE"
    INVARIANT = "INVARIANT"


@dataclass
class Budget:
    max_nodes: int
    max_edges: int
    max_chars: int

    def __post_init__(self) -> None:
        assert self.max_nodes >= 1, (
            f"Budget.max_nodes must be >= 1, got {self.max_nodes}"
        )
        assert self.max_chars >= MIN_CONTEXT_SIZE, (
            f"Budget.max_chars must be >= MIN_CONTEXT_SIZE ({MIN_CONTEXT_SIZE}), got {self.max_chars}"
        )


class RagMode(Enum):
    OFF = "OFF"
    LOCAL = "LOCAL"
    GLOBAL = "GLOBAL"
    HYBRID = "HYBRID"


@dataclass(frozen=True)
class RAGPolicy:
    """RAG pipeline constraints. I-ARCH-LAYER-SEPARATION-1: RAG ranks L2 output only.

    Phase 55: declared. Phase 57: soft enforcement (warning). Phase 58: hard enforcement.

    allow_global_search MUST remain False (I-RAG-SCOPE-1): global vector search bypasses
    the graph scope and allows RAG to introduce documents outside ContextEngine output.
    """

    max_documents: int = 20
    allow_global_search: bool = False  # I-RAG-SCOPE-1: MUST remain False
    min_graph_hops: int = 0


@dataclass(frozen=True)
class NavigationPolicy:
    budget: Budget
    rag_mode: RagMode
    rag_policy: RAGPolicy = field(default_factory=RAGPolicy)  # Phase 55: backward compat default
