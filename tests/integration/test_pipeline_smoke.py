"""Integration tests — CLI smoke, Level A (T-1007a).

Invariants: I-EXEC-SUCCESS-1, I-USAGE-1, I-CLI-API-1, I-FAIL-1
"""
from __future__ import annotations

import contextlib
import io
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def sdd_cli_runner(monkeypatch):
    """In-process CLI runner for sdd.cli.main.

    Invokes sdd.cli.main() with captured stdout/stderr and returns a
    SimpleNamespace(returncode, stdout, stderr).

    For ``report-error``: injects an SDDError before the inner handler
    so cli.py's ``except SDDError`` path (I-FAIL-1) is exercised without
    touching the real EventLog.
    """
    from sdd.core.errors import Inconsistency

    def _sdd_error_injection(_args: list[str]) -> int:
        raise Inconsistency("smoke-test SDDError injection")

    def run(args: list[str]) -> SimpleNamespace:
        if args and args[0] == "report-error":
            monkeypatch.setattr(
                "sdd.commands.report_error.main", _sdd_error_injection
            )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        exit_code = 0
        with (
            contextlib.redirect_stdout(stdout_buf),
            contextlib.redirect_stderr(stderr_buf),
        ):
            try:
                from sdd.cli import main as cli_main

                cli_main(args)
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 0

        return SimpleNamespace(
            returncode=exit_code,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
        )

    return run


def test_smoke_show_state(sdd_cli_runner: object) -> None:
    """I-EXEC-SUCCESS-1: success path exits 0 and prints state containing 'phase'."""
    result = sdd_cli_runner(["show-state"])
    assert result.returncode == 0
    assert "phase" in result.stdout.lower()


def test_smoke_report_error_exit_code(sdd_cli_runner: object) -> None:
    """I-FAIL-1: SDDError propagating to cli.py::main produces exit 1 + JSON stderr."""
    result = sdd_cli_runner(["report-error", "--type", "SmokeTest", "--message", "x"])
    assert result.returncode == 1  # known SDDError path
    assert result.stderr  # JSON present


def test_smoke_unknown_command(sdd_cli_runner: object) -> None:
    """I-USAGE-1: unknown subcommand produces UsageError JSON on stderr with exit 1."""
    result = sdd_cli_runner(["unknown-subcommand"])
    assert result.returncode == 1  # USAGE_ERR path — I-USAGE-1
    payload = json.loads(result.stderr)
    assert payload["error_type"] == "UsageError"
    assert payload["exit_code"] == 1
