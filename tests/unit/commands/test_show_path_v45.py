"""Tests for BC-45-F — show_path.py PG mode password masking (Spec_v45 §10 test 10)."""
from __future__ import annotations

from sdd.commands.show_path import _show_event_store_path


class TestShowEventStorePath:
    def test_show_path_pg_mode_hides_password(self, monkeypatch) -> None:
        """BC-45-F: SDD_DATABASE_URL set → output contains no password, prefixed with [PG]."""
        pg_url = "postgresql://sdd:supersecret@localhost:5432/sdd"
        monkeypatch.setenv("SDD_DATABASE_URL", pg_url)

        result = _show_event_store_path()

        assert result.startswith("[PG] ")
        assert "supersecret" not in result
        assert "localhost:5432/sdd" in result

    def test_show_path_no_env_returns_duckdb_path(self, monkeypatch) -> None:
        """BC-45-F: SDD_DATABASE_URL not set → falls back to DuckDB file path."""
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)

        result = _show_event_store_path()

        assert "[PG]" not in result
        assert "sdd_events.duckdb" in result

    def test_show_path_pg_url_without_password(self, monkeypatch) -> None:
        """BC-45-F: PG URL without password → shown safely with [PG] prefix."""
        pg_url = "postgresql://sdd@localhost:5432/sdd"
        monkeypatch.setenv("SDD_DATABASE_URL", pg_url)

        result = _show_event_store_path()

        assert result.startswith("[PG] ")
        assert "localhost:5432/sdd" in result
