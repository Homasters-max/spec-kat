"""Unit tests for sdd explain CLI error paths — I-RUNTIME-ORCHESTRATOR-1, I-GRAPH-IMPLEMENTS-2."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestExplainCLIErrorPaths:
    """Test error paths in explain.run() not covered by integration tests."""

    def test_empty_edge_types_early_exit(self, capsys) -> None:
        """Exit 1 when --edge-types flag is explicitly empty frozenset."""
        from sdd.graph_navigation.cli.explain import run

        result = run("FILE:src/foo.py", edge_types=frozenset())
        assert result == 1
        captured = capsys.readouterr()
        assert "INVALID_ARGUMENT" in captured.err

    def test_index_builder_error(self, capsys) -> None:
        """Exit 1 when IndexBuilder.build() raises."""
        from sdd.graph_navigation.cli import explain

        with patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib:
            mock_ib.return_value.build.side_effect = RuntimeError("build failed")
            result = explain.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_error(self, capsys) -> None:
        """Exit 1 when GraphService.get_or_build() raises."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = RuntimeError("graph error")
            result = explain.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_node_not_found(self, capsys) -> None:
        """Exit 1 with NOT_FOUND when node_id absent from graph."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = explain.run("FILE:missing.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "NOT_FOUND" in captured.err

    def test_engine_query_error(self, capsys) -> None:
        """Exit 1 when first engine.query() raises."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": MagicMock()}
        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.explain.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.explain.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.side_effect = RuntimeError("engine fail")
            result = explain.run("FILE:src/foo.py")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_command_bfs_retry_on_empty_context(self, capsys) -> None:
        """I-GRAPH-IMPLEMENTS-2: COMMAND node with empty BFS retries from handler node."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        mock_edge = MagicMock()
        mock_edge.kind = "implements"
        mock_edge.src = "FILE:src/sdd/commands/complete.py"
        mock_graph = MagicMock()
        mock_graph.nodes = {"COMMAND:complete": MagicMock()}
        mock_graph.edges_in.get.return_value = [mock_edge]

        mock_ctx = MagicMock()
        mock_ctx.selection_exhausted = True
        mock_ctx.nodes = []

        mock_response = MagicMock()
        mock_response.context = mock_ctx

        mock_retry_response = MagicMock()
        mock_retry_response.context = MagicMock(budget_used={})

        mock_engine = MagicMock()
        mock_engine.query.side_effect = [mock_response, mock_retry_response]

        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.explain.ContextEngine", return_value=mock_engine),
            patch("sdd.graph_navigation.cli.explain.ContextRuntime"),
            patch("sdd.graph_navigation.cli.explain.format_text", return_value="output"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = explain.run("COMMAND:complete")
        assert result == 0

    def test_command_bfs_retry_engine_error(self, capsys) -> None:
        """Exit 1 when retry engine.query() raises (I-GRAPH-IMPLEMENTS-2 path)."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        mock_edge = MagicMock()
        mock_edge.kind = "implements"
        mock_edge.src = "FILE:src/sdd/commands/complete.py"
        mock_graph = MagicMock()
        mock_graph.nodes = {"COMMAND:complete": MagicMock()}
        mock_graph.edges_in.get.return_value = [mock_edge]

        mock_ctx = MagicMock()
        mock_ctx.selection_exhausted = True
        mock_ctx.nodes = []

        mock_response = MagicMock()
        mock_response.context = mock_ctx

        mock_engine = MagicMock()
        mock_engine.query.side_effect = [mock_response, RuntimeError("retry fail")]

        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.explain.ContextEngine", return_value=mock_engine),
            patch("sdd.graph_navigation.cli.explain.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = explain.run("COMMAND:complete")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_debug_output_path(self, capsys) -> None:
        """Exit 0 with debug output when debug=True."""
        from sdd.graph_navigation.cli import explain

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"FILE:src/foo.py": MagicMock()}
        mock_response = MagicMock()
        mock_response.context = MagicMock(
            selection_exhausted=False, nodes=[], budget_used={}
        )
        mock_policy = MagicMock()
        mock_policy.budget = MagicMock(max_nodes=10, max_edges=20, max_chars=1000)
        with (
            patch("sdd.graph_navigation.cli.explain.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.explain.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.explain.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.explain.ContextRuntime"),
            patch("sdd.graph_navigation.cli.explain.PolicyResolver") as mock_pr,
            patch("sdd.graph_navigation.cli.explain.format_text", return_value="output"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.return_value = mock_response
            mock_pr.return_value.resolve.return_value = mock_policy
            result = explain.run("FILE:src/foo.py", debug=True)
        assert result == 0
