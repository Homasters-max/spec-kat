"""CLI handler: sdd graph-guard check --session-id <id> — BC-61-E2.

I-GRAPH-PROTOCOL-1:      resolve ≥1 AND explain ≥1 AND trace ≥1 before any write in write_scope.
I-GRAPH-GUARD-1:         exit 1 when I-GRAPH-PROTOCOL-1 not satisfied.
I-GRAPH-COVERAGE-REQ-1:  write_target ∉ trace_path ∪ explain_nodes → exit 1 (S12).
I-EXPLAIN-USAGE-1:       explain_node ∉ trace_path ∪ write_targets → exit 1 (S13).
"""
from __future__ import annotations

import json
import sys

from sdd.graph_navigation.cli.formatting import emit_error
from sdd.graph_navigation.session_state import GraphSessionState
from sdd.infra.paths import get_sdd_root


def _load_session(session_id: str) -> GraphSessionState | None:
    path = get_sdd_root() / "runtime" / "sessions" / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return GraphSessionState(
        session_id=data["session_id"],
        phase_id=data["phase_id"],
        allowed_files=frozenset(data.get("allowed_files", [])),
        trace_path=data.get("trace_path", []),
        traversal_depth_max=data.get("traversal_depth_max", 0),
        fallback_used=data.get("fallback_used", False),
        explain_nodes=frozenset(data.get("explain_nodes", [])),
        write_targets=frozenset(data.get("write_targets", [])),
        depth_justification=data.get("depth_justification", ""),
    )


def _check_protocol(state: GraphSessionState) -> list[str]:
    violations: list[str] = []
    # I-GRAPH-PROTOCOL-1: resolve ≥1 (graph navigation must have produced allowed files)
    if not state.allowed_files:
        violations.append(
            "I-GRAPH-PROTOCOL-1: no graph navigation performed (allowed_files empty)"
        )
    # I-GRAPH-PROTOCOL-1: trace ≥1 (trace_path must be non-empty)
    if not state.trace_path:
        violations.append(
            "I-GRAPH-PROTOCOL-1: no trace performed (trace_path empty)"
        )
    # I-FALLBACK-STRICT-1: fallback allowed only when resolve=NOT_FOUND + task_inputs set
    if state.fallback_used and not state.allowed_files:
        violations.append(
            "I-FALLBACK-STRICT-1: fallback used but no files resolved (allowed_files empty)"
        )
    # I-GRAPH-DEPTH-1: traversal_depth_max ≥ 2 OR depth_justification provided
    if state.traversal_depth_max < 2 and not state.depth_justification:
        violations.append(
            "I-GRAPH-DEPTH-1: traversal_depth_max < 2 and depth_justification not provided"
        )
    # I-GRAPH-COVERAGE-REQ-1: each write_target must appear in trace_path ∪ explain_nodes
    trace_set = set(state.trace_path)
    for wt in sorted(state.write_targets):
        if wt not in trace_set and wt not in state.explain_nodes:
            violations.append(
                f"I-GRAPH-COVERAGE-REQ-1: write_target {wt!r} not in trace_path ∪ explain_nodes"
            )
    # I-EXPLAIN-USAGE-1: each explain_node must appear in trace_path ∪ write_targets
    for en in sorted(state.explain_nodes):
        if en not in trace_set and en not in state.write_targets:
            violations.append(
                f"I-EXPLAIN-USAGE-1: explain_node {en!r} not in trace_path ∪ write_targets"
            )
    return violations


def run(session_id: str) -> int:
    """Execute graph-guard check pipeline. Returns exit code (0 = pass, 1 = violation)."""
    state = _load_session(session_id)
    if state is None:
        emit_error("NOT_FOUND", f"Session not found: {session_id!r}")
        return 1

    violations = _check_protocol(state)
    if violations:
        json.dump(
            {"error": "GRAPH_PROTOCOL_VIOLATION", "violations": violations},
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1

    return 0
