"""GraphFactsBuilder: assembles DeterministicGraph from SpatialIndex (BC-36-2)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sdd.graph.errors import GraphInvariantError
from sdd.graph.projection import project_node
from sdd.graph.types import EDGE_KIND_PRIORITY, DeterministicGraph, Edge

if TYPE_CHECKING:
    from sdd.graph.extractors import EdgeExtractor
    from sdd.spatial.index import SpatialIndex


class _DeterministicGraphBuilder:
    """Private: builds edges_out/edges_in indexes from a flat edge list.

    I-GRAPH-FACTS-ESCAPE-1: not exported; only callable from GraphFactsBuilder.build().
    """

    def build(
        self,
        nodes: dict[str, Any],
        edges: list[Edge],
        snapshot_hash: str,
    ) -> DeterministicGraph:
        edges_out: dict[str, list[Edge]] = {nid: [] for nid in nodes}
        edges_in: dict[str, list[Edge]] = {nid: [] for nid in nodes}

        for edge in edges:
            # src/dst already validated by GraphFactsBuilder (I-GRAPH-1)
            edges_out[edge.src].append(edge)
            edges_in[edge.dst].append(edge)

        # Deterministic ordering per node (I-GRAPH-DET-1, I-GRAPH-DET-3)
        for lst in edges_out.values():
            lst.sort(key=lambda e: e.edge_id)
        for lst in edges_in.values():
            lst.sort(key=lambda e: e.edge_id)

        return DeterministicGraph(
            nodes=nodes,
            edges_out=edges_out,
            edges_in=edges_in,
            source_snapshot_hash=snapshot_hash,
        )


class GraphFactsBuilder:
    """Orchestrates EdgeExtractors to build a DeterministicGraph (BC-36-2).

    I-GRAPH-FS-ISOLATION-1: zero direct open() calls.
    I-GRAPH-FACTS-ESCAPE-1: _DeterministicGraphBuilder is private, not in __init__.py.
    """

    def __init__(self, extractors: list[EdgeExtractor] | None = None) -> None:
        from sdd.graph.extractors import _DEFAULT_EXTRACTORS

        self._extractors: list[EdgeExtractor] = (
            extractors if extractors is not None else _DEFAULT_EXTRACTORS
        )

    def build(self, index: SpatialIndex) -> DeterministicGraph:
        """Build DeterministicGraph from SpatialIndex.

        1. Project all SpatialNodes → Nodes.
        2. Collect edges from all extractors (no open() calls).
        3. Verify I-GRAPH-PRIORITY-1: priority == EDGE_KIND_PRIORITY[kind].
        4. Verify I-GRAPH-1: all edge src/dst exist as nodes.
        5. Verify I-GRAPH-EMITS-1: emits edges have COMMAND src and EVENT dst.
        6. Verify I-DDD-1: means edges have TERM src.
        7. Build edges_out/edges_in indexes (I-GRAPH-DET-3).
        8. Set source_snapshot_hash = index.snapshot_hash (I-GRAPH-LINEAGE-1).
        """
        # Step 1: project nodes
        nodes = {n.node_id: project_node(n) for n in index.nodes.values()}

        # Step 2: collect edges from all extractors
        all_edges: list[Edge] = []
        for extractor in self._extractors:
            all_edges.extend(extractor.extract(index))

        # Step 3: I-GRAPH-PRIORITY-1
        for edge in all_edges:
            expected = EDGE_KIND_PRIORITY.get(edge.kind)
            if expected is None:
                raise GraphInvariantError(
                    f"I-GRAPH-PRIORITY-1: unknown edge kind {edge.kind!r}; "
                    f"allowed: {sorted(EDGE_KIND_PRIORITY)}"
                )
            if edge.priority != expected:
                raise GraphInvariantError(
                    f"I-GRAPH-PRIORITY-1: edge {edge.edge_id!r} kind={edge.kind!r} "
                    f"has priority {edge.priority!r}, expected {expected!r}"
                )

        # Step 4: I-GRAPH-1 (referential integrity)
        for edge in all_edges:
            if edge.src not in nodes:
                raise GraphInvariantError(
                    f"I-GRAPH-1: edge {edge.edge_id!r} src={edge.src!r} not in nodes"
                )
            if edge.dst not in nodes:
                raise GraphInvariantError(
                    f"I-GRAPH-1: edge {edge.edge_id!r} dst={edge.dst!r} not in nodes"
                )

        # Step 5: I-GRAPH-EMITS-1 (emits: COMMAND|FILE → EVENT)
        # COMMAND nodes in the index all point to registry.py; individual handler files
        # are FILE nodes — both are valid emits sources (extractor filters to handlers only).
        for edge in all_edges:
            if edge.kind == "emits":
                src_node = nodes[edge.src]
                dst_node = nodes[edge.dst]
                if src_node.kind not in {"COMMAND", "FILE"}:
                    raise GraphInvariantError(
                        f"I-GRAPH-EMITS-1: emits edge {edge.edge_id!r} "
                        f"src={edge.src!r} has kind {src_node.kind!r}, expected COMMAND or FILE"
                    )
                if dst_node.kind != "EVENT":
                    raise GraphInvariantError(
                        f"I-GRAPH-EMITS-1: emits edge {edge.edge_id!r} "
                        f"dst={edge.dst!r} has kind {dst_node.kind!r}, expected EVENT"
                    )

        # Step 6: I-DDD-1 (means: TERM → any valid node)
        for edge in all_edges:
            if edge.kind == "means":
                src_node = nodes[edge.src]
                if src_node.kind != "TERM":
                    raise GraphInvariantError(
                        f"I-DDD-1: means edge {edge.edge_id!r} "
                        f"src={edge.src!r} has kind {src_node.kind!r}, expected TERM"
                    )

        # Steps 7–8: build final graph
        return _DeterministicGraphBuilder().build(
            nodes=nodes,
            edges=all_edges,
            snapshot_hash=index.snapshot_hash,
        )
