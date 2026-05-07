"""Tests for BC-18 compat adapter: to_navigation_intent (all QueryIntent variants)."""
from __future__ import annotations

import pytest

from sdd.context_kernel.intent import QueryIntent
from sdd.spatial.adapter import to_navigation_intent
from sdd.spatial.navigator import NavigationIntent


@pytest.mark.parametrize("intent,expected_type", [
    (QueryIntent.RESOLVE_EXACT, "locate"),
    (QueryIntent.SEARCH,        "explore"),
    (QueryIntent.EXPLAIN,       "analyze"),
    (QueryIntent.TRACE,         "analyze"),
    (QueryIntent.INVARIANT,     "analyze"),
])
def test_to_navigation_intent_mapping(intent: QueryIntent, expected_type: str) -> None:
    result = to_navigation_intent(intent)
    assert isinstance(result, NavigationIntent)
    assert result.type == expected_type


def test_all_query_intents_covered() -> None:
    """Every QueryIntent member must be present in the mapping (no KeyError)."""
    for intent in QueryIntent:
        result = to_navigation_intent(intent)
        assert isinstance(result, NavigationIntent), f"Missing mapping for {intent}"
