"""End-to-end smoke test: sdd complete T-NNN via subprocess with isolated tmp dir.

Invariants covered: I-CMD-ENV-6
Spec ref: Spec_v9 §2 BC-CMD-TEST, §9 Verification row 2
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest


_MINIMAL_TASKSET = textwrap.dedent("""\
    T-001: Smoke fixture task

    Status:               TODO
    Spec ref:             §smoke
    Inputs:
    Outputs:
    Checks:
    spec_refs:            []
    produces_invariants:  []
    requires_invariants:  []
    Depends on:
""")

_MINIMAL_STATE = textwrap.dedent("""\
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


@pytest.fixture()
def isolated_sdd_env(tmp_path: Path):
    """Isolated tmp dir with a real TaskSet, state, and seeded DuckDB."""
    from datetime import UTC, datetime
    from sdd.infra.event_log import sdd_append

    taskset = tmp_path / "TaskSet_v1.md"
    state = tmp_path / "state.yaml"
    db = tmp_path / "events.duckdb"

    taskset.write_text(_MINIMAL_TASKSET, encoding="utf-8")
    state.write_text(_MINIMAL_STATE, encoding="utf-8")

    # Seed phase context so PhaseGuard passes (I-KERNEL-WRITE-1)
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 1, "tasks_total": 1, "plan_version": 1,
         "actor": "test-seed",
         "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        db_path=str(db), level="L1", event_source="runtime",
    )

    return {"taskset": str(taskset), "state": str(state), "db": str(db)}


def test_sdd_complete_exits_zero(isolated_sdd_env) -> None:
    """sdd complete T-001 exits 0 when task is TODO in an isolated environment (I-CMD-ENV-6)."""
    env = isolated_sdd_env
    result = subprocess.run(
        [
            "sdd", "complete", "T-001",
            "--phase", "1",
            "--taskset", env["taskset"],
            "--state", env["state"],
            "--db", env["db"],
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sdd complete exited {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
