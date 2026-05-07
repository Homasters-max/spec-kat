"""GraphService: cache-aware graph orchestration (I-GRAPH-SERVICE-1, I-GRAPH-SUBSYSTEM-1)."""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from sdd.graph.builder import GraphFactsBuilder
from sdd.graph.cache import GRAPH_SCHEMA_VERSION, GraphCache
from sdd.graph.extractors import EdgeExtractor, _DEFAULT_EXTRACTORS

if TYPE_CHECKING:
    from sdd.graph.types import DeterministicGraph
    from sdd.spatial.index import SpatialIndex

logger = logging.getLogger(__name__)


def _extractor_hashes(extractors: list[EdgeExtractor]) -> str:
    """Deterministic string from extractor EXTRACTOR_VERSION values (I-GRAPH-FINGERPRINT-1).

    Sorted so fingerprint is independent of extractor list order.
    inspect.getsource() is NOT used (R-INSPECT fix).
    """
    return ":".join(sorted(e.EXTRACTOR_VERSION for e in extractors))


def _build_fingerprint(snapshot_hash: str, extractor_hashes_str: str) -> str:
    """sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes).

    I-GRAPH-CACHE-2: git_tree_hash MUST NOT appear in fingerprint.
    """
    raw = f"{snapshot_hash}:{GRAPH_SCHEMA_VERSION}:{extractor_hashes_str}"
    return hashlib.sha256(raw.encode()).hexdigest()


class GraphService:
    """Cache-aware orchestration: get_or_build() returns cached or freshly built graph.

    I-GRAPH-SERVICE-1: single entry point for graph retrieval/construction.
    I-GRAPH-SUBSYSTEM-1: no imports from sdd.context_kernel, sdd.policy, sdd.graph_navigation
    (I-PHASE-ISOLATION-1).
    """

    def __init__(
        self,
        cache: GraphCache | None = None,
        extractors: list[EdgeExtractor] | None = None,
    ) -> None:
        self._extractors: list[EdgeExtractor] = (
            extractors if extractors is not None else list(_DEFAULT_EXTRACTORS)
        )
        self._cache = cache if cache is not None else GraphCache()
        self._builder = GraphFactsBuilder(self._extractors)

    def get_or_build(
        self,
        index: SpatialIndex,
        force_rebuild: bool = False,
    ) -> DeterministicGraph:
        """Return cached graph or build and cache a new one.

        fingerprint = sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes)
        git_tree_hash is NOT part of fingerprint (I-GRAPH-CACHE-2).
        force_rebuild=True bypasses cache lookup and stores fresh result.
        """
        extractor_hashes_str = _extractor_hashes(self._extractors)
        fingerprint = _build_fingerprint(index.snapshot_hash, extractor_hashes_str)

        if not force_rebuild:
            cached = self._cache.get(fingerprint)
            if cached is not None:
                logger.debug("GraphService: cache hit fingerprint=%s", fingerprint[:16])
                return cached

        logger.debug(
            "GraphService: building graph force_rebuild=%s fingerprint=%s",
            force_rebuild,
            fingerprint[:16],
        )
        graph = self._builder.build(index)
        self._cache.store(fingerprint, graph)
        return graph
