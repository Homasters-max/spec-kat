# EVAL ONLY — deterministic synthetic graph artifacts for Phase 61 evaluation scenarios
"""Eval fixtures: deterministic test graph data for graph-guided implement protocol evaluation.

Keywords: graph-guided resolve explain trace write anchor session graph-guard protocol
eval fixture deterministic synthetic phase-61 enforcement scope
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalFixtureTarget:
    """Graph write target for S1 (normal path: resolve→explain→trace→write) eval scenario.

    Keywords: normal-path resolve explain trace write graph-guard anchor-chain session-id
    """

    node_id: str
    file_path: str
    anchor_chain: tuple[str, ...]

    @classmethod
    def default(cls) -> "EvalFixtureTarget":
        # EVAL ONLY
        return cls(
            node_id="FILE:src/sdd/eval/eval_fixtures.py",
            file_path="src/sdd/eval/eval_fixtures.py",
            anchor_chain=("FILE:src/sdd/eval/__init__.py",),
        )


@dataclass(frozen=True)
class EvalGuardCheck:
    """Protocol guard check state for S2/S7/S8 (enforcement) eval scenarios.

    Keywords: graph-guard check protocol enforce exit-1 violation session-id
    resolve explain trace protocol-satisfied incomplete-state
    """

    session_id: str
    resolved: bool
    explained: frozenset[str]
    traced: frozenset[str]

    @property
    def protocol_satisfied(self) -> bool:
        return self.resolved and bool(self.explained) and bool(self.traced)

    @classmethod
    def incomplete(cls) -> "EvalGuardCheck":
        """S2/S7: no graph steps taken — protocol not satisfied, guard must exit 1."""
        # EVAL ONLY
        return cls(
            session_id="eval-s2-no-graph",
            resolved=False,
            explained=frozenset(),
            traced=frozenset(),
        )

    @classmethod
    def complete(cls) -> "EvalGuardCheck":
        """S1: full graph protocol satisfied — guard must exit 0."""
        # EVAL ONLY
        return cls(
            session_id="eval-s1-normal",
            resolved=True,
            explained=frozenset(["FILE:src/sdd/eval/eval_fixtures.py"]),
            traced=frozenset(["FILE:src/sdd/eval/eval_fixtures.py"]),
        )


@dataclass(frozen=True)
class EvalSparseGraph:
    """Sparse graph fixture for S3 (NOT_FOUND fallback) eval scenario.

    Keywords: sparse-graph not-found fallback resolve bm25-index missing-node
    graph-navigation graceful-degradation scope-violation-zero
    """

    query: str
    expected_kind: str
    exists_in_index: bool

    @classmethod
    def not_found(cls) -> "EvalSparseGraph":
        """S3: query targets a node absent from the graph index."""
        # EVAL ONLY
        return cls(
            query="nonexistent_module_xyz_eval_sparse_fixture",
            expected_kind="MODULE",
            exists_in_index=False,
        )


@dataclass(frozen=True)
class EvalHiddenDep:
    """Hidden dependency fixture for S4 (trace-before-write) eval scenario.

    Keywords: hidden-dependency trace before-write scope allowed-files imports-edge
    transitive-dependency acknowledgment graph-protocol enforcement
    """

    source_node: str
    hidden_dep_node: str
    trace_path: tuple[str, ...]

    @classmethod
    def default(cls) -> "EvalHiddenDep":
        """S4: eval_deep.py depends on eval_fixtures.py via imports edge (hidden dep)."""
        # EVAL ONLY
        return cls(
            source_node="FILE:src/sdd/eval/eval_deep.py",
            hidden_dep_node="FILE:src/sdd/eval/eval_fixtures.py",
            trace_path=(
                "FILE:src/sdd/eval/eval_deep.py",
                "FILE:src/sdd/eval/eval_fixtures.py",
            ),
        )


@dataclass(frozen=True)
class EvalMultiHop:
    """Multi-hop graph traversal fixture for S6 (BFS depth ≥2) eval scenario.

    Keywords: multi-hop bfs depth traversal graph-navigation imports anchor-chain
    two-hop reachability eval-deep eval-fixtures transitive
    """

    anchor_node: str
    hop1_nodes: tuple[str, ...]
    hop2_nodes: tuple[str, ...]

    @classmethod
    def default(cls) -> "EvalMultiHop":
        """S6: __init__.py →(imports)→ eval_fixtures.py →(imports)→ eval_deep.py."""
        # EVAL ONLY
        return cls(
            anchor_node="FILE:src/sdd/eval/__init__.py",
            hop1_nodes=("FILE:src/sdd/eval/eval_fixtures.py",),
            hop2_nodes=("FILE:src/sdd/eval/eval_deep.py",),
        )
