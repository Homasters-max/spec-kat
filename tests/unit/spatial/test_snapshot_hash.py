"""Tests for snapshot_hash and read_content accessor on SpatialIndex.

Covers: I-SI-READ-1, I-GRAPH-FS-ROOT-1 (T-5004).
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from sdd.spatial.index import IndexBuilder, SpatialIndex, build_index
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(root: Path, py_content: str = '"""Module A."""\n') -> str:
    src = root / "src" / "sdd"
    src.mkdir(parents=True)
    (src / "module.py").write_text(py_content)
    (root / ".sdd" / "tasks").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("")
    return str(root)


# ---------------------------------------------------------------------------
# I-SI-READ-1: snapshot_hash is content-based
# ---------------------------------------------------------------------------

class TestSnapshotHashContentBased:
    def test_snapshot_hash_content_based(self, tmp_path):
        """I-SI-READ-1: snapshot_hash MUST change when FILE content changes."""
        project = _make_project(tmp_path / "proj_a", '"""Version A."""\n')
        index_a = build_index(project)

        py_file = Path(project) / "src" / "sdd" / "module.py"
        py_file.write_text('"""Version B."""\n')
        index_b = build_index(project)

        assert index_a.snapshot_hash != index_b.snapshot_hash

    def test_snapshot_hash_stable_for_identical_content(self, tmp_path):
        """I-GRAPH-CACHE-2: same content → same snapshot_hash across builds."""
        project = _make_project(tmp_path / "proj", '"""Stable content."""\n')
        h1 = build_index(project).snapshot_hash
        h2 = build_index(project).snapshot_hash
        assert h1 == h2

    def test_snapshot_hash_is_sha256_hex(self, tmp_path):
        project = _make_project(tmp_path / "proj", '"""Any content."""\n')
        index = build_index(project)
        assert len(index.snapshot_hash) == 64
        assert all(c in "0123456789abcdef" for c in index.snapshot_hash)

    def test_snapshot_hash_independent_of_build_timestamp(self, tmp_path):
        """snapshot_hash MUST NOT incorporate time-based fields (determinism)."""
        project = _make_project(tmp_path / "proj", '"""Deterministic."""\n')
        h1 = build_index(project).snapshot_hash
        h2 = build_index(project).snapshot_hash
        assert h1 == h2


# ---------------------------------------------------------------------------
# I-SI-READ-1 + I-GRAPH-FS-ROOT-1: read_content is only public accessor
# ---------------------------------------------------------------------------

class TestReadContentIsOnlyPublicAccessor:
    def test_read_content_is_only_public_accessor(self, tmp_path):
        """I-SI-READ-1: read_content() MUST be the only public accessor for file content.

        I-GRAPH-FS-ROOT-1: SpatialIndex does NOT re-read from filesystem;
        content is pre-loaded by IndexBuilder and accessed exclusively via read_content().
        """
        content = '"""My module."""\nx = 42\n'
        project = _make_project(tmp_path / "proj", content)
        index = build_index(project)

        node = index.nodes["FILE:src/sdd/module.py"]

        # read_content() returns correct content
        assert index.read_content(node) == content

        # _content_map is private (underscore prefix)
        assert hasattr(index, "_content_map"), "_content_map must exist internally"
        assert not any(
            attr == "content_map"
            for attr in dir(index)
            if not attr.startswith("_")
        ), "content_map must not be a public attribute"

        # No other public method on SpatialIndex returns file content
        public_methods = [
            name for name, _ in inspect.getmembers(index, predicate=inspect.ismethod)
            if not name.startswith("_") and name != "read_content"
        ]
        for method_name in public_methods:
            method = getattr(index, method_name)
            try:
                result = method(node)
                assert result != content, (
                    f"Public method {method_name!r} returned file content — "
                    "violates I-SI-READ-1: only read_content() may return content"
                )
            except (TypeError, KeyError, AttributeError):
                pass  # expected — wrong signature or non-content method

    def test_read_content_does_not_open_filesystem(self, tmp_path):
        """I-GRAPH-FS-ROOT-1: read_content() uses pre-loaded data, never opens files."""
        import builtins

        content = '"""Cached content."""\n'
        project = _make_project(tmp_path / "proj", content)
        index = build_index(project)
        node = index.nodes["FILE:src/sdd/module.py"]

        # After build, read_content() must NOT open any file
        original_open = builtins.open
        open_calls: list[str] = []

        def tracking_open(file, *args, **kwargs):
            open_calls.append(str(file))
            return original_open(file, *args, **kwargs)

        builtins.open = tracking_open
        try:
            result = index.read_content(node)
        finally:
            builtins.open = original_open

        assert result == content
        assert open_calls == [], (
            f"I-GRAPH-FS-ROOT-1: read_content() must not open files; opened: {open_calls}"
        )

    def test_read_content_returns_empty_for_non_file_nodes(self, tmp_path):
        """I-SI-READ-1: read_content() returns '' for non-FILE nodes."""
        project = _make_project(tmp_path / "proj")
        index = build_index(project)
        for node in index.nodes.values():
            if node.kind != "FILE":
                assert index.read_content(node) == "", (
                    f"{node.node_id}: expected '' but read_content returned content"
                )

    def test_content_map_key_is_path_not_node_id(self, tmp_path):
        """_content_map is keyed by file path (rel), consistent with read_content()."""
        content = '"""Key check."""\n'
        project = _make_project(tmp_path / "proj", content)
        index = build_index(project)
        node = index.nodes["FILE:src/sdd/module.py"]
        assert node.path in index._content_map
        assert index._content_map[node.path] == content
