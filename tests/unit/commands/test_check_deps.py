"""Tests for _check_deps guard-lite (T-3212, BC-32-6, I-CMD-IDEM-2).

Acceptance: sdd complete T-NNN с невыполненной dep завершается exit 1 с error_type=DependencyNotMet.
"""
from __future__ import annotations

import pytest

from sdd.commands.complete import _check_deps
from sdd.core.errors import DependencyNotMet
from sdd.domain.guards.context import DAG


def test_check_deps_no_deps_allows():
    """Task with no declared dependencies is always allowed."""
    _check_deps("T-3212", frozenset(), DAG(deps={}))


def test_check_deps_all_deps_done_allows():
    """All dependencies DONE → no exception raised."""
    dag = DAG(deps={"T-3212": frozenset(["T-3211"])})
    _check_deps("T-3212", frozenset(["T-3211"]), dag)


def test_check_deps_missing_dep_raises():
    """Undone dependency → DependencyNotMet with blocking task in message."""
    dag = DAG(deps={"T-3212": frozenset(["T-3211"])})
    with pytest.raises(DependencyNotMet) as exc_info:
        _check_deps("T-3212", frozenset(), dag)
    assert "T-3211" in str(exc_info.value)


def test_check_deps_error_type_is_dependency_not_met():
    """Error type name matches acceptance criterion (error_type=DependencyNotMet)."""
    dag = DAG(deps={"T-3212": frozenset(["T-3211"])})
    with pytest.raises(DependencyNotMet) as exc_info:
        _check_deps("T-3212", frozenset(), dag)
    assert type(exc_info.value).__name__ == "DependencyNotMet"


def test_check_deps_partial_done_blocks():
    """Only some deps done → still raises for undone ones."""
    dag = DAG(deps={"T-3212": frozenset(["T-3210", "T-3211"])})
    with pytest.raises(DependencyNotMet) as exc_info:
        _check_deps("T-3212", frozenset(["T-3210"]), dag)
    assert "T-3211" in str(exc_info.value)
    assert "T-3210" not in str(exc_info.value)
