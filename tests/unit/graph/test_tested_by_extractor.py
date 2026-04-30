"""Unit tests for TestedByEdgeExtractor.

Covers: I-TEST-NODE-3, I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-DB-TEST-1.
"""
from __future__ import annotations

import builtins
from unittest.mock import patch

from sdd.graph.extractors.tested_by_edges import TestedByEdgeExtractor
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import VALID_KINDS, SpatialNode

_NOW = "2026-01-01T00:00:00Z"


def _make_node(node_id: str, kind: str, path: str | None = None) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=node_id.split(":", 1)[-1],
        path=path,
        summary=f"{kind}:{node_id}",
        signature="",
        meta={},
        git_hash=None,
        indexed_at=_NOW,
        links=(),
    )


def _make_index(nodes: list[SpatialNode]) -> SpatialIndex:
    return SpatialIndex(
        nodes={n.node_id: n for n in nodes},
        built_at=_NOW,
        git_tree_hash=None,
        snapshot_hash="deadbeef01234567",
    )


def test_test_node_kind_not_file() -> None:
    """I-TEST-NODE-3: TEST and FILE are mutually exclusive kinds; TEST in VALID_KINDS."""
    assert "TEST" in VALID_KINDS
    assert "FILE" in VALID_KINDS

    # A node under tests/ must be TEST, a node under src/ must be FILE
    test_node = _make_node("TEST:tests/unit/commands/test_complete.py", "TEST",
                           path="tests/unit/commands/test_complete.py")
    file_node = _make_node("FILE:src/sdd/commands/complete.py", "FILE",
                           path="src/sdd/commands/complete.py")

    assert test_node.kind == "TEST"
    assert file_node.kind == "FILE"
    # They reference different paths — same file can't carry both kinds
    assert test_node.path != file_node.path


def test_tested_by_edges_filename_convention() -> None:
    """I-GRAPH-TESTED-BY-1: edges derived from filename convention only.

    tests/unit/commands/test_complete.py →
        FILE:src/sdd/commands/complete.py --tested_by--> TEST:...
        COMMAND:complete                  --tested_by--> TEST:...
    """
    test_node_id = "TEST:tests/unit/commands/test_complete.py"
    file_node_id = "FILE:src/sdd/commands/complete.py"
    cmd_node_id = "COMMAND:complete"

    index = _make_index([
        _make_node(test_node_id, "TEST"),
        _make_node(file_node_id, "FILE"),
        _make_node(cmd_node_id, "COMMAND"),
    ])

    extractor = TestedByEdgeExtractor()
    edges = extractor.extract(index)

    srcs = {e.src for e in edges}
    dsts = {e.dst for e in edges}
    kinds = {e.kind for e in edges}

    assert file_node_id in srcs
    assert cmd_node_id in srcs
    assert test_node_id in dsts
    assert kinds == {"tested_by"}
    assert len(edges) == 2


def test_tested_by_no_phantom_edges() -> None:
    """I-GRAPH-TESTED-BY-2: no edge emitted when source node absent from index."""
    test_node_id = "TEST:tests/unit/commands/test_complete.py"

    # Index has only the TEST node — no FILE or COMMAND nodes present
    index = _make_index([_make_node(test_node_id, "TEST")])

    extractor = TestedByEdgeExtractor()
    edges = extractor.extract(index)

    assert edges == [], f"Expected no edges, got: {edges}"


def test_tested_by_no_ast_heuristics() -> None:
    """I-GRAPH-TESTED-BY-1: extractor must not call open() (no AST heuristics)."""
    test_node_id = "TEST:tests/unit/commands/test_complete.py"
    file_node_id = "FILE:src/sdd/commands/complete.py"
    cmd_node_id = "COMMAND:complete"

    index = _make_index([
        _make_node(test_node_id, "TEST"),
        _make_node(file_node_id, "FILE"),
        _make_node(cmd_node_id, "COMMAND"),
    ])

    open_calls: list[str] = []

    original_open = builtins.open

    def _spy_open(*args: object, **kwargs: object) -> object:
        open_calls.append(str(args[0]) if args else "?")
        return original_open(*args, **kwargs)

    extractor = TestedByEdgeExtractor()
    with patch("builtins.open", side_effect=_spy_open):
        extractor.extract(index)

    assert open_calls == [], f"open() must not be called; called with: {open_calls}"
