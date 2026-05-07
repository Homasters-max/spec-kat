"""Tests for graph/types.py — Edge validation and canonical priority table (I-GRAPH-DET-2)."""
from __future__ import annotations

import pytest

from sdd.graph.types import EDGE_KIND_PRIORITY, Edge


def _make_edge(priority: float, kind: str = "emits") -> Edge:
    return Edge(
        edge_id="abc123def456789a",
        src="node-A",
        dst="node-B",
        kind=kind,
        priority=priority,
        source="test",
        meta={},
    )


def test_edge_priority_out_of_range() -> None:
    """Edge.__post_init__ MUST raise ValueError when priority ∉ [0.0, 1.0] (I-GRAPH-TYPES-1)."""
    with pytest.raises(ValueError, match="priority"):
        _make_edge(priority=1.01)
    with pytest.raises(ValueError, match="priority"):
        _make_edge(priority=-0.01)


def test_edge_priority_from_canonical_table() -> None:
    """All EDGE_KIND_PRIORITY values MUST be valid priorities — Edge creation succeeds (I-GRAPH-DET-2)."""
    for kind, priority in EDGE_KIND_PRIORITY.items():
        edge = _make_edge(priority=priority, kind=kind)
        assert edge.priority == priority
        assert 0.0 <= edge.priority <= 1.0
