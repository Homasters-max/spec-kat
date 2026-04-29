"""GlossaryEdgeExtractor: 'means' edges from TERM node links.

I-DDD-1: validates TERM references exist in index.
I-GRAPH-EXTRACTOR-2: no open(); all content via index.read_content().
I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
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


class GlossaryEdgeExtractor:
    """Extract 'means' edges from TERM nodes via SpatialNode.links.

    I-DDD-1: SpatialNode.links is the primary source of means edges for TERM nodes.
    Each linked target MUST exist in the index; missing references are logged and skipped.
    """

    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: "SpatialIndex") -> list[Edge]:  # noqa: UP037
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        all_node_ids: set[str] = set(index.nodes)
        edges: list[Edge] = []

        for node_id, node in index.nodes.items():
            if node.kind != "TERM":
                continue

            for target_id in node.links:
                if target_id not in all_node_ids:
                    # I-DDD-1: invalid TERM reference — log and skip (do not raise)
                    logger.warning(
                        "GlossaryEdgeExtractor: TERM %r links to unknown node %r (I-DDD-1)",
                        node_id,
                        target_id,
                    )
                    continue
                if target_id == node_id:
                    continue
                edges.append(_make_edge(node_id, "means", target_id, "glossary"))

        return edges
