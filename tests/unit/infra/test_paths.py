"""Tests for event_store_url() and is_production_event_store() — I-EVENT-STORE-URL-1, I-PROD-GUARD-1."""
from __future__ import annotations

import subprocess

import pytest

from sdd.infra.paths import event_store_url, is_production_event_store


class TestEventStoreUrl:
    def test_event_store_url_raises_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        with pytest.raises(EnvironmentError, match="SDD_DATABASE_URL is not set"):
            event_store_url()

    def test_event_store_url_returns_pg_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://user:pass@localhost/sdd_test")
        assert event_store_url() == "postgresql://user:pass@localhost/sdd_test"


class TestIsProductionEventStore:
    def test_is_production_event_store_raises_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        with pytest.raises(EnvironmentError, match="SDD_DATABASE_URL is not set"):
            is_production_event_store("postgresql://user:pass@localhost/sdd_prod")

    def test_is_production_event_store_matches_pg_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://user:pass@localhost/sdd_prod")
        assert is_production_event_store("postgresql://user:pass@localhost/sdd_prod") is True
        assert is_production_event_store("postgresql://user:pass@localhost/sdd_other") is False


def test_no_event_store_file_calls_in_cli() -> None:
    """I-CLI-DB-RESOLUTION-1: CLI modules MUST NOT call event_store_file()."""
    result = subprocess.run(
        [
            "grep", "-r", "event_store_file()", "src/sdd/",
            "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "", (
        f"I-CLI-DB-RESOLUTION-1 violated. Files calling event_store_file():\n{result.stdout}"
    )


def test_event_store_file_removed() -> None:
    """I-EVENT-STORE-FILE-REMOVED-1: event_store_file() MUST NOT exist in sdd.infra.paths."""
    import sdd.infra.paths as paths_module
    assert not hasattr(paths_module, "event_store_file"), (
        "I-EVENT-STORE-FILE-REMOVED-1 violated: event_store_file() still exists in sdd.infra.paths"
    )


def test_no_duckdb_hardcodes_in_cli() -> None:
    """I-CLI-DB-RESOLUTION-1: CLI MUST NOT hardcode .duckdb paths.

    Exception: show_path.py.
    """
    result = subprocess.run(
        [
            "grep", "-r", "sdd_events.duckdb", "src/sdd/",
            "--include=*.py",
            "--exclude=show_path.py",
            "--exclude=paths.py",
        ],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "", (
        f"I-CLI-DB-RESOLUTION-1 violated. Hardcoded .duckdb paths:\n{result.stdout}"
    )


def test_update_state_argparse_no_eager_eval() -> None:
    """BC-44-B: update_state.py --db and --state MUST use default=None (lazy eval)."""
    result = subprocess.run(
        ["grep", "-n", r"default=.*event_store", "src/sdd/commands/update_state.py"],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "", (
        f"BC-44-B violated: update_state.py has eager argparse eval:\n{result.stdout}"
    )


def test_query_events_argparse_no_eager_eval() -> None:
    """BC-44-B: query_events.py --db MUST use default=None (lazy eval)."""
    result = subprocess.run(
        ["grep", "-n", r"default=.*event_store", "src/sdd/commands/query_events.py"],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "", (
        f"BC-44-B violated: query_events.py has eager argparse eval:\n{result.stdout}"
    )


def test_report_error_argparse_no_eager_eval() -> None:
    """BC-44-B: report_error.py --db MUST use default=None (lazy eval)."""
    result = subprocess.run(
        ["grep", "-n", r"default=.*event_store", "src/sdd/commands/report_error.py"],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "", (
        f"BC-44-B violated: report_error.py has eager argparse eval:\n{result.stdout}"
    )


def test_log_tool_uses_event_store_url_fallback() -> None:
    """BC-44-D: log_tool.py MUST use event_store_url() as DB path fallback."""
    result = subprocess.run(
        ["grep", "-n", "event_store_url", "src/sdd/hooks/log_tool.py"],
        capture_output=True,
        text=True,
    )
    assert result.stdout != "", (
        "BC-44-D violated: log_tool.py does not use event_store_url() as fallback"
    )
