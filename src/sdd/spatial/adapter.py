"""BC-18 compatibility adapter: QueryIntent → NavigationIntent conversion.

I-INTENT-CANONICAL-1: this is the ONLY location where NavigationIntent may be
constructed from a QueryIntent. ContextEngine, ContextAssembler, and DocProvider
MUST NOT import NavigationIntent directly.
"""
from __future__ import annotations

from sdd.context_kernel.intent import QueryIntent
from sdd.spatial.navigator import NavigationIntent

_QUERY_INTENT_TO_NAV: dict[QueryIntent, str] = {
    QueryIntent.RESOLVE_EXACT: "locate",
    QueryIntent.SEARCH:        "explore",
    QueryIntent.EXPLAIN:       "analyze",
    QueryIntent.TRACE:         "analyze",
    QueryIntent.INVARIANT:     "analyze",
}


def to_navigation_intent(intent: QueryIntent) -> NavigationIntent:
    """Convert QueryIntent to NavigationIntent (BC-18 compat). Single definition site."""
    return NavigationIntent(type=_QUERY_INTENT_TO_NAV[intent])  # type: ignore[arg-type]
