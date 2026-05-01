"""Import-coverage tests for re-export / shim modules with no testable logic."""
from __future__ import annotations

import importlib
import warnings


def test_policy_types_exports():
    from sdd.policy.types import (
        BFS_OVERSELECT_FACTOR,
        MIN_CONTEXT_SIZE,
        Budget,
        NavigationPolicy,
        QueryIntent,
        RagMode,
    )
    assert QueryIntent is not None
    assert RagMode is not None
    assert Budget is not None
    assert NavigationPolicy is not None
    assert isinstance(BFS_OVERSELECT_FACTOR, (int, float))
    assert isinstance(MIN_CONTEXT_SIZE, int)


def test_tool_definitions_non_empty():
    from sdd.graph_navigation.tool_definitions import TOOL_DEFINITIONS
    assert isinstance(TOOL_DEFINITIONS, list)
    assert len(TOOL_DEFINITIONS) > 0
    assert all("name" in d for d in TOOL_DEFINITIONS)


def test_build_context_deprecated_import():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import importlib
        import sys
        # Remove from cache so the warning fires again
        for mod in list(sys.modules):
            if "sdd.context.build_context" in mod:
                del sys.modules[mod]
        import sdd.context.build_context  # noqa: F401
    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) >= 1
    assert "deprecated" in str(dep_warnings[0].message).lower()


def test_build_context_exports_build_context():
    import sdd.context.build_context as m
    assert hasattr(m, "build_context")
    assert hasattr(m, "ContextDepth")
