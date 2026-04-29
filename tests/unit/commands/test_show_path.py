"""Tests for commands/show_path.py — BC-45-F, I-EVENT-STORE-FILE-REMOVED-1."""
from __future__ import annotations

import pytest

from sdd.commands.show_path import main


def test_show_path_no_env_returns_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """BC-45-F: sdd path eventlog MUST exit with error when SDD_DATABASE_URL is not set."""
    monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["eventlog"])
    assert exc_info.value.code == 1
