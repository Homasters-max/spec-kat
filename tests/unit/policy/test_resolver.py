"""Tests for PolicyResolver — DoD 7 coverage (test_22 equivalent)."""
from __future__ import annotations

import pytest

from sdd.policy import Budget, MIN_CONTEXT_SIZE, NavigationPolicy, QueryIntent, RagMode
from sdd.policy.resolver import PolicyResolver


@pytest.fixture()
def resolver() -> PolicyResolver:
    return PolicyResolver()


# --- DoD 7: _DEFAULT covers all 5 QueryIntent (test_22) ---

def test_all_intents_have_default_policy() -> None:
    """PolicyResolver._DEFAULT MUST cover every QueryIntent (DoD 7)."""
    for intent in QueryIntent:
        assert intent in PolicyResolver._DEFAULT, f"Missing default policy for {intent}"


def test_default_count_matches_intent_count() -> None:
    assert len(PolicyResolver._DEFAULT) == len(QueryIntent)


# --- All 5 intents resolve without error ---

@pytest.mark.parametrize("intent", list(QueryIntent))
def test_resolve_returns_navigation_policy(resolver: PolicyResolver, intent: QueryIntent) -> None:
    policy = resolver.resolve(intent)
    assert isinstance(policy, NavigationPolicy)
    assert isinstance(policy.budget, Budget)
    assert isinstance(policy.rag_mode, RagMode)


# --- Determinism ---

@pytest.mark.parametrize("intent", list(QueryIntent))
def test_resolve_is_deterministic(resolver: PolicyResolver, intent: QueryIntent) -> None:
    assert resolver.resolve(intent) is resolver.resolve(intent)


# --- Specific intent values per Spec_v51 §1 ---

def test_resolve_exact_is_off(resolver: PolicyResolver) -> None:
    policy = resolver.resolve(QueryIntent.RESOLVE_EXACT)
    assert policy.rag_mode == RagMode.OFF
    assert policy.budget.max_nodes == 5
    assert policy.budget.max_chars == 4000


def test_explain_is_local(resolver: PolicyResolver) -> None:
    policy = resolver.resolve(QueryIntent.EXPLAIN)
    assert policy.rag_mode == RagMode.LOCAL
    assert policy.budget.max_nodes == 20
    assert policy.budget.max_chars == 16000


def test_trace_is_local(resolver: PolicyResolver) -> None:
    policy = resolver.resolve(QueryIntent.TRACE)
    assert policy.rag_mode == RagMode.LOCAL
    assert policy.budget.max_nodes == 30
    assert policy.budget.max_chars == 20000


def test_invariant_is_off(resolver: PolicyResolver) -> None:
    policy = resolver.resolve(QueryIntent.INVARIANT)
    assert policy.rag_mode == RagMode.OFF
    assert policy.budget.max_nodes == 10
    assert policy.budget.max_chars == 8000


def test_search_is_local(resolver: PolicyResolver) -> None:
    policy = resolver.resolve(QueryIntent.SEARCH)
    assert policy.rag_mode == RagMode.LOCAL
    assert policy.budget.max_nodes == 15
    assert policy.budget.max_chars == 12000


# --- Budget validation: max_chars < MIN_CONTEXT_SIZE raises (I-CONTEXT-BUDGET-VALID-1) ---

def test_budget_max_chars_below_min_raises() -> None:
    with pytest.raises((AssertionError, ValueError)):
        Budget(max_nodes=5, max_edges=10, max_chars=MIN_CONTEXT_SIZE - 1)


def test_budget_max_chars_exactly_min_is_valid() -> None:
    b = Budget(max_nodes=1, max_edges=0, max_chars=MIN_CONTEXT_SIZE)
    assert b.max_chars == MIN_CONTEXT_SIZE


def test_budget_max_nodes_zero_raises() -> None:
    with pytest.raises((AssertionError, ValueError)):
        Budget(max_nodes=0, max_edges=0, max_chars=MIN_CONTEXT_SIZE)


# --- v1: GLOBAL and HYBRID are disabled (I-RAG-GLOBAL-V1-DISABLED-1) ---

def test_no_global_rag_mode_in_defaults() -> None:
    for policy in PolicyResolver._DEFAULT.values():
        assert policy.rag_mode not in (RagMode.GLOBAL, RagMode.HYBRID), (
            f"v1: GLOBAL/HYBRID must be disabled, found {policy.rag_mode}"
        )


# --- NavigationPolicy is frozen (no mutation) ---

def test_navigation_policy_is_frozen() -> None:
    policy = PolicyResolver._DEFAULT[QueryIntent.RESOLVE_EXACT]
    with pytest.raises((AttributeError, TypeError)):
        policy.rag_mode = RagMode.LOCAL  # type: ignore[misc]
