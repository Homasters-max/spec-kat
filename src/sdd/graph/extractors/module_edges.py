"""ModuleEdgeExtractor: contains edges from MODULE nodes to FILE nodes.

I-MODULE-COHESION-1: each FILE node maps to its most specific MODULE via path prefix.
I-GRAPH-EXTRACTOR-2: no open() calls; all content via index.read_content(node).
I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, ClassVar

from sdd.graph.types import EDGE_KIND_PRIORITY, Edge

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex


def _edge_id(src: str, kind: str, dst: str) -> str:
    """sha256(src:kind:dst)[:16] — I-GRAPH-DET-2."""
    return hashlib.sha256(f"{src}:{kind}:{dst}".encode()).hexdigest()[:16]


class ModuleEdgeExtractor:
    """Extract contains edges: MODULE → FILE (most specific module wins).

    I-MODULE-COHESION-1: for each FILE node, find the MODULE whose path is the
    longest prefix of the FILE's directory path. Skips FILE nodes with no match.
    """

    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: "SpatialIndex") -> list[Edge]:
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        # Build sorted list of (module_path, module_node_id) — longest first
        modules: list[tuple[str, str]] = []
        for node_id, node in index.nodes.items():
            if node.kind == "MODULE" and node.path:
                modules.append((node.path, node_id))
        # Sort by path length descending so most specific match wins
        modules.sort(key=lambda x: len(x[0]), reverse=True)

        edges: list[Edge] = []
        for node_id, node in index.nodes.items():
            if node.kind != "FILE" or not node.path:
                continue
            file_dir = node.path.rsplit("/", 1)[0] if "/" in node.path else ""
            # Find most specific MODULE whose path is a prefix of the file's directory
            matched_module: str | None = None
            for module_path, module_node_id in modules:
                if file_dir == module_path or file_dir.startswith(module_path + "/"):
                    matched_module = module_node_id
                    break
            if matched_module is None:
                continue
            edges.append(Edge(
                edge_id=_edge_id(matched_module, "contains", node_id),
                src=matched_module,
                dst=node_id,
                kind="contains",
                priority=EDGE_KIND_PRIORITY["contains"],
                source="module_edge_extractor",
                meta={},
            ))

        return edges
