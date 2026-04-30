"""CLI handler: sdd resolve <query> — BC-36-7.

Canonical pipeline (I-RUNTIME-ORCHESTRATOR-1):
  IndexBuilder → GraphService → parse_query_intent → PolicyResolver → ContextRuntime → format

I-PHASE-ISOLATION-1: no direct sdd.graph.cache or sdd.graph.builder imports.
I-RUNTIME-ORCHESTRATOR-1: no domain logic beyond pipeline calls and arg parsing.
"""
from __future__ import annotations

from typing import Any

from sdd.context_kernel.assembler import ContextAssembler
from sdd.context_kernel.engine import ContextEngine
from sdd.context_kernel.intent import QueryIntent, parse_query_intent
from sdd.context_kernel.runtime import ContextRuntime
from sdd.graph.service import GraphService
from sdd.graph_navigation.cli.formatting import debug_output, emit_error, format_json, format_text
from sdd.policy.resolver import PolicyResolver
from sdd.spatial.index import IndexBuilder


def run(
    query: str,
    *,
    rebuild: bool = False,
    fmt: str = "text",
    debug: bool = False,
    project_root: str = ".",
) -> int:
    """Execute sdd resolve pipeline. Returns exit code (0 = success, 1 = error)."""
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

    # I-INTENT-CANONICAL-1: intent determined by parse_query_intent for resolve command.
    intent = parse_query_intent(query)
    policy = PolicyResolver().resolve(intent)

    engine = ContextEngine(ContextAssembler())
    runtime = ContextRuntime(engine)

    # ContextRuntime.query() does not forward intent to ContextEngine (Phase 51 limitation).
    # Use _doc_provider_factory to construct DocProvider, then call engine directly with
    # explicit SEARCH intent so BM25 candidate ranking runs (I-SEARCH-NO-EMBED-1).
    doc_provider = runtime._doc_provider_factory(index)
    try:
        response = engine.query(graph, policy, doc_provider, query, intent=intent)
    except Exception as exc:
        emit_error("INTERNAL_ERROR", str(exc))
        return 1

    # I-CLI-ERROR-CODES-1: NOT_FOUND when SEARCH returns 0 candidates.
    if intent is QueryIntent.SEARCH and not response.candidates:
        emit_error("NOT_FOUND", f"No candidates found for query: {query!r}")
        return 1

    dbg: dict[str, Any] | None = None
    if debug:
        ctx = response.context
        dbg = debug_output(
            intent=intent.value,
            selection={
                "start_node": None,
                "strategy": f"{intent.value}_DEFAULT_V1",
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
