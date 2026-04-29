"""Behavior parity test suite — Phase 13 STEP 3.

Tests 1–3: structural parity (T-1307)
Tests 4–5: state and sequencing (T-1308)
Tests 6–7: command and guard parity (T-1309)
Tests 8–9: state sync and sys.modules (T-1310)
Tests 10–11: projection and CLI consistency (T-1311)

All tests use tmp_db_path (PostgreSQL) — never touches production DB (I-EXEC-ISOL-1).
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventInput, sdd_append, sdd_append_batch, sdd_replay


# ---------------------------------------------------------------------------
# Test 1: DB schema parity (I-RUNTIME-1)
# ---------------------------------------------------------------------------

_EXPECTED_COLUMNS = {
    "sequence_id",
    "event_id",
    "event_type",
    "payload",
    "metadata",
    "created_at",
    "level",
    "event_source",
    "caused_by_meta_seq",
    "expired",
    "batch_id",
}


def test_db_schema_parity(tmp_db_path: str):
    """I-RUNTIME-1: open_sdd_connection creates event_log table with the full schema."""
    conn = open_sdd_connection(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'event_log' ORDER BY column_name"
        ).fetchall()
    finally:
        conn.close()

    actual_columns = {row[0] for row in rows}
    assert actual_columns == _EXPECTED_COLUMNS, (
        f"Schema mismatch.\n  expected: {sorted(_EXPECTED_COLUMNS)}\n  actual:   {sorted(actual_columns)}"
    )


# ---------------------------------------------------------------------------
# Test 2: event append parity (I-RUNTIME-1)
# ---------------------------------------------------------------------------

def test_event_append_parity(tmp_db_path: str):
    """I-RUNTIME-1: sdd_append writes an event readable back with correct fields."""
    payload = {"phase_id": 1, "task_id": "T-001", "actor": "llm"}

    sdd_append(
        "TaskImplemented",
        payload,
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    conn = open_sdd_connection(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, level, event_source, expired "
            "FROM event_log WHERE event_type = 'TaskImplemented'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"Expected 1 event, got {len(rows)}"
    event_type, level, event_source, expired = rows[0]
    assert event_type == "TaskImplemented"
    assert level == "L1"
    assert event_source == "runtime"
    assert expired is False


# ---------------------------------------------------------------------------
# Test 3: taskset parse equivalence (I-RUNTIME-1)
# ---------------------------------------------------------------------------

_TASKSET_CONTENT = textwrap.dedent("""\
    ## T-001: First task

    Status:               TODO
    Spec ref:             Spec_v1 §2
    Inputs:               src/foo.py
    Outputs:              src/bar.py
    spec_refs:            Spec_v1 §2
    produces_invariants:  I-FOO-1
    requires_invariants:
    Depends on:

    ---

    ## T-002: Second task

    Status:               DONE
    Spec ref:             Spec_v1 §3
    Inputs:               src/bar.py
    Outputs:              src/baz.py
    spec_refs:            Spec_v1 §3
    produces_invariants:
    requires_invariants:  I-FOO-1
    Depends on:           T-001

    ---
""")


def test_taskset_parse_equivalence(tmp_path):
    """I-RUNTIME-1: parse_taskset returns correct Task objects for a known TaskSet markdown."""
    from sdd.domain.tasks.parser import parse_taskset

    taskset_path = tmp_path / "TaskSet_v1.md"
    taskset_path.write_text(_TASKSET_CONTENT, encoding="utf-8")

    tasks = parse_taskset(str(taskset_path))

    assert len(tasks) == 2

    t1 = tasks[0]
    assert t1.task_id == "T-001"
    assert t1.title == "First task"
    assert t1.status == "TODO"
    assert t1.inputs == ("src/foo.py",)
    assert t1.outputs == ("src/bar.py",)
    assert t1.produces_invariants == ("I-FOO-1",)
    assert t1.requires_invariants == ()
    assert t1.depends_on == ()

    t2 = tasks[1]
    assert t2.task_id == "T-002"
    assert t2.title == "Second task"
    assert t2.status == "DONE"
    assert t2.depends_on == ("T-001",)
    assert t2.requires_invariants == ("I-FOO-1",)
    assert t2.produces_invariants == ()


# ---------------------------------------------------------------------------
# Test 4: state yaml roundtrip (I-STATE-SYNC-1)
# ---------------------------------------------------------------------------

def test_state_yaml_roundtrip(tmp_path):
    """I-STATE-SYNC-1: write_state then read_state preserves all SDDState fields exactly."""
    from sdd.domain.state.reducer import SDDState
    from sdd.domain.state.yaml_state import read_state, write_state

    state_path = str(tmp_path / "State_index.yaml")

    original = SDDState(
        phase_current=5,
        plan_version=5,
        tasks_version=5,
        tasks_total=10,
        tasks_completed=3,
        tasks_done_ids=("T-501", "T-502", "T-503"),
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )

    write_state(original, state_path)
    restored = read_state(state_path)

    assert restored.phase_current == original.phase_current
    assert restored.plan_version == original.plan_version
    assert restored.tasks_version == original.tasks_version
    assert restored.tasks_total == original.tasks_total
    assert restored.tasks_completed == original.tasks_completed
    assert restored.tasks_done_ids == original.tasks_done_ids
    assert restored.invariants_status == original.invariants_status
    assert restored.tests_status == original.tests_status
    assert restored.schema_version == original.schema_version
    assert restored.snapshot_event_id == original.snapshot_event_id
    assert restored.phase_status == original.phase_status
    assert restored.plan_status == original.plan_status
    assert restored.state_hash == original.state_hash


# ---------------------------------------------------------------------------
# Test 5: event order determinism (I-BEHAVIOR-SEQ-1)
# ---------------------------------------------------------------------------

def test_event_order_determinism(tmp_db_path: str):
    """I-BEHAVIOR-SEQ-1: sdd_replay() is stable across multiple calls on the same DB."""
    _append_task_trace(tmp_db_path)

    events1 = sdd_replay(db_path=tmp_db_path)
    events2 = sdd_replay(db_path=tmp_db_path)

    seq1 = [(e["event_type"], i) for i, e in enumerate(events1)]
    seq2 = [(e["event_type"], i) for i, e in enumerate(events2)]

    assert seq1 == seq2, (
        f"Event sequences differ.\n  call1: {seq1}\n  call2: {seq2}"
    )


def _append_task_trace(db: str) -> None:
    """Append a deterministic trace of two events simulating sdd complete T-001."""
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 1, "tasks_total": 1, "plan_version": 1,
         "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=db,
        level="L1",
        event_source="runtime",
    )
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-001", "phase_id": 1},
        db_path=db,
        level="L1",
        event_source="runtime",
    )


# ---------------------------------------------------------------------------
# Test 6: command event equivalence (I-RUNTIME-1, I-STATE-SYNC-1)
# ---------------------------------------------------------------------------

_TASKSET_TODO = textwrap.dedent("""\
    ## T-001: Test task

    Status:               TODO
    Spec ref:             Spec_v1 §1
    Inputs:               src/foo.py
    Outputs:              src/bar.py
    spec_refs:            Spec_v1 §1
    produces_invariants:
    requires_invariants:
    Depends on:

    ---
""")


def test_command_event_equivalence(tmp_path, tmp_db_path: str):
    """I-RUNTIME-1 + I-STATE-SYNC-1: execute_and_project emits TaskImplemented and syncs state."""
    from sdd.commands.registry import REGISTRY, execute_and_project
    from sdd.core.payloads import build_command
    from sdd.domain.state.yaml_state import read_state

    state_path = str(tmp_path / "State_index.yaml")
    taskset_path = str(tmp_path / "TaskSet_v1.md")

    (tmp_path / "TaskSet_v1.md").write_text(_TASKSET_TODO, encoding="utf-8")

    # Seed phase context so PhaseGuard passes (I-KERNEL-WRITE-1)
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 1, "tasks_total": 1, "plan_version": 1,
         "actor": "test-seed", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path, level="L1", event_source="runtime",
    )

    execute_and_project(
        REGISTRY["complete"],
        build_command("CompleteTask", task_id="T-001", phase_id=1,
                      taskset_path=taskset_path, state_path=state_path),
        db_path=tmp_db_path,
        state_path=state_path,
        taskset_path=taskset_path,
    )

    events = sdd_replay(db_path=tmp_db_path)
    ti_events = [e for e in events if e["event_type"] == "TaskImplemented"]
    assert len(ti_events) == 1, f"Expected 1 TaskImplemented event, got {len(ti_events)}"
    assert ti_events[0]["payload"]["task_id"] == "T-001"
    assert ti_events[0]["payload"]["phase_id"] == 1

    state = read_state(state_path)
    assert "T-001" in state.tasks_done_ids, "T-001 must appear in tasks_done_ids after complete"
    assert state.tasks_completed == 1


# ---------------------------------------------------------------------------
# Test 7: guard behavior equivalence (I-CLI-API-1, I-RUNTIME-1)
# ---------------------------------------------------------------------------

def test_guard_behavior_equivalence(tmp_path):
    """I-CLI-API-1 + I-RUNTIME-1: guard rejection for DONE task serializes as I-CLI-API-1 JSON."""
    import contextlib
    import io
    import json as json_mod

    from sdd.cli import _emit_json_error
    from sdd.core.errors import InvalidState, SDDError
    from sdd.domain.guards.context import DAG, EventLogView, GuardContext, PhaseState
    from sdd.domain.guards.task_guard import make_task_guard
    from sdd.domain.norms.catalog import NormCatalog
    from sdd.domain.state.reducer import EMPTY_STATE
    from sdd.domain.tasks.parser import Task

    done_task = Task(
        task_id="T-001",
        title="Already done task",
        status="DONE",
        spec_section="Spec_v1 §1",
        inputs=(), outputs=(), checks=(), spec_refs=(),
        produces_invariants=(), requires_invariants=(),
    )
    ctx = GuardContext(
        state=EMPTY_STATE,
        phase=PhaseState(phase_id=1, status="ACTIVE"),
        task=done_task,
        norms=NormCatalog(entries=(), strict=False),
        event_log=EventLogView(db_path=str(tmp_path / "unused.duckdb")),
        task_graph=DAG(deps={}),
        now="2026-01-01T00:00:00Z",
    )

    with pytest.raises(InvalidState) as exc_info:
        make_task_guard("T-001")(ctx)

    exc = exc_info.value
    assert isinstance(exc, SDDError), "InvalidState must be an SDDError subclass (I-CLI-API-1)"
    assert "T-001" in str(exc)
    assert "DONE" in str(exc)

    stderr_buf = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf):
        _emit_json_error(type(exc).__name__, str(exc), 1)

    payload = json_mod.loads(stderr_buf.getvalue().strip())
    assert {"error_type", "message", "exit_code"} <= set(payload.keys()), (
        f"I-CLI-API-1: JSON must contain error_type, message, exit_code. Got: {set(payload.keys())}"
    )
    assert payload["error_type"] == "InvalidState"
    assert payload["exit_code"] == 1
    assert "T-001" in payload["message"]


# ---------------------------------------------------------------------------
# Test 8: state always synced after command (I-STATE-SYNC-1)
# ---------------------------------------------------------------------------

_MINIMAL_STATE_YAML = textwrap.dedent("""\
    phase:
      current: 1
      status: ACTIVE
    plan:
      version: 1
      status: ACTIVE
    tasks:
      version: 1
      total: 1
      completed: 0
      done_ids: []
    invariants:
      status: UNKNOWN
    tests:
      status: UNKNOWN
    meta:
      last_updated: "2026-01-01T00:00:00Z"
      schema_version: 1
""")


def test_state_always_synced_after_command(tmp_path, tmp_db_path: str):
    """I-STATE-SYNC-1: State_index.yaml updated before sdd complete process exits."""
    import subprocess

    from sdd.domain.state.yaml_state import read_state

    taskset_path = tmp_path / "TaskSet_v1.md"
    state_path = tmp_path / "State_index.yaml"

    taskset_path.write_text(_TASKSET_TODO, encoding="utf-8")
    state_path.write_text(_MINIMAL_STATE_YAML, encoding="utf-8")

    # Seed phase context so PhaseGuard passes (I-KERNEL-WRITE-1)
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 1, "tasks_total": 1, "plan_version": 1,
         "actor": "test-seed", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path, level="L1", event_source="runtime",
    )

    result = subprocess.run(
        [
            "sdd", "complete", "T-001",
            "--phase", "1",
            "--taskset", str(taskset_path),
            "--state", str(state_path),
            "--db", tmp_db_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sdd complete failed (exit {result.returncode})\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    state = read_state(str(state_path))
    assert "T-001" in state.tasks_done_ids, (
        "I-STATE-SYNC-1: T-001 missing from tasks_done_ids after process exit"
    )
    assert state.tasks_completed == 1, (
        f"I-STATE-SYNC-1: tasks_completed={state.tasks_completed!r}, expected 1"
    )


# ---------------------------------------------------------------------------
# Test 9: no .sdd/_deprecated_tools in sys.modules (I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1)
# ---------------------------------------------------------------------------

def test_no_runtime_import_of_sdd_tools(tmp_path):
    """I-TOOL-PATH-1 + I-RUNTIME-LINEAGE-1: no .sdd.tools in sys.modules after sdd command."""
    import subprocess, sys, json
    result = subprocess.run(
        ["python3", "-c",
         "import sdd.cli; import sys; import json; "
         "bad = [m for m in sys.modules if '.sdd.tools' in m or '\\.sdd\\\\tools' in m]; "
         "print(json.dumps(bad))"],
        capture_output=True, text=True
    )
    assert json.loads(result.stdout) == []


# ---------------------------------------------------------------------------
# Test 10: projection equivalence (I-RUNTIME-1, I-BEHAVIOR-SEQ-1)
# ---------------------------------------------------------------------------

def test_projection_equivalence(tmp_path, tmp_db_path: str):
    """I-RUNTIME-1, I-BEHAVIOR-SEQ-1: rebuild_state produces same counts as EventReducer.reduce()."""
    from sdd.domain.state.reducer import EventReducer, SDDState
    from sdd.domain.state.yaml_state import read_state, write_state
    from sdd.infra.projections import rebuild_state

    state_path = str(tmp_path / "State_index.yaml")

    initial = SDDState(
        phase_current=1, plan_version=1, tasks_version=1, tasks_total=3,
        tasks_completed=0, tasks_done_ids=(),
        invariants_status="UNKNOWN", tests_status="UNKNOWN",
        last_updated="2026-01-01T00:00:00Z", schema_version=1,
        snapshot_event_id=None, phase_status="ACTIVE", plan_status="ACTIVE",
    )
    write_state(initial, state_path)

    sdd_append("TaskImplemented", {"task_id": "T-001", "phase_id": 1},
               db_path=tmp_db_path, level="L1", event_source="runtime")
    sdd_append("TaskImplemented", {"task_id": "T-002", "phase_id": 1},
               db_path=tmp_db_path, level="L1", event_source="runtime")

    # Path 1: projections.py rebuild_state
    rebuild_state(tmp_db_path, state_path)
    proj_state = read_state(state_path)

    # Path 2: EventReducer directly on raw DB events (mirrors projections._replay_all exactly)
    conn = open_sdd_connection(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, payload, level, event_source, caused_by_meta_seq "
            "FROM event_log ORDER BY sequence_id ASC"
        ).fetchall()
    finally:
        conn.close()

    raw_events: list[dict] = []
    for event_type, payload, level, event_source, caused_by_meta_seq in rows:
        # psycopg3 returns JSONB as dict already
        payload_dict: dict = payload if isinstance(payload, dict) else {}
        event: dict = {
            "event_type": event_type,
            "level": level,
            "event_source": event_source,
            "caused_by_meta_seq": caused_by_meta_seq,
        }
        event.update(payload_dict)
        raw_events.append(event)
    # Filter to phase 1 — mirrors projections.rebuild_state phase filter
    phase_events = [e for e in raw_events if e.get("phase_id") is None or e.get("phase_id") == 1]
    reducer_state = EventReducer().reduce(phase_events)

    assert proj_state.tasks_completed == reducer_state.tasks_completed, (
        f"tasks_completed mismatch: proj={proj_state.tasks_completed}, "
        f"reducer={reducer_state.tasks_completed}"
    )
    assert set(proj_state.tasks_done_ids) == set(reducer_state.tasks_done_ids), (
        f"tasks_done_ids mismatch: proj={set(proj_state.tasks_done_ids)}, "
        f"reducer={set(reducer_state.tasks_done_ids)}"
    )


# ---------------------------------------------------------------------------
# Test 11: CLI projection consistency (I-RUNTIME-1)
# ---------------------------------------------------------------------------

def test_cli_projection_consistency(tmp_path, tmp_db_path: str):
    """I-RUNTIME-1: sdd show-state output is consistent with projections.py (not stale cache)."""
    import shutil
    import subprocess

    from sdd.domain.state.yaml_state import read_state
    from sdd.infra.projections import rebuild_state

    state_path = tmp_path / "State_index.yaml"
    taskset_path = tmp_path / "TaskSet_v1.md"

    taskset_path.write_text(_TASKSET_TODO, encoding="utf-8")
    state_path.write_text(_MINIMAL_STATE_YAML, encoding="utf-8")

    # Seed phase context so PhaseGuard passes (I-KERNEL-WRITE-1)
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 1, "tasks_total": 1, "plan_version": 1,
         "actor": "test-seed", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path, level="L1", event_source="runtime",
    )

    result = subprocess.run(
        [
            "sdd", "complete", "T-001",
            "--phase", "1",
            "--taskset", str(taskset_path),
            "--state", str(state_path),
            "--db", tmp_db_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sdd complete failed (exit {result.returncode})\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # What sdd show-state reads: the YAML written by sdd complete
    cmd_state = read_state(str(state_path))

    # What projections.py derives from EventLog (idempotent rebuild)
    proj_state_path = str(tmp_path / "proj_state.yaml")
    shutil.copy(str(state_path), proj_state_path)
    rebuild_state(tmp_db_path, proj_state_path)
    proj_state = read_state(proj_state_path)

    assert cmd_state.tasks_completed == proj_state.tasks_completed, (
        f"tasks_completed: cmd={cmd_state.tasks_completed}, proj={proj_state.tasks_completed}"
    )
    assert set(cmd_state.tasks_done_ids) == set(proj_state.tasks_done_ids), (
        f"tasks_done_ids: cmd={set(cmd_state.tasks_done_ids)}, proj={set(proj_state.tasks_done_ids)}"
    )
