"""Tests for show_state — I-SHOW-STATE-1 (BC-41-C, Phase 41).

Invariants: I-SHOW-STATE-1
Acceptance: test_show_state_latest_completed_field PASS; test_show_state_context_ne_latest PASS
"""
from __future__ import annotations

from sdd.commands.show_state import _latest_completed, _parse_snapshots, _render


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    *,
    phase_current: int = 41,
    plan_version: int = 41,
    tasks_version: int = 41,
    tasks_total: int = 5,
    tasks_completed: int = 3,
    done_ids: list[str] | None = None,
    snapshots: list[dict] | None = None,
) -> dict:
    done = done_ids if done_ids is not None else [f"T-{phase_current}0{i}" for i in range(1, tasks_completed + 1)]
    return {
        "phase": {"current": phase_current, "status": "ACTIVE"},
        "plan": {"version": plan_version, "status": "ACTIVE"},
        "tasks": {
            "version": tasks_version,
            "total": tasks_total,
            "completed": tasks_completed,
            "done_ids": done,
        },
        "invariants": {"status": "UNKNOWN"},
        "tests": {"status": "UNKNOWN"},
        "phases_snapshots": snapshots or [],
    }


def _snapshot(phase_id: int, status: str) -> dict:
    return {
        "phase_id": phase_id,
        "phase_status": status,
        "plan_status": "COMPLETE" if status == "COMPLETE" else "ACTIVE",
        "tasks_total": 5,
        "tasks_completed": 5 if status == "COMPLETE" else 0,
        "tasks_done_ids": [],
        "plan_version": phase_id,
        "tasks_version": phase_id,
        "invariants_status": "PASS" if status == "COMPLETE" else "UNKNOWN",
        "tests_status": "PASS" if status == "COMPLETE" else "UNKNOWN",
    }


# ---------------------------------------------------------------------------
# test_show_state_latest_completed_field
# ---------------------------------------------------------------------------

def test_show_state_latest_completed_field() -> None:
    """phase.latest_completed MUST appear in output, derived from phases_snapshots.

    I-SHOW-STATE-1: never inferred from flat phase_current alone.
    """
    snapshots = [
        _snapshot(30, "COMPLETE"),
        _snapshot(31, "COMPLETE"),
        _snapshot(41, "ACTIVE"),
    ]
    state = _make_state(
        phase_current=41,
        plan_version=41,
        tasks_version=41,
        snapshots=snapshots,
    )

    output = _render(state)

    assert "phase.latest_completed" in output
    # max COMPLETE phase_id from snapshots is 31
    parsed = _parse_snapshots(state)
    assert _latest_completed(parsed) == 31
    assert "| phase.latest_completed | 31 |" in output


# ---------------------------------------------------------------------------
# test_show_state_context_ne_latest
# ---------------------------------------------------------------------------

def test_show_state_context_ne_latest() -> None:
    """When phase.current != latest_completed, both values MUST be explicitly shown.

    I-SHOW-STATE-1: show-state output must carry both fields so context ≠ latest is visible.
    Scenario: user navigated to phase 32 (switch-phase 32) but phases 33 and 34 are COMPLETE.
    """
    snapshots = [
        _snapshot(32, "ACTIVE"),
        _snapshot(33, "COMPLETE"),
        _snapshot(34, "COMPLETE"),
    ]
    state = _make_state(
        phase_current=32,
        plan_version=32,
        tasks_version=32,
        tasks_total=5,
        tasks_completed=3,
        done_ids=["T-3201", "T-3202", "T-3203"],
        snapshots=snapshots,
    )

    output = _render(state)

    # phase.current (context) = 32
    assert "| phase.current | 32 |" in output
    # phase.latest_completed = 34 (max of COMPLETE snapshots)
    assert "| phase.latest_completed | 34 |" in output
    # The two values must differ — this is the core of I-SHOW-STATE-1
    parsed = _parse_snapshots(state)
    assert _latest_completed(parsed) == 34
    assert state["phase"]["current"] != _latest_completed(parsed)
