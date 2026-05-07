"""Tests for GraphFactsBuilder (I-GRAPH-DET-1..3, I-GRAPH-EXTRACTOR-1, I-GRAPH-FACTS-ESCAPE-1)."""
from __future__ import annotations

import hashlib
from typing import ClassVar

from sdd.graph.builder import GraphFactsBuilder
from sdd.graph.types import EDGE_KIND_PRIORITY, DeterministicGraph, Edge
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode

_NOW = "2026-01-01T00:00:00Z"


def _make_node(
    node_id: str,
    kind: str,
    label: str,
    path: str | None = None,
    meta: dict | None = None,
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path=path,
        summary=f"{kind}:{label}",
        signature="",
        meta=meta or {},
        git_hash=None,
        indexed_at=_NOW,
    )


def _make_index(
    nodes: list[SpatialNode],
    snapshot_hash: str = "testhash01234567",
) -> SpatialIndex:
    nodes_dict = {n.node_id: n for n in nodes}
    index = SpatialIndex(
        nodes=nodes_dict,
        built_at=_NOW,
        git_tree_hash=None,
        snapshot_hash=snapshot_hash,
    )
    index._content_map = {}
    return index


class _NoOpExtractor:
    """Custom extractor that emits no edges — for isolation testing."""

    EXTRACTOR_VERSION: ClassVar[str] = "0.0.1"

    def extract(self, index: SpatialIndex) -> list[Edge]:
        return []


class _SingleEdgeExtractor:
    """Custom extractor that emits one deterministic edge."""

    EXTRACTOR_VERSION: ClassVar[str] = "0.0.1"

    def __init__(self, src: str, dst: str, kind: str = "imports") -> None:
        self._src = src
        self._dst = dst
        self._kind = kind

    def extract(self, index: SpatialIndex) -> list[Edge]:
        edge_id = hashlib.sha256(
            f"{self._src}:{self._kind}:{self._dst}".encode()
        ).hexdigest()[:16]
        return [
            Edge(
                edge_id=edge_id,
                src=self._src,
                dst=self._dst,
                kind=self._kind,
                priority=EDGE_KIND_PRIORITY[self._kind],
                source="test",
                meta={},
            )
        ]


# ---------------------------------------------------------------------------
# Test 10: graph_facts_builder_custom_extractors — I-GRAPH-EXTRACTOR-1
# ---------------------------------------------------------------------------

def test_graph_facts_builder_custom_extractors() -> None:
    """I-GRAPH-EXTRACTOR-1: GraphFactsBuilder uses the provided extractor list, not defaults."""
    node_a = _make_node("FILE:src/sdd/a.py", "FILE", "a.py", path="src/sdd/a.py")
    node_b = _make_node("FILE:src/sdd/b.py", "FILE", "b.py", path="src/sdd/b.py")
    index = _make_index([node_a, node_b])

    custom = _SingleEdgeExtractor("FILE:src/sdd/a.py", "FILE:src/sdd/b.py", "imports")
    graph = GraphFactsBuilder(extractors=[custom]).build(index)

    assert isinstance(graph, DeterministicGraph)
    out = graph.edges_out.get("FILE:src/sdd/a.py", [])
    assert len(out) == 1
    assert out[0].kind == "imports"
    assert out[0].dst == "FILE:src/sdd/b.py"

    # Reverse index is consistent (I-GRAPH-DET-3)
    inc = graph.edges_in.get("FILE:src/sdd/b.py", [])
    assert len(inc) == 1
    assert inc[0].edge_id == out[0].edge_id


# ---------------------------------------------------------------------------
# Test 12: graph_builder_deterministic — I-GRAPH-DET-1..3
# ---------------------------------------------------------------------------

def test_graph_builder_deterministic() -> None:
    """I-GRAPH-DET-1: same SpatialIndex + extractors → identical DeterministicGraph twice."""
    node_a = _make_node("FILE:src/sdd/a.py", "FILE", "a.py", path="src/sdd/a.py")
    node_b = _make_node("FILE:src/sdd/b.py", "FILE", "b.py", path="src/sdd/b.py")
    index = _make_index([node_a, node_b], snapshot_hash="abc123def456")

    extractor = _SingleEdgeExtractor("FILE:src/sdd/a.py", "FILE:src/sdd/b.py", "imports")
    builder = GraphFactsBuilder(extractors=[extractor])

    graph1 = builder.build(index)
    graph2 = builder.build(index)

    # Nodes identical
    assert set(graph1.nodes) == set(graph2.nodes)
    for nid in graph1.nodes:
        assert graph1.nodes[nid] == graph2.nodes[nid]

    # Edge ordering deterministic (I-GRAPH-DET-3)
    for nid in graph1.nodes:
        ids1 = [e.edge_id for e in graph1.edges_out.get(nid, [])]
        ids2 = [e.edge_id for e in graph2.edges_out.get(nid, [])]
        assert ids1 == ids2

    # source_snapshot_hash traces back to index (I-GRAPH-LINEAGE-1)
    assert graph1.source_snapshot_hash == index.snapshot_hash
    assert graph2.source_snapshot_hash == index.snapshot_hash
