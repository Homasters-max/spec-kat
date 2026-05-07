"""CLI execution contract tests — BC-EXEC (Spec_v10 §9, tests 1–6).

Invariants: I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1
"""
from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import click
import pytest

from sdd.cli import main
from sdd.core.errors import ScopeViolation


def _run(exc_or_return, *, args=None):
    """Call main(args) capturing stderr; return (exit_code, stderr_text)."""
    buf = StringIO()
    side = {"side_effect": exc_or_return} if isinstance(exc_or_return, BaseException) else {"return_value": exc_or_return}
    with patch("sdd.cli.cli", **side):
        with patch("sys.stderr", buf):
            with pytest.raises(SystemExit) as exc:
                main(args)
    return exc.value.code, buf.getvalue()


def test_success_path_exit_zero():
    """I-EXEC-SUCCESS-1: success path calls sys.exit(result or 0), exits 0."""
    with patch("sdd.cli.cli", return_value=0):
        with pytest.raises(SystemExit) as exc:
            main([])
    assert exc.value.code == 0


def test_sdd_error_json_stderr_exit_1():
    """I-FAIL-1, I-CLI-API-1: SDDError → JSON on stderr with exit_code 1, sys.exit(1)."""
    code, stderr = _run(ScopeViolation("path not allowed"))
    assert code == 1
    data = json.loads(stderr)
    assert data["error_type"] == "ScopeViolation"
    assert data["message"] == "path not allowed"
    assert data["exit_code"] == 1


def test_unexpected_exception_json_stderr_exit_2():
    """I-FAIL-1, I-CLI-API-1: unexpected Exception → JSON on stderr with exit_code 2, sys.exit(2)."""
    code, stderr = _run(RuntimeError("internal boom"))
    assert code == 2
    data = json.loads(stderr)
    assert data["error_type"] == "UnexpectedException"
    assert data["message"] == "internal boom"
    assert data["exit_code"] == 2


def test_click_exception_exit_1_not_2():
    """I-USAGE-1, I-CLI-API-1: click.ClickException → exit 1, NOT 2."""
    code, stderr = _run(click.UsageError("bad args"))
    assert code == 1
    assert code != 2
    data = json.loads(stderr)
    assert data["exit_code"] == 1


def test_click_exception_no_error_event():
    """I-ERR-CLI-1: click.ClickException MUST NOT produce ErrorEvent in the EventLog."""
    with patch("sdd.cli.cli", side_effect=click.UsageError("bad args")), \
         patch("sdd.infra.event_log.sdd_append") as mock_append:
        buf = StringIO()
        with patch("sys.stderr", buf):
            with pytest.raises(SystemExit):
                main([])
    mock_append.assert_not_called()


def test_cli_json_schema_fields():
    """I-CLI-API-1: JSON error output has exactly {error_type, message, exit_code}."""
    _code, stderr = _run(RuntimeError("schema check"))
    data = json.loads(stderr)
    assert set(data.keys()) == {"error_type", "message", "exit_code"}
