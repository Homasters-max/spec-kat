"""Tests for PhaseOrder — BC-41-F, I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1."""
from __future__ import annotations

import logging

import pytest

from sdd.domain.phase_order import PhaseOrder, PhaseOrderEntry
from sdd.domain.state.reducer import FrozenPhaseSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snap(
    phase_id: int,
    logical_type: str | None = None,
    anchor_phase_id: int | None = None,
) -> FrozenPhaseSnapshot:
    return FrozenPhaseSnapshot(
        phase_id=phase_id,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
        tasks_total=5,
        tasks_completed=0,
        tasks_done_ids=(),
        plan_version=phase_id,
        tasks_version=phase_id,
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        plan_hash="",
        logical_type=logical_type,
        anchor_phase_id=anchor_phase_id,
    )


def _ids(entries: list[PhaseOrderEntry]) -> list[int]:
    return [e.phase_id for e in entries]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_phase_order_sort_none_is_execution_order() -> None:
    """I-PHASE-ORDER-EXEC-1: phases with logical_type=None sorted by phase_id."""
    snaps = [_snap(7), _snap(3), _snap(5)]
    result = PhaseOrder.sort(snaps)
    assert _ids(result) == [3, 5, 7]


def test_phase_order_sort_patch_after_anchor() -> None:
    """I-LOGICAL-META-1: patch phase appears immediately after its anchor."""
    snaps = [_snap(10), _snap(11, logical_type="patch", anchor_phase_id=10)]
    result = PhaseOrder.sort(snaps)
    assert _ids(result) == [10, 11]


def test_phase_order_sort_backfill_before_anchor() -> None:
    """I-LOGICAL-META-1: backfill phase appears immediately before its anchor."""
    snaps = [_snap(10), _snap(11, logical_type="backfill", anchor_phase_id=10)]
    result = PhaseOrder.sort(snaps)
    assert _ids(result) == [11, 10]


def test_phase_order_sort_mixed_types() -> None:
    """patch and backfill both anchored to same phase sort correctly around anchor."""
    snaps = [
        _snap(10),
        _snap(11, logical_type="patch", anchor_phase_id=10),
        _snap(9, logical_type="backfill", anchor_phase_id=10),
    ]
    result = PhaseOrder.sort(snaps)
    # backfill(9) at (10,0,9), normal(10) at (10,1,10), patch(11) at (10,2,11)
    assert _ids(result) == [9, 10, 11]


def test_phase_order_unknown_anchor_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """I-LOGICAL-META-1: anchor_phase_id not in snapshots → fallback to execution order + warning."""
    snaps = [_snap(10), _snap(11, logical_type="patch", anchor_phase_id=99)]
    with caplog.at_level(logging.WARNING, logger="root"):
        result = PhaseOrder.sort(snaps)
    assert _ids(result) == [10, 11]
    assert any("anchor_phase_id" in r.message for r in caplog.records)


def test_phase_order_unknown_logical_type_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """I-LOGICAL-META-1: unknown logical_type string → fallback to execution order + warning."""
    snaps = [_snap(10), _snap(5, logical_type="invalid_type")]
    with caplog.at_level(logging.WARNING, logger="root"):
        result = PhaseOrder.sort(snaps)
    assert _ids(result) == [5, 10]
    assert any("unknown logical_type" in r.message for r in caplog.records)


def test_phase_order_entries_carry_metadata() -> None:
    """PhaseOrderEntry preserves logical_type and anchor_phase_id from snapshot."""
    snaps = [_snap(10, logical_type="patch", anchor_phase_id=9), _snap(9)]
    result = PhaseOrder.sort(snaps)
    entry_10 = next(e for e in result if e.phase_id == 10)
    assert entry_10.logical_type == "patch"
    assert entry_10.anchor_phase_id == 9


def test_phase_order_sort_empty() -> None:
    assert PhaseOrder.sort([]) == []


def test_phase_order_sort_single_phase() -> None:
    snaps = [_snap(5)]
    result = PhaseOrder.sort(snaps)
    assert _ids(result) == [5]
