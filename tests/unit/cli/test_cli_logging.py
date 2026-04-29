"""Tests for I-CLI-LOG-LEVEL-1: logging.basicConfig called before subcommand, INFO visible in stderr."""
from __future__ import annotations

import io
import logging
from unittest.mock import patch

from click.testing import CliRunner

from sdd.cli import cli


def test_cli_basicconfig_called_before_subcommand():
    """I-CLI-LOG-LEVEL-1: logging.basicConfig is called before any subcommand body runs."""
    call_order: list[str] = []

    def track_basicconfig(**kwargs):
        call_order.append("basicConfig")

    def track_subcommand(args: list[str]) -> int:
        call_order.append("subcommand")
        return 0

    runner = CliRunner()
    with (
        patch("logging.basicConfig", side_effect=track_basicconfig),
        patch("sdd.commands.show_state.main", side_effect=track_subcommand),
    ):
        runner.invoke(cli, ["show-state"])

    assert "basicConfig" in call_order, "logging.basicConfig was never called"
    assert "subcommand" in call_order, "subcommand handler was never called"
    assert call_order.index("basicConfig") < call_order.index("subcommand"), (
        f"expected basicConfig before subcommand, got: {call_order}"
    )


def test_cli_info_log_visible_in_stderr():
    """I-CLI-LOG-LEVEL-1: INFO-level messages emitted after CLI init appear in stderr.

    basicConfig is idempotent once handlers exist (R-3). We clear root handlers before
    invocation so basicConfig actually installs a StreamHandler, then verify the handler
    routes INFO messages to the capture buffer.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    root.setLevel(logging.WARNING)

    captured = io.StringIO()

    def installing_basicconfig(**kwargs):
        handler = logging.StreamHandler(captured)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    def subcommand_that_logs(args: list[str]) -> int:
        logging.getLogger("sdd.sentinel").info("SENTINEL_INFO_MESSAGE")
        return 0

    try:
        runner = CliRunner()
        with (
            patch("logging.basicConfig", side_effect=installing_basicconfig),
            patch("sdd.commands.show_state.main", side_effect=subcommand_that_logs),
        ):
            runner.invoke(cli, ["show-state"])

        assert "SENTINEL_INFO_MESSAGE" in captured.getvalue(), (
            f"Expected INFO message in captured output, got: {captured.getvalue()!r}"
        )
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
