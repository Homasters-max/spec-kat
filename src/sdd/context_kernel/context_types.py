"""Core data types for the context_kernel bounded context (BC-36)."""
from __future__ import annotations

from dataclasses import dataclass

from sdd.context_kernel.intent import QueryIntent, SearchCandidate


@dataclass(frozen=True)
class Context:
    """Resolved context payload produced by ContextEngine.

    exhausted=True  — all matching candidates have been surfaced;
                      caller MUST NOT request further results for this query.
    exhausted=False — result set may be partial; caller MAY request more.
    """

    intent: QueryIntent
    candidates: tuple[SearchCandidate, ...]
    exhausted: bool

    @classmethod
    def empty(cls, intent: QueryIntent) -> Context:
        """Exhausted empty context — no candidates found."""
        return cls(intent=intent, candidates=(), exhausted=True)
