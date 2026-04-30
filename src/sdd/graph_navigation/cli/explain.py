"""CLI handler: sdd explain <node_id> — BC-36-7.

Canonical pipeline (I-RUNTIME-ORCHESTRATOR-1):
  IndexBuilder → GraphService → EXPLAIN intent → PolicyResolver → ContextRuntime → format

I-INTENT-HEURISTIC-1:    EXPLAIN intent is set by CLI routing, not parse_query_intent.
I-GRAPH-IMPLEMENTS-2:    fallback to FILE handler seed when COMMAND BFS returns empty context.
I-PHASE-ISOLATION-1:     no direct sdd.graph.cache or sdd.graph.builder imports.
I-RUNTIME-ORCHESTRATOR-1: no domain logic beyond pipeline calls and arg parsing.
"""
from __future__ import annotations

import sys
from typing import Any

from sdd.context_kernel.assembler import ContextAssembler
from sdd.context_kernel.engine import ContextEngine
from sdd.context_kernel.intent import QueryIntent
from sdd.context_kernel.runtime import ContextRuntime
from sdd.graph.service import GraphService
from sdd.graph_navigation.cli.formatting import debug_output, emit_error, format_json, format_text
from sdd.policy.resolver import PolicyResolver
from sdd.spatial.index import IndexBuilder


def run(
    node_id: str,
    *,
    rebuild: bool = False,
    fmt: str = "text",
    debug: bool = False,
    project_root: str = ".",
) -> int:
    """Execute sdd explain pipeline. Returns exit code (0 = success, 1 = error)."""
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

    # I-CLI-ERROR-CODES-1: NOT_FOUND when node_id absent from graph.
    if node_id not in graph.nodes:
        emit_error("NOT_FOUND", f"Node not found: {node_id!r}")
        return 1

    # I-INTENT-HEURISTIC-1: EXPLAIN is set exclusively by CLI routing.
    intent = QueryIntent.EXPLAIN
    policy = PolicyResolver().resolve(intent)

    engine = ContextEngine(ContextAssembler())
    runtime = ContextRuntime(engine)

    doc_provider = runtime._doc_provider_factory(index)
    try:
        response = engine.query(graph, policy, doc_provider, node_id, intent=intent)
    except Exception as exc:
        emit_error("INTERNAL_ERROR", str(exc))
        return 1

    # I-GRAPH-IMPLEMENTS-2: COMMAND node with empty BFS → seed from FILE handler node.
    seed_node_id = node_id
    if (
        node_id.startswith("COMMAND:")
        and getattr(response.context, "selection_exhausted", False)
        and len(getattr(response.context, "nodes", [])) <= 1
    ):
        impl_edges = [
            e for e in graph.edges_in.get(node_id, []) if e.kind == "implements"
        ]
        if impl_edges:
            handler_node_id = impl_edges[0].src
            print(
                f"EXPLAIN: COMMAND BFS empty for {node_id!r}; retrying from handler {handler_node_id!r}",
                file=sys.stderr,
            )
            seed_node_id = handler_node_id
            try:
                response = engine.query(graph, policy, doc_provider, handler_node_id, intent=intent)
            except Exception as exc:
                emit_error("INTERNAL_ERROR", str(exc))
                return 1

    dbg: dict[str, Any] | None = None
    if debug:
        ctx = response.context
        dbg = debug_output(
            intent=intent.value,
            selection={
                "start_node": seed_node_id,
                "strategy": "EXPLAIN_DEFAULT_V1",
                "steps": [],
            },
            budget={
                "max_nodes": policy.budget.max_nodes,
                "max_edges": policy.budget.max_edges,
                "max_chars": policy.budget.max_chars,
                **getattr(ctx, "budget_used", {}),
            },
        )

    output = format_json(response, dbg) if fmt == "json" else format_text(response)
    print(output)
    return 0
