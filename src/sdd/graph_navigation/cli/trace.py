"""CLI handler: sdd trace <node_id> — BC-36-7.

Canonical pipeline (I-RUNTIME-ORCHESTRATOR-1):
  IndexBuilder → GraphService → TRACE intent → PolicyResolver → ContextRuntime → format

I-INTENT-HEURISTIC-1: TRACE intent is set by CLI routing, not parse_query_intent.
I-PHASE-ISOLATION-1:  no direct sdd.graph.cache or sdd.graph.builder imports.
I-RUNTIME-ORCHESTRATOR-1: no domain logic beyond pipeline calls and arg parsing.
"""
from __future__ import annotations

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
    edge_types: frozenset[str] | None = None,
) -> int:
    """Execute sdd trace pipeline. Returns exit code (0 = success, 1 = error)."""
    if edge_types is not None and not edge_types:
        emit_error("INVALID_ARGUMENT", "--edge-types must not be empty; omit flag for default traversal")
        return 1
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

    # I-INTENT-HEURISTIC-1: TRACE is set exclusively by CLI routing.
    intent = QueryIntent.TRACE
    policy = PolicyResolver().resolve(intent)

    engine = ContextEngine(ContextAssembler())
    runtime = ContextRuntime(engine)

    # ContextRuntime.query() does not forward intent to ContextEngine (Phase 51 limitation).
    # Use ContextRuntime's doc_provider_factory to construct DocProvider, then call engine
    # directly with explicit TRACE intent to satisfy reverse-BFS traversal requirement (INT-2).
    doc_provider = runtime._doc_provider_factory(index)
    try:
        response = engine.query(graph, policy, doc_provider, node_id, intent=intent, edge_types=edge_types)
    except Exception as exc:
        emit_error("INTERNAL_ERROR", str(exc))
        return 1

    # I-CLI-ERROR-CODES-1: NOT_FOUND when node_id absent from graph.
    if node_id not in graph.nodes:
        emit_error("NOT_FOUND", f"Node not found: {node_id!r}")
        return 1

    dbg: dict[str, Any] | None = None
    if debug:
        ctx = response.context
        dbg = debug_output(
            intent=intent.value,
            selection={
                "start_node": node_id,
                "strategy": "TRACE_DEFAULT_V1",
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
