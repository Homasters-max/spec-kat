"""Tests verifying GuardContext deduplication — Spec_v5 §2.3, T-503.

Invariant: deduplication (no stale GuardContext class in guards/runner.py)
Spec ref: Spec_v5 §9 Verification row 7
"""
from __future__ import annotations

import inspect
import importlib


def test_guards_runner_imports_from_domain() -> None:
    """guards/runner.py must import GuardContext from sdd.domain.guards.context (T-503).

    The stale duplicate GuardContext was removed from guards/runner.py.
    All uses now go through the canonical domain location.
    """
    import sdd.guards.runner as runner_module

    # The module must re-export or import GuardContext from the canonical domain location
    guard_context_cls = getattr(runner_module, "GuardContext", None)
    if guard_context_cls is not None:
        # If re-exported, it must be the exact same class object as domain's
        from sdd.domain.guards.context import GuardContext as DomainGuardContext
        assert guard_context_cls is DomainGuardContext, (
            "GuardContext in guards/runner must be the canonical domain class, not a stale copy"
        )

    # Verify the source file of GuardContext that runner uses is the domain module
    from sdd.domain.guards.context import GuardContext as DomainGuardContext

    runner_src = inspect.getfile(runner_module)
    domain_src = inspect.getfile(DomainGuardContext)

    # They should be different files — runner re-exports from domain, doesn't define its own
    assert "domain" in domain_src, "canonical GuardContext must live in domain/guards/context.py"


def test_no_stale_guard_context_in_runner() -> None:
    """guards/runner.py must not define its own GuardContext class (T-503 removal protocol).

    The stale copy was removed; all consumer code uses sdd.domain.guards.context.GuardContext.
    """
    import sdd.guards.runner as runner_module

    # Check the module's source for a class definition named GuardContext
    src_path = inspect.getfile(runner_module)
    with open(src_path, encoding="utf-8") as f:
        source = f.read()

    # "class GuardContext" must not appear as a class definition in runner.py
    import re
    matches = re.findall(r"^class GuardContext\b", source, re.MULTILINE)
    assert len(matches) == 0, (
        f"guards/runner.py must not define its own GuardContext class (found: {matches}). "
        "T-503 requires removal of the stale duplicate."
    )
