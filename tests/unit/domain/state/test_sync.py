"""Tests for sync_state — Spec_v2 §9 row 3 — I-ST-4, I-ST-6, I-EL-9."""
from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from sdd.core.errors import Inconsistency, MissingState
from sdd.domain.state.reducer import EMPTY_STATE, SDDState
from sdd.domain.state.sync import sync_state
from sdd.infra.event_log import sdd_replay as _default_replay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides: object) -> SDDState:
    defaults: dict[str, object] = dict(
        phase_current=2,
        plan_version=2,
        tasks_version=2,
        tasks_total=5,
        tasks_completed=2,
        tasks_done_ids=("T-201", "T-202"),
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-04-20T12:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )
    defaults.update(overrides)
    return SDDState(**defaults)


def _task(task_id: str, status: str = "DONE") -> Any:
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


def _runtime_l1(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_type": event_type, "event_source": "runtime", "level": "L1", **payload}


def _task_implemented_events(*task_ids: str) -> list[dict[str, object]]:
    return [
        _runtime_l1("TaskImplemented", task_id=tid, phase_id="2")
        for tid in task_ids
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sync_uses_eventlog_for_task_counts(tmp_path):
    """tasks_completed and tasks_done_ids come from EventLog, not TaskSet DONE count (I-ST-4, I-ST-6)."""
    state_path = str(tmp_path / "State_index.yaml")

    # EventLog says 2 tasks done; TaskSet also says 2 DONE (aligned — no Inconsistency).
    events = _task_implemented_events("T-201", "T-202")
    tasks = [_task("T-201"), _task("T-202"), _task("T-203", status="TODO")]

    emit = MagicMock()

    with (
        patch("sdd.domain.state.sync.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.sync.read_state", side_effect=MissingState("absent")),
        patch("sdd.domain.state.sync.write_state") as mock_write,
    ):
        result = sync_state(
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
            replay_fn=lambda: events,
        )

    # tasks_completed and tasks_done_ids derived from EventLog reduce()
    assert result.tasks_completed == 2
    assert set(result.tasks_done_ids) == {"T-201", "T-202"}
    # tasks_total from TaskSet length
    assert result.tasks_total == 3
    mock_write.assert_called_once()


def test_sync_raises_inconsistency_on_divergence(tmp_path):
    """Raises Inconsistency when TaskSet DONE count differs from EventLog tasks_completed (I-ST-4)."""
    state_path = str(tmp_path / "State_index.yaml")

    # EventLog says 2 tasks done; TaskSet says 3 DONE — divergence.
    events = _task_implemented_events("T-201", "T-202")
    tasks = [_task("T-201"), _task("T-202"), _task("T-203")]  # 3 DONE

    emit = MagicMock()

    with (
        patch("sdd.domain.state.sync.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.sync.read_state", side_effect=MissingState("absent")),
        patch("sdd.domain.state.sync.write_state"),
    ):
        with pytest.raises(Inconsistency, match="diverges"):
            sync_state(
                taskset_path="fake.md",
                state_path=state_path,
                emit=emit,
                replay_fn=lambda: events,
            )

    emit.assert_not_called()


def test_sync_preserves_phase_fields(tmp_path):
    """phase_status and plan_status are preserved from existing YAML, not overwritten (I-ST-6)."""
    state_path = str(tmp_path / "State_index.yaml")

    events = _task_implemented_events("T-201")
    tasks = [_task("T-201")]

    existing = _make_state(
        tasks_completed=1,
        tasks_done_ids=("T-201",),
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )

    captured: list[SDDState] = []
    emit = MagicMock()

    def fake_write(state: SDDState, path: str) -> None:
        captured.append(state)

    with (
        patch("sdd.domain.state.sync.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.sync.read_state", return_value=existing),
        patch("sdd.domain.state.sync.write_state", side_effect=fake_write),
    ):
        result = sync_state(
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
            replay_fn=lambda: events,
        )

    assert result.phase_status == "ACTIVE"
    assert result.plan_status == "ACTIVE"


def test_sync_emits_state_derivation_event(tmp_path):
    """emit is called exactly once with a StateDerivationCompletedEvent(derived_from="eventlog")."""
    state_path = str(tmp_path / "State_index.yaml")

    events = _task_implemented_events("T-201")
    tasks = [_task("T-201")]

    emitted: list[Any] = []
    emit = MagicMock(side_effect=lambda e: emitted.append(e))

    with (
        patch("sdd.domain.state.sync.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.sync.read_state", side_effect=MissingState("absent")),
        patch("sdd.domain.state.sync.write_state"),
    ):
        sync_state(
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
            replay_fn=lambda: events,
        )

    assert emit.call_count == 1
    event = emitted[0]
    assert event.event_type == "StateDerivationCompleted"
    assert event.derived_from == "eventlog"


def test_sync_no_direct_db_calls():
    """sync.py must not contain any direct duckdb.connect( call (I-EL-9)."""
    import sdd.domain.state.sync as sync_module

    source = inspect.getsource(sync_module)
    # Search for actual call pattern (parenthesis required), not docstring mentions.
    assert "duckdb.connect(" not in source


def test_sync_replay_fn_injectable():
    """replay_fn parameter is injectable with a default of sdd_replay (I-ST-6)."""
    sig = inspect.signature(sync_state)
    assert "replay_fn" in sig.parameters
    param = sig.parameters["replay_fn"]
    assert param.default is _default_replay


def test_sync_absent_yaml_uses_reducer_defaults(tmp_path):
    """When YAML file is absent, phase_status/plan_status fall back to reducer defaults (I-ST-6)."""
    state_path = str(tmp_path / "State_index.yaml")

    # PhaseInitialized event sets phase_status="ACTIVE" in reducer.
    events = [
        _runtime_l1(
            "PhaseInitialized",
            phase_id=2,
            tasks_total=1,
            plan_version=2,
            actor="llm",
            timestamp="2026-04-20T12:00:00Z",
        ),
        *_task_implemented_events("T-201"),
    ]
    tasks = [_task("T-201")]

    captured: list[SDDState] = []
    emit = MagicMock()

    def fake_write(state: SDDState, path: str) -> None:
        captured.append(state)

    with (
        patch("sdd.domain.state.sync.parse_taskset", return_value=tasks),
        patch("sdd.domain.state.sync.read_state", side_effect=MissingState("no yaml")),
        patch("sdd.domain.state.sync.write_state", side_effect=fake_write),
    ):
        result = sync_state(
            taskset_path="fake.md",
            state_path=state_path,
            emit=emit,
            replay_fn=lambda: events,
        )

    # Falls back to reducer-derived phase_status ("ACTIVE" from PhaseInitialized event).
    assert result.phase_status == "ACTIVE"
    assert len(captured) == 1
