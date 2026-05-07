"""Tests for GraphCache (I-GRAPH-CACHE-1, I-GRAPH-META-DEBUG-1)."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from sdd.graph.cache import GRAPH_SCHEMA_VERSION, GraphCache
from sdd.graph.projection import project_node
from sdd.graph.types import DeterministicGraph, Node
from sdd.spatial.nodes import SpatialNode

_NOW = "2026-01-01T00:00:00Z"


def _make_spatial_node(
    node_id: str,
    kind: str = "FILE",
    meta: dict | None = None,
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=node_id,
        path=f"src/{node_id}.py",
        summary=f"{kind}:{node_id}",
        signature="",
        meta=meta or {},
        git_hash=None,
        indexed_at=_NOW,
    )


def _make_graph(snapshot_hash: str = "abc123") -> DeterministicGraph:
    node = Node(node_id="FILE:x", kind="FILE", label="x", summary="s", meta={})
    return DeterministicGraph(
        nodes={"FILE:x": node},
        edges_out={"FILE:x": []},
        edges_in={"FILE:x": []},
        source_snapshot_hash=snapshot_hash,
    )


# ---------------------------------------------------------------------------
# test_graph_cache_stores_and_retrieves — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_cache_stores_and_retrieves() -> None:
    """GraphCache.store/get round-trip preserves the graph (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = GraphCache(cache_dir=Path(tmpdir))
        graph = _make_graph("hash1")
        cache.store("key1", graph)
        result = cache.get("key1")
        assert result is not None
        assert result.source_snapshot_hash == "hash1"


# ---------------------------------------------------------------------------
# test_graph_cache_evicts_on_schema_version_mismatch — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_cache_evicts_on_schema_version_mismatch() -> None:
    """Cache returns None when stored schema_version != GRAPH_SCHEMA_VERSION (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = GraphCache(cache_dir=Path(tmpdir))
        graph = _make_graph("hash2")
        cache.store("key2", graph)

        cache_file = Path(tmpdir) / "key2.json"
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        payload["schema_version"] = "0.0.0-stale"
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        result = cache.get("key2")
        assert result is None, "Stale schema_version must evict cache entry"


# ---------------------------------------------------------------------------
# test_graph_cache_miss_returns_none — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_cache_miss_returns_none() -> None:
    """Cache returns None for unknown key (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = GraphCache(cache_dir=Path(tmpdir))
        assert cache.get("nonexistent") is None


# ---------------------------------------------------------------------------
# test_graph_cache_invalidate — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_cache_invalidate() -> None:
    """Cache.invalidate removes entry; subsequent get returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = GraphCache(cache_dir=Path(tmpdir))
        graph = _make_graph("hash3")
        cache.store("key3", graph)
        assert cache.get("key3") is not None
        cache.invalidate("key3")
        assert cache.get("key3") is None


# ---------------------------------------------------------------------------
# test_graph_cache_stored_payload_contains_schema_version — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_cache_stored_payload_contains_schema_version() -> None:
    """Stored JSON payload contains 'schema_version': GRAPH_SCHEMA_VERSION (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = GraphCache(cache_dir=Path(tmpdir))
        graph = _make_graph("hash4")
        cache.store("key4", graph)

        cache_file = Path(tmpdir) / "key4.json"
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        assert payload.get("schema_version") == GRAPH_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# test_project_node_debug_logs_dropped_keys — I-GRAPH-META-DEBUG-1
# ---------------------------------------------------------------------------

def test_project_node_debug_logs_dropped_keys(caplog: pytest.LogCaptureFixture) -> None:
    """project_node logs WARNING for dropped unknown meta keys when DEBUG not enabled (I-GRAPH-META-DEBUG-1)."""
    node = _make_spatial_node("FILE:a", meta={"unknown_key": "val", "another_bad": 42})
    with caplog.at_level(logging.WARNING, logger="sdd.graph.projection"):
        result = project_node(node)

    assert "unknown_key" not in result.meta
    assert "another_bad" not in result.meta

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, "Expected WARNING log when unknown meta keys are dropped"
    assert any("unknown_key" in r.message for r in warning_records)
