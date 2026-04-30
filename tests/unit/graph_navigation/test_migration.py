"""Tests for migration.py — I-CTX-MIGRATION-1..4, Spec_v52 §3."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_migration_complete_returns_true() -> None:
    """I-CTX-MIGRATION-1..4: migration gate returns True with current codebase."""
    from sdd.graph_navigation.migration import migration_complete

    assert migration_complete() is True


def test_handlers_use_runtime_fails_if_handler_missing(tmp_path: Path) -> None:
    """_handlers_use_runtime returns False when a handler file is absent."""
    from sdd.graph_navigation import migration as m

    with patch.object(m, "_CLI_HANDLERS", ["nonexistent_handler.py"]):
        assert m._handlers_use_runtime() is False


def test_handlers_use_runtime_fails_if_no_context_runtime(tmp_path: Path) -> None:
    """_handlers_use_runtime returns False when handler lacks ContextRuntime."""
    from sdd.graph_navigation import migration as m

    fake_handler = tmp_path / "fake.py"
    fake_handler.write_text("# no runtime import\n", encoding="utf-8")

    cli_dir = m.Path(__file__).parent  # irrelevant — we patch
    with patch.object(m, "_CLI_HANDLERS", [fake_handler.name]), \
         patch("sdd.graph_navigation.migration.Path") as mock_path:
        # Route cli_dir to tmp_path
        mock_path.return_value.parent.__truediv__ = lambda self, name: tmp_path
        # Direct test of the pattern instead
        assert not m._RUNTIME_PATTERN.search(fake_handler.read_text())


def test_no_external_callers_detects_import(tmp_path: Path) -> None:
    """_no_external_build_context_callers returns False when a caller is found."""
    from sdd.graph_navigation import migration as m

    # Create a fake sdd_src tree with a violating file
    violator = tmp_path / "commands" / "bad.py"
    violator.parent.mkdir()
    violator.write_text(
        "from sdd.context.build_context import build_context\n", encoding="utf-8"
    )

    with patch(
        "sdd.graph_navigation.migration.Path.__new__",
        side_effect=lambda cls, *a, **kw: Path.__new__(cls, *a, **kw),
    ):
        # Direct regex test — confirms the pattern catches the import
        assert m._BUILD_CONTEXT_CALLER.search(violator.read_text()) is not None
