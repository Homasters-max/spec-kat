# EVAL ONLY — synthetic graph test artifacts for Phase 61 evaluation scenarios
"""sdd.eval — deterministic eval fixtures for graph-guided implement evaluation.

Keywords: eval graph-guided resolve explain trace write protocol anchor session
"""
from sdd.eval.eval_fixtures import (
    EvalFixtureTarget,
    EvalGuardCheck,
    EvalSparseGraph,
    EvalHiddenDep,
    EvalMultiHop,
)

__all__ = [
    "EvalFixtureTarget",
    "EvalGuardCheck",
    "EvalSparseGraph",
    "EvalHiddenDep",
    "EvalMultiHop",
]
