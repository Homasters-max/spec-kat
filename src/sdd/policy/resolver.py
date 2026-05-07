from __future__ import annotations

from sdd.policy import Budget, NavigationPolicy, QueryIntent, RagMode


class PolicyResolver:
    """Pure mapping: QueryIntent → NavigationPolicy.

    Single source of truth for intent → (Budget, RagMode) in the system.
    No knowledge of DeterministicGraph, traversal, ContextEngine, GraphService.
    """

    # v1: GLOBAL and HYBRID are disabled (I-RAG-GLOBAL-V1-DISABLED-1)
    _DEFAULT: dict[QueryIntent, NavigationPolicy] = {
        QueryIntent.RESOLVE_EXACT: NavigationPolicy(Budget(5, 10, 4000), RagMode.OFF),
        QueryIntent.EXPLAIN: NavigationPolicy(Budget(20, 40, 16000), RagMode.LOCAL),
        QueryIntent.TRACE: NavigationPolicy(Budget(30, 60, 20000), RagMode.LOCAL),
        QueryIntent.INVARIANT: NavigationPolicy(Budget(10, 20, 8000), RagMode.OFF),
        QueryIntent.SEARCH: NavigationPolicy(Budget(15, 0, 12000), RagMode.LOCAL),
    }

    def resolve(self, intent: QueryIntent) -> NavigationPolicy:
        """Deterministic resolution. Called exactly once per ContextRuntime.query()."""
        return self._DEFAULT[intent]
