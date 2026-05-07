"""Deprecated: sdd.context.build_context moved to sdd.context_legacy.build_context.

I-GRAPH-FS-ROOT-1: After migration_complete() == True, direct FS reads in this
module violate the invariant.  This shim exists solely for backward compatibility
with external consumers that import from the old path.

Internal SDD code MUST NOT import from this module (I-CTX-MIGRATION-1).
"""
import warnings

warnings.warn(
    "sdd.context.build_context is deprecated; "
    "import from sdd.context_legacy.build_context instead",
    DeprecationWarning,
    stacklevel=2,
)

from sdd.context_legacy.build_context import (  # noqa: E402, F401
    EFFECTIVE_BUDGET,
    TOKEN_BUDGET,
    ContextDepth,
    build_context,
    main,
)

__all__ = ["build_context", "ContextDepth", "TOKEN_BUDGET", "EFFECTIVE_BUDGET", "main"]
