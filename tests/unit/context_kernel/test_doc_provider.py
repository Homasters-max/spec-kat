"""Tests for DocProvider, DefaultContentMapper, _extract_references (T-5111)."""
from __future__ import annotations

import ast
import inspect

import pytest

from sdd.context_kernel.documents import (
    DefaultContentMapper,
    DocProvider,
    DocumentChunk,
    _extract_references,
)
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = "2026-01-01T00:00:00Z"


def _node(
    node_id: str,
    kind: str = "FILE",
    path: str | None = None,
    meta: dict | None = None,
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=node_id,
        path=path,
        summary=f"summary of {node_id}",
        signature="",
        meta=meta or {},
        git_hash=None,
        indexed_at=_NOW,
    )


def _index(nodes: dict[str, SpatialNode], content_map: dict[str, str] | None = None) -> SpatialIndex:
    idx = SpatialIndex(
        nodes=nodes,
        built_at=_NOW,
        git_tree_hash=None,
    )
    idx._content_map = content_map or {}
    return idx


# ---------------------------------------------------------------------------
# DocumentChunk — basic construction
# ---------------------------------------------------------------------------

class TestDocumentChunk:
    def test_fields_stored(self):
        chunk = DocumentChunk(
            node_id="FILE:x.py",
            content="hello",
            kind="code",
            char_count=5,
            meta={"a": 1},
            references=["FILE:y.py"],
        )
        assert chunk.node_id == "FILE:x.py"
        assert chunk.content == "hello"
        assert chunk.char_count == 5
        assert chunk.references == ["FILE:y.py"]


# ---------------------------------------------------------------------------
# DefaultContentMapper
# ---------------------------------------------------------------------------

class TestDefaultContentMapper:
    def setup_method(self):
        self.mapper = DefaultContentMapper()

    def test_non_file_node_returns_empty(self):
        """I-DOC-NON-FILE-1: non-FILE node always yields '' regardless of content."""
        for kind in ("COMMAND", "TASK", "GUARD", "INVARIANT", "TERM", "REDUCER", "EVENT"):
            node = _node("X:y", kind=kind)
            assert self.mapper.extract_chunk(node, "some content") == ""

    def test_file_node_without_bounds_returns_whole(self):
        node = _node("FILE:a.py", kind="FILE", path="src/a.py")
        content = "line1\nline2\nline3"
        assert self.mapper.extract_chunk(node, content) == content

    def test_file_node_with_bounds_slices_lines(self):
        node = _node("FILE:a.py", kind="FILE", path="src/a.py", meta={"line_start": 2, "line_end": 3})
        content = "line1\nline2\nline3\nline4"
        result = self.mapper.extract_chunk(node, content)
        assert result == "line2\nline3"

    def test_file_node_single_line(self):
        node = _node("FILE:a.py", kind="FILE", path="src/a.py", meta={"line_start": 1, "line_end": 1})
        content = "only\nsecond"
        assert self.mapper.extract_chunk(node, content) == "only"

    def test_file_node_partial_meta_no_slice(self):
        """Only line_start without line_end → whole file returned."""
        node = _node("FILE:a.py", kind="FILE", path="src/a.py", meta={"line_start": 2})
        content = "a\nb\nc"
        assert self.mapper.extract_chunk(node, content) == content


# ---------------------------------------------------------------------------
# _extract_references
# ---------------------------------------------------------------------------

class TestExtractReferences:
    def test_finds_valid_node_ids(self):
        valid = frozenset({"FILE:src/a.py", "COMMAND:complete"})
        content = "Uses FILE:src/a.py and COMMAND:complete here."
        refs = _extract_references(content, valid)
        assert set(refs) == {"FILE:src/a.py", "COMMAND:complete"}

    def test_filters_out_unknown_ids(self):
        valid = frozenset({"FILE:src/a.py"})
        content = "FILE:src/a.py and UNKNOWN:thing"
        refs = _extract_references(content, valid)
        assert refs == ["FILE:src/a.py"]

    def test_deduplicates(self):
        valid = frozenset({"FILE:x.py"})
        content = "FILE:x.py appears FILE:x.py twice"
        refs = _extract_references(content, valid)
        assert refs.count("FILE:x.py") == 1

    def test_empty_content(self):
        assert _extract_references("", frozenset({"FILE:x.py"})) == []

    def test_trailing_punctuation_stripped(self):
        """Trailing .,;:) must not prevent matching."""
        valid = frozenset({"FILE:src/a.py"})
        content = "see FILE:src/a.py."
        refs = _extract_references(content, valid)
        assert "FILE:src/a.py" in refs

    def test_preserves_order_of_first_occurrence(self):
        valid = frozenset({"FILE:a.py", "FILE:b.py"})
        content = "FILE:a.py then FILE:b.py then FILE:a.py"
        refs = _extract_references(content, valid)
        assert refs == ["FILE:a.py", "FILE:b.py"]


# ---------------------------------------------------------------------------
# DocProvider — get_chunks (cache path)
# ---------------------------------------------------------------------------

class TestDocProviderCachePath:
    def _provider_with_file(self, path: str, content: str) -> DocProvider:
        node = _node(f"FILE:{path}", kind="FILE", path=path)
        idx = _index({f"FILE:{path}": node}, {path: content})
        return DocProvider(idx)

    def test_returns_chunk_for_known_file_node(self):
        dp = self._provider_with_file("src/a.py", "hello world")
        chunks = dp.get_chunks(["FILE:src/a.py"])
        assert len(chunks) == 1
        assert chunks[0].node_id == "FILE:src/a.py"
        assert chunks[0].content == "hello world"

    def test_char_count_correct(self):
        dp = self._provider_with_file("src/a.py", "abc")
        chunks = dp.get_chunks(["FILE:src/a.py"])
        assert chunks[0].char_count == 3

    def test_unknown_node_id_silently_skipped(self):
        dp = self._provider_with_file("src/a.py", "x")
        chunks = dp.get_chunks(["DOES_NOT_EXIST"])
        assert chunks == []

    def test_meta_copied_from_node(self):
        node = _node("FILE:f.py", kind="FILE", path="f.py", meta={"line_start": 1, "line_end": 2})
        idx = _index({"FILE:f.py": node}, {"f.py": "a\nb\nc"})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["FILE:f.py"])
        assert chunks[0].meta == {"line_start": 1, "line_end": 2}

    def test_kind_mapped_code_for_file(self):
        dp = self._provider_with_file("src/a.py", "x")
        chunks = dp.get_chunks(["FILE:src/a.py"])
        assert chunks[0].kind == "code"

    def test_kind_mapped_task(self):
        node = _node("TASK:T-001", kind="TASK", path=None)
        idx = _index({"TASK:T-001": node})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["TASK:T-001"])
        assert chunks[0].kind == "task"
        assert chunks[0].content == ""

    def test_kind_mapped_invariant(self):
        node = _node("INVARIANT:I-1", kind="INVARIANT", path=None)
        idx = _index({"INVARIANT:I-1": node})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["INVARIANT:I-1"])
        assert chunks[0].kind == "invariant"

    def test_kind_fallback_doc_for_unknown(self):
        node = _node("GUARD:foo", kind="GUARD", path=None)
        idx = _index({"GUARD:foo": node})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["GUARD:foo"])
        assert chunks[0].kind == "doc"

    def test_multiple_chunks_returned_in_order(self):
        nodes = {
            "FILE:a.py": _node("FILE:a.py", path="a.py"),
            "FILE:b.py": _node("FILE:b.py", path="b.py"),
        }
        idx = _index(nodes, {"a.py": "AAA", "b.py": "BBB"})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["FILE:a.py", "FILE:b.py"])
        assert [c.node_id for c in chunks] == ["FILE:a.py", "FILE:b.py"]

    def test_references_filtered_to_valid_ids(self):
        node_a = _node("FILE:a.py", path="a.py")
        node_b = _node("FILE:b.py", path="b.py")
        content_a = "see FILE:b.py and UNKNOWN:x"
        idx = _index({"FILE:a.py": node_a, "FILE:b.py": node_b}, {"a.py": content_a, "b.py": ""})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["FILE:a.py"])
        assert "FILE:b.py" in chunks[0].references
        assert not any("UNKNOWN" in r for r in chunks[0].references)

    def test_empty_content_yields_empty_references(self):
        """Empty content must produce empty references list (no regex run)."""
        node = _node("TASK:T-001", kind="TASK", path=None)
        idx = _index({"TASK:T-001": node})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["TASK:T-001"])
        assert chunks[0].references == []


# ---------------------------------------------------------------------------
# DocProvider — non-FILE node explicit (I-DOC-NON-FILE-1)
# ---------------------------------------------------------------------------

class TestDocProviderNonFileEmpty:
    """I-DOC-NON-FILE-1: non-FILE nodes must yield an empty-content DocumentChunk."""

    @pytest.mark.parametrize("kind", ["COMMAND", "GUARD", "REDUCER", "EVENT", "TASK", "INVARIANT", "TERM"])
    def test_non_file_node_empty_chunk(self, kind: str):
        node = _node(f"{kind}:x", kind=kind, path=None)
        idx = _index({f"{kind}:x": node})
        dp = DocProvider(idx)
        chunks = dp.get_chunks([f"{kind}:x"])
        assert len(chunks) == 1
        assert chunks[0].content == ""
        assert chunks[0].char_count == 0


# ---------------------------------------------------------------------------
# DocProvider — filesystem fallback (tmp_path isolation)
# ---------------------------------------------------------------------------

class TestDocProviderFilesystemFallback:
    """SpatialIndex loaded from disk has empty _content_map — DocProvider reads filesystem."""

    def test_reads_file_from_filesystem_when_cache_miss(self, tmp_path):
        file_path = tmp_path / "module.py"
        file_path.write_text("def hello(): ...")

        rel = str(file_path)
        node = _node(f"FILE:{rel}", kind="FILE", path=rel)
        # _content_map is empty — simulates a loaded-from-disk index
        idx = _index({f"FILE:{rel}": node}, {})
        dp = DocProvider(idx)

        chunks = dp.get_chunks([f"FILE:{rel}"])
        assert chunks[0].content == "def hello(): ..."

    def test_oserror_yields_empty_content(self, tmp_path):
        missing = str(tmp_path / "nonexistent.py")
        node = _node(f"FILE:{missing}", kind="FILE", path=missing)
        idx = _index({f"FILE:{missing}": node}, {})
        dp = DocProvider(idx)

        chunks = dp.get_chunks([f"FILE:{missing}"])
        assert chunks[0].content == ""
        assert chunks[0].char_count == 0

    def test_cache_takes_priority_over_filesystem(self, tmp_path):
        """When _content_map has the path, filesystem must NOT be read."""
        file_path = tmp_path / "x.py"
        file_path.write_text("on-disk content")

        rel = str(file_path)
        node = _node(f"FILE:{rel}", kind="FILE", path=rel)
        idx = _index({f"FILE:{rel}": node}, {rel: "cached content"})
        dp = DocProvider(idx)

        chunks = dp.get_chunks([f"FILE:{rel}"])
        assert chunks[0].content == "cached content"

    def test_non_file_node_no_filesystem_access(self, tmp_path):
        """Non-FILE nodes never attempt filesystem access, even with a path set."""
        sentinel = tmp_path / "sentinel.py"
        sentinel.write_text("SHOULD_NOT_READ")

        # Deliberately use COMMAND kind with a path — _read_raw must return "" via index
        node = _node("COMMAND:foo", kind="COMMAND", path=str(sentinel))
        idx = _index({"COMMAND:foo": node}, {})
        dp = DocProvider(idx)
        chunks = dp.get_chunks(["COMMAND:foo"])
        assert chunks[0].content == ""


# ---------------------------------------------------------------------------
# Grep assertion: DocProvider is the sole I/O point (I-DOC-FS-IO-1)
# ---------------------------------------------------------------------------

class TestDocProviderSoleIOPoint:
    def test_open_calls_only_inside_doc_provider(self):
        """I-DOC-FS-IO-1: `open(` must appear only inside DocProvider._read_raw in documents.py."""
        import sdd.context_kernel.documents as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)

        open_call_locations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name != "open":
                continue
            # Walk upward via parent tracking: find enclosing function/class
            open_call_locations.append(ast.unparse(node))

        # All open() calls must exist inside DocProvider._read_raw only.
        # We verify by checking the source text — _read_raw is the sole method with open().
        lines = source.split("\n")
        open_lines = [ln.strip() for ln in lines if "open(" in ln and not ln.strip().startswith("#")]

        for ln in open_lines:
            assert "DocProvider" not in ln or True  # structural check below

        # Structural: find ClassDef DocProvider, then _read_raw method, collect its line range
        class_node: ast.ClassDef | None = None
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef) and n.name == "DocProvider":
                class_node = n
                break
        assert class_node is not None, "DocProvider class not found in documents.py"

        read_raw: ast.FunctionDef | None = None
        for n in ast.walk(class_node):
            if isinstance(n, ast.FunctionDef) and n.name == "_read_raw":
                read_raw = n
                break
        assert read_raw is not None, "_read_raw method not found in DocProvider"

        read_raw_lines = set(range(read_raw.lineno, read_raw.end_lineno + 1))

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            func = n.func
            call_name = ""
            if isinstance(func, ast.Name):
                call_name = func.id
            elif isinstance(func, ast.Attribute):
                call_name = func.attr
            if call_name != "open":
                continue
            assert hasattr(n, "lineno"), "open() call has no line number"
            assert n.lineno in read_raw_lines, (
                f"open() call at line {n.lineno} is outside DocProvider._read_raw "
                f"(lines {read_raw.lineno}–{read_raw.end_lineno}). "
                "I-DOC-FS-IO-1: DocProvider must be the sole filesystem I/O point."
            )
