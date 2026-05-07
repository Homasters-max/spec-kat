"""Tests for yaml_state — read_state, write_state, atomic write crash safety.

Invariants: I-LOGIC-COVER-2
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.domain.state.reducer import SDDState
from sdd.domain.state.yaml_state import read_state, write_state


def _make_state(
    phase_current: int = 16,
    tasks_total: int = 10,
    tasks_completed: int = 3,
) -> SDDState:
    return SDDState(
        phase_current=phase_current,
        plan_version=phase_current,
        tasks_version=phase_current,
        tasks_total=tasks_total,
        tasks_completed=tasks_completed,
        tasks_done_ids=tuple(f"T-{phase_current}0{i}" for i in range(1, tasks_completed + 1)),
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-04-23T00:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )


class TestAtomicWriteCrash:
    """write_state must not corrupt the original file when atomic_write raises mid-write."""

    def test_atomic_write_crash(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "State_index.yaml")

        initial_state = _make_state(tasks_completed=3)
        write_state(initial_state, state_file)

        with open(state_file, encoding="utf-8") as f:
            original_content = f.read()

        updated_state = _make_state(tasks_completed=5)
        with patch("sdd.infra.audit.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                write_state(updated_state, state_file)

        with open(state_file, encoding="utf-8") as f:
            post_crash_content = f.read()

        assert post_crash_content == original_content, (
            "write_state crash must not corrupt the original file"
        )

    def test_atomic_write_crash_preserves_readability(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "State_index.yaml")

        initial_state = _make_state(tasks_completed=2)
        write_state(initial_state, state_file)

        updated_state = _make_state(tasks_completed=7)
        with patch("sdd.infra.audit.os.replace", side_effect=OSError("simulated crash")):
            with pytest.raises(OSError):
                write_state(updated_state, state_file)

        recovered = read_state(state_file)
        assert recovered.tasks_completed == 2
        assert recovered.phase_current == initial_state.phase_current

    def test_atomic_write_crash_no_temp_file_leak(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "State_index.yaml")

        initial_state = _make_state()
        write_state(initial_state, state_file)

        with patch("sdd.infra.audit.os.replace", side_effect=OSError("crash")):
            with pytest.raises(OSError):
                write_state(_make_state(tasks_completed=5), state_file)

        dir_contents = os.listdir(str(tmp_path))
        assert dir_contents == ["State_index.yaml"], (
            f"Unexpected files after crash: {dir_contents}"
        )


class TestWriteStateRoundtrip:
    """write_state → read_state round-trip correctness."""

    def test_roundtrip_basic(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "State_index.yaml")
        state = _make_state()
        write_state(state, state_file)
        recovered = read_state(state_file)

        assert recovered.phase_current == state.phase_current
        assert recovered.tasks_completed == state.tasks_completed
        assert recovered.tasks_done_ids == state.tasks_done_ids
        assert recovered.invariants_status == state.invariants_status
        assert recovered.phase_status == state.phase_status
        assert recovered.plan_status == state.plan_status

    def test_roundtrip_state_hash_verified(self, tmp_path: Path) -> None:
        state_file = str(tmp_path / "State_index.yaml")
        state = _make_state()
        write_state(state, state_file)
        recovered = read_state(state_file)
        assert recovered.state_hash == state.state_hash
