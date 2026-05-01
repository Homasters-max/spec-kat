"""Integration tests: sdd graph-guard check — I-GRAPH-GUARD-1 (BC-56-G1, T-5608).

INT-GG-1: graph call logged → graph-guard check exit 0
INT-GG-2: no calls in log → graph-guard check exit 1
INT-GG-3: call logged for different session → guard sees no calls for current session → exit 1
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.infra.graph_call_log import GraphCallEntry, log_graph_call, query_graph_calls
from sdd.graph_navigation.cli import graph_guard


def _run_main(args: list[str]) -> tuple[int, str, str]:
    """Run graph_guard.main() with captured stdout/stderr."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout_buf),
        contextlib.redirect_stderr(stderr_buf),
    ):
        rc = graph_guard.main(args)
    return rc, stdout_buf.getvalue(), stderr_buf.getvalue()


def _make_entry(session_id: str) -> GraphCallEntry:
    return GraphCallEntry(
        command="explain",
        args={"node_id": "FILE:src/sdd/infra/graph_call_log.py"},
        session_id=session_id,
        ts="2026-05-01T00:00:00+00:00",
        result_size={"nodes": 3, "edges": 2},
    )


# ---------------------------------------------------------------------------
# INT-GG-1: graph call logged → graph-guard check exit 0
# ---------------------------------------------------------------------------

def test_intgg1_call_logged_exit_0() -> None:
    """INT-GG-1: log_graph_call → query_graph_calls returns ≥1 → graph-guard exit 0."""
    session_id = "intgg1-session"
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        log_path = f.name

    entry = _make_entry(session_id)
    log_graph_call(entry, log_path=log_path)

    calls = query_graph_calls(session_id=session_id, log_path=log_path)
    assert len(calls) == 1, "sanity: log_graph_call must write exactly one entry"

    with patch.object(graph_guard, "query_graph_calls", side_effect=lambda **kw: query_graph_calls(log_path=log_path, **kw)):
        with patch.object(graph_guard, "get_current_session_id", return_value=session_id):
            rc, _out, _err = _run_main(["check", "--task", "T-5608"])

    assert rc == 0, f"INT-GG-1: expected exit 0 after logging call, got {rc}"

    Path(log_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# INT-GG-2: no calls in log → graph-guard check exit 1
# ---------------------------------------------------------------------------

def test_intgg2_no_calls_exit_1() -> None:
    """INT-GG-2: empty log file → query_graph_calls returns [] → graph-guard exit 1."""
    session_id = "intgg2-session"
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        log_path = f.name

    calls = query_graph_calls(session_id=session_id, log_path=log_path)
    assert calls == [], "sanity: empty file must return []"

    with patch.object(graph_guard, "query_graph_calls", side_effect=lambda **kw: query_graph_calls(log_path=log_path, **kw)):
        with patch.object(graph_guard, "get_current_session_id", return_value=session_id):
            rc, _out, err = _run_main(["check", "--task", "T-5608"])

    assert rc == 1, f"INT-GG-2: expected exit 1 with no calls, got {rc}"
    error = json.loads(err)
    assert error["error_type"] == "GRAPH_GUARD_VIOLATION"
    assert error["violated_invariant"] == "I-GRAPH-GUARD-1"

    Path(log_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# INT-GG-3: call for different session → guard finds no calls → exit 1
# ---------------------------------------------------------------------------

def test_intgg3_wrong_session_exit_1() -> None:
    """INT-GG-3: call logged for session-A, guard checks session-B → exit 1."""
    session_a = "intgg3-session-a"
    session_b = "intgg3-session-b"
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        log_path = f.name

    log_graph_call(_make_entry(session_a), log_path=log_path)

    calls_b = query_graph_calls(session_id=session_b, log_path=log_path)
    assert calls_b == [], "sanity: filter by session must exclude other sessions"

    with patch.object(graph_guard, "query_graph_calls", side_effect=lambda **kw: query_graph_calls(log_path=log_path, **kw)):
        with patch.object(graph_guard, "get_current_session_id", return_value=session_b):
            rc, _out, err = _run_main(["check", "--task", "T-5608"])

    assert rc == 1, f"INT-GG-3: expected exit 1 for wrong session, got {rc}"
    error = json.loads(err)
    assert error["violated_invariant"] == "I-GRAPH-GUARD-1"

    Path(log_path).unlink(missing_ok=True)
