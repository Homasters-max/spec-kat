"""Tests for BC-56-A1: GraphCallLog module.

Coverage: I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1
Acceptance criteria: write→read roundtrip; session_id filter; absent file → []; malformed → skipped.
"""
from __future__ import annotations

import json
import os

import pytest

from sdd.infra.graph_call_log import GraphCallEntry, log_graph_call, query_graph_calls


def _make_entry(
    command: str = "explain",
    session_id: str | None = "sess-001",
    nodes: int = 3,
    edges: int = 2,
) -> GraphCallEntry:
    return GraphCallEntry(
        command=command,
        args={"node_id": "FILE:src/foo.py", "edge_types": ["imports"]},
        session_id=session_id,
        ts="2026-05-01T10:00:00+00:00",
        result_size={"nodes": nodes, "edges": edges},
    )


def test_roundtrip(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    entry = _make_entry()
    log_graph_call(entry, log_path=log)
    result = query_graph_calls(log_path=log)
    assert len(result) == 1
    assert result[0].command == "explain"
    assert result[0].session_id == "sess-001"
    assert result[0].result_size == {"nodes": 3, "edges": 2}


def test_multiple_entries_appended(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    for cmd in ("explain", "trace", "resolve"):
        log_graph_call(_make_entry(command=cmd, session_id=f"sess-{cmd}"), log_path=log)
    result = query_graph_calls(log_path=log)
    assert len(result) == 3
    commands = [e.command for e in result]
    assert commands == ["explain", "trace", "resolve"]


def test_session_id_filter(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    log_graph_call(_make_entry(session_id="sess-A"), log_path=log)
    log_graph_call(_make_entry(session_id="sess-B"), log_path=log)
    log_graph_call(_make_entry(session_id="sess-A"), log_path=log)

    result_a = query_graph_calls(session_id="sess-A", log_path=log)
    assert len(result_a) == 2
    assert all(e.session_id == "sess-A" for e in result_a)

    result_b = query_graph_calls(session_id="sess-B", log_path=log)
    assert len(result_b) == 1


def test_absent_file_returns_empty(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "nonexistent.jsonl")
    result = query_graph_calls(log_path=log)
    assert result == []


def test_malformed_line_skipped(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    valid = _make_entry()
    log_graph_call(valid, log_path=log)

    with open(log, "a", encoding="utf-8") as f:
        f.write("not-json\n")
        f.write('{"command": "trace"}\n')  # missing required fields

    result = query_graph_calls(log_path=log)
    assert len(result) == 1
    assert result[0].command == "explain"


def test_none_session_id_stored_and_retrieved(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    entry = _make_entry(session_id=None)
    log_graph_call(entry, log_path=log)
    result = query_graph_calls(log_path=log)
    assert len(result) == 1
    assert result[0].session_id is None


def test_session_id_filter_excludes_none_session(tmp_path: pytest.TempPathFactory) -> None:
    log = str(tmp_path / "graph_calls.jsonl")
    log_graph_call(_make_entry(session_id=None), log_path=log)
    log_graph_call(_make_entry(session_id="sess-X"), log_path=log)

    result = query_graph_calls(session_id="sess-X", log_path=log)
    assert len(result) == 1
    assert result[0].session_id == "sess-X"


def test_to_dict_from_dict_roundtrip() -> None:
    entry = _make_entry()
    restored = GraphCallEntry.from_dict(entry.to_dict())
    assert restored == entry
