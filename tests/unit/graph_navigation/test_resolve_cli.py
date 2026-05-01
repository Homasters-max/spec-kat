"""Unit tests for sdd resolve CLI error paths — I-RUNTIME-ORCHESTRATOR-1, I-SEARCH-DIRECT-1."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestResolveCLIErrorPaths:
    """Test error paths in resolve.run() not covered by integration tests."""

    def test_no_query_no_node_id(self, capsys) -> None:
        """Exit 1 when neither query nor --node-id provided."""
        from sdd.graph_navigation.cli.resolve import run

        result = run(None, node_id=None)
        assert result == 1
        captured = capsys.readouterr()
        assert "USAGE_ERROR" in captured.err

    def test_index_builder_error(self, capsys) -> None:
        """Exit 1 when IndexBuilder.build() raises."""
        from sdd.graph_navigation.cli import resolve

        with patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib:
            mock_ib.return_value.build.side_effect = RuntimeError("build failed")
            result = resolve.run("some query")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_error(self, capsys) -> None:
        """Exit 1 when GraphService.get_or_build() raises."""
        from sdd.graph_navigation.cli import resolve

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.resolve.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = RuntimeError("graph error")
            result = resolve.run("some query")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_node_id_not_found(self, capsys) -> None:
        """Exit 1 when --node-id not in graph.nodes."""
        from sdd.graph_navigation.cli import resolve

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        with (
            patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.resolve.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = resolve.run(None, node_id="FILE:missing.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "NOT_FOUND" in captured.err

    def test_engine_query_error_node_id_path(self, capsys) -> None:
        """Exit 1 when engine.query() raises in node_id path."""
        from sdd.graph_navigation.cli import resolve

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": MagicMock()}
        with (
            patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.resolve.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.resolve.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.resolve.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.side_effect = RuntimeError("engine fail")
            result = resolve.run(None, node_id="FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_engine_query_error_search_path(self, capsys) -> None:
        """Exit 1 when engine.query() raises in query/search path."""
        from sdd.graph_navigation.cli import resolve

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        with (
            patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.resolve.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.resolve.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.resolve.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.side_effect = RuntimeError("engine fail")
            result = resolve.run("some query")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_debug_output_with_node_id(self, capsys) -> None:
        """Exit 0 with debug output in node_id path."""
        from sdd.graph_navigation.cli import resolve

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": MagicMock()}
        mock_response = MagicMock()
        mock_response.context = MagicMock(budget_used={})
        mock_policy = MagicMock()
        mock_policy.budget = MagicMock(max_nodes=10, max_edges=20, max_chars=1000)
        with (
            patch("sdd.graph_navigation.cli.resolve.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.resolve.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.resolve.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.resolve.ContextRuntime"),
            patch("sdd.graph_navigation.cli.resolve.PolicyResolver") as mock_pr,
            patch("sdd.graph_navigation.cli.resolve.format_text", return_value="output"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.return_value = mock_response
            mock_pr.return_value.resolve.return_value = mock_policy
            result = resolve.run(None, node_id="FILE:src/foo.py", debug=True)
        assert result == 0
