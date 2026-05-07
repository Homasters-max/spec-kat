"""Tests for ActivatePhaseCommand + ActivatePhaseHandler.

Invariants covered: I-ACT-1, I-HANDLER-BATCH-PURE-1, I-PHASE-EVENT-PAIR-1, I-IDEM-SCHEMA-1,
                    I-PHASE-INIT-2, I-PHASE-INIT-3
Spec ref: Spec_v15 §2 BC-4; Phase_v15.5 §4; T-1514, T-1723, T-2303 acceptance
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.commands.activate_phase import ActivatePhaseCommand, ActivatePhaseHandler, _resolve_tasks_total
from sdd.core.errors import Inconsistency, InvalidActor, MissingContext
from sdd.core.events import PhaseInitializedEvent, PhaseStartedEvent, compute_command_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd(
    command_id: str | None = None,
    phase_id: int = 5,
    actor: str = "human",
    tasks_total: int = 3,
) -> ActivatePhaseCommand:
    return ActivatePhaseCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ActivatePhaseCommand",
        payload={"phase_id": phase_id, "tasks_total": tasks_total},
        phase_id=phase_id,
        actor=actor,
        tasks_total=tasks_total,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_activate_phase_emits_atomic_pair(tmp_db_path: str) -> None:
    """ActivatePhaseHandler emits exactly [PhaseStarted, PhaseInitialized] (I-PHASE-EVENT-PAIR-1, I-ACT-1)."""
    cmd = _cmd(actor="human", tasks_total=7)
    result = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    assert len(result) == 2

    started = result[0]
    assert isinstance(started, PhaseStartedEvent)
    assert started.event_type == "PhaseStarted"
    assert started.phase_id == 5
    assert started.actor == "human"

    initialized = result[1]
    assert isinstance(initialized, PhaseInitializedEvent)
    assert initialized.event_type == "PhaseInitialized"
    assert initialized.phase_id == 5
    assert initialized.tasks_total == 7
    assert initialized.plan_version == 5

    # pair consistency (I-PHASE-EVENT-PAIR-1)
    assert started.phase_id == initialized.phase_id


def test_llm_actor_rejected(tmp_db_path: str) -> None:
    """actor='llm' is rejected with InvalidActor — I-ACT-1 (phase activation is human-only)."""
    cmd = _cmd(actor="llm")
    with pytest.raises(InvalidActor):
        ActivatePhaseHandler(tmp_db_path).handle(cmd)


def test_invalid_actor_raises(tmp_db_path: str) -> None:
    """Any non-'human' actor is rejected with InvalidActor — I-ACT-1."""
    cmd = _cmd(actor="robot")
    with pytest.raises(InvalidActor):
        ActivatePhaseHandler(tmp_db_path).handle(cmd)


# ---------------------------------------------------------------------------
# T-1723: Idempotency fix — I-IDEM-SCHEMA-1
# ---------------------------------------------------------------------------


def test_command_id_differs_for_different_phase(tmp_db_path: str) -> None:
    """Different phase_id → different command_id (I-IDEM-SCHEMA-1)."""
    cmd_a = _cmd(phase_id=5, tasks_total=10)
    cmd_b = _cmd(phase_id=6, tasks_total=10)
    assert compute_command_id(cmd_a) != compute_command_id(cmd_b)


def test_command_id_differs_for_different_tasks_total(tmp_db_path: str) -> None:
    """Different tasks_total → different command_id (I-IDEM-SCHEMA-1)."""
    cmd_a = _cmd(phase_id=5, tasks_total=10)
    cmd_b = _cmd(phase_id=5, tasks_total=21)
    assert compute_command_id(cmd_a) != compute_command_id(cmd_b)


def test_command_id_stable_for_same_phase_and_tasks(tmp_db_path: str) -> None:
    """Same (phase_id, tasks_total) → identical command_id across two instances (idempotent)."""
    cmd_a = _cmd(phase_id=7, tasks_total=15)
    cmd_b = _cmd(phase_id=7, tasks_total=15)
    assert compute_command_id(cmd_a) == compute_command_id(cmd_b)


def test_payload_contains_phase_id_and_tasks_total(tmp_db_path: str) -> None:
    """ActivatePhaseCommand.payload must contain phase_id and tasks_total (I-IDEM-SCHEMA-1)."""
    cmd = _cmd(phase_id=17, tasks_total=22)
    assert cmd.payload["phase_id"] == 17
    assert cmd.payload["tasks_total"] == 22


# ---------------------------------------------------------------------------
# T-2303: _resolve_tasks_total unit tests — I-PHASE-INIT-2, I-PHASE-INIT-3
# ---------------------------------------------------------------------------


def _make_taskset(tmp_path: Path, phase_id: int, task_count: int) -> Path:
    lines: list[str] = [f"# TaskSet_v{phase_id}\n\n"]
    for i in range(task_count):
        lines.append(f"## T-{phase_id:02d}{i:02d}: Task {i}\n")
        lines.append("Status: TODO\n\n")
    path = tmp_path / f"TaskSet_v{phase_id}.md"
    path.write_text("".join(lines))
    return path


def test_resolve_tasks_total_autodetect(tmp_path: Path) -> None:
    """arg=None → auto-detect count from TaskSet (I-PHASE-INIT-2)."""
    ts = _make_taskset(tmp_path, 99, 5)
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts):
        assert _resolve_tasks_total(99, None) == 5


def test_resolve_tasks_total_explicit_match(tmp_path: Path) -> None:
    """arg == actual count → return count unchanged (I-PHASE-INIT-2)."""
    ts = _make_taskset(tmp_path, 99, 5)
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts):
        assert _resolve_tasks_total(99, 5) == 5


def test_resolve_tasks_total_mismatch(tmp_path: Path) -> None:
    """arg != actual count → Inconsistency (I-PHASE-INIT-2)."""
    ts = _make_taskset(tmp_path, 99, 5)
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts):
        with pytest.raises(Inconsistency):
            _resolve_tasks_total(99, 3)


def test_resolve_tasks_total_missing_file(tmp_path: Path) -> None:
    """TaskSet file absent → MissingContext (I-PHASE-INIT-3)."""
    missing = tmp_path / "TaskSet_v99.md"
    with patch("sdd.commands.activate_phase.taskset_file", return_value=missing):
        with pytest.raises(MissingContext):
            _resolve_tasks_total(99, None)


def test_resolve_tasks_total_empty_taskset(tmp_path: Path) -> None:
    """TaskSet file exists but has no T-NNN headers → MissingContext (I-PHASE-INIT-3)."""
    empty = tmp_path / "TaskSet_v99.md"
    empty.write_text("# TaskSet_v99\n\nNo tasks defined here.\n")
    with patch("sdd.commands.activate_phase.taskset_file", return_value=empty):
        with pytest.raises(MissingContext):
            _resolve_tasks_total(99, None)


# ---------------------------------------------------------------------------
# T-2304: main() integration tests — I-PHASE-INIT-2, I-PHASE-INIT-3, BC-23-2
# ---------------------------------------------------------------------------


from sdd.commands.activate_phase import main  # noqa: E402


def test_main_autodetect_happy_path(tmp_path: Path) -> None:
    """No --tasks: auto-detect from TaskSet → exit 0, tasks_total == TaskSet size (I-PHASE-INIT-2/3)."""
    ts = _make_taskset(tmp_path, 99, 4)
    captured: list = []
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts), \
         patch("sdd.commands.registry.execute_and_project", lambda h, c, db_path: captured.append(c)):
        rc = main(["99", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 0
    assert len(captured) == 1
    assert captured[0].tasks_total == 4


def test_main_missing_taskset(tmp_path: Path) -> None:
    """TaskSet absent → exit 1, no event written (I-PHASE-INIT-3)."""
    missing = tmp_path / "TaskSet_v99.md"
    with patch("sdd.commands.activate_phase.taskset_file", return_value=missing):
        rc = main(["99", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 1


def test_main_mismatch(tmp_path: Path) -> None:
    """--tasks N where N != TaskSet count → exit 1, no event written (I-PHASE-INIT-2)."""
    ts = _make_taskset(tmp_path, 99, 4)
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts):
        rc = main(["99", "--tasks", "9", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 1


def test_main_deprecated_tasks_arg(tmp_path: Path) -> None:
    """--tasks N (matching) → exit 0 + DeprecationWarning emitted (BC-23-2)."""
    ts = _make_taskset(tmp_path, 99, 4)
    with patch("sdd.commands.activate_phase.taskset_file", return_value=ts), \
         patch("sdd.commands.registry.execute_and_project", lambda h, c, db_path: None), \
         pytest.warns(DeprecationWarning, match="--tasks is deprecated"):
        rc = main(["99", "--tasks", "4", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 0
