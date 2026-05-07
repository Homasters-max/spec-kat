"""TestedByEdgeExtractor: tested_by edges from FILE/COMMAND nodes to TEST nodes.

I-GRAPH-EXTRACTOR-2: no open() calls; filesystem access via os.walk only.
I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
I-GRAPH-TESTED-BY-1: filename convention only — no AST heuristics.
I-GRAPH-TESTED-BY-2: no phantom edges; emit only if TEST node exists (scanned by builder).
"""
from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, ClassVar

from sdd.graph.types import EDGE_KIND_PRIORITY, Edge

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex


def _edge_id(src: str, kind: str, dst: str) -> str:
    """sha256(src:kind:dst)[:16] — I-GRAPH-DET-2."""
    return hashlib.sha256(f"{src}:{kind}:{dst}".encode()).hexdigest()[:16]


def _make_tested_by_edge(src: str, dst: str) -> Edge:
    return Edge(
        edge_id=_edge_id(src, "tested_by", dst),
        src=src,
        dst=dst,
        kind="tested_by",
        priority=EDGE_KIND_PRIORITY["tested_by"],
        source="tested_by_convention",
        meta={},
    )


def _scan_test_node_ids(project_root: str) -> frozenset[str]:
    """Return all TEST node IDs by scanning test directories. No open() calls."""
    result: set[str] = set()
    for scan_dir in ("tests/unit", "tests/integration", "tests/property", "tests/fuzz"):
        abs_dir = os.path.join(project_root, scan_dir)
        if not os.path.isdir(abs_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(abs_dir):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, project_root).replace(os.sep, "/")
                result.add(f"TEST:{rel_path}")
    return frozenset(result)


def _derive_src_nodes(test_node_id: str) -> tuple[str | None, str | None]:
    """Derive (file_node_id, cmd_node_id) from a TEST node ID via filename convention.

    Convention: TEST:tests/unit/<mod...>/test_<name>.py
      → FILE:src/sdd/<mod...>/<name>.py
      → COMMAND:<name> (underscores → dashes)

    Returns (None, None) for paths that don't match the convention.
    Only tests/unit/ and tests/integration/ produce tested_by edges.
    """
    path = test_node_id.removeprefix("TEST:")
    parts = path.split("/")
    # Require: tests/{unit|integration}/<at least one mod segment>/test_<name>.py
    if len(parts) < 4:
        return None, None
    if parts[0] != "tests" or parts[1] not in ("unit", "integration"):
        return None, None
    filename = parts[-1]
    if not filename.startswith("test_") or not filename.endswith(".py"):
        return None, None

    name = filename[5:-3]          # strip "test_" prefix and ".py" suffix
    mod_parts = parts[2:-1]        # path segments between tier dir and filename

    file_node_id = "FILE:src/sdd/" + "/".join(mod_parts) + "/" + name + ".py"
    cmd_node_id = "COMMAND:" + name.replace("_", "-")
    return file_node_id, cmd_node_id


class TestedByEdgeExtractor:
    """Emit 'tested_by' edges: COMMAND → TEST and FILE → TEST.

    Strategy: filename convention only (deterministic, no heuristics).
      tests/unit/commands/test_complete.py
        → COMMAND:complete        --tested_by--> TEST:tests/unit/commands/test_complete.py
        → FILE:src/sdd/commands/complete.py --tested_by--> TEST:tests/unit/commands/test_complete.py

    I-GRAPH-TESTED-BY-1: only filename convention; no AST heuristics.
    I-GRAPH-TESTED-BY-2: edges emitted only if TEST node exists (no phantom edges).
    """

    EXTRACTOR_VERSION: ClassVar[str] = "tested_by_v1"

    def __init__(self, project_root: str | None = None) -> None:
        self._project_root = project_root

    def extract(self, index: "SpatialIndex") -> list[Edge]:
        """Pure function: SpatialIndex → list[Edge]. No open() calls."""
        # Collect known TEST node IDs (I-GRAPH-TESTED-BY-2: no phantom edges)
        test_node_ids: set[str] = set()
        if self._project_root:
            test_node_ids.update(_scan_test_node_ids(self._project_root))

        # Also include any TEST nodes already in the index
        for node_id in index.nodes:
            if node_id.startswith("TEST:"):
                test_node_ids.add(node_id)

        if not test_node_ids:
            return []

        edges: list[Edge] = []
        for test_node_id in sorted(test_node_ids):  # sorted for determinism
            file_node_id, cmd_node_id = _derive_src_nodes(test_node_id)

            # FILE → TEST edge (only if FILE node exists in index — I-GRAPH-TESTED-BY-2)
            if file_node_id and file_node_id in index.nodes:
                edges.append(_make_tested_by_edge(file_node_id, test_node_id))

            # COMMAND → TEST edge (only if COMMAND node exists in index — I-GRAPH-TESTED-BY-2)
            if cmd_node_id and cmd_node_id in index.nodes:
                edges.append(_make_tested_by_edge(cmd_node_id, test_node_id))

        return edges
