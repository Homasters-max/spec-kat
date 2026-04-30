"""ImplementsEdgeExtractor: implements edges from handler FILE nodes to COMMAND nodes.

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


def _command_name_to_handler_path(cmd_name: str) -> str:
    """Convert command name (e.g. 'activate-phase') to handler file path."""
    filename = cmd_name.replace("-", "_")
    return f"src/sdd/commands/{filename}.py"


class ImplementsEdgeExtractor:
    """Extract implements edges: handler FILE → COMMAND.

    I-GRAPH-IMPLEMENTS-1: each COMMAND node with a corresponding handler FILE node
    gets exactly one incoming implements edge from that FILE node.

    Convention: COMMAND label 'foo-bar' maps to handler at src/sdd/commands/foo_bar.py.
    """

    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: "SpatialIndex") -> list[Edge]:
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        file_nodes_by_path: dict[str, str] = {}
        for node_id, node in index.nodes.items():
            if node.kind == "FILE" and node.path:
                file_nodes_by_path[node.path] = node_id

        edges: list[Edge] = []
        for node_id, node in index.nodes.items():
            if node.kind != "COMMAND":
                continue
            cmd_name = node_id.removeprefix("COMMAND:")
            expected_path = _command_name_to_handler_path(cmd_name)
            handler_file_id = file_nodes_by_path.get(expected_path)
            if handler_file_id is None:
                continue
            edges.append(Edge(
                edge_id=_edge_id(handler_file_id, "implements", node_id),
                src=handler_file_id,
                dst=node_id,
                kind="implements",
                priority=EDGE_KIND_PRIORITY["implements"],
                source="implements_extractor",
                meta={},
            ))

        return edges
