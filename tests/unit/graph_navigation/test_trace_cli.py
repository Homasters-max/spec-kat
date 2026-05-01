"""Unit tests for sdd trace CLI error paths — I-RUNTIME-ORCHESTRATOR-1."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestTraceCLIErrorPaths:
    """Test error paths in trace.run() (lines not covered by integration tests)."""

    def test_empty_edge_types_early_exit(self, capsys) -> None:
        """Exit 1 when --edge-types flag is explicitly empty frozenset."""
        from sdd.graph_navigation.cli.trace import run

        result = run("FILE:src/foo.py", edge_types=frozenset())
        assert result == 1
        captured = capsys.readouterr()
        assert "INVALID_ARGUMENT" in captured.err

    def test_index_builder_error(self, capsys) -> None:
        """Exit 1 when IndexBuilder.build() raises."""
        from sdd.graph_navigation.cli import trace

        with patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib:
            mock_ib.return_value.build.side_effect = RuntimeError("build failed")
            result = trace.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_error(self, capsys) -> None:
        """Exit 1 when GraphService.get_or_build() raises."""
        from sdd.graph_navigation.cli import trace

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.trace.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = RuntimeError("graph error")
            result = trace.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_invariant_error(self, capsys) -> None:
        """Exit 1 with INVARIANT_VIOLATION when GraphInvariantError raised."""
        from sdd.graph.errors import GraphInvariantError
        from sdd.graph_navigation.cli import trace

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.trace.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = GraphInvariantError("inv")
            result = trace.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "INVARIANT_VIOLATION" in captured.err

    def test_engine_query_error(self, capsys) -> None:
        """Exit 1 when engine.query() raises."""
        from sdd.graph_navigation.cli import trace

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": MagicMock()}
        with (
            patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.trace.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.trace.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.trace.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.side_effect = RuntimeError("engine fail")
            result = trace.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_node_not_found(self, capsys) -> None:
        """Exit 1 with NOT_FOUND when node_id absent from graph."""
        from sdd.graph_navigation.cli import trace

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        mock_response = MagicMock()
        mock_response.context = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.trace.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.trace.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.trace.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.return_value = mock_response
            result = trace.run("FILE:missing.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "NOT_FOUND" in captured.err

    def test_debug_output_path(self, capsys) -> None:
        """Exit 0 with debug output when debug=True and node found."""
        from sdd.graph_navigation.cli import trace

        mock_index = MagicMock()
        mock_node = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": mock_node}
        mock_response = MagicMock()
        mock_response.context = MagicMock(budget_used={})
        mock_policy = MagicMock()
        mock_policy.budget = MagicMock(max_nodes=10, max_edges=20, max_chars=1000)
        with (
            patch("sdd.graph_navigation.cli.trace.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.trace.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.trace.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.trace.ContextRuntime"),
            patch("sdd.graph_navigation.cli.trace.PolicyResolver") as mock_pr,
            patch("sdd.graph_navigation.cli.trace.format_text", return_value="output"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.return_value = mock_response
            mock_pr.return_value.resolve.return_value = mock_policy
            result = trace.run("FILE:src/foo.py", debug=True)
        assert result == 0
