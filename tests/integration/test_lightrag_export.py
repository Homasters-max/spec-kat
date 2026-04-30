"""Integration tests: LightRAGExporter — tests 67, 68, INT-9.

67. test_exporter_skip_if_kg_exists   — I-RAG-EXPORT-FRESHNESS-1
68. test_exporter_not_called_from_context_engine — I-RAG-EXPORT-NOT-IN-QUERY-1 (grep)
INT-9. test_int9_export_uses_existing_node_ids — export node_ids == graph node_ids; chunks == docs
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdd.context_kernel.documents import DocumentChunk
from sdd.graph.types import DeterministicGraph, Node
from sdd.graph_navigation.rag.lightrag_exporter import LightRAGExporter

_SRC = Path(__file__).parents[2] / "src" / "sdd"


def _make_graph(node_ids: list[str]) -> DeterministicGraph:
    nodes = {
        nid: Node(node_id=nid, kind="FILE", label=nid, summary="", meta={"path": f"{nid}.py"})
        for nid in node_ids
    }
    return DeterministicGraph(
        nodes=nodes,
        edges_out={},
        edges_in={},
        source_snapshot_hash="fp_test",
    )


def _make_docs(node_ids: list[str]) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            node_id=nid,
            content=f"content of {nid}",
            kind="code",
            char_count=len(f"content of {nid}"),
            meta={"path": f"{nid}.py"},
            references=[],
        )
        for nid in node_ids
    ]


def _make_registry(*, has_kg: bool, tmp_path: Path | None = None) -> MagicMock:
    registry = MagicMock()
    registry.has_kg.return_value = has_kg
    if tmp_path is not None:
        registry.get_path.return_value = tmp_path / "kg"
    return registry


def _make_rag_client() -> MagicMock:
    client = MagicMock()
    return client


# ---------------------------------------------------------------------------
# Test 67 — I-RAG-EXPORT-FRESHNESS-1: skip if KG already exists
# ---------------------------------------------------------------------------

def test_exporter_skip_if_kg_exists(tmp_path: Path) -> None:
    """Test 67: повторный вызов при has_kg=True → insert_custom_kg не вызывается."""
    node_ids = ["FILE:a", "FILE:b"]
    graph = _make_graph(node_ids)
    docs = _make_docs(node_ids)
    registry = _make_registry(has_kg=True, tmp_path=tmp_path)
    rag_client = _make_rag_client()

    LightRAGExporter().export(graph, docs, rag_client, registry, "fp_test")

    registry.has_kg.assert_called_once_with("fp_test")
    rag_client.insert_custom_kg.assert_not_called()


# ---------------------------------------------------------------------------
# Test 68 — I-RAG-EXPORT-NOT-IN-QUERY-1: grep-тест
# ---------------------------------------------------------------------------

_QUERY_HANDLER_FILES = [
    _SRC / "graph_navigation" / "cli" / "resolve.py",
    _SRC / "graph_navigation" / "cli" / "explain.py",
    _SRC / "graph_navigation" / "cli" / "trace.py",
    _SRC / "graph_navigation" / "cli" / "invariant.py",
    _SRC / "context_kernel" / "engine.py",
    _SRC / "context_kernel" / "runtime.py",
]


@pytest.mark.parametrize("handler_path", _QUERY_HANDLER_FILES, ids=lambda p: p.name)
def test_exporter_not_called_from_context_engine(handler_path: Path) -> None:
    """Test 68: I-RAG-EXPORT-NOT-IN-QUERY-1 — LightRAGExporter не импортируется из query-пути."""
    assert handler_path.exists(), f"handler file missing: {handler_path}"
    tree = ast.parse(handler_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "LightRAGExporter" not in alias.name, (
                    f"{handler_path.name}: direct import of LightRAGExporter forbidden"
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "LightRAGExporter", (
                    f"{handler_path.name}: 'from ... import LightRAGExporter' forbidden"
                )
            if node.module and "lightrag_exporter" in node.module:
                pytest.fail(
                    f"{handler_path.name}: imports from lightrag_exporter module (forbidden)"
                )


# ---------------------------------------------------------------------------
# INT-9 — export не создаёт новые node_id; chunks == docs
# ---------------------------------------------------------------------------

def test_int9_export_uses_existing_node_ids(tmp_path: Path) -> None:
    """INT-9: entities/chunks exported use only graph node_ids; no new ids invented."""
    node_ids = ["FILE:src/a.py", "COMMAND:complete", "EVENT:TaskImplemented"]
    graph = _make_graph(node_ids)
    docs = _make_docs(node_ids)
    registry = _make_registry(has_kg=False, tmp_path=tmp_path)
    rag_client = _make_rag_client()

    LightRAGExporter().export(graph, docs, rag_client, registry, "fp_test")

    rag_client.insert_custom_kg.assert_called_once()
    kg = rag_client.insert_custom_kg.call_args[0][0]

    exported_entity_ids = {e["entity_name"] for e in kg["entities"]}
    assert exported_entity_ids == set(node_ids), (
        f"INT-9: entity_names diverge from graph nodes: "
        f"extra={exported_entity_ids - set(node_ids)}, "
        f"missing={set(node_ids) - exported_entity_ids}"
    )

    exported_chunk_ids = {c["source_id"] for c in kg["chunks"]}
    doc_ids = {d.node_id for d in docs}
    assert exported_chunk_ids == doc_ids, (
        f"INT-9: chunk source_ids diverge from doc node_ids: "
        f"extra={exported_chunk_ids - doc_ids}, missing={doc_ids - exported_chunk_ids}"
    )

    for chunk in kg["chunks"]:
        matching_doc = next((d for d in docs if d.node_id == chunk["source_id"]), None)
        assert matching_doc is not None
        assert chunk["content"] == matching_doc.content, (
            f"INT-9: chunk content mismatch for {chunk['source_id']!r}"
        )
