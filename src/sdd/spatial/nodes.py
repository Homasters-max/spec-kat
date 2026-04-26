from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpatialNode:
    node_id:    str
    kind:       str        # FILE|COMMAND|GUARD|REDUCER|EVENT|TASK|INVARIANT|TERM
    label:      str
    path:       str | None  # None for virtual nodes (INVARIANT, TERM)
    summary:    str         # ~80 tokens; I-SUMMARY-1: 1 line; I-SUMMARY-2: never empty
    signature:  str         # ~300 tokens; I-SIGNATURE-1: interface only (def/class/types)
    meta:       dict
    git_hash:   str | None  # blob SHA from git ls-files -s; None for TERM/INVARIANT
    indexed_at: str         # ISO-8601

    # TERM-specific fields; for non-TERM nodes use defaults
    definition: str = ""
    aliases:    tuple[str, ...] = ()
    links:      tuple[str, ...] = ()  # I-DDD-1: primary source of means edges for TERM

    def __post_init__(self) -> None:
        if not self.summary:
            raise ValueError(f"I-SUMMARY-2: summary must not be empty: {self.node_id!r}")
        if "\n" in self.summary:
            raise ValueError(f"I-SUMMARY-1: summary must be 1 line: {self.node_id!r}")


@dataclass(frozen=True)
class SpatialEdge:
    """Schema contract for Phase 19 (DuckDB graph backend). Not persisted in Phase 18."""
    edge_id: str    # sha256(src+":"+kind+":"+dst)[:16] — deterministic
    src:     str    # node_id of source
    dst:     str    # node_id of destination
    kind:    str    # imports|emits|defined_in|depends_on|tested_by|verified_by|means
    meta:    dict
