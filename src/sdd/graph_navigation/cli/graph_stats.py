"""CLI handler: sdd graph-stats — graph node/edge statistics (BC-56-G2)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from sdd.graph.service import GraphService
from sdd.graph_navigation.cli.formatting import emit_error
from sdd.spatial.index import IndexBuilder


def run(
    node_type: str | None = None,
    edge_type: str | None = None,
    fmt: str = "text",
    project_root: str = ".",
) -> int:
    """Compute and print graph statistics. Returns exit code."""
    try:
        index = IndexBuilder(project_root).build()
    except Exception as exc:
        emit_error("GRAPH_NOT_BUILT", str(exc))
        return 1

    try:
        graph = GraphService().get_or_build(index)
    except Exception as exc:
        from sdd.graph.errors import GraphInvariantError
        err = "INVARIANT_VIOLATION" if isinstance(exc, GraphInvariantError) else "GRAPH_NOT_BUILT"
        emit_error(err, str(exc))
        return 1

    nodes = list(graph.nodes.values())
    if node_type:
        nodes = [n for n in nodes if n.kind == node_type]
    node_counts: Counter[str] = Counter(n.kind for n in nodes)

    all_edges = [e for edges in graph.edges_out.values() for e in edges]
    if edge_type:
        all_edges = [e for e in all_edges if e.kind == edge_type]
    edge_counts: Counter[str] = Counter(e.kind for e in all_edges)

    stats: dict = {
        "nodes": {
            "total": len(nodes),
            "by_kind": dict(sorted(node_counts.items())),
        },
        "edges": {
            "total": len(all_edges),
            "by_kind": dict(sorted(edge_counts.items())),
        },
    }
    if node_type or edge_type:
        filt: dict[str, str] = {}
        if node_type:
            filt["node_type"] = node_type
        if edge_type:
            filt["edge_type"] = edge_type
        stats["filter"] = filt

    if fmt == "json":
        print(json.dumps(stats, indent=2))
    else:
        _print_text(stats, node_type=node_type, edge_type=edge_type)

    return 0


def _print_text(
    stats: dict,
    *,
    node_type: str | None,
    edge_type: str | None,
) -> None:
    filter_parts = []
    if node_type:
        filter_parts.append(f"node-type={node_type}")
    if edge_type:
        filter_parts.append(f"edge-type={edge_type}")
    filter_str = f" (filter: {', '.join(filter_parts)})" if filter_parts else ""

    print(f"**Graph Stats**{filter_str}\n")
    print(f"Nodes: {stats['nodes']['total']}")
    for kind, count in sorted(stats["nodes"]["by_kind"].items(), key=lambda x: -x[1]):
        print(f"  {kind}: {count}")
    print(f"\nEdges: {stats['edges']['total']}")
    for kind, count in sorted(stats["edges"]["by_kind"].items(), key=lambda x: -x[1]):
        print(f"  {kind}: {count}")


def main(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sdd graph-stats", add_help=True)
    parser.add_argument("--edge-type", dest="edge_type", default=None, help="Filter by edge kind (e.g. imports, emits)")
    parser.add_argument("--node-type", dest="node_type", default=None, help="Filter by node kind (e.g. FILE, COMMAND)")
    parser.add_argument("--format", dest="fmt", choices=["json", "text"], default="text", help="Output format")
    parsed = parser.parse_args(args)
    return run(node_type=parsed.node_type, edge_type=parsed.edge_type, fmt=parsed.fmt)
