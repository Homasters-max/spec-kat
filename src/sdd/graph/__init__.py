from __future__ import annotations

from sdd.graph.errors import GraphInvariantError
from sdd.graph.types import (
    EDGE_KIND_PRIORITY,
    DeterministicGraph,
    Edge,
    Node,
)

__all__ = [
    "DeterministicGraph",
    "Node",
    "Edge",
    "GraphService",
    "GraphInvariantError",
    "EDGE_KIND_PRIORITY",
]


class GraphService:
    """Build + cache boundary (I-GRAPH-SUBSYSTEM-1).

    Full implementation lives in sdd.graph.service (T-5018).
    Единственный публичный метод: get_or_build(index, force_rebuild=False) → DeterministicGraph.
    """

    def get_or_build(
        self,
        index: object,
        force_rebuild: bool = False,
    ) -> DeterministicGraph:
        raise NotImplementedError
