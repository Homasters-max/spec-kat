"""Shared CLI output formatting — format_json, format_text, format_error, debug_output.

I-CLI-FORMAT-1:        --format json outputs valid NavigationResponse JSON on stdout.
I-CLI-TRANSPARENCY-1:  debug_output exposes selection steps per stage.
I-CLI-TRANSPARENCY-2:  debug_output exposes budget and actual resource usage.
I-CLI-ERROR-CODES-1:   format_error emits structured JSON compatible with I-CLI-API-1.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from sdd.context_kernel.rag_types import NavigationResponse


def _context_to_dict(ctx: Any) -> dict[str, Any]:
    def _enum_val(v: object) -> object:
        return v.value if hasattr(v, "value") else str(v)

    return {
        "intent": _enum_val(getattr(ctx, "intent", None)),
        "effective_intent": _enum_val(getattr(ctx, "effective_intent", None)),
        "intent_transform_reason": getattr(ctx, "intent_transform_reason", None),
        "nodes": [
            {
                "node_id": n.node_id,
                "kind": n.kind,
                "label": n.label,
                "summary": n.summary,
            }
            for n in getattr(ctx, "nodes", [])
        ],
        "edges": [
            {"edge_id": e.edge_id, "src": e.src, "dst": e.dst, "kind": e.kind}
            for e in getattr(ctx, "edges", [])
        ],
        "budget_used": getattr(ctx, "budget_used", {}),
        "selection_exhausted": getattr(ctx, "selection_exhausted", True),
        "graph_snapshot_hash": getattr(ctx, "graph_snapshot_hash", ""),
        "context_id": getattr(ctx, "context_id", ""),
    }


def format_json(response: NavigationResponse, debug_info: dict[str, Any] | None = None) -> str:
    """Serialize NavigationResponse to JSON string (I-CLI-FORMAT-1).

    debug_info is nested under "debug" key when present (I-CLI-TRANSPARENCY-1/2).
    """
    candidates = None
    if response.candidates is not None:
        candidates = [
            {
                "node_id": c.node_id,
                "kind": c.kind,
                "label": c.label,
                "summary": c.summary,
                "fuzzy_score": c.fuzzy_score,
            }
            for c in response.candidates
        ]

    payload: dict[str, Any] = {
        "context": _context_to_dict(response.context),
        "rag_summary": response.rag_summary,
        "rag_mode": response.rag_mode,
        "candidates": candidates,
    }
    if debug_info is not None:
        payload["debug"] = debug_info

    return json.dumps(payload, indent=2)


def format_text(response: NavigationResponse) -> str:
    """Format NavigationResponse as human-readable markdown."""
    ctx = response.context
    lines: list[str] = []

    def _ev(v: object) -> str:
        return v.value if hasattr(v, "value") else str(v)

    intent_str = _ev(getattr(ctx, "intent", ""))
    effective_str = _ev(getattr(ctx, "effective_intent", intent_str))

    if effective_str != intent_str:
        lines.append(f"**Intent:** {intent_str} → {effective_str}")
        reason = getattr(ctx, "intent_transform_reason", None)
        if reason:
            lines.append(f"*{reason}*")
    else:
        lines.append(f"**Intent:** {intent_str}")

    nodes = getattr(ctx, "nodes", [])
    if nodes:
        lines.append("")
        lines.append(f"**Nodes** ({len(nodes)}):")
        for n in nodes:
            lines.append(f"- `{n.node_id}` ({n.kind}): {n.label}")

    edges = getattr(ctx, "edges", [])
    if edges:
        lines.append("")
        lines.append(f"**Edges** ({len(edges)}):")
        for e in edges:
            lines.append(f"- `{e.src}` —[{e.kind}]→ `{e.dst}`")

    if response.candidates:
        lines.append("")
        lines.append(f"**Search candidates** ({len(response.candidates)}):")
        for c in response.candidates:
            lines.append(
                f"- `{c.node_id}` ({c.kind}): {c.label} [score={c.fuzzy_score:.3f}]"
            )

    budget = getattr(ctx, "budget_used", {})
    if budget:
        lines.append("")
        parts = ", ".join(f"{k}={v}" for k, v in sorted(budget.items()))
        lines.append(f"**Budget used:** {parts}")

    if response.rag_summary:
        lines.append("")
        lines.append(f"**RAG summary** (mode={response.rag_mode}):")
        lines.append(response.rag_summary)

    return "\n".join(lines)


def format_error(
    error_type: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """Serialize CLI error as JSON string (I-CLI-ERROR-CODES-1, I-CLI-API-1)."""
    payload: dict[str, Any] = {"error_type": error_type, "message": message}
    if extra:
        payload.update(extra)
    return json.dumps(payload)


def emit_error(
    error_type: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write error JSON to stderr."""
    print(format_error(error_type, message, extra), file=sys.stderr)


def debug_output(
    intent: str,
    selection: dict[str, Any],
    budget: dict[str, Any],
    dropped: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Build debug transparency payload (I-CLI-TRANSPARENCY-1/2).

    Returns dict merged into JSON output or rendered as a block in text mode.
    """
    return {
        "intent": intent,
        "selection": selection,
        "budget": budget,
        "dropped": dropped if dropped is not None else {"nodes": [], "edges": []},
    }
