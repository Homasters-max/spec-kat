"""Tests for intent.py — I-INTENT-HEURISTIC-1, I-SEARCH-NO-EMBED-1, I-SEARCH-AUTO-EXACT-1."""
from __future__ import annotations

import dataclasses

import pytest

from sdd.context_kernel.intent import QueryIntent, SearchCandidate, parse_query_intent


# ---------------------------------------------------------------------------
# parse_query_intent — RESOLVE_EXACT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "COMMAND:complete",
    "EVENT:PhaseInitialized",
    "TASK:T-5101",
    "NAMESPACE:some-id",
    "A:b",
])
def test_resolve_exact_for_namespace_id_pattern(query: str) -> None:
    assert parse_query_intent(query) is QueryIntent.RESOLVE_EXACT


def test_resolve_exact_strips_whitespace() -> None:
    assert parse_query_intent("  COMMAND:complete  ") is QueryIntent.RESOLVE_EXACT


# ---------------------------------------------------------------------------
# parse_query_intent — INVARIANT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "I-1",
    "I-DB-TEST-1",
    "I-SPEC-EXEC-1",
    "I-INTENT-HEURISTIC-1",
    "I-RRL-2",
    "I-A",
])
def test_invariant_pattern(query: str) -> None:
    assert parse_query_intent(query) is QueryIntent.INVARIANT


# ---------------------------------------------------------------------------
# parse_query_intent — SEARCH (everything else)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "how does phase activation work",
    "activate phase",
    "complete task",
    "command complete",
    "command:complete",   # lowercase namespace → not RESOLVE_EXACT
    "I-lowercase",        # not I-UPPERCASE → not INVARIANT
    "i-1",               # lowercase → not INVARIANT
    "explain kernel",
    "trace dependencies",
    "",
    "COMMAND",
    "COMMAND:",
    ":complete",
    "namespace:id:extra",
])
def test_search_for_freeform_queries(query: str) -> None:
    assert parse_query_intent(query) is QueryIntent.SEARCH


# ---------------------------------------------------------------------------
# I-INTENT-HEURISTIC-1 — EXPLAIN and TRACE MUST NOT be inferred by heuristics
# ---------------------------------------------------------------------------

def test_parse_query_intent_no_explain_trace() -> None:
    """parse_query_intent() output MUST be one of {RESOLVE_EXACT, INVARIANT, SEARCH}.

    EXPLAIN and TRACE are set exclusively by CLI routing, never by parse_query_intent()
    (I-INTENT-HEURISTIC-1). This test uses keyword-heavy queries that could naively
    trigger EXPLAIN or TRACE — they MUST all map to SEARCH.
    """
    explain_like = [
        "explain how event sourcing works",
        "explain the write kernel",
        "how to explain phases",
        "what does EXPLAIN mean",
    ]
    trace_like = [
        "trace the activation flow",
        "trace dependencies of T-5101",
        "show trace for command complete",
        "trace back",
    ]
    prohibited = {QueryIntent.EXPLAIN, QueryIntent.TRACE}
    for query in explain_like + trace_like:
        result = parse_query_intent(query)
        assert result not in prohibited, (
            f"parse_query_intent({query!r}) returned {result} — EXPLAIN/TRACE "
            "MUST NOT be inferred from keyword heuristics (I-INTENT-HEURISTIC-1)"
        )
        assert result is QueryIntent.SEARCH


# ---------------------------------------------------------------------------
# QueryIntent enum — completeness
# ---------------------------------------------------------------------------

def test_query_intent_has_five_members() -> None:
    members = {e.name for e in QueryIntent}
    assert members == {"RESOLVE_EXACT", "SEARCH", "EXPLAIN", "TRACE", "INVARIANT"}


# ---------------------------------------------------------------------------
# SearchCandidate — I-SEARCH-NO-EMBED-1 (BM25, no embedding fields)
# ---------------------------------------------------------------------------

def test_search_candidate_fields() -> None:
    """SearchCandidate MUST have exactly the fields declared in spec §2.3.

    fuzzy_score is BM25-based. No embedding-based similarity field is allowed
    (I-SEARCH-NO-EMBED-1).
    """
    candidate = SearchCandidate(
        node_id="COMMAND:complete",
        kind="COMMAND",
        label="complete",
        summary="Mark task done",
        fuzzy_score=0.87,
    )
    assert candidate.node_id == "COMMAND:complete"
    assert candidate.kind == "COMMAND"
    assert candidate.label == "complete"
    assert candidate.summary == "Mark task done"
    assert candidate.fuzzy_score == pytest.approx(0.87)


def test_search_candidate_is_frozen() -> None:
    candidate = SearchCandidate(
        node_id="X:y", kind="K", label="l", summary="s", fuzzy_score=0.5
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        candidate.fuzzy_score = 1.0  # type: ignore[misc]


def test_search_candidate_no_embedding_field() -> None:
    """No embedding-based similarity field allowed on SearchCandidate (I-SEARCH-NO-EMBED-1)."""
    forbidden_names = {"embedding", "embedding_score", "vector_score", "cosine_similarity"}
    field_names = {f.name for f in dataclasses.fields(SearchCandidate)}
    overlap = field_names & forbidden_names
    assert not overlap, f"SearchCandidate has forbidden embedding fields: {overlap}"


# ---------------------------------------------------------------------------
# I-SEARCH-AUTO-EXACT-1 — interface contract for single-candidate auto-upgrade
# ---------------------------------------------------------------------------

def test_search_candidate_exposes_node_id_for_auto_exact_upgrade() -> None:
    """SearchCandidate.node_id MUST be accessible to ContextEngine._build_selection().

    When SEARCH returns exactly one SearchCandidate, ContextEngine MUST automatically
    upgrade intent to RESOLVE_EXACT using candidate.node_id as the lookup key
    (I-SEARCH-AUTO-EXACT-1). This test verifies the interface contract from the
    intent layer: node_id is a non-empty string on a properly constructed candidate.
    """
    single = SearchCandidate(
        node_id="EVENT:PhaseInitialized",
        kind="EVENT",
        label="PhaseInitialized",
        summary="Emitted when a phase is activated",
        fuzzy_score=0.95,
    )
    assert isinstance(single.node_id, str)
    assert single.node_id  # non-empty — required for ContextEngine lookup
