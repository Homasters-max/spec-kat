"""SpatialNode → Node projection layer for the graph subsystem (BC-36-1)."""
from __future__ import annotations

import logging

from sdd.graph.types import ALLOWED_META_KEYS, Node
from sdd.spatial.nodes import SpatialNode

logger = logging.getLogger(__name__)


def project_node(n: SpatialNode) -> Node:
    """Project SpatialNode → Node using ALLOWED_META_KEYS allowlist (I-GRAPH-META-1).

    Indexing fields (signature, git_hash, indexed_at) are never copied (I-GRAPH-TYPES-1).
    Unknown meta keys are silently dropped; logged at DEBUG in debug mode,
    WARNING in production when non-empty (I-GRAPH-META-DEBUG-1).
    """
    dropped_keys = [k for k in n.meta if k not in ALLOWED_META_KEYS]
    if dropped_keys:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "project_node: dropping meta keys %s for node %r",
                sorted(dropped_keys),
                n.node_id,
            )
        else:
            logger.warning(
                "project_node: dropping meta keys %s for node %r",
                sorted(dropped_keys),
                n.node_id,
            )
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
