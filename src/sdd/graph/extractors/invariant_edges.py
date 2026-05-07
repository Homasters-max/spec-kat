"""InvariantEdgeExtractor: 'verified_by' and 'introduced_in' edges from INVARIANT nodes.

I-GRAPH-EXTRACTOR-2: no open(); all content via index.read_content().
I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
I-GRAPH-PRIORITY-1: edge priority from EDGE_KIND_PRIORITY.
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, ClassVar

from sdd.graph.errors import GraphInvariantError
from sdd.graph.types import EDGE_KIND_PRIORITY, Edge

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex

logger = logging.getLogger(__name__)


def _edge_id(src: str, kind: str, dst: str) -> str:
    return hashlib.sha256(f"{src}:{kind}:{dst}".encode()).hexdigest()[:16]


def _make_edge(src: str, kind: str, dst: str, source: str) -> Edge:
    if kind not in EDGE_KIND_PRIORITY:
        raise GraphInvariantError(f"Unknown edge kind {kind!r}; not in EDGE_KIND_PRIORITY")
    return Edge(
        edge_id=_edge_id(src, kind, dst),
        src=src,
        dst=dst,
        kind=kind,
        priority=EDGE_KIND_PRIORITY[kind],
        source=source,
        meta={},
    )


def _as_list(value: object) -> list[str]:
    """Normalise a meta value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return [str(value)]


class InvariantEdgeExtractor:
    """Extract 'verified_by' and 'introduced_in' edges from INVARIANT nodes.

    Sources:
      - node.meta['verified_by']   → INVARIANT --[verified_by]--> test_node
      - node.meta['introduced_in'] → INVARIANT --[introduced_in]--> phase_node
    """

    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: "SpatialIndex") -> list[Edge]:  # noqa: UP037
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        all_node_ids: set[str] = set(index.nodes)
        edges: list[Edge] = []

        for node_id, node in index.nodes.items():
            if node.kind != "INVARIANT":
                continue

            # verified_by edges
            for target_id in _as_list(node.meta.get("verified_by")):
                if target_id not in all_node_ids:
                    logger.warning(
                        "InvariantEdgeExtractor: INVARIANT %r verified_by unknown node %r",
                        node_id,
                        target_id,
                    )
                    continue
                edges.append(_make_edge(node_id, "verified_by", target_id, "invariant_meta"))

            # introduced_in edges
            for target_id in _as_list(node.meta.get("introduced_in")):
                if target_id not in all_node_ids:
                    logger.warning(
                        "InvariantEdgeExtractor: INVARIANT %r introduced_in unknown node %r",
                        node_id,
                        target_id,
                    )
                    continue
                edges.append(_make_edge(node_id, "introduced_in", target_id, "invariant_meta"))

        return edges
