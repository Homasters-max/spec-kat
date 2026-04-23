"""BC-CONTEXT public API — re-exports (Spec_v2 §2)."""
from sdd.context.build_context import (
    EFFECTIVE_BUDGET,
    TOKEN_BUDGET,
    ContextDepth,
    build_context,
)

__all__ = ["build_context", "ContextDepth", "TOKEN_BUDGET", "EFFECTIVE_BUDGET"]
