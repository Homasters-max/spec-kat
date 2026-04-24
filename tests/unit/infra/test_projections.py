"""Tests for infra/projections.py — rebuild_taskset and rebuild_state.

Invariants covered: I-ES-4, I-ES-5
Spec ref: Spec_v4 §9 Verification row (I-ES-5), T-407
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sdd.infra.event_log import sdd_append
from sdd.infra.projections import rebuild_state, rebuild_taskset


# ── fixtures ──────────────────────────────────────────────────────────────────

_TASKSET_ONE_TASK = """\
T-001: Test task

Status:               TODO
Spec ref:             Spec_v1 §1
Invariants:           I-EL-1
Inputs:               src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           basic test

---
"""

_TASKSET_TWO_TASKS = """\
T-001: First task

Status:               TODO
Spec ref:             Spec_v1 §1
Invariants:           I-EL-1
Inputs:               src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           first test

---

T-002: Second task

Status:               TODO
Spec ref:             Spec_v1 §1
Invariants:           I-EL-2
Inputs:               src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           second test

---
"""


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ── tests ─────────────────────────────────────────────────────────────────────


def test_rebuild_recovers_after_partial_crash(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """Crash recovery (I-ES-5): EventLog has TaskImplemented, projection is stale.
    rebuild_taskset must recover the correct DONE status from EventLog replay.
    """
    taskset_path = tmp_path / "TaskSet_v1.md"
    _write(taskset_path, _TASKSET_ONE_TASK)

    # Step 1 — handler appended event to EventLog (succeeded)
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    # Crash: rebuild_taskset was never called — projection is still stale
    assert "TODO" in taskset_path.read_text()

    # Recovery: rebuild reads EventLog and fixes the projection
    rebuild_taskset(tmp_db_path, str(taskset_path))

    recovered = taskset_path.read_text()
    assert "DONE" in recovered
    assert "TODO" not in recovered


def test_rebuild_taskset_marks_only_done_tasks(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """rebuild_taskset updates only the tasks present in EventLog done_ids; others stay TODO."""
    taskset_path = tmp_path / "TaskSet_v1.md"
    _write(taskset_path, _TASKSET_TWO_TASKS)

    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    rebuild_taskset(tmp_db_path, str(taskset_path))

    content = taskset_path.read_text()
    lines = content.splitlines()

    t001_status = next(
        (l for l in lines if l.startswith("Status:") and "T-001" not in l), None
    )

    # Find status lines per task by scanning in order
    task_statuses: dict[str, str] = {}
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("T-") and ":" in stripped:
            tid = stripped.split(":")[0]
            if tid.startswith("T-"):
                current = tid
        if current and stripped.startswith("Status:"):
            status = stripped.split("Status:")[-1].strip()
            task_statuses[current] = status

    assert task_statuses.get("T-001") == "DONE"
    assert task_statuses.get("T-002") == "TODO"


def test_rebuild_taskset_is_idempotent(tmp_path: Any, tmp_db_path: str) -> None:
    """Calling rebuild_taskset twice produces the same result (idempotent)."""
    taskset_path = tmp_path / "TaskSet_v1.md"
    _write(taskset_path, _TASKSET_ONE_TASK)

    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    rebuild_taskset(tmp_db_path, str(taskset_path))
    first_result = taskset_path.read_text()

    rebuild_taskset(tmp_db_path, str(taskset_path))
    second_result = taskset_path.read_text()

    assert first_result == second_result
    assert "DONE" in second_result


def test_rebuild_taskset_empty_eventlog_leaves_todo(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """rebuild_taskset with an empty EventLog leaves all tasks as TODO."""
    taskset_path = tmp_path / "TaskSet_v1.md"
    _write(taskset_path, _TASKSET_ONE_TASK)

    rebuild_taskset(tmp_db_path, str(taskset_path))

    assert "TODO" in taskset_path.read_text()


def test_rebuild_state_creates_state_from_eventlog(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """rebuild_state derives correct tasks_done_ids from EventLog replay (I-ES-4)."""
    from sdd.domain.state.yaml_state import read_state

    state_path = tmp_path / "State_index.yaml"

    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    rebuild_state(tmp_db_path, str(state_path))

    state = read_state(str(state_path))
    assert "T-001" in state.tasks_done_ids


# ---------------------------------------------------------------------------
# Phase 5 named tests (Spec_v5 §9 Verification row 8)
# I-PROJ-1, I-PROJ-2
# ---------------------------------------------------------------------------


def test_rebuild_state_derives_from_eventlog(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """rebuild_state derives state from EventLog replay when no YAML exists (I-PROJ-1).

    tasks_done_ids and tasks_completed are always EventLog-derived, not YAML-sourced.
    """
    from sdd.domain.state.yaml_state import read_state

    state_path = tmp_path / "State_index.yaml"

    sdd_append(
        "TaskImplemented",
        {"task_id": "T-501", "phase_id": 5},
        db_path=tmp_db_path,
        level="L1",
    )
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-502", "phase_id": 5},
        db_path=tmp_db_path,
        level="L1",
    )

    # No existing YAML — rebuild must use EventLog
    rebuild_state(tmp_db_path, str(state_path))

    state = read_state(str(state_path))
    assert "T-501" in state.tasks_done_ids
    assert "T-502" in state.tasks_done_ids
    assert state.tasks_completed == 2


def test_rebuild_state_no_yaml_copy(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """Derived fields (tasks_done_ids, tasks_completed) come from EventLog, not YAML.

    Even when a stale YAML exists with tasks_completed=0, rebuild_state re-derives
    from EventLog — the YAML's derived fields are not copied (I-PROJ-1).
    """
    from sdd.domain.state.reducer import SDDState
    from sdd.domain.state.yaml_state import read_state, write_state

    state_path = tmp_path / "State_index.yaml"

    # Write stale YAML with no tasks done
    stale_state = SDDState(
        phase_current=5,
        plan_version=5,
        tasks_version=5,
        tasks_total=2,
        tasks_completed=0,
        tasks_done_ids=(),
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )
    write_state(stale_state, str(state_path))

    # EventLog has a TaskImplemented event not reflected in the stale YAML
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-501", "phase_id": 5},
        db_path=tmp_db_path,
        level="L1",
    )

    rebuild_state(tmp_db_path, str(state_path))

    recovered = read_state(str(state_path))
    # Derived field must come from EventLog, not from stale YAML
    assert "T-501" in recovered.tasks_done_ids
    assert recovered.tasks_completed >= 1


def test_rebuild_after_phase_activated(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """After a PhaseActivatedEvent in EventLog, rebuild_state reflects phase_status='ACTIVE'
    (I-PROJ-1 — Phase 5 EventLog derivation)."""
    from sdd.domain.state.yaml_state import read_state

    state_path = tmp_path / "State_index.yaml"

    sdd_append(
        "PhaseActivated",
        {"phase_id": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    # No existing YAML — derived from EventLog
    rebuild_state(tmp_db_path, str(state_path))

    state = read_state(str(state_path))
    assert state.phase_status == "ACTIVE"


def test_rebuild_state_compat_mode_no_activation_events(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """When no PhaseActivated events exist (pre-Phase-5 EventLog), rebuild_state falls back
    to reading phase_status / plan_status from existing YAML (I-PROJ-2 compat mode)."""
    from sdd.domain.state.reducer import SDDState
    from sdd.domain.state.yaml_state import read_state, write_state

    state_path = tmp_path / "State_index.yaml"

    # YAML has human-managed ACTIVE status
    yaml_state = SDDState(
        phase_current=4,
        plan_version=4,
        tasks_version=4,
        tasks_total=5,
        tasks_completed=3,
        tasks_done_ids=("T-401", "T-402", "T-403"),
        invariants_status="PASS",
        tests_status="PASS",
        last_updated="2026-01-01T00:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )
    write_state(yaml_state, str(state_path))

    # EventLog has NO PhaseActivated events (pre-Phase-5)
    # Only a TaskImplemented from phase 4 work
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-404", "phase_id": 4},
        db_path=tmp_db_path,
        level="L1",
    )

    rebuild_state(tmp_db_path, str(state_path))

    recovered = read_state(str(state_path))
    # phase_status / plan_status must be preserved from YAML (compat fallback)
    assert recovered.phase_status == "ACTIVE"
    assert recovered.plan_status == "ACTIVE"
    # Derived field T-404 from EventLog is present
    assert "T-404" in recovered.tasks_done_ids


# ---------------------------------------------------------------------------
# get_current_state tests (I-PROJECTION-READ-1, I-STATE-ACCESS-LAYER-1) — T-1514
# ---------------------------------------------------------------------------


def test_get_current_state_no_compat_fallback(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """get_current_state uses pure replay — no YAML compat fallback (I-PROJECTION-READ-1)."""
    from sdd.infra.projections import get_current_state

    # Empty EventLog → default PLANNED state; no YAML present to fall back to
    state = get_current_state(tmp_db_path)
    assert state.phase_status == "PLANNED"
    assert state.tasks_completed == 0


def test_get_current_state_is_deterministic(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """get_current_state returns identical result on repeated calls (deterministic)."""
    from sdd.infra.projections import get_current_state

    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    state1 = get_current_state(tmp_db_path)
    state2 = get_current_state(tmp_db_path)
    assert state1 == state2


def test_get_current_state_partial_legacy(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """get_current_state handles legacy PhaseActivated events correctly."""
    from sdd.infra.projections import get_current_state

    sdd_append(
        "PhaseActivated",
        {"phase_id": 5, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )

    state = get_current_state(tmp_db_path)
    # PhaseActivated sets phase_status ACTIVE in reducer (I-REDUCER-LEGACY-1)
    assert state.phase_status == "ACTIVE"


def test_get_current_state_full_replay_from_seq_zero(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """get_current_state replays from seq=0 — all events included (I-PROJECTION-READ-1)."""
    from sdd.infra.projections import get_current_state

    for i in range(1, 4):
        sdd_append(
            "TaskImplemented",
            {"task_id": f"T-00{i}", "phase_id": 1},
            db_path=tmp_db_path,
            level="L1",
        )

    state = get_current_state(tmp_db_path)
    assert state.tasks_completed == 3
    assert "T-001" in state.tasks_done_ids
    assert "T-002" in state.tasks_done_ids
    assert "T-003" in state.tasks_done_ids


def test_rebuild_state_recovers_after_partial_crash(
    tmp_path: Any, tmp_db_path: str
) -> None:
    """rebuild_state crash recovery (I-ES-5): stale State_index gets corrected from EventLog."""
    from sdd.domain.state.reducer import SDDState
    from sdd.domain.state.yaml_state import read_state, write_state

    state_path = tmp_path / "State_index.yaml"

    # Write a stale state: tasks_completed=0, done_ids=[]
    stale_state = SDDState(
        phase_current=1,
        plan_version=1,
        tasks_version=1,
        tasks_total=1,
        tasks_completed=0,
        tasks_done_ids=[],
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )
    write_state(stale_state, str(state_path))

    # EventLog has the TaskImplemented event (handler succeeded before crash)
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=tmp_db_path,
        level="L1",
    )

    # Verify stale state doesn't reflect the event yet
    pre_recovery = read_state(str(state_path))
    assert "T-001" not in pre_recovery.tasks_done_ids

    # Recovery
    rebuild_state(tmp_db_path, str(state_path))

    recovered = read_state(str(state_path))
    assert "T-001" in recovered.tasks_done_ids
