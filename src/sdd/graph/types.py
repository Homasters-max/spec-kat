from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from sdd.spatial.nodes import SpatialNode

from sdd.graph.errors import GraphInvariantError  # noqa: F401 — re-exported for consumers

logger = logging.getLogger(__name__)

# Canonical edge-kind priority table (I-GRAPH-PRIORITY-1).
# Each EdgeExtractor MUST assign priority = EDGE_KIND_PRIORITY[edge.kind].
EDGE_KIND_PRIORITY: dict[str, float] = {
    "emits":         0.95,
    "guards":        0.90,
    "implements":    0.85,
    "tested_by":     0.80,
    "verified_by":   0.75,
    "depends_on":    0.70,
    "introduced_in": 0.65,
    "imports":       0.60,
    "means":         0.50,
    "contains":      0.45,
}

# Allowlist for meta keys copied from SpatialNode (I-GRAPH-META-1).
# Additions require a spec bump.
ALLOWED_META_KEYS: frozenset[str] = frozenset({
    "path", "language", "line_start", "line_end", "links", "phase",
    "verified_by", "introduced_in", "depends_on", "implements",
    "module_path",
})


@dataclass(frozen=True)
class Node:
    """Graph-layer projection of SpatialNode. No indexing fields (I-GRAPH-TYPES-1)."""
    node_id: str
    kind: str       # COMMAND|EVENT|TASK|TERM|INVARIANT|FILE|...
    label: str
    summary: str
    meta: dict[str, Any]


@dataclass(frozen=True)
class Edge:
    """Directed typed edge. edge_id = sha256(src:kind:dst)[:16] (I-GRAPH-DET-2)."""
    edge_id: str    # sha256(f"{src}:{kind}:{dst}")[:16]
    src: str        # node_id
    dst: str        # node_id
    kind: str       # emits|guards|implements|depends_on|means|imports|...
    priority: float  # 0.0..1.0; MUST equal EDGE_KIND_PRIORITY[kind]
    source: str     # ast_emits|taskset_depends_on|glossary|...
    meta: dict[str, Any]

    def __post_init__(self) -> None:
        if not (0.0 <= self.priority <= 1.0):
            raise ValueError(
                f"Edge.priority must be in [0.0, 1.0], got {self.priority!r}"
            )
        if not self.edge_id:
            raise ValueError("Edge.edge_id must be non-empty")


@dataclass
class DeterministicGraph:
    """Deterministic in-memory graph fully reconstructable from SpatialIndex.

    edges_out[src] and edges_in[dst] are mutually consistent (I-GRAPH-DET-3).
    source_snapshot_hash links the graph back to the SpatialIndex it was built from
    (I-GRAPH-LINEAGE-1).
    """
    nodes: dict[str, Node]
    edges_out: dict[str, list[Edge]]  # src node_id → outgoing edges
    edges_in: dict[str, list[Edge]]   # dst node_id → incoming edges
    source_snapshot_hash: str

    def neighbors(
        self,
        node_id: str,
        kinds: set[str] | None = None,
    ) -> list[Edge]:
        """Return outgoing edges from node_id, optionally filtered by kind."""
        edges = self.edges_out.get(node_id, [])
        if kinds is None:
            return list(edges)
        return [e for e in edges if e.kind in kinds]

    def reverse_neighbors(
        self,
        node_id: str,
        kinds: set[str] | None = None,
    ) -> list[Edge]:
        """Return incoming edges to node_id, optionally filtered by kind."""
        edges = self.edges_in.get(node_id, [])
        if kinds is None:
            return list(edges)
        return [e for e in edges if e.kind in kinds]


def project_node(n: SpatialNode) -> Node:
    """Project SpatialNode → Node using ALLOWED_META_KEYS allowlist (I-GRAPH-META-1).

    Unknown keys are dropped silently in production; logged as WARNING if non-empty.
    """
    dropped = {k: v for k, v in n.meta.items() if k not in ALLOWED_META_KEYS}
    if dropped:
        logger.warning("project_node: dropping unknown meta keys %s for node %r", list(dropped), n.node_id)
    return Node(
        node_id=n.node_id,
        kind=n.kind,
        label=n.label,
        summary=n.summary,
        meta={
            "path": n.path,
            **{k: v for k, v in n.meta.items() if k in ALLOWED_META_KEYS},
        },
    )


class EdgeExtractor(Protocol):
    """Protocol for all edge extractors (R-INSPECT fix: inspect.getsource() forbidden)."""
    EXTRACTOR_VERSION: ClassVar[str]  # semver; required (I-GRAPH-FINGERPRINT-1)

    def extract(self, index: object) -> list[Edge]:
        """Pure function: SpatialIndex → list[Edge]. No side effects. No open()."""
        ...
