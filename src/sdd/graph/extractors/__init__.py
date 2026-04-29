"""EdgeExtractor protocol and default extractor registry (I-GRAPH-EXTRACTOR-1,2)."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from sdd.graph.types import Edge

if TYPE_CHECKING:
    from sdd.spatial.index import SpatialIndex


class EdgeExtractor(Protocol):
    """Pure SpatialIndex → list[Edge] transformer. No side effects. No open() calls.

    I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required; inspect.getsource() forbidden.
    I-GRAPH-EXTRACTOR-2: all content access MUST go through index.read_content(node).
    """

    EXTRACTOR_VERSION: ClassVar[str]  # semver; cache fingerprint component

    def extract(self, index: SpatialIndex) -> list[Edge]:
        ...


# Populated as extractors are implemented (T-5011..T-5013).
from sdd.graph.extractors.ast_edges import ASTEdgeExtractor
from sdd.graph.extractors.glossary_edges import GlossaryEdgeExtractor
from sdd.graph.extractors.invariant_edges import InvariantEdgeExtractor
from sdd.graph.extractors.task_deps import TaskDepsExtractor

_DEFAULT_EXTRACTORS: list[EdgeExtractor] = [
    ASTEdgeExtractor(),
    GlossaryEdgeExtractor(),
    InvariantEdgeExtractor(),
    TaskDepsExtractor(),
]
