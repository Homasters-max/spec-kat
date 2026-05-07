"""Tests for _check_anchor_guard in activate_phase.py.

Invariants: I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2
"""
from __future__ import annotations

import pytest

from sdd.commands.activate_phase import _check_anchor_guard
from sdd.core.errors import Inconsistency


def test_activate_phase_anchor_not_in_phases_known_denied() -> None:
    """anchor_phase_id not in phases_known must raise Inconsistency.

    I-LOGICAL-ANCHOR-1: anchor_phase_id ∉ phases_known → reject.
    """
    with pytest.raises(Inconsistency, match="I-LOGICAL-ANCHOR-1"):
        _check_anchor_guard(
            logical_type="backfill",
            anchor_phase_id=99,
            phases_known=frozenset({1, 2, 3}),
        )


def test_activate_phase_anchor_consistency_violated() -> None:
    """Providing only one of --logical-type / --anchor must raise Inconsistency.

    I-LOGICAL-ANCHOR-2: logical_type and anchor_phase_id must be provided together.
    """
    with pytest.raises(Inconsistency, match="I-LOGICAL-ANCHOR-2"):
        _check_anchor_guard(
            logical_type="patch",
            anchor_phase_id=None,
            phases_known=frozenset({1, 2}),
        )

    with pytest.raises(Inconsistency, match="I-LOGICAL-ANCHOR-2"):
        _check_anchor_guard(
            logical_type=None,
            anchor_phase_id=2,
            phases_known=frozenset({1, 2}),
        )


def test_activate_phase_anchor_both_none_skipped() -> None:
    """Both None must pass without error — backward compat."""
    _check_anchor_guard(
        logical_type=None,
        anchor_phase_id=None,
        phases_known=frozenset({1, 2}),
    )


def test_activate_phase_anchor_valid_passes() -> None:
    """Both provided and anchor_phase_id ∈ phases_known must pass."""
    _check_anchor_guard(
        logical_type="backfill",
        anchor_phase_id=2,
        phases_known=frozenset({1, 2, 3}),
    )
