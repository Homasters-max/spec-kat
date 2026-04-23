"""Tests for norm_catalog — stdlib YAML fallback and core behaviour.

Invariants: I-LOGIC-COVER-3
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sdd.domain.norms.catalog as cat_mod
from sdd.domain.norms.catalog import NormCatalog, NormEntry, load_catalog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_catalog(path: Path, norms: list[dict]) -> str:
    """Write norms as JSON (a strict YAML subset) and return the file path."""
    path.write_text(json.dumps({"norms": norms}), encoding="utf-8")
    return str(path)


_SAMPLE_NORM = {
    "norm_id": "TEST-1",
    "actor": "llm",
    "enforcement": "hard",
    "description": "test norm",
    "forbidden_actions": ["bad_action"],
    "allowed_actions": ["good_action"],
}


# ---------------------------------------------------------------------------
# I-LOGIC-COVER-3: stdlib YAML fallback
# ---------------------------------------------------------------------------

class TestStdlibYamlFallback:
    """load_catalog must work when PyYAML is replaced by json.load (stdlib fallback)."""

    def test_stdlib_yaml_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """I-LOGIC-COVER-3: catalog loads correctly via json.load fallback."""
        # Simulate PyYAML being unavailable by patching _safe_load to json.load
        monkeypatch.setattr(cat_mod, "_safe_load", json.load)

        catalog_file = _write_catalog(tmp_path / "norm_catalog.json", [_SAMPLE_NORM])
        catalog = load_catalog(catalog_file)

        assert isinstance(catalog, NormCatalog)
        norm = catalog.get_norm("TEST-1")
        assert norm is not None
        assert norm.actor == "llm"
        assert norm.severity == "hard"
        assert not catalog.is_allowed("llm", "bad_action")
        assert catalog.is_allowed("llm", "good_action")

    def test_stdlib_yaml_fallback_multiple_norms(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """I-LOGIC-COVER-3: fallback handles multiple norm entries correctly."""
        monkeypatch.setattr(cat_mod, "_safe_load", json.load)

        norms = [
            {
                "norm_id": "NORM-A",
                "actor": "llm",
                "enforcement": "hard",
                "description": "norm A",
                "forbidden_actions": ["action_x"],
                "allowed_actions": [],
            },
            {
                "norm_id": "NORM-B",
                "actor": "human",
                "enforcement": "soft",
                "description": "norm B",
                "forbidden_actions": [],
                "allowed_actions": ["action_y"],
            },
        ]
        catalog_file = _write_catalog(tmp_path / "catalog.json", norms)
        catalog = load_catalog(catalog_file)

        assert catalog.get_norm("NORM-A") is not None
        assert catalog.get_norm("NORM-B") is not None
        assert len(catalog.entries) == 2

    def test_stdlib_yaml_fallback_empty_norms(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """I-LOGIC-COVER-3: fallback handles an empty norms list without error."""
        monkeypatch.setattr(cat_mod, "_safe_load", json.load)

        catalog_file = _write_catalog(tmp_path / "empty.json", [])
        catalog = load_catalog(catalog_file)

        assert isinstance(catalog, NormCatalog)
        assert len(catalog.entries) == 0


# ---------------------------------------------------------------------------
# NormCatalog.is_allowed — core semantics
# ---------------------------------------------------------------------------

class TestNormCatalogIsAllowed:
    def _catalog(self, *entries: NormEntry, strict: bool = True) -> NormCatalog:
        return NormCatalog(entries=tuple(entries), strict=strict)

    def _entry(self, actor: str, action: str, result: str, norm_id: str = "T-1") -> NormEntry:
        return NormEntry(norm_id=norm_id, actor=actor, action=action, result=result,
                         description="", severity="hard")

    def test_explicit_forbidden_blocks(self) -> None:
        catalog = self._catalog(self._entry("llm", "bad", "forbidden"))
        assert not catalog.is_allowed("llm", "bad")

    def test_explicit_allowed_passes(self) -> None:
        catalog = self._catalog(self._entry("llm", "ok", "allowed"))
        assert catalog.is_allowed("llm", "ok")

    def test_unknown_action_strict_denies(self) -> None:
        catalog = self._catalog(strict=True)
        assert not catalog.is_allowed("llm", "unknown_action")

    def test_unknown_action_permissive_allows(self) -> None:
        catalog = self._catalog(strict=False)
        assert catalog.is_allowed("llm", "unknown_action")

    def test_any_actor_matches_any(self) -> None:
        catalog = self._catalog(self._entry("any", "shared_action", "forbidden"))
        assert not catalog.is_allowed("llm", "shared_action")
        assert not catalog.is_allowed("human", "shared_action")
