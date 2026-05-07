"""Tests for edge extractors (I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1)."""
from __future__ import annotations

import ast
import builtins
import hashlib
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from sdd.graph.extractors.ast_edges import ASTEdgeExtractor
from sdd.graph.extractors.glossary_edges import GlossaryEdgeExtractor
from sdd.graph.extractors.implements_edges import ImplementsEdgeExtractor
from sdd.graph.extractors.invariant_edges import InvariantEdgeExtractor
from sdd.graph.extractors.module_edges import ModuleEdgeExtractor
from sdd.graph.extractors.task_deps import TaskDepsExtractor
from sdd.graph.types import EDGE_KIND_PRIORITY
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode

_NOW = "2026-01-01T00:00:00Z"


def _make_node(
    node_id: str,
    kind: str,
    label: str,
    path: str | None = None,
    meta: dict | None = None,
    links: tuple[str, ...] = (),
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path=path,
        summary=f"{kind}:{label}",
        signature="",
        meta=meta or {},
        git_hash=None,
        indexed_at=_NOW,
        links=links,
    )


def _make_index(
    nodes: list[SpatialNode],
    content_map: dict[str, str] | None = None,
) -> SpatialIndex:
    nodes_dict = {n.node_id: n for n in nodes}
    index = SpatialIndex(
        nodes=nodes_dict,
        built_at=_NOW,
        git_tree_hash=None,
        snapshot_hash="deadbeef01234567",
    )
    index._content_map = content_map or {}
    return index


# ---------------------------------------------------------------------------
# Test 4: ast_edge_extractor_emits — I-GRAPH-EMITS-1
# ---------------------------------------------------------------------------

def test_ast_edge_extractor_emits() -> None:
    """I-GRAPH-EMITS-1: ASTEdgeExtractor emits an emits-edge when FILE calls EVENT class."""
    file_path = "src/sdd/commands/do_something.py"
    file_node = _make_node(f"FILE:{file_path}", "FILE", "do_something.py", path=file_path)
    event_node = _make_node("EVENT:TaskCreatedEvent", "EVENT", "TaskCreatedEvent")

    content = (
        "from sdd.core.events import TaskCreatedEvent\n\n"
        "def run():\n"
        "    return TaskCreatedEvent(data={})\n"
    )
    index = _make_index([file_node, event_node], {file_path: content})

    edges = ASTEdgeExtractor().extract(index)

    emits_edges = [e for e in edges if e.kind == "emits"]
    assert len(emits_edges) == 1
    assert emits_edges[0].src == f"FILE:{file_path}"
    assert emits_edges[0].dst == "EVENT:TaskCreatedEvent"
    assert emits_edges[0].priority == EDGE_KIND_PRIORITY["emits"]


# ---------------------------------------------------------------------------
# Test 5: ast_edge_extractor_imports
# ---------------------------------------------------------------------------

def test_ast_edge_extractor_imports() -> None:
    """ASTEdgeExtractor emits imports-edges for sdd.* module imports."""
    file_a_path = "src/sdd/graph/builder.py"
    file_b_path = "src/sdd/graph/types.py"
    node_a = _make_node(f"FILE:{file_a_path}", "FILE", "builder.py", path=file_a_path)
    node_b = _make_node(f"FILE:{file_b_path}", "FILE", "types.py", path=file_b_path)

    content_a = "from sdd.graph.types import Edge, Node\n"
    content_b = "class Node: ...\nclass Edge: ...\n"
    index = _make_index([node_a, node_b], {file_a_path: content_a, file_b_path: content_b})

    edges = ASTEdgeExtractor().extract(index)

    imports_edges = [e for e in edges if e.kind == "imports"]
    assert any(
        e.src == f"FILE:{file_a_path}" and e.dst == f"FILE:{file_b_path}"
        for e in imports_edges
    )
    assert all(e.priority == EDGE_KIND_PRIORITY["imports"] for e in imports_edges)


# ---------------------------------------------------------------------------
# Test 6: glossary_edge_extractor_means — I-DDD-1
# ---------------------------------------------------------------------------

def test_glossary_edge_extractor_means() -> None:
    """I-DDD-1: GlossaryEdgeExtractor emits means-edges from TERM.links."""
    term_node = _make_node(
        "TERM:graph",
        "TERM",
        "Graph",
        links=("COMMAND:build-graph", "FILE:src/sdd/graph/builder.py"),
    )
    cmd_node = _make_node("COMMAND:build-graph", "COMMAND", "sdd build-graph")
    file_node = _make_node(
        "FILE:src/sdd/graph/builder.py", "FILE", "builder.py",
        path="src/sdd/graph/builder.py",
    )
    index = _make_index([term_node, cmd_node, file_node])

    edges = GlossaryEdgeExtractor().extract(index)

    means_edges = [e for e in edges if e.kind == "means"]
    assert len(means_edges) == 2
    targets = {e.dst for e in means_edges}
    assert "COMMAND:build-graph" in targets
    assert "FILE:src/sdd/graph/builder.py" in targets
    assert all(e.src == "TERM:graph" for e in means_edges)
    assert all(e.priority == EDGE_KIND_PRIORITY["means"] for e in means_edges)


# ---------------------------------------------------------------------------
# Test 7: invariant_edge_extractor_verified_by
# ---------------------------------------------------------------------------

def test_invariant_edge_extractor_verified_by() -> None:
    """InvariantEdgeExtractor emits verified_by-edges from INVARIANT.meta['verified_by']."""
    inv_node = _make_node(
        "INVARIANT:I-GRAPH-DET-1",
        "INVARIANT",
        "I-GRAPH-DET-1",
        meta={"verified_by": "FILE:tests/unit/graph/test_builder.py"},
    )
    test_node = _make_node(
        "FILE:tests/unit/graph/test_builder.py",
        "FILE",
        "test_builder.py",
        path="tests/unit/graph/test_builder.py",
    )
    index = _make_index([inv_node, test_node])

    edges = InvariantEdgeExtractor().extract(index)

    vb_edges = [e for e in edges if e.kind == "verified_by"]
    assert len(vb_edges) == 1
    assert vb_edges[0].src == "INVARIANT:I-GRAPH-DET-1"
    assert vb_edges[0].dst == "FILE:tests/unit/graph/test_builder.py"
    assert vb_edges[0].priority == EDGE_KIND_PRIORITY["verified_by"]


# ---------------------------------------------------------------------------
# Test 8: task_deps_extractor_depends_on
# ---------------------------------------------------------------------------

def test_task_deps_extractor_depends_on() -> None:
    """TaskDepsExtractor emits depends_on-edges from TASK.meta['depends_on']."""
    task_a = _make_node("TASK:T-5002", "TASK", "T-5002", meta={"depends_on": "TASK:T-5001"})
    task_b = _make_node("TASK:T-5001", "TASK", "T-5001")
    index = _make_index([task_a, task_b])

    edges = TaskDepsExtractor().extract(index)

    dep_edges = [e for e in edges if e.kind == "depends_on"]
    assert len(dep_edges) == 1
    assert dep_edges[0].src == "TASK:T-5002"
    assert dep_edges[0].dst == "TASK:T-5001"
    assert dep_edges[0].priority == EDGE_KIND_PRIORITY["depends_on"]


# ---------------------------------------------------------------------------
# Test 9: extractor_no_open_call — I-GRAPH-EXTRACTOR-2
# ---------------------------------------------------------------------------

def test_extractor_no_open_call() -> None:
    """I-GRAPH-EXTRACTOR-2: no extractor may call open() during extract()."""
    file_path = "src/sdd/foo.py"
    node = _make_node(f"FILE:{file_path}", "FILE", "foo.py", path=file_path)
    index = _make_index([node], {file_path: "x = 1\n"})

    def _fail_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"open() called from extractor: args={args!r}")

    extractors = [
        ASTEdgeExtractor(),
        GlossaryEdgeExtractor(),
        InvariantEdgeExtractor(),
        TaskDepsExtractor(),
    ]

    with patch.object(builtins, "open", side_effect=_fail_open):
        for extractor in extractors:
            extractor.extract(index)


# ---------------------------------------------------------------------------
# Test 28: test_command_nodes_have_implements_edges — I-GRAPH-IMPLEMENTS-1
# ---------------------------------------------------------------------------

def test_command_nodes_have_implements_edges() -> None:
    """I-GRAPH-IMPLEMENTS-1: each COMMAND node with a handler FILE gets an implements edge."""
    handler_path = "src/sdd/commands/activate_phase.py"
    file_node = _make_node(f"FILE:{handler_path}", "FILE", "activate_phase.py", path=handler_path)
    cmd_node = _make_node("COMMAND:activate-phase", "COMMAND", "activate-phase")
    # COMMAND without a corresponding handler file — must produce no edge
    cmd_no_handler = _make_node("COMMAND:unknown-cmd", "COMMAND", "unknown-cmd")
    index = _make_index([file_node, cmd_node, cmd_no_handler])

    edges = ImplementsEdgeExtractor().extract(index)

    impl_edges = [e for e in edges if e.kind == "implements"]
    assert len(impl_edges) == 1, f"expected 1 implements edge, got {len(impl_edges)}"
    assert impl_edges[0].src == f"FILE:{handler_path}"
    assert impl_edges[0].dst == "COMMAND:activate-phase"
    assert impl_edges[0].priority == EDGE_KIND_PRIORITY["implements"]
    assert impl_edges[0].source == "implements_extractor"


# ---------------------------------------------------------------------------
# Test 50: graph_fingerprint_changes_on_extractor_code_change — I-GRAPH-FINGERPRINT-1
# ---------------------------------------------------------------------------

def test_graph_fingerprint_changes_on_extractor_code_change() -> None:
    """I-GRAPH-FINGERPRINT-1: different EXTRACTOR_VERSION → different extractor hash."""

    def _extractor_hash(extractors: list) -> str:
        versions = sorted(e.EXTRACTOR_VERSION for e in extractors)
        payload = str(versions) + repr(EDGE_KIND_PRIORITY)
        return hashlib.sha256(payload.encode()).hexdigest()

    class _BumpedAST(ASTEdgeExtractor):
        EXTRACTOR_VERSION: ClassVar[str] = "2.0.0"

    hash_v1 = _extractor_hash([ASTEdgeExtractor(), GlossaryEdgeExtractor()])
    hash_v2 = _extractor_hash([_BumpedAST(), GlossaryEdgeExtractor()])

    assert hash_v1 != hash_v2


# ---------------------------------------------------------------------------
# Test 57: fs_root_only_spatial_index — I-GRAPH-FS-ROOT-1 (grep-test)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests for ModuleEdgeExtractor (T-5515, Acceptance #9 + I-MODULE-COHESION-1)
# ---------------------------------------------------------------------------

def test_module_edge_extractor_version() -> None:
    """I-GRAPH-FINGERPRINT-1: ModuleEdgeExtractor.EXTRACTOR_VERSION is set."""
    assert ModuleEdgeExtractor.EXTRACTOR_VERSION == "1.0.0"


def test_module_edge_extractor_produces_contains_edges() -> None:
    """(9) ModuleEdgeExtractor.extract() produces contains edges from MODULE:sdd.graph to FILE nodes."""
    module_node = _make_node("MODULE:sdd.graph", "MODULE", "sdd.graph", path="src/sdd/graph")
    file1 = _make_node("FILE:src/sdd/graph/types.py", "FILE", "types.py", path="src/sdd/graph/types.py")
    file2 = _make_node("FILE:src/sdd/graph/builder.py", "FILE", "builder.py", path="src/sdd/graph/builder.py")
    index = _make_index([module_node, file1, file2])

    edges = ModuleEdgeExtractor().extract(index)

    contains_edges = [e for e in edges if e.kind == "contains"]
    assert len(contains_edges) == 2
    assert all(e.src == "MODULE:sdd.graph" for e in contains_edges)
    assert {e.dst for e in contains_edges} == {
        "FILE:src/sdd/graph/types.py",
        "FILE:src/sdd/graph/builder.py",
    }
    assert all(e.priority == EDGE_KIND_PRIORITY["contains"] for e in contains_edges)
    assert all(e.source == "module_edge_extractor" for e in contains_edges)


def test_module_edge_extractor_most_specific_match() -> None:
    """(9) nested collision: src/sdd/graph/extractors/module_edges.py → MODULE:sdd.graph.extractors, not MODULE:sdd.graph."""
    module_graph = _make_node("MODULE:sdd.graph", "MODULE", "sdd.graph", path="src/sdd/graph")
    module_extractors = _make_node(
        "MODULE:sdd.graph.extractors", "MODULE", "sdd.graph.extractors",
        path="src/sdd/graph/extractors",
    )
    file_in_extractors = _make_node(
        "FILE:src/sdd/graph/extractors/module_edges.py",
        "FILE", "module_edges.py",
        path="src/sdd/graph/extractors/module_edges.py",
    )
    file_in_graph = _make_node(
        "FILE:src/sdd/graph/types.py", "FILE", "types.py",
        path="src/sdd/graph/types.py",
    )
    index = _make_index([module_graph, module_extractors, file_in_extractors, file_in_graph])

    edges = ModuleEdgeExtractor().extract(index)

    dst_to_src = {e.dst: e.src for e in edges if e.kind == "contains"}
    assert dst_to_src["FILE:src/sdd/graph/extractors/module_edges.py"] == "MODULE:sdd.graph.extractors"
    assert dst_to_src["FILE:src/sdd/graph/types.py"] == "MODULE:sdd.graph"


def test_module_edge_extractor_no_module_match_skipped() -> None:
    """FILE with no matching MODULE is gracefully skipped — no edge emitted."""
    file_orphan = _make_node(
        "FILE:src/sdd/orphan.py", "FILE", "orphan.py", path="src/sdd/orphan.py",
    )
    index = _make_index([file_orphan])

    edges = ModuleEdgeExtractor().extract(index)

    assert edges == []


def test_module_edge_extractor_no_open_call() -> None:
    """I-GRAPH-EXTRACTOR-2: ModuleEdgeExtractor.extract() must not call open()."""
    module_node = _make_node("MODULE:sdd.graph", "MODULE", "sdd.graph", path="src/sdd/graph")
    file_node = _make_node(
        "FILE:src/sdd/graph/types.py", "FILE", "types.py", path="src/sdd/graph/types.py",
    )
    index = _make_index([module_node, file_node])

    def _fail_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"open() called from ModuleEdgeExtractor: args={args!r}")

    with patch.object(builtins, "open", side_effect=_fail_open):
        ModuleEdgeExtractor().extract(index)


# ---------------------------------------------------------------------------
# Test 57: fs_root_only_spatial_index — I-GRAPH-FS-ROOT-1 (grep-test)
# ---------------------------------------------------------------------------

def test_fs_root_only_spatial_index() -> None:
    """I-GRAPH-FS-ROOT-1: sdd/graph/ modules MUST NOT call open() or read_text() directly."""
    graph_root = Path(__file__).parent.parent.parent.parent / "src" / "sdd" / "graph"
    assert graph_root.is_dir(), f"graph root not found: {graph_root}"

    violations: list[str] = []
    repo_root = graph_root.parent.parent.parent

    for py_file in sorted(graph_root.rglob("*.py")):
        source = py_file.read_text()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                violations.append(f"{py_file.relative_to(repo_root)}:{node.lineno} open()")
            elif isinstance(func, ast.Attribute) and func.attr in ("read_text", "read_bytes"):
                violations.append(
                    f"{py_file.relative_to(repo_root)}:{node.lineno} .{func.attr}()"
                )

    assert violations == [], (
        "I-GRAPH-FS-ROOT-1 violations in sdd/graph/:\n" + "\n".join(violations)
    )
