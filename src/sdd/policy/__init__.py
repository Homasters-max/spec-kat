from __future__ import annotations

from dataclasses import dataclass
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
class NavigationPolicy:
    budget: Budget
    rag_mode: RagMode
