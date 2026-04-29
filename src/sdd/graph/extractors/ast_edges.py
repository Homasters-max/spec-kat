"""ASTEdgeExtractor: imports, emits, guards, tested_by edges from Python AST.

I-GRAPH-EXTRACTOR-2: no open() calls; all content via index.read_content(node).
I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
"""
from __future__ import annotations

import ast
import hashlib
from typing import TYPE_CHECKING, ClassVar

from sdd.graph.errors import GraphInvariantError
from sdd.graph.types import EDGE_KIND_PRIORITY, Edge

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex
    from sdd.spatial.nodes import SpatialNode


def _edge_id(src: str, kind: str, dst: str) -> str:
    """sha256(src:kind:dst)[:16] — I-GRAPH-DET-2."""
    return hashlib.sha256(f"{src}:{kind}:{dst}".encode()).hexdigest()[:16]


def _make_edge(src: str, kind: str, dst: str, source: str) -> Edge:
    if kind not in EDGE_KIND_PRIORITY:
        raise GraphInvariantError(f"Unknown edge kind {kind!r}; not in EDGE_KIND_PRIORITY")
    return Edge(
        edge_id=_edge_id(src, kind, dst),
        src=src,
        dst=dst,
        kind=kind,
        priority=EDGE_KIND_PRIORITY[kind],
        source=source,
        meta={},
    )


def _module_to_file_node_id(module: str) -> str | None:
    """Convert Python dotted module path → FILE node_id convention.

    e.g. 'sdd.graph.types' → 'FILE:src/sdd/graph/types.py'
    Only sdd.* modules are indexed as FILE nodes.
    """
    if not module.startswith("sdd.") and module != "sdd":
        return None
    rel_path = "src/" + module.replace(".", "/") + ".py"
    return f"FILE:{rel_path}"


def _collect_imported_modules(tree: ast.Module) -> list[str]:
    """Collect all top-level module names from import statements."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def _collect_called_names(tree: ast.Module) -> set[str]:
    """Collect all names that appear as direct callees (ClassName(...)).

    I-GRAPH-EMITS-1 condition 3: reference must be a direct Call node,
    not a string annotation.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


class ASTEdgeExtractor:
    """Extract imports, emits, guards, tested_by edges via static Python AST analysis.

    I-GRAPH-EMITS-1: emits edge only when all 4 conditions are satisfied:
      1. Source node is a FILE kind node.
      2. Source file is not the events definition file itself.
      3. Target event class is a known EVENT node in the current index.
      4. The event class name appears in a direct ast.Call context (not annotation).
    """

    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: "SpatialIndex") -> list[Edge]:  # noqa: UP037
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        event_nodes: dict[str, str] = {}   # class_name → node_id
        guard_node_ids: set[str] = set()   # node_ids of GUARD kind
        guard_modules: set[str] = set()    # module paths that correspond to GUARDs
        file_node_ids: set[str] = set()    # all known FILE node_ids

        for node_id, node in index.nodes.items():
            if node.kind == "EVENT":
                label = node.label  # e.g. "TaskImplementedEvent"
                event_nodes[label] = node_id
            elif node.kind == "GUARD":
                guard_node_ids.add(node_id)
                if node.path:
                    # Convert path like "src/sdd/guards/phase_guard.py" → module "sdd.guards.phase_guard"
                    if node.path.startswith("src/"):
                        mod = node.path[len("src/"):].rstrip(".py").replace("/", ".").removesuffix(".py")
                        guard_modules.add(mod)
            elif node.kind == "FILE":
                file_node_ids.add(node_id)

        edges: list[Edge] = []

        for node_id, node in index.nodes.items():
            if node.kind != "FILE":
                continue
            path = node.path or ""
            if not path.endswith(".py"):
                continue

            content = index.read_content(node)
            if not content.strip():
                continue

            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            # --- imports edges ---
            for module in _collect_imported_modules(tree):
                target_id = _module_to_file_node_id(module)
                if target_id and target_id in file_node_ids and target_id != node_id:
                    edges.append(_make_edge(node_id, "imports", target_id, "ast_imports"))

            # --- emits edges (I-GRAPH-EMITS-1) ---
            # Condition 2: skip the events definition file itself
            is_events_file = path.endswith("core/events.py")
            if not is_events_file and event_nodes:
                called_names = _collect_called_names(tree)
                for class_name, event_node_id in event_nodes.items():
                    # Condition 4: class name appears in direct Call context
                    if class_name in called_names:
                        edges.append(_make_edge(node_id, "emits", event_node_id, "ast_emits"))

            # --- guards edges ---
            for module in _collect_imported_modules(tree):
                # Any import from a guard module creates a guards edge
                if module in guard_modules:
                    guard_id = f"GUARD:{module.rsplit('.', 1)[-1]}"
                    if guard_id in guard_node_ids:
                        edges.append(_make_edge(node_id, "guards", guard_id, "ast_guards"))

        return edges
