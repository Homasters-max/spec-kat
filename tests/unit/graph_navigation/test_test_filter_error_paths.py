"""Additional tests for sdd test-filter error paths and BFS edge cases."""
from __future__ import annotations

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


def _tested_by_edge(src: str, dst: str) -> Edge:
    return Edge(
        edge_id=f"{src}:tb:{dst}"[:16],
        src=src,
        dst=dst,
        kind="tested_by",
        priority=EDGE_KIND_PRIORITY["tested_by"],
        source="test",
        meta={},
    )


class TestTestFilterErrorPaths:

    def test_index_builder_error(self, capsys) -> None:
        """Exit 1 when IndexBuilder.build() raises."""
        from sdd.graph_navigation.cli import test_filter

        with patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib:
            mock_ib.return_value.build.side_effect = RuntimeError("build failed")
            result = test_filter.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_error(self, capsys) -> None:
        """Exit 1 when GraphService.get_or_build() raises."""
        from sdd.graph_navigation.cli import test_filter

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.test_filter.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = RuntimeError("graph err")
            result = test_filter.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_node_not_found(self, capsys) -> None:
        """Exit 1 when node_id not in graph."""
        from sdd.graph_navigation.cli import test_filter

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        with (
            patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.test_filter.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = test_filter.run("FILE:missing.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "NOT_FOUND" in captured.err

    def test_fallback_config_error_when_tier_missing(self, capsys) -> None:
        """Exit 1 when tier command not found in config (CONFIG_ERROR)."""
        from sdd.graph_navigation.cli import test_filter

        node_id = "FILE:src/foo.py"
        nodes = {node_id: Node(node_id=node_id, kind="FILE", label="foo.py", summary="", meta={})}
        graph = _make_graph(nodes)
        fake_index = MagicMock()
        fake_config: dict = {"build": {"commands": {}}}

        with (
            patch("sdd.graph_navigation.cli.test_filter.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.test_filter.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.test_filter.load_config", return_value=fake_config),
        ):
            mock_ib.return_value.build.return_value = fake_index
            mock_gs.return_value.get_or_build.return_value = graph
            result = test_filter.run(node_id, tier="default")
        assert result == 1
        captured = capsys.readouterr()
        assert "CONFIG_ERROR" in captured.err

    def test_bfs_non_test_dst_skipped(self) -> None:
        """BFS over non-TEST dst nodes — they are visited but not appended to test_nodes."""
        from sdd.graph_navigation.cli.test_filter import _bfs_tested_by

        node_id = "FILE:src/foo.py"
        file_node = "FILE:src/bar.py"
        test_node = "TEST:tests/test_foo.py"
        nodes = {
            node_id: Node(node_id=node_id, kind="FILE", label="foo.py", summary="", meta={}),
            file_node: Node(node_id=file_node, kind="FILE", label="bar.py", summary="", meta={}),
            test_node: Node(node_id=test_node, kind="TEST", label="test_foo.py", summary="", meta={}),
        }
        edges_out = {
            node_id: [
                _tested_by_edge(node_id, file_node),
                _tested_by_edge(node_id, test_node),
            ]
        }
        graph = _make_graph(nodes, edges_out)
        result = _bfs_tested_by(graph, node_id)
        assert test_node in result
        assert file_node not in result

    def test_bfs_depth_limit_respected(self) -> None:
        """BFS stops at max_depth=2 — nodes beyond depth 2 not traversed."""
        from sdd.graph_navigation.cli.test_filter import _bfs_tested_by

        n0 = "FILE:src/a.py"
        n1 = "FILE:src/b.py"
        n2 = "FILE:src/c.py"
        t3 = "TEST:tests/test_deep.py"
        nodes = {
            n0: Node(node_id=n0, kind="FILE", label="a.py", summary="", meta={}),
            n1: Node(node_id=n1, kind="FILE", label="b.py", summary="", meta={}),
            n2: Node(node_id=n2, kind="FILE", label="c.py", summary="", meta={}),
            t3: Node(node_id=t3, kind="TEST", label="test_deep.py", summary="", meta={}),
        }
        edges_out = {
            n0: [_tested_by_edge(n0, n1)],
            n1: [_tested_by_edge(n1, n2)],
            n2: [_tested_by_edge(n2, t3)],
        }
        graph = _make_graph(nodes, edges_out)
        result = _bfs_tested_by(graph, n0, max_depth=2)
        assert t3 not in result

    def test_bfs_visited_prevents_cycles(self) -> None:
        """BFS visited set prevents revisiting the same node in cycles."""
        from sdd.graph_navigation.cli.test_filter import _bfs_tested_by

        n0 = "FILE:src/a.py"
        t1 = "TEST:tests/test_a.py"
        nodes = {
            n0: Node(node_id=n0, kind="FILE", label="a.py", summary="", meta={}),
            t1: Node(node_id=t1, kind="TEST", label="test_a.py", summary="", meta={}),
        }
        edges_out = {
            n0: [_tested_by_edge(n0, t1), _tested_by_edge(n0, t1)],
        }
        graph = _make_graph(nodes, edges_out)
        result = _bfs_tested_by(graph, n0)
        assert result.count(t1) == 1
