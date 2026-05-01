"""Unit tests for sdd invariant CLI error paths — I-RUNTIME-ORCHESTRATOR-1."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestInvariantCLIErrorPaths:
    """Test error paths in invariant.run() not covered by integration tests."""

    def test_index_builder_error(self, capsys) -> None:
        """Exit 1 when IndexBuilder.build() raises."""
        from sdd.graph_navigation.cli import invariant

        with patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib:
            mock_ib.return_value.build.side_effect = RuntimeError("build failed")
            result = invariant.run("I-GRAPH-PROTOCOL-1")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_error(self, capsys) -> None:
        """Exit 1 when GraphService.get_or_build() raises."""
        from sdd.graph_navigation.cli import invariant

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.invariant.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = RuntimeError("graph error")
            result = invariant.run("I-GRAPH-PROTOCOL-1")
        assert result == 1
        captured = capsys.readouterr()
        assert "GRAPH_NOT_BUILT" in captured.err

    def test_graph_service_invariant_violation_error(self, capsys) -> None:
        """Exit 1 with INVARIANT_VIOLATION when GraphInvariantError raised."""
        from sdd.graph.errors import GraphInvariantError
        from sdd.graph_navigation.cli import invariant

        mock_index = MagicMock()
        with (
            patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.invariant.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.side_effect = GraphInvariantError("inv")
            result = invariant.run("I-GRAPH-PROTOCOL-1")
        assert result == 1
        captured = capsys.readouterr()
        assert "INVARIANT_VIOLATION" in captured.err

    def test_node_not_found(self, capsys) -> None:
        """Exit 1 with NOT_FOUND when INVARIANT node absent from graph."""
        from sdd.graph_navigation.cli import invariant

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        with (
            patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.invariant.GraphService") as mock_gs,
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            result = invariant.run("I-MISSING")
        assert result == 1
        captured = capsys.readouterr()
        assert "NOT_FOUND" in captured.err

    def test_engine_query_error(self, capsys) -> None:
        """Exit 1 when engine.query() raises."""
        from sdd.graph_navigation.cli import invariant

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"INVARIANT:I-GRAPH-PROTOCOL-1": MagicMock()}
        with (
            patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.invariant.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.invariant.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.invariant.ContextRuntime"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.side_effect = RuntimeError("engine fail")
            result = invariant.run("I-GRAPH-PROTOCOL-1")
        assert result == 1
        captured = capsys.readouterr()
        assert "INTERNAL_ERROR" in captured.err

    def test_debug_output_path(self, capsys) -> None:
        """Exit 0 with debug output when debug=True and node found."""
        from sdd.graph_navigation.cli import invariant

        mock_index = MagicMock()
        mock_graph = MagicMock()
        mock_graph.nodes = {"INVARIANT:I-GRAPH-PROTOCOL-1": MagicMock()}
        mock_response = MagicMock()
        mock_response.context = MagicMock(budget_used={})
        mock_policy = MagicMock()
        mock_policy.budget = MagicMock(max_nodes=10, max_edges=20, max_chars=1000)
        with (
            patch("sdd.graph_navigation.cli.invariant.IndexBuilder") as mock_ib,
            patch("sdd.graph_navigation.cli.invariant.GraphService") as mock_gs,
            patch("sdd.graph_navigation.cli.invariant.ContextEngine") as mock_ce,
            patch("sdd.graph_navigation.cli.invariant.ContextRuntime"),
            patch("sdd.graph_navigation.cli.invariant.PolicyResolver") as mock_pr,
            patch("sdd.graph_navigation.cli.invariant.format_text", return_value="output"),
        ):
            mock_ib.return_value.build.return_value = mock_index
            mock_gs.return_value.get_or_build.return_value = mock_graph
            mock_ce.return_value.query.return_value = mock_response
            mock_pr.return_value.resolve.return_value = mock_policy
            result = invariant.run("I-GRAPH-PROTOCOL-1", debug=True)
        assert result == 0
