"""Tests for init_state — Spec_v2 §9 row 4 — I-ST-5, I-EL-9."""
from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sdd.core.errors import InvalidState
from sdd.domain.state.init_state import init_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(task_id: str, status: str = "TODO") -> Any:
    from sdd.domain.tasks.parser import Task
    return Task(
        task_id=task_id,
        title=task_id,
        status=status,
        spec_section="§9",
        inputs=(),
        outputs=(),
        checks=(),
        spec_refs=(),
        produces_invariants=(),
        requires_invariants=(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_init_state_creates_yaml(tmp_path):
    """init_state calls write_state when state_path does not exist (I-ST-5)."""
    state_path = str(tmp_path / "State_index.yaml")
    tasks = [_task("T-101"), _task("T-102")]

    emit = MagicMock()

    with (
        patch("sdd.domain.state.init_state.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.init_state.write_state") as mock_write,
    ):
        result = init_state(
            phase_id=1,
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
        )

    mock_write.assert_called_once()
    written_state, written_path = mock_write.call_args[0]
    assert written_path == state_path
    assert written_state.phase_current == 1
    assert result.phase_current == 1


def test_init_state_raises_if_exists(tmp_path):
    """init_state raises InvalidState when state_path already exists (I-ST-5)."""
    state_path = tmp_path / "State_index.yaml"
    state_path.write_text("exists")

    with pytest.raises(InvalidState, match="already exists"):
        init_state(
            phase_id=1,
            taskset_path="fake.md",
            state_path=str(state_path),
            emit=MagicMock(),
        )


def test_init_state_counts_match_taskset(tmp_path):
    """tasks_total, tasks_completed, and tasks_done_ids reflect the parsed TaskSet (I-ST-5)."""
    state_path = str(tmp_path / "State_index.yaml")
    tasks = [_task("T-101", "DONE"), _task("T-102"), _task("T-103")]

    emit = MagicMock()

    with (
        patch("sdd.domain.state.init_state.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.init_state.write_state"),
    ):
        result = init_state(
            phase_id=1,
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
        )

    assert result.tasks_total == 3
    assert result.tasks_completed == 1
    assert result.tasks_done_ids == ("T-101",)


def test_init_state_emits_phase_initialized_then_derivation(tmp_path):
    """emit is called exactly twice: PhaseInitializedEvent then StateDerivationCompletedEvent(derived_from="initial")."""
    state_path = str(tmp_path / "State_index.yaml")
    tasks = [_task("T-101")]

    emitted: list[Any] = []
    emit = MagicMock(side_effect=lambda e: emitted.append(e))

    with (
        patch("sdd.domain.state.init_state.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.init_state.write_state"),
    ):
        init_state(
            phase_id=2,
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
        )

    assert emit.call_count == 2
    assert emitted[0].event_type == "PhaseInitialized"
    assert emitted[1].event_type == "StateDerivationCompleted"
    assert emitted[1].derived_from == "initial"


def test_init_state_no_db_calls():
    """init_state.py must not contain any direct duckdb.connect( call (I-EL-9)."""
    import sdd.domain.state.init_state as init_module

    source = inspect.getsource(init_module)
    assert "duckdb.connect(" not in source
