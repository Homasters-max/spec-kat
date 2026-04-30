"""Tests for LightRAGRegistry — I-RAG-EXPORT-FRESHNESS-1, I-RAG-REGISTRY-PURE-1."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdd.graph_navigation.rag.registry import LightRAGRegistry
from sdd.infra.paths import reset_sdd_root


@pytest.fixture()
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LightRAGRegistry:
    monkeypatch.setenv("SDD_HOME", str(tmp_path / ".sdd"))
    reset_sdd_root()
    yield LightRAGRegistry()
    reset_sdd_root()


# Test 59
def test_registry_has_kg_false_when_missing(registry: LightRAGRegistry) -> None:
    assert registry.has_kg("abc123") is False


# Test 60
def test_registry_has_kg_true_after_export(registry: LightRAGRegistry) -> None:
    fingerprint = "deadbeef"
    kg_path = registry.get_path(fingerprint)
    kg_path.mkdir(parents=True, exist_ok=True)
    assert registry.has_kg(fingerprint) is True


def test_registry_get_path_deterministic(registry: LightRAGRegistry) -> None:
    fp = "fp42"
    assert registry.get_path(fp) == registry.get_path(fp)


def test_registry_get_path_contains_fingerprint(registry: LightRAGRegistry) -> None:
    fp = "unique_fp"
    path = registry.get_path(fp)
    assert fp in str(path)


# Test 62
def test_registry_does_not_import_graph_service() -> None:
    """I-RAG-REGISTRY-PURE-1: registry.py must not import GraphService, ContextEngine, LightRAGClient."""
    import ast
    from pathlib import Path

    src = (Path(__file__).parents[3] / "src" / "sdd" / "graph_navigation" / "rag" / "registry.py").read_text()
    tree = ast.parse(src)
    forbidden = {"GraphService", "ContextEngine", "LightRAGClient"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
    assert not forbidden & imported, f"registry.py imports forbidden names: {forbidden & imported}"
