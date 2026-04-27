"""Tests for BC-41-E: logical metadata in FrozenPhaseSnapshot and reducer — I-LOGICAL-META-1."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sdd.domain.state.reducer import FrozenPhaseSnapshot, reduce


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_type": event_type, "event_source": "runtime", "level": "L1", **payload}


def _phase_initialized(phase_id: int, **extra: object) -> dict[str, object]:
    return _runtime_l1(
        "PhaseInitialized",
        phase_id=phase_id,
        tasks_total=5,
        plan_version=phase_id,
        actor="human",
        timestamp="2026-01-01T00:00:00Z",
        **extra,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_frozen_snapshot_carries_logical_fields() -> None:
    """BC-41-E: FrozenPhaseSnapshot has logical_type and anchor_phase_id fields."""
    snap = FrozenPhaseSnapshot(
        phase_id=10,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
        tasks_total=5,
        tasks_completed=0,
        tasks_done_ids=(),
        plan_version=10,
        tasks_version=10,
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        plan_hash="",
        logical_type="patch",
        anchor_phase_id=9,
    )
    assert snap.logical_type == "patch"
    assert snap.anchor_phase_id == 9


def test_frozen_snapshot_logical_fields_default_to_none() -> None:
    """BC-41-E: logical_type and anchor_phase_id default to None."""
    snap = FrozenPhaseSnapshot(
        phase_id=1,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
        tasks_total=0,
        tasks_completed=0,
        tasks_done_ids=(),
        plan_version=1,
        tasks_version=1,
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
    )
    assert snap.logical_type is None
    assert snap.anchor_phase_id is None


def test_reducer_copies_logical_fields_blindly() -> None:
    """I-LOGICAL-META-1: reducer stores logical_type/anchor_phase_id in snapshot without interpretation."""
    events = [
        _phase_initialized(10, logical_type="backfill", anchor_phase_id=7),
    ]
    state = reduce(events)
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    snap = snap_map[10]
    assert snap.logical_type == "backfill"
    assert snap.anchor_phase_id == 7


def test_reducer_copies_logical_fields_patch() -> None:
    """I-LOGICAL-META-1: reducer stores patch type blindly."""
    events = [
        _phase_initialized(5, logical_type="patch", anchor_phase_id=3),
    ]
    state = reduce(events)
    snap = {s.phase_id: s for s in state.phases_snapshots}[5]
    assert snap.logical_type == "patch"
    assert snap.anchor_phase_id == 3


def test_reducer_copies_logical_fields_none() -> None:
    """I-LOGICAL-META-1: reducer stores None logical metadata blindly (no coercion)."""
    events = [
        _phase_initialized(2),
    ]
    state = reduce(events)
    snap = {s.phase_id: s for s in state.phases_snapshots}[2]
    assert snap.logical_type is None
    assert snap.anchor_phase_id is None


def test_logical_meta_not_referenced_in_guards() -> None:
    """I-LOGICAL-META-1: guards MUST NOT reference logical_type or anchor_phase_id.

    This is an AST/grep contract test. Zero matches expected in src/sdd/domain/guards/.
    """
    guards_dir = Path(__file__).parents[4] / "src" / "sdd" / "domain" / "guards"
    result = subprocess.run(
        ["grep", "-rn", r"logical_type\|anchor_phase_id", str(guards_dir)],
        capture_output=True,
        text=True,
    )
    matches = [line for line in result.stdout.splitlines() if "__pycache__" not in line]
    assert matches == [], (
        f"Guards MUST NOT reference logical_type or anchor_phase_id (I-LOGICAL-META-1).\n"
        f"Found {len(matches)} match(es):\n" + "\n".join(matches)
    )
