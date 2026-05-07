"""Tests for activate-phase --executed-by and plan_hash — T-2910.

Invariants covered: I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-DB-TEST-1
Spec ref: Spec_v29 §10 (тест 3: test_activate_phase_executed_by_llm,
          тест 4: test_activate_phase_plan_hash)
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.commands.activate_phase import (
    ActivatePhaseCommand,
    ActivatePhaseHandler,
    _compute_plan_hash,
    main,
)
from sdd.core.errors import MissingContext
from sdd.core.events import PhaseInitializedEvent


def _make_plan(tmp_path: Path, phase_id: int, content: str = "# Plan\n") -> Path:
    path = tmp_path / f"Plan_v{phase_id}.md"
    path.write_text(content)
    return path


def _make_taskset(tmp_path: Path, phase_id: int, task_count: int = 3) -> Path:
    lines = [f"# TaskSet_v{phase_id}\n\n"]
    for i in range(task_count):
        lines.append(f"## T-{phase_id:02d}{i:02d}: Task {i}\n")
        lines.append("Status: TODO\n\n")
    path = tmp_path / f"TaskSet_v{phase_id}.md"
    path.write_text("".join(lines))
    return path


# ---------------------------------------------------------------------------
# тест 3: test_activate_phase_executed_by_llm
# ---------------------------------------------------------------------------


def test_activate_phase_executed_by_llm(tmp_path: Path) -> None:
    """I-SESSION-ACTOR-1: actor='human' preserved; executed_by='llm' goes into payload only."""
    plan = _make_plan(tmp_path, 99, "# Plan v99\nContent\n")
    ts = _make_taskset(tmp_path, 99, 3)
    captured: list = []
    with (
        patch("sdd.commands.activate_phase.plan_file", return_value=plan),
        patch("sdd.commands.activate_phase.taskset_file", return_value=ts),
        patch("sdd.commands.registry.execute_and_project", lambda h, c, db_path: captured.append(c)),
    ):
        rc = main(["99", "--executed-by", "llm", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 0
    assert len(captured) == 1
    cmd = captured[0]
    # I-SESSION-ACTOR-1: actor field MUST be "human", not "llm"
    assert cmd.actor == "human", f"expected actor='human', got {cmd.actor!r}"
    assert cmd.executed_by == "llm"
    assert cmd.payload["executed_by"] == "llm"


def test_activate_phase_executed_by_llm_handler(tmp_db_path: str) -> None:
    """Handler propagates executed_by='llm' into PhaseInitializedEvent (I-SESSION-ACTOR-1)."""
    cmd = ActivatePhaseCommand(
        command_id=str(uuid.uuid4()),
        command_type="ActivatePhaseCommand",
        payload={"phase_id": 5, "tasks_total": 3, "executed_by": "llm", "plan_hash": "abc123deadbeef0"},
        phase_id=5,
        actor="human",
        tasks_total=3,
        plan_hash="abc123deadbeef0",
        executed_by="llm",
    )
    events = ActivatePhaseHandler(tmp_db_path).handle(cmd)
    initialized = next(e for e in events if isinstance(e, PhaseInitializedEvent))
    # actor stays "human" in the emitted event
    assert initialized.actor == "human"
    # executed_by is carried through
    assert initialized.executed_by == "llm"
    assert initialized.plan_hash == "abc123deadbeef0"


# ---------------------------------------------------------------------------
# тест 4: test_activate_phase_plan_hash
# ---------------------------------------------------------------------------


def test_activate_phase_plan_hash(tmp_path: Path) -> None:
    """I-SESSION-PLAN-HASH-1: plan_hash = sha256(Plan_vN.md)[:16]; set when --executed-by present."""
    content = "# Plan v99\nSome content\n"
    plan = _make_plan(tmp_path, 99, content)
    ts = _make_taskset(tmp_path, 99, 3)
    expected_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    captured: list = []
    with (
        patch("sdd.commands.activate_phase.plan_file", return_value=plan),
        patch("sdd.commands.activate_phase.taskset_file", return_value=ts),
        patch("sdd.commands.registry.execute_and_project", lambda h, c, db_path: captured.append(c)),
    ):
        rc = main(["99", "--executed-by", "llm", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 0
    cmd = captured[0]
    assert cmd.plan_hash == expected_hash, f"expected {expected_hash!r}, got {cmd.plan_hash!r}"
    assert len(cmd.plan_hash) == 16


def test_compute_plan_hash_algorithm(tmp_path: Path) -> None:
    """_compute_plan_hash returns sha256(content)[:16] — I-SESSION-PLAN-HASH-1."""
    content = "Hello, plan!\n"
    plan = _make_plan(tmp_path, 42, content)
    expected = hashlib.sha256(content.encode()).hexdigest()[:16]
    with patch("sdd.commands.activate_phase.plan_file", return_value=plan):
        result = _compute_plan_hash(42)
    assert result == expected
    assert len(result) == 16


def test_compute_plan_hash_missing_file(tmp_path: Path) -> None:
    """_compute_plan_hash raises MissingContext if Plan file absent — I-SESSION-PLAN-HASH-1."""
    missing = tmp_path / "Plan_v99.md"
    with patch("sdd.commands.activate_phase.plan_file", return_value=missing):
        with pytest.raises(MissingContext):
            _compute_plan_hash(99)


def test_plan_hash_empty_when_no_executed_by(tmp_path: Path) -> None:
    """plan_hash='' when --executed-by not provided — I-SESSION-PLAN-HASH-1 boundary."""
    ts = _make_taskset(tmp_path, 99, 3)
    captured: list = []
    with (
        patch("sdd.commands.activate_phase.taskset_file", return_value=ts),
        patch("sdd.commands.registry.execute_and_project", lambda h, c, db_path: captured.append(c)),
    ):
        rc = main(["99", "--db", str(tmp_path / "db.duckdb")])
    assert rc == 0
    cmd = captured[0]
    assert cmd.plan_hash == ""
    assert cmd.executed_by == ""
