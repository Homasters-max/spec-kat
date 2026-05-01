"""Unit tests for sdd.graph_navigation.cli.formatting."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sdd.graph_navigation.cli.formatting import (
    debug_output,
    emit_error,
    format_error,
    format_json,
    format_text,
)
from sdd.policy import QueryIntent


def _ctx(nodes=(), edges=(), intent=None, effective_intent=None, **kw):
    return SimpleNamespace(
        intent=intent or QueryIntent.EXPLAIN,
        effective_intent=effective_intent or QueryIntent.EXPLAIN,
        intent_transform_reason=None,
        nodes=list(nodes),
        edges=list(edges),
        budget_used={},
        selection_exhausted=True,
        graph_snapshot_hash="abc123",
        context_id="ctx-1",
        **kw,
    )


def _node(node_id="n1", kind="module", label="L", summary="S"):
    return SimpleNamespace(node_id=node_id, kind=kind, label=label, summary=summary)


def _edge(edge_id="e1", src="a", dst="b", kind="imports"):
    return SimpleNamespace(edge_id=edge_id, src=src, dst=dst, kind=kind)


def _resp(context=None, rag_summary=None, rag_mode=None, candidates=None):
    return SimpleNamespace(
        context=context or _ctx(),
        rag_summary=rag_summary,
        rag_mode=rag_mode,
        candidates=candidates,
    )


# ── format_error ─────────────────────────────────────────────────────────────


def test_format_error_basic():
    out = format_error("NotFound", "missing resource")
    data = json.loads(out)
    assert data["error_type"] == "NotFound"
    assert data["message"] == "missing resource"


def test_format_error_with_extra():
    out = format_error("E", "msg", extra={"code": 42, "phase": 61})
    data = json.loads(out)
    assert data["code"] == 42
    assert data["phase"] == 61


def test_format_error_no_extra_key():
    out = format_error("E", "msg")
    data = json.loads(out)
    assert "extra" not in data


# ── emit_error ────────────────────────────────────────────────────────────────


def test_emit_error_writes_to_stderr(capsys):
    emit_error("TestError", "something went wrong")
    err = capsys.readouterr().err
    data = json.loads(err)
    assert data["error_type"] == "TestError"
    assert data["message"] == "something went wrong"


def test_emit_error_with_extra(capsys):
    emit_error("E", "msg", extra={"detail": "x"})
    err = capsys.readouterr().err
    data = json.loads(err)
    assert data["detail"] == "x"


# ── debug_output ─────────────────────────────────────────────────────────────


def test_debug_output_basic():
    result = debug_output("EXPLAIN", {"nodes": 2}, {"tokens": 100})
    assert result["intent"] == "EXPLAIN"
    assert result["selection"] == {"nodes": 2}
    assert result["budget"] == {"tokens": 100}
    assert result["dropped"] == {"nodes": [], "edges": []}


def test_debug_output_with_dropped():
    dropped = {"nodes": ["n1"], "edges": ["e1"]}
    result = debug_output("SEARCH", {}, {}, dropped=dropped)
    assert result["dropped"] == dropped


# ── format_json ───────────────────────────────────────────────────────────────


def test_format_json_basic():
    resp = _resp()
    out = format_json(resp)
    data = json.loads(out)
    assert "context" in data
    assert data["rag_summary"] is None
    assert data["candidates"] is None


def test_format_json_with_rag_summary():
    resp = _resp(rag_summary="summary text", rag_mode="LOCAL")
    out = format_json(resp)
    data = json.loads(out)
    assert data["rag_summary"] == "summary text"
    assert data["rag_mode"] == "LOCAL"


def test_format_json_with_debug_info():
    resp = _resp()
    debug = {"intent": "EXPLAIN", "selection": {}, "budget": {}}
    out = format_json(resp, debug_info=debug)
    data = json.loads(out)
    assert "debug" in data
    assert data["debug"]["intent"] == "EXPLAIN"


def test_format_json_without_debug():
    resp = _resp()
    out = format_json(resp)
    data = json.loads(out)
    assert "debug" not in data


def test_format_json_with_candidates():
    cand = SimpleNamespace(node_id="n1", kind="module", label="L", summary="S", fuzzy_score=0.9)
    resp = _resp(candidates=[cand])
    out = format_json(resp)
    data = json.loads(out)
    assert data["candidates"] is not None
    assert data["candidates"][0]["node_id"] == "n1"
    assert data["candidates"][0]["fuzzy_score"] == pytest.approx(0.9)


def test_format_json_context_nodes_edges():
    node = _node("n2", "function", "myFn", "does X")
    edge = _edge("e1", "a", "b", "calls")
    ctx = _ctx(nodes=[node], edges=[edge])
    resp = _resp(context=ctx)
    out = format_json(resp)
    data = json.loads(out)
    ctx_data = data["context"]
    assert ctx_data["nodes"][0]["node_id"] == "n2"
    assert ctx_data["edges"][0]["src"] == "a"


# ── format_text ───────────────────────────────────────────────────────────────


def test_format_text_intent_same():
    resp = _resp()
    out = format_text(resp)
    assert "**Intent:**" in out
    assert "→" not in out


def test_format_text_intent_transformed():
    ctx = _ctx(intent=QueryIntent.SEARCH, effective_intent=QueryIntent.EXPLAIN)
    ctx.intent_transform_reason = "only one match"
    resp = _resp(context=ctx)
    out = format_text(resp)
    assert "→" in out
    assert "only one match" in out


def test_format_text_with_nodes():
    node = _node("n1", "module", "MyModule", "does stuff")
    ctx = _ctx(nodes=[node])
    resp = _resp(context=ctx)
    out = format_text(resp)
    assert "**Nodes**" in out
    assert "n1" in out


def test_format_text_no_nodes():
    resp = _resp()
    out = format_text(resp)
    assert "**Nodes**" not in out


def test_format_text_with_edges():
    edge = _edge("e1", "src_mod", "dst_mod", "imports")
    ctx = _ctx(edges=[edge])
    resp = _resp(context=ctx)
    out = format_text(resp)
    assert "**Edges**" in out
    assert "src_mod" in out


def test_format_text_with_rag_summary():
    resp = _resp(rag_summary="RAG says hello", rag_mode="LOCAL")
    out = format_text(resp)
    assert "RAG says hello" in out
    assert "mode=LOCAL" in out


def test_format_text_no_rag_summary():
    resp = _resp()
    out = format_text(resp)
    assert "RAG summary" not in out


def test_format_text_with_candidates():
    cand = SimpleNamespace(node_id="n1", kind="module", label="L", summary="S", fuzzy_score=0.85)
    ctx = _ctx()
    resp = _resp(context=ctx, candidates=[cand])
    out = format_text(resp)
    assert "**Search candidates**" in out
    assert "n1" in out
    assert "0.850" in out


def test_format_text_with_budget():
    ctx = _ctx()
    ctx.budget_used = {"tokens": 500, "nodes": 10}
    resp = _resp(context=ctx)
    out = format_text(resp)
    assert "**Budget used:**" in out
    assert "tokens=500" in out
