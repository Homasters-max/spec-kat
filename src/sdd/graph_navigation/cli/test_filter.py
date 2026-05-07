"""CLI handler: sdd test-filter --node NODE_ID [--tier fast|default|full].

I-TEST-FILTER-1: returns pytest returncode unchanged; 0 TEST-nodes → fallback, not error.
I-TEST-FILTER-2: key 'test_filter' in project_profile.yaml starts with 'test' → excluded
  from task mode automatically (I-TASK-MODE-1).
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from collections import deque

from sdd.graph.service import GraphService
from sdd.graph.types import DeterministicGraph
from sdd.graph_navigation.cli.formatting import emit_error
from sdd.infra.config_loader import load_config
from sdd.infra.paths import config_file
from sdd.spatial.index import IndexBuilder

_TIER_TO_CMD_KEY: dict[str, str] = {
    "fast": "test_fast",
    "default": "test",
    "full": "test_full",
}


def _bfs_tested_by(graph: DeterministicGraph, start_node_id: str, max_depth: int = 2) -> list[str]:
    """BFS over out-edges of kind 'tested_by', depth ≤ max_depth. Returns TEST node_ids."""
    visited: set[str] = {start_node_id}
    queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])
    test_nodes: list[str] = []

    while queue:
        node_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in graph.neighbors(node_id, kinds={"tested_by"}):
            dst = edge.dst
            if dst in visited:
                continue
            visited.add(dst)
            if dst.startswith("TEST:"):
                test_nodes.append(dst)
            queue.append((dst, depth + 1))

    return test_nodes


def run(
    node_id: str,
    *,
    tier: str = "default",
    rebuild: bool = False,
    project_root: str = ".",
) -> int:
    """Execute sdd test-filter pipeline. Returns pytest exit code (I-TEST-FILTER-1)."""
    try:
        index = IndexBuilder(project_root).build()
    except Exception as exc:
        emit_error("GRAPH_NOT_BUILT", str(exc))
        return 1

    try:
        graph = GraphService().get_or_build(index, force_rebuild=rebuild)
    except Exception as exc:
        from sdd.graph.errors import GraphInvariantError
        err = "INVARIANT_VIOLATION" if isinstance(exc, GraphInvariantError) else "GRAPH_NOT_BUILT"
        emit_error(err, str(exc))
        return 1

    if node_id not in graph.nodes:
        emit_error("NOT_FOUND", f"Node not found: {node_id!r}")
        return 1

    test_node_ids = _bfs_tested_by(graph, node_id)

    if not test_node_ids:
        tier_key = _TIER_TO_CMD_KEY.get(tier, "test")
        print(
            f"WARNING: no tested_by edges from {node_id!r}; falling back to tier '{tier_key}'",
            file=sys.stderr,
        )
        config = load_config(config_file())
        fallback_cmd = config.get("build", {}).get("commands", {}).get(tier_key)
        if not fallback_cmd:
            emit_error("CONFIG_ERROR", f"Tier command '{tier_key}' not found in project_profile.yaml")
            return 1
        result = subprocess.run(shlex.split(fallback_cmd))
        return result.returncode

    test_paths = [nid[len("TEST:"):] for nid in test_node_ids]
    result = subprocess.run(["pytest", *test_paths, "-q", "-m", "not pg"])
    return result.returncode
