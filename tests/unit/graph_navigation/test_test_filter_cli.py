"""Tests for sdd test-filter CLI handler — I-TEST-FILTER-1, I-DB-TEST-1."""
from __future__ import annotations

import shlex
from unittest.mock import MagicMock, patch

from sdd.graph.types import EDGE_KIND_PRIORITY, DeterministicGraph, Edge, Node


def _make_graph(
    nodes: dict[str, Node],
    edges_out: dict[str, list[Edge]] | None = None,
) -> DeterministicGraph:
    edges_out = edges_out or {}
    edges_in: dict[str, list[Edge]] = {}
    for _src, edges in edges_out.items():
        for e in edges:
            edges_in.setdefault(e.dst, []).append(e)
    return DeterministicGraph(
        nodes=nodes,
        edges_out=edges_out,
        edges_in=edges_in,
        source_snapshot_hash="testhash",
    )


def _make_tested_by_edge(src: str, dst: str) -> Edge:
    return Edge(
        edge_id=f"{src}:tested_by:{dst}"[:16],
        src=src,
        dst=dst,
        kind="tested_by",
        priority=EDGE_KIND_PRIORITY["tested_by"],
        source="test",
        meta={},
    )


def test_test_filter_runs_targeted_pytest() -> None:
    """I-TEST-FILTER-1: pytest is invoked with test paths from tested_by edges; returncode passes through."""
    node_id = "CMD:my_command"
    test_path = "tests/unit/test_foo.py"
    test_node_id = f"TEST:{test_path}"

    nodes = {
        node_id: Node(node_id=node_id, kind="COMMAND", label="my_command", summary="", meta={}),
        test_node_id: Node(node_id=test_node_id, kind="TEST", label=test_path, summary="", meta={}),
    }
    edge = _make_tested_by_edge(node_id, test_node_id)
    graph = _make_graph(nodes, {node_id: [edge]})

    fake_index = MagicMock()
    fake_result = MagicMock()
    fake_result.returncode = 42

    with (
        patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib,
        patch("sdd.graph_navigation.cli.test_filter.GraphService") as mock_gs,
        patch("sdd.graph_navigation.cli.test_filter.subprocess.run", return_value=fake_result) as mock_run,
    ):
        mock_ib.return_value.build.return_value = fake_index
        mock_gs.return_value.get_or_build.return_value = graph

        from sdd.graph_navigation.cli.test_filter import run
        rc = run(node_id)

    assert rc == 42
    mock_run.assert_called_once_with(["pytest", test_path, "-q", "-m", "not pg"])


def test_test_filter_fallback_when_no_edges() -> None:
    """I-TEST-FILTER-1: no tested_by edges → fallback to tier command; returncode passes through."""
    node_id = "CMD:my_command"
    nodes = {
        node_id: Node(node_id=node_id, kind="COMMAND", label="my_command", summary="", meta={}),
    }
    graph = _make_graph(nodes)

    fake_index = MagicMock()
    fake_result = MagicMock()
    fake_result.returncode = 0

    fallback_cmd = "pytest tests/ -x -q"
    fake_config = {"build": {"commands": {"test": fallback_cmd}}}

    with (
        patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib,
        patch("sdd.graph_navigation.cli.test_filter.GraphService") as mock_gs,
        patch("sdd.graph_navigation.cli.test_filter.load_config", return_value=fake_config),
        patch("sdd.graph_navigation.cli.test_filter.subprocess.run", return_value=fake_result) as mock_run,
    ):
        mock_ib.return_value.build.return_value = fake_index
        mock_gs.return_value.get_or_build.return_value = graph

        from sdd.graph_navigation.cli.test_filter import run
        rc = run(node_id, tier="default")

    assert rc == 0
    mock_run.assert_called_once_with(shlex.split(fallback_cmd))
