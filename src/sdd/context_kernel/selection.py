"""RankedNode, RankedEdge, Selection, _build_selection() — BFS traversal core (BC-36-3)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from sdd.graph.types import DeterministicGraph, Edge
from sdd.policy import BFS_OVERSELECT_FACTOR, Budget


@dataclass(frozen=True)
class RankedNode:
    node_id: str
    hop: int
    global_importance_score: float  # max(priority) over ALL incoming edges in DeterministicGraph (I-RANKED-NODE-BP-1)


@dataclass(frozen=True)
class RankedEdge:
    edge_id: str
    src: str
    dst: str
    hop: int
    priority: float


@dataclass
class Selection:
    seed: str  # node_id of seed node (immutable anchor)
    nodes: dict[str, RankedNode] = field(default_factory=dict)
    edges: dict[str, RankedEdge] = field(default_factory=dict)


def _global_importance(graph: DeterministicGraph, dst: str, fallback_edge: Edge) -> float:
    """max(priority) over ALL incoming edges in graph for dst (I-RANKED-NODE-BP-1)."""
    all_in = graph.edges_in.get(dst, [fallback_edge])
    return max(e.priority for e in all_in)


def _build_selection(
    graph: DeterministicGraph,
    budget: Budget,
    seed_node_id: str,
    expand: Callable[[DeterministicGraph, str, int], list[Edge]],
) -> Selection:
    """BFS selection with early-stop at max_nodes * BFS_OVERSELECT_FACTOR (I-BFS-BUDGET-1).

    global_importance_score is computed over ALL incoming edges of dst in graph,
    not only edges present in the current selection (I-RANKED-NODE-BP-1).
    Seed node is always added at hop=0 with global_importance_score=1.0 (I-CONTEXT-SEED-1).
    """
    nodes: dict[str, RankedNode] = {}
    edges: dict[str, RankedEdge] = {}

    nodes[seed_node_id] = RankedNode(
        node_id=seed_node_id,
        hop=0,
        global_importance_score=1.0,
    )
    queue: deque[tuple[str, int]] = deque([(seed_node_id, 0)])

    while queue:
        node_id, hop = queue.popleft()
        if len(nodes) >= budget.max_nodes * BFS_OVERSELECT_FACTOR:
            break  # I-BFS-BUDGET-1: early-stop prevents O(N) traversal on large graphs
        for edge in expand(graph, node_id, hop):
            dst = edge.dst
            if dst not in nodes or hop + 1 < nodes[dst].hop:
                gis = _global_importance(graph, dst, edge)
                nodes[dst] = RankedNode(
                    node_id=dst,
                    hop=hop + 1,
                    global_importance_score=gis,
                )
                edges[edge.edge_id] = RankedEdge(
                    edge_id=edge.edge_id,
                    src=edge.src,
                    dst=dst,
                    hop=hop + 1,
                    priority=edge.priority,
                )
                queue.append((dst, hop + 1))

    return Selection(seed=seed_node_id, nodes=nodes, edges=edges)
