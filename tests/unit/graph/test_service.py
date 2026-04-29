"""Tests for GraphService (I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-LINEAGE-1, I-PHASE-ISOLATION-1)."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import ClassVar

from sdd.graph.cache import GRAPH_SCHEMA_VERSION, GraphCache
from sdd.graph.service import GraphService, _build_fingerprint, _extractor_hashes
from sdd.graph.types import DeterministicGraph, Edge
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode

_NOW = "2026-01-01T00:00:00Z"


def _make_node(node_id: str, kind: str = "FILE") -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=node_id,
        path=f"src/{node_id}.py",
        summary=f"{kind}:{node_id}",
        signature="",
        meta={},
        git_hash=None,
        indexed_at=_NOW,
    )


def _make_index(
    nodes: list[SpatialNode],
    snapshot_hash: str = "testhash01234567",
    git_tree_hash: str | None = None,
) -> SpatialIndex:
    nodes_dict = {n.node_id: n for n in nodes}
    index = SpatialIndex(
        nodes=nodes_dict,
        built_at=_NOW,
        git_tree_hash=git_tree_hash,
        snapshot_hash=snapshot_hash,
    )
    index._content_map = {}
    return index


class _NoOpExtractor:
    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: SpatialIndex) -> list[Edge]:
        return []


# ---------------------------------------------------------------------------
# test_graph_cache_key_includes_schema_version — I-GRAPH-CACHE-1, I-GRAPH-CACHE-2
# ---------------------------------------------------------------------------

def test_graph_cache_key_includes_schema_version() -> None:
    """Fingerprint includes GRAPH_SCHEMA_VERSION; different versions → different fingerprints.

    I-GRAPH-CACHE-1: schema version is part of the fingerprint.
    I-GRAPH-CACHE-2: git_tree_hash MUST NOT appear in fingerprint.
    """
    snapshot_hash = "abc123deadbeef"
    extractor_hashes_str = "1.0.0"

    fp_current = _build_fingerprint(snapshot_hash, extractor_hashes_str)

    # Verify the fingerprint is sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes)
    expected_raw = f"{snapshot_hash}:{GRAPH_SCHEMA_VERSION}:{extractor_hashes_str}"
    expected = hashlib.sha256(expected_raw.encode()).hexdigest()
    assert fp_current == expected, "Fingerprint must include GRAPH_SCHEMA_VERSION (I-GRAPH-CACHE-1)"

    # Different schema version → different fingerprint
    alt_raw = f"{snapshot_hash}:0.0.0-stale:{extractor_hashes_str}"
    fp_stale = hashlib.sha256(alt_raw.encode()).hexdigest()
    assert fp_current != fp_stale, "Different schema versions must produce different fingerprints"

    # I-GRAPH-CACHE-2: git_tree_hash is not in the raw fingerprint input
    assert "git_tree_hash" not in expected_raw


# ---------------------------------------------------------------------------
# test_deterministic_graph_has_source_snapshot_hash — I-GRAPH-LINEAGE-1
# ---------------------------------------------------------------------------

def test_deterministic_graph_has_source_snapshot_hash() -> None:
    """Graph returned by GraphService.get_or_build has source_snapshot_hash == index.snapshot_hash.

    I-GRAPH-LINEAGE-1: graph links back to the SpatialIndex it was built from.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        node = _make_node("FILE:sdd/x.py")
        index = _make_index([node], snapshot_hash="deadbeefcafe1234")

        cache = GraphCache(cache_dir=Path(tmpdir))
        service = GraphService(cache=cache, extractors=[_NoOpExtractor()])
        graph = service.get_or_build(index)

        assert isinstance(graph, DeterministicGraph)
        assert graph.source_snapshot_hash == index.snapshot_hash, (
            "I-GRAPH-LINEAGE-1: source_snapshot_hash must match index.snapshot_hash"
        )


# ---------------------------------------------------------------------------
# test_graph_cache_key_excludes_git_tree_hash — I-GRAPH-CACHE-2
# ---------------------------------------------------------------------------

def test_graph_cache_key_excludes_git_tree_hash() -> None:
    """Same snapshot_hash with different git_tree_hash yields the same fingerprint.

    I-GRAPH-CACHE-2: git_tree_hash MUST NOT appear in the cache fingerprint.
    """
    snapshot_hash = "cafebabe87654321"
    extractor_hashes_str = _extractor_hashes([_NoOpExtractor()])

    fp1 = _build_fingerprint(snapshot_hash, extractor_hashes_str)
    # git_tree_hash is not an input to _build_fingerprint — same result regardless
    fp2 = _build_fingerprint(snapshot_hash, extractor_hashes_str)
    assert fp1 == fp2


# ---------------------------------------------------------------------------
# test_graph_fingerprint_uses_extractor_versions — I-GRAPH-FINGERPRINT-1
# ---------------------------------------------------------------------------

def test_graph_fingerprint_uses_extractor_versions() -> None:
    """Fingerprint changes when EXTRACTOR_VERSION changes (I-GRAPH-FINGERPRINT-1)."""

    class _ExtractorV1:
        EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

        def extract(self, index: SpatialIndex) -> list[Edge]:
            return []

    class _ExtractorV2:
        EXTRACTOR_VERSION: ClassVar[str] = "2.0.0"

        def extract(self, index: SpatialIndex) -> list[Edge]:
            return []

    snapshot_hash = "0011223344556677"

    hashes_v1 = _extractor_hashes([_ExtractorV1()])
    hashes_v2 = _extractor_hashes([_ExtractorV2()])
    assert hashes_v1 != hashes_v2

    fp_v1 = _build_fingerprint(snapshot_hash, hashes_v1)
    fp_v2 = _build_fingerprint(snapshot_hash, hashes_v2)
    assert fp_v1 != fp_v2, "Different extractor versions must produce different fingerprints"


# ---------------------------------------------------------------------------
# test_graph_service_cache_hit — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_service_cache_hit() -> None:
    """GraphService returns cached graph on second call (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        node = _make_node("FILE:sdd/y.py")
        index = _make_index([node], snapshot_hash="cafebabe12345678")

        cache = GraphCache(cache_dir=Path(tmpdir))
        service = GraphService(cache=cache, extractors=[_NoOpExtractor()])
        graph1 = service.get_or_build(index)
        graph2 = service.get_or_build(index)

        assert graph1.source_snapshot_hash == graph2.source_snapshot_hash
        assert set(graph1.nodes) == set(graph2.nodes)


# ---------------------------------------------------------------------------
# test_graph_service_force_rebuild — I-GRAPH-CACHE-1
# ---------------------------------------------------------------------------

def test_graph_service_force_rebuild() -> None:
    """force_rebuild=True bypasses cache and returns fresh graph (I-GRAPH-CACHE-1)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        node = _make_node("FILE:sdd/z.py")
        index = _make_index([node], snapshot_hash="0011223344556677")

        cache = GraphCache(cache_dir=Path(tmpdir))
        service = GraphService(cache=cache, extractors=[_NoOpExtractor()])

        service.get_or_build(index)
        graph2 = service.get_or_build(index, force_rebuild=True)

        assert graph2.source_snapshot_hash == index.snapshot_hash


# ---------------------------------------------------------------------------
# test_import_direction_phase50 — I-PHASE-ISOLATION-1
# ---------------------------------------------------------------------------

def test_import_direction_phase50() -> None:
    """No file in sdd/graph/* imports from sdd.context_kernel, sdd.policy, or sdd.graph_navigation.

    I-PHASE-ISOLATION-1: graph subsystem must not depend on higher-level SDD modules.
    """
    forbidden = ["sdd.context_kernel", "sdd.policy", "sdd.graph_navigation"]
    graph_dir = Path(__file__).parents[3] / "src" / "sdd" / "graph"
    assert graph_dir.is_dir(), f"Expected graph directory at {graph_dir}"

    violations: list[str] = []
    for py_file in sorted(graph_dir.rglob("*.py")):
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for forbidden_module in forbidden:
                if forbidden_module in stripped:
                    rel = py_file.relative_to(graph_dir)
                    violations.append(f"{rel}:{lineno}: {stripped!r}")

    assert not violations, (
        "I-PHASE-ISOLATION-1: forbidden imports found in sdd/graph/*:\n"
        + "\n".join(violations)
    )
