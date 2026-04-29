"""QueryIntent, parse_query_intent(), SearchCandidate — BC-36-3 intent layer."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class QueryIntent(Enum):
    RESOLVE_EXACT = "resolve_exact"
    SEARCH = "search"
    EXPLAIN = "explain"
    TRACE = "trace"
    INVARIANT = "invariant"


# NAMESPACE:ID — e.g. "COMMAND:complete", "EVENT:PhaseInitialized"
_NAMESPACE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*:[A-Za-z0-9_-]+$")

# Invariant identifier — e.g. "I-1", "I-DB-TEST-1", "I-SPEC-EXEC-1"
_INVARIANT_RE = re.compile(r"^I-[A-Z0-9][A-Z0-9_-]*$")


def parse_query_intent(query: str) -> QueryIntent:
    """Map raw query string to QueryIntent.

    RESOLVE_EXACT: NAMESPACE:ID pattern (colon-separated, uppercase namespace).
    INVARIANT:     I-NNN pattern (starts with I-).
    otherwise:     SEARCH.

    MUST NOT infer EXPLAIN or TRACE from keyword heuristics (I-INTENT-HEURISTIC-1).
    EXPLAIN and TRACE are set exclusively by CLI routing, never by this function.
    """
    q = query.strip()
    if _NAMESPACE_ID_RE.match(q):
        return QueryIntent.RESOLVE_EXACT
    if _INVARIANT_RE.match(q):
        return QueryIntent.INVARIANT
    return QueryIntent.SEARCH


@dataclass(frozen=True)
class SearchCandidate:
    """Ranked candidate returned by SEARCH intent (I-SEARCH-CANDIDATE-1).

    fuzzy_score computed via BM25 over (label + ' ' + summary) corpus.
    Embedding-based similarity is forbidden (I-SEARCH-NO-EMBED-1).

    If SEARCH returns exactly one candidate, ContextEngine._build_selection()
    auto-upgrades intent to RESOLVE_EXACT and builds a full selection for that node.
    NavigationResponse.candidates still exposes the single candidate for transparency
    (I-SEARCH-AUTO-EXACT-1). This upgrade logic lives exclusively in ContextEngine.
    """

    node_id: str
    kind: str
    label: str
    summary: str
    fuzzy_score: float
