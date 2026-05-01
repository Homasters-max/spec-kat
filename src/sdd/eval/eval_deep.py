# EVAL ONLY — 2-hop chain node for Phase 61 multi-hop BFS evaluation (S6)
"""Eval deep module: terminal node in a 2-hop imports chain for graph traversal evaluation.

Reachability chain:
  FILE:src/sdd/eval/__init__.py  →(imports)→  FILE:src/sdd/eval/eval_fixtures.py
  FILE:src/sdd/eval/eval_fixtures.py  →(imports)→  FILE:src/sdd/eval/eval_deep.py

Keywords: multi-hop bfs traversal graph-navigation eval-deep anchor-chain imports
two-hop reachability depth-2 transitive resolve explain trace
"""
from __future__ import annotations

from sdd.eval.eval_fixtures import EvalHiddenDep, EvalMultiHop


class EvalDeepAnchor:
    """2-hop BFS anchor: reachable only via eval_fixtures, not directly from __init__.

    Keywords: deep-anchor two-hop graph-traversal bfs depth resolve explain trace
    phase-61 scenario-s6 multi-hop reachability eval-only
    """

    def __init__(self) -> None:
        # EVAL ONLY — deterministic fixture instances
        self.multi_hop: EvalMultiHop = EvalMultiHop.default()
        self.hidden_dep: EvalHiddenDep = EvalHiddenDep.default()

    @property
    def node_id(self) -> str:
        """Canonical graph node ID for this eval artifact."""
        return "FILE:src/sdd/eval/eval_deep.py"

    @property
    def hop_depth(self) -> int:
        """BFS depth from anchor FILE:src/sdd/eval/__init__.py — must be ≥2 for S6."""
        return 2
