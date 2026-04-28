"""Tests for event_store_url() and is_production_event_store() — I-EVENT-STORE-URL-1, I-PROD-GUARD-1."""
from __future__ import annotations

import pytest

from sdd.infra.paths import event_store_file, event_store_url, is_production_event_store


class TestEventStoreUrl:
    def test_event_store_url_pg_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://user:pass@localhost/sdd_test")
        assert event_store_url() == "postgresql://user:pass@localhost/sdd_test"

    def test_event_store_url_duckdb_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        assert event_store_url() == str(event_store_file())


class TestIsProductionEventStore:
    def test_is_production_event_store_pg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDD_DATABASE_URL", "postgresql://user:pass@localhost/sdd_prod")
        assert is_production_event_store("postgresql://user:pass@localhost/sdd_prod") is True
        assert is_production_event_store("postgresql://user:pass@localhost/sdd_other") is False

    def test_is_production_event_store_duckdb(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        prod_path = str(event_store_file())
        assert is_production_event_store(prod_path) is True
        other_path = str(tmp_path / "test.duckdb")
        assert is_production_event_store(other_path) is False
