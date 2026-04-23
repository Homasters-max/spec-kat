"""Tests for ValidateTaskHandler — Spec_v4 §9 Verification row 5.

Invariants: I-CMD-1, I-ES-2
"""
from __future__ import annotations

import uuid

import pytest

from sdd.commands.update_state import ValidateTaskCommand, ValidateTaskHandler
from sdd.domain.state.yaml_state import read_state
from sdd.infra.db import open_sdd_connection

_TASKSET_CONTENT = """\
T-412: SomeTask

Status:               DONE

---

T-413: AnotherTask

Status:               TODO

---
"""

_STATE_CONTENT = """\
phase:
  current: 4
  status: ACTIVE
plan:
  version: 4
  status: ACTIVE
tasks:
  version: 4
  total: 2
  completed: 1
  done_ids:
    - T-412
invariants:
  status: UNKNOWN
tests:
  status: UNKNOWN
meta:
  last_updated: 2026-01-01T00:00:00Z
  schema_version: 1
senar:
  norm_catalog: null
  audit_log: null
  last_invariant_check: null
  invariant_check_result: null
  open_incidents: []
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_sdd.duckdb")
    conn = open_sdd_connection(path)
    conn.close()
    return path


@pytest.fixture
def taskset_file(tmp_path) -> str:
    p = tmp_path / "TaskSet_v4.md"
    p.write_text(_TASKSET_CONTENT, encoding="utf-8")
    return str(p)


@pytest.fixture
def state_file(tmp_path) -> str:
    p = tmp_path / "State_index.yaml"
    p.write_text(_STATE_CONTENT, encoding="utf-8")
    return str(p)


def _make_cmd(
    task_id: str,
    result: str,
    taskset_path: str,
    state_path: str,
    command_id: str | None = None,
) -> ValidateTaskCommand:
    return ValidateTaskCommand(
        command_type="ValidateTaskCommand",
        payload={},
        task_id=task_id,
        phase_id=4,
        result=result,
        taskset_path=taskset_path,
        state_path=state_path,
        command_id=command_id or str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_validate_pass_updates_state(db_path, taskset_file, state_file):
    """Calling with result=PASS writes invariants_status=PASS and tests_status=PASS."""
    cmd = _make_cmd("T-412", "PASS", taskset_file, state_file)
    ValidateTaskHandler(db_path).handle(cmd)

    state = read_state(state_file)
    assert state.invariants_status == "PASS"
    assert state.tests_status == "PASS"


def test_validate_fail_updates_state(db_path, taskset_file, state_file):
    """Calling with result=FAIL writes invariants_status=FAIL and tests_status=FAIL."""
    cmd = _make_cmd("T-412", "FAIL", taskset_file, state_file)
    ValidateTaskHandler(db_path).handle(cmd)

    state = read_state(state_file)
    assert state.invariants_status == "FAIL"
    assert state.tests_status == "FAIL"


def test_validate_task_idempotent(db_path, taskset_file, state_file):
    """Second call with the same command_id returns [] (I-CMD-1)."""
    cmd = _make_cmd("T-412", "PASS", taskset_file, state_file)
    handler = ValidateTaskHandler(db_path)

    events_first = handler.handle(cmd)
    events_second = handler.handle(cmd)

    assert len(events_first) > 0
    assert events_second == []


def test_validate_emits_task_validated_event(db_path, taskset_file, state_file):
    """Returned events contain exactly one TaskValidatedEvent with correct fields."""
    cmd = _make_cmd("T-412", "PASS", taskset_file, state_file)
    events = ValidateTaskHandler(db_path).handle(cmd)

    validated = [e for e in events if e.event_type == "TaskValidated"]
    assert len(validated) == 1

    ev = validated[0]
    assert ev.task_id == "T-412"   # type: ignore[attr-defined]
    assert ev.result == "PASS"     # type: ignore[attr-defined]
    assert ev.phase_id == 4        # type: ignore[attr-defined]
    assert ev.level == "L1"
