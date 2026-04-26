"""Tests for src/sdd/cli.py — I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3."""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

import sdd.cli as cli_module
from sdd.cli import cli

EXPECTED_COMMANDS = {
    "complete",
    "validate",
    "show-state",
    "activate-phase",
    "replay",
    "query-events",
    "metrics-report",
    "report-error",
}


def test_help_lists_all_commands():
    """I-PKG-2: sdd --help exits 0 and output contains all 8 subcommand names."""
    result = subprocess.run(["sdd", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    for cmd in EXPECTED_COMMANDS:
        assert cmd in result.stdout, f"Missing subcommand in --help output: {cmd!r}"


def test_cli_is_pure_router():
    """I-CLI-1: cli.py has no sdd.infra/sdd.domain import nodes (AST-verified).

    sdd.guards.* are CLI adapters, not domain logic — imports from them are allowed.
    """
    cli_path = Path(cli_module.__file__)
    tree = ast.parse(cli_path.read_text(encoding="utf-8"))
    forbidden = ("sdd.infra", "sdd.domain")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for prefix in forbidden:
                assert not node.module.startswith(prefix), (
                    f"Forbidden import '{node.module}' at line {node.lineno}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden:
                    assert not alias.name.startswith(prefix), (
                        f"Forbidden import '{alias.name}' at line {node.lineno}"
                    )


def test_exit_code_success():
    """I-CLI-2: CLI exits 0 when underlying main() returns 0."""
    runner = CliRunner()
    with patch("sdd.commands.show_state.main", return_value=0):
        result = runner.invoke(cli, ["show-state"])
    assert result.exit_code == 0


def test_exit_code_validation_failure():
    """I-CLI-2: CLI exits 1 when underlying main() returns 1 (known SDD error)."""
    runner = CliRunner()
    with patch("sdd.commands.show_state.main", return_value=1):
        result = runner.invoke(cli, ["show-state"])
    assert result.exit_code == 1


def test_exit_code_unexpected_error():
    """I-CLI-2: CLI exits 2 when underlying main() returns 2 (unexpected exception)."""
    runner = CliRunner()
    with patch("sdd.commands.show_state.main", return_value=2):
        result = runner.invoke(cli, ["show-state"])
    assert result.exit_code == 2


def test_complete_routes_to_update_state():
    """sdd complete T-NNN calls update_state.main with [\"complete\", \"T-NNN\"]."""
    runner = CliRunner()
    with patch("sdd.commands.update_state.main", return_value=0) as mock_main:
        result = runner.invoke(cli, ["complete", "T-801"])
    assert result.exit_code == 0
    mock_main.assert_called_once_with(["complete", "T-801"])


def test_query_events_pass_through_args():
    """sdd query-events passes all args to query_events.main unchanged."""
    runner = CliRunner()
    with patch("sdd.commands.query_events.main", return_value=0) as mock_main:
        result = runner.invoke(cli, ["query-events", "--phase", "7"])
    assert result.exit_code == 0
    mock_main.assert_called_once_with(["--phase", "7"])


def test_show_state_registered():
    """show-state subcommand is registered in the CLI group."""
    assert "show-state" in cli.commands


def test_cli_vs_main_equivalence_complete():
    """I-CLI-3: exit code via CLI equals return value via direct main() for complete."""
    runner = CliRunner()
    with patch("sdd.commands.update_state.main", return_value=0) as mock_main:
        cli_result = runner.invoke(cli, ["complete", "T-801"])
    cli_exit = cli_result.exit_code
    direct_exit = mock_main.return_value
    assert cli_exit == direct_exit == 0


def test_cli_vs_main_equivalence_show_state():
    """I-CLI-3: exit code via CLI equals return value via direct main() for show-state."""
    runner = CliRunner()
    with patch("sdd.commands.show_state.main", return_value=0) as mock_main:
        cli_result = runner.invoke(cli, ["show-state"])
    cli_exit = cli_result.exit_code
    direct_exit = mock_main.return_value
    assert cli_exit == direct_exit == 0
