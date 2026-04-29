from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from sdd.graph.types import DeterministicGraph, Edge, Node
from sdd.infra.paths import get_sdd_root

GRAPH_SCHEMA_VERSION: str = "50.1"

logger = logging.getLogger(__name__)


def _default_cache_dir() -> Path:
    return get_sdd_root() / "runtime" / "graph_cache"


def _graph_to_dict(graph: DeterministicGraph) -> dict:
    return {
        "nodes": {k: asdict(v) for k, v in graph.nodes.items()},
        "edges_out": {k: [asdict(e) for e in edges] for k, edges in graph.edges_out.items()},
        "edges_in": {k: [asdict(e) for e in edges] for k, edges in graph.edges_in.items()},
        "source_snapshot_hash": graph.source_snapshot_hash,
    }


def _graph_from_dict(data: dict) -> DeterministicGraph:
    nodes = {k: Node(**v) for k, v in data["nodes"].items()}
    edges_out = {k: [Edge(**e) for e in edges] for k, edges in data["edges_out"].items()}
    edges_in = {k: [Edge(**e) for e in edges] for k, edges in data["edges_in"].items()}
    return DeterministicGraph(
        nodes=nodes,
        edges_out=edges_out,
        edges_in=edges_in,
        source_snapshot_hash=data["source_snapshot_hash"],
    )


class GraphCache:
    """Pure memoization: key → DeterministicGraph.

    No build logic. No knowledge of index or extractor types (R-PICKLE fix).
    Storage: JSON files in cache_dir with schema_version header.
    Eviction: get() returns None when stored schema_version != GRAPH_SCHEMA_VERSION.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir: Path = cache_dir if cache_dir is not None else _default_cache_dir()

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def get(self, key: str) -> DeterministicGraph | None:
        """Return cached graph or None (miss / schema mismatch / corrupt)."""
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                payload = json.loads(f.read())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("GraphCache: failed to read %s: %s", path, exc)
            return None
        if payload.get("schema_version") != GRAPH_SCHEMA_VERSION:
            logger.debug("GraphCache: schema_version mismatch for key %s — evicting", key)
            return None
        try:
            return _graph_from_dict(payload["graph"])
        except (KeyError, TypeError) as exc:
            logger.warning("GraphCache: failed to deserialize graph for key %s: %s", key, exc)
            return None

    def store(self, key: str, graph: DeterministicGraph) -> None:
        """Persist graph to cache with current GRAPH_SCHEMA_VERSION header."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "graph": _graph_to_dict(graph),
        }
        self._cache_path(key).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def invalidate(self, key: str) -> None:
        """Remove cached entry for key if it exists."""
        path = self._cache_path(key)
        if path.exists():
            path.unlink()
