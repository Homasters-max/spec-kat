"""GraphSessionState — session-scoped read access record for graph navigation.

I-SEARCH-DIRECT-1: graph navigation MUST NOT access files directly; all file reads
are gated through GraphSessionState.allowed_files resolved in the current session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List


@dataclass
class GraphSessionState:
    """Immutable snapshot of files and traversal path allowed in a graph session."""

    session_id: str
    phase_id: int
    allowed_files: FrozenSet[str]
    trace_path: List[str] = field(default_factory=list)

    # I-GRAPH-DEPTH-1: max traversal depth reached in this session
    traversal_depth_max: int = 0
    # I-FALLBACK-STRICT-1: True if any fallback was used during graph navigation
    fallback_used: bool = False
    # I-EXPLAIN-USAGE-1: set of node IDs visited via explain in this session
    explain_nodes: FrozenSet[str] = field(default_factory=frozenset)
    # I-GRAPH-COVERAGE-REQ-1: files declared as write targets for this session
    write_targets: FrozenSet[str] = field(default_factory=frozenset)
    # I-GRAPH-DEPTH-1: human-readable justification for traversal depth chosen
    depth_justification: str = ""

    def is_allowed(self, file_path: str) -> bool:
        return file_path in self.allowed_files

    def with_trace(self, node_id: str) -> "GraphSessionState":
        return GraphSessionState(
            session_id=self.session_id,
            phase_id=self.phase_id,
            allowed_files=self.allowed_files,
            trace_path=self.trace_path + [node_id],
            traversal_depth_max=self.traversal_depth_max,
            fallback_used=self.fallback_used,
            explain_nodes=self.explain_nodes,
            write_targets=self.write_targets,
            depth_justification=self.depth_justification,
        )
