"""CLI handler: sdd graph-guard check — BC-56-G1 + BC-61-E2.

BC-56-G1  (main):  check --task T-NNN [--session-id <id>]
  Uses query_graph_calls() — exit 0 if ≥1 valid call, exit 1 with I-GRAPH-GUARD-1.

BC-61-E2  (run):   check --session-id <id> (legacy, used by older sessions)
  Uses GraphSessionState — checks I-GRAPH-PROTOCOL-1 violations.

I-GRAPH-GUARD-1:         Each IMPLEMENT session MUST have ≥1 valid GraphCallEntry.
I-GRAPH-PROTOCOL-1:      resolve ≥1 AND explain ≥1 AND trace ≥1 before any write in write_scope.
I-GRAPH-COVERAGE-REQ-1:  write_target ∉ trace_path ∪ explain_nodes → exit 1 (S12).
I-EXPLAIN-USAGE-1:       explain_node ∉ trace_path ∪ write_targets → exit 1 (S13).
"""
from __future__ import annotations

import argparse
import json
import sys

from sdd.graph_navigation.cli.formatting import emit_error
from sdd.graph_navigation.session_state import GraphSessionState
from sdd.infra.graph_call_log import query_graph_calls
from sdd.infra.paths import get_sdd_root
from sdd.infra.session_context import get_current_session_id


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


def main(args: list[str]) -> int:
    """BC-56-G1: sdd graph-guard check --task T-NNN [--session-id <id>].

    exit 0  if ≥1 valid GraphCallEntry for session (I-GRAPH-GUARD-1 satisfied).
    exit 1  with JSON stderr if no calls found.
    Read-only: does not go through REGISTRY.
    """
    if not args or args[0] != "check":
        _emit_json_error(
            "USAGE_ERROR",
            "Usage: sdd graph-guard check --task T-NNN [--session-id <id>]",
            violated_invariant="I-GRAPH-GUARD-1",
        )
        return 1

    parser = argparse.ArgumentParser(prog="sdd graph-guard check", add_help=False)
    parser.add_argument("--task", dest="task_id", required=True, metavar="T-NNN")
    parser.add_argument("--session-id", dest="session_id", default=None)
    parser.error = lambda msg: (_ for _ in ()).throw(ValueError(msg))  # type: ignore[method-assign]

    try:
        parsed = parser.parse_args(args[1:])
    except (SystemExit, ValueError):
        _emit_json_error(
            "USAGE_ERROR",
            "Usage: sdd graph-guard check --task T-NNN [--session-id <id>]",
            violated_invariant="I-GRAPH-GUARD-1",
        )
        return 1

    session_id = parsed.session_id if parsed.session_id is not None else get_current_session_id()

    if session_id is None:
        _emit_json_error(
            "GRAPH_GUARD_VIOLATION",
            (
                f"No session_id available for task {parsed.task_id} — "
                "current_session.json absent or empty"
            ),
            violated_invariant="I-GRAPH-GUARD-1",
        )
        return 1

    calls = query_graph_calls(session_id=session_id)
    valid_calls = [c for c in calls if c.session_id is not None]

    if len(valid_calls) >= 1:
        return 0

    _emit_json_error(
        "GRAPH_GUARD_VIOLATION",
        (
            f"Task {parsed.task_id}: no graph navigation calls found for "
            f"session {session_id!r}. "
            "Use sdd explain/trace/resolve before sdd complete (I-GRAPH-GUARD-1)."
        ),
        violated_invariant="I-GRAPH-GUARD-1",
    )
    return 1


def _emit_json_error(error_type: str, message: str, *, violated_invariant: str) -> None:
    json.dump(
        {
            "error_type": error_type,
            "message": message,
            "violated_invariant": violated_invariant,
            "exit_code": 1,
        },
        sys.stderr,
    )
    sys.stderr.write("\n")


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
