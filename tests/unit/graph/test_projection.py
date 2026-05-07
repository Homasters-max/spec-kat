"""Tests for graph/projection.py — SpatialNode → Node projection (I-GRAPH-META-1, I-GRAPH-TYPES-1)."""
from __future__ import annotations

from sdd.graph.projection import project_node
from sdd.graph.types import ALLOWED_META_KEYS
from sdd.spatial.nodes import SpatialNode


def _make_spatial(meta: dict, path: str | None = "src/foo.py") -> SpatialNode:
    return SpatialNode(
        node_id="test-node-1",
        kind="FILE",
        label="foo",
        path=path,
        summary="A test node",
        signature="def foo(): ...",
        meta=meta,
        git_hash="deadbeef",
        indexed_at="2026-01-01T00:00:00Z",
    )


def test_project_node_excludes_indexing_fields() -> None:
    """Indexing fields (signature, git_hash, indexed_at) MUST NOT appear in Node.meta (I-GRAPH-TYPES-1)."""
    node = project_node(_make_spatial(meta={
        "signature": "def foo(): ...",
        "git_hash": "deadbeef",
        "indexed_at": "2026-01-01T00:00:00Z",
    }))
    assert "signature" not in node.meta
    assert "git_hash" not in node.meta
    assert "indexed_at" not in node.meta


def test_project_node_allowlist() -> None:
    """Only ALLOWED_META_KEYS (plus 'path') MUST appear in Node.meta (I-GRAPH-META-1)."""
    meta = {k: f"val-{k}" for k in ALLOWED_META_KEYS}
    node = project_node(_make_spatial(meta=meta))
    for key in node.meta:
        assert key == "path" or key in ALLOWED_META_KEYS, f"unexpected key in meta: {key!r}"


def test_project_node_blocklist_removed() -> None:
    """Unknown meta keys not in ALLOWED_META_KEYS MUST be dropped silently (I-GRAPH-META-1)."""
    node = project_node(_make_spatial(meta={
        "language": "python",
        "custom_secret_key": "should-be-dropped",
        "another_unknown": 42,
    }))
    assert "custom_secret_key" not in node.meta
    assert "another_unknown" not in node.meta
    assert node.meta.get("language") == "python"
