"""Integration tests: PostgresEventLog + Projector against live PostgreSQL.

Tests 10–18 (Spec_v43):
  10: append/replay       (I-EVENT-1, I-EVENT-2, I-ORDER-1)
  11: optimistic lock     (I-OPTLOCK-1)
  12: idempotency         (I-IDEM-SCHEMA-1)
  13: Projector apply     (I-PROJ-1)
  14: idempotent Projector(I-PROJ-1)
  15: rebuild             (I-REBUILD-ATOMIC-1, I-REPLAY-1, I-PROJ-VERSION-1)
  16: full pipeline       (I-FAIL-1, I-PROJ-1, I-LAYER-1)
  17: failure isolation   (I-FAIL-1)
  18: no direct mutations (I-EVENT-1, I-PROJ-WRITE-1) — static grep/ast check

Skipped when SDD_DATABASE_URL is not set (pg_url fixture calls pytest.skip).
"""
from __future__ import annotations

import ast
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sdd.core.errors import StaleStateError
from sdd.core.events import TaskImplementedEvent
from sdd.db.connection import open_db_connection
from sdd.infra.event_log import PostgresEventLog
from sdd.infra.projector import Projector

pytestmark = pytest.mark.pg

_SCHEMA = "p_test_el"
_SDD_PROJECT = "test_el"

# Projection tables that must only be written via Projector.apply() (I-PROJ-WRITE-1)
_PROJECTION_TABLES = frozenset({
    "P_TASKS", "P_PHASES", "P_SESSIONS", "P_DECISIONS", "P_INVARIANTS", "P_SPECS",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_event(task_id: str, phase_id: int = 43) -> TaskImplementedEvent:
    return TaskImplementedEvent(
        event_type="TaskImplemented",
        event_id=f"test-el-{task_id}",
        appended_at=0,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        task_id=task_id,
        phase_id=phase_id,
        timestamp="2026-01-01T00:00:00Z",
    )


def _query_task(pg_url: str, task_id: str) -> Any:
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT task_id, phase_id, status FROM p_tasks WHERE task_id = %s",
            (task_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _query_p_meta(pg_url: str) -> int | None:
    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT last_applied_sequence_id FROM p_meta")
        row = cur.fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixture: isolated schema
# ---------------------------------------------------------------------------

@pytest.fixture()
def _pg_el_schema(
    pg_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Create isolated schema p_test_el; set SDD_PROJECT; drop schema on teardown."""
    monkeypatch.setenv("SDD_PROJECT", _SDD_PROJECT)

    import psycopg

    conn = psycopg.connect(pg_url)
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
        conn.execute("CREATE SCHEMA IF NOT EXISTS shared")
        conn.commit()
    finally:
        conn.close()

    yield

    conn = psycopg.connect(pg_url)
    try:
        conn.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 10: append/replay (I-EVENT-1, I-EVENT-2, I-ORDER-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_10_append_replay(pg_url: str) -> None:
    """I-EVENT-1, I-EVENT-2, I-ORDER-1: events are replayed in sequence_id ASC order."""
    pg_el = PostgresEventLog(pg_url)

    ev1 = _task_event("T-EL-10A")
    ev2 = _task_event("T-EL-10B")
    pg_el.append([ev1], source="test", allow_outside_kernel="test")
    pg_el.append([ev2], source="test", allow_outside_kernel="test")

    rows = pg_el.replay()
    task_rows = [r for r in rows if r["event_type"] == "TaskImplemented"]
    assert len(task_rows) == 2, f"Expected 2 TaskImplemented rows, got {len(task_rows)}"
    assert task_rows[0]["sequence_id"] < task_rows[1]["sequence_id"], (
        "I-ORDER-1: sequence_id must be monotonically increasing"
    )
    ids = {r["payload"]["task_id"] for r in task_rows}
    assert ids == {"T-EL-10A", "T-EL-10B"}, f"Unexpected task IDs in replay: {ids}"


# ---------------------------------------------------------------------------
# Test 11: optimistic lock (I-OPTLOCK-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_11_optimistic_lock(pg_url: str) -> None:
    """I-OPTLOCK-1: append with stale expected_head raises StaleStateError.

    expected_head=None means "skip check" — lock is only active when head is explicit.
    To trigger StaleStateError: capture head after TX-A, advance it via TX-B,
    then attempt TX-C with the now-stale head from TX-A.
    """
    pg_el = PostgresEventLog(pg_url)

    # TX-A: append first event
    pg_el.append([_task_event("T-EL-11A")], source="test", allow_outside_kernel="test")
    head_after_a = pg_el.max_seq()
    assert head_after_a is not None

    # TX-B: advance head beyond head_after_a
    pg_el.append([_task_event("T-EL-11B")], source="test", allow_outside_kernel="test")

    # TX-C: stale expected_head — current max != head_after_a → StaleStateError
    with pytest.raises(StaleStateError):
        pg_el.append(
            [_task_event("T-EL-11C")],
            source="test",
            expected_head=head_after_a,  # stale: TX-B has already advanced the head
            allow_outside_kernel="test",
        )


# ---------------------------------------------------------------------------
# Test 12: idempotency (I-IDEM-SCHEMA-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_12_idempotency(pg_url: str) -> None:
    """I-IDEM-SCHEMA-1: duplicate (command_id, event_index) pairs are skipped silently."""
    pg_el = PostgresEventLog(pg_url)
    ev = _task_event("T-EL-12")
    cmd_id = "cmd-idem-el-001"

    pg_el.append([ev], source="test", command_id=cmd_id, allow_outside_kernel="test")
    pg_el.append([ev], source="test", command_id=cmd_id, allow_outside_kernel="test")

    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM event_log WHERE payload->>'command_id' = %s",
            (cmd_id,),
        )
        count = cur.fetchone()[0]
    finally:
        conn.close()

    assert count == 1, (
        f"I-IDEM-SCHEMA-1: expected 1 row for command_id={cmd_id!r}, got {count}"
    )


# ---------------------------------------------------------------------------
# Test 13: Projector apply (I-PROJ-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_13_projector_apply(pg_url: str) -> None:
    """I-PROJ-1: TaskImplemented event → p_tasks row with status='DONE'."""
    task_id = "T-EL-13"
    ev = _task_event(task_id)

    pg_el = PostgresEventLog(pg_url)
    pg_el.append([ev], source="test", allow_outside_kernel="test")

    with Projector(pg_url) as projector:
        projector.apply(ev)

    row = _query_task(pg_url, task_id)
    assert row is not None, f"I-PROJ-1: no p_tasks row for task_id={task_id!r}"
    assert row[2] == "DONE", f"I-PROJ-1: expected status='DONE', got {row[2]!r}"


# ---------------------------------------------------------------------------
# Test 14: idempotent Projector (I-PROJ-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_14_projector_idempotent(pg_url: str) -> None:
    """I-PROJ-1: applying the same event twice → exactly 1 row in p_tasks (ON CONFLICT DO UPDATE)."""
    task_id = "T-EL-14"
    ev = _task_event(task_id)

    with Projector(pg_url) as p1:
        p1.apply(ev)

    with Projector(pg_url) as p2:
        p2.apply(ev)

    conn = open_db_connection(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM p_tasks WHERE task_id = %s", (task_id,))
        count = cur.fetchone()[0]
    finally:
        conn.close()

    assert count == 1, (
        f"I-PROJ-1 idempotency: expected 1 row for {task_id!r}, got {count}"
    )


# ---------------------------------------------------------------------------
# Test 15: rebuild (I-REBUILD-ATOMIC-1, I-REPLAY-1, I-PROJ-VERSION-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_15_rebuild(pg_url: str) -> None:
    """I-REBUILD-ATOMIC-1, I-REPLAY-1, I-PROJ-VERSION-1: rebuild() is atomic and consistent."""
    import psycopg

    task_a = "T-EL-15A"
    task_b = "T-EL-15B"

    pg_el = PostgresEventLog(pg_url)
    pg_el.append([_task_event(task_a)], source="test", allow_outside_kernel="test")
    pg_el.append([_task_event(task_b)], source="test", allow_outside_kernel="test")
    expected_max_seq = pg_el.max_seq()
    assert expected_max_seq is not None

    # rebuild() requires a connection with the right search_path (I-REBUILD-ATOMIC-1)
    raw_conn = psycopg.connect(pg_url)
    try:
        raw_conn.execute(f"SET search_path = {_SCHEMA}, shared")
        with Projector(pg_url) as projector:
            projector.rebuild(raw_conn)
    finally:
        raw_conn.close()

    # I-REPLAY-1: p_tasks reflects all events
    row_a = _query_task(pg_url, task_a)
    row_b = _query_task(pg_url, task_b)
    assert row_a is not None and row_a[2] == "DONE", f"I-REPLAY-1: missing {task_a} in p_tasks"
    assert row_b is not None and row_b[2] == "DONE", f"I-REPLAY-1: missing {task_b} in p_tasks"

    # I-PROJ-VERSION-1: p_meta.last_applied_sequence_id == MAX(event_log.sequence_id)
    last_applied = _query_p_meta(pg_url)
    assert last_applied == expected_max_seq, (
        f"I-PROJ-VERSION-1: p_meta.last_applied_sequence_id={last_applied} "
        f"!= max_seq={expected_max_seq}"
    )


# ---------------------------------------------------------------------------
# Test 16: full pipeline TX1+TX2+YAML (I-FAIL-1, I-PROJ-1, I-LAYER-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_16_full_pipeline_tx1_tx2_yaml(pg_url: str, tmp_path: Path) -> None:
    """I-FAIL-1, I-PROJ-1, I-LAYER-1: TX1 (event_log) → TX2 (p_*) → YAML (State_index.yaml).

    Verifies the three-layer pipeline: L1 event_log (SSOT) → L2 p_* (projection cache)
    → L3 YAML (CLI read interface). Each layer written only from the previous one (I-LAYER-1).
    """
    from sdd.commands.registry import _apply_projector_safe
    from sdd.infra.projections import RebuildMode, rebuild_state

    task_id = "T-EL-16"
    ev = _task_event(task_id)

    # TX1: append to PostgreSQL event_log (L1 SSOT)
    pg_el = PostgresEventLog(pg_url)
    pg_el.append([ev], source="test", allow_outside_kernel="test")
    assert pg_el.max_seq() is not None, "TX1: event_log must have a committed row"

    # TX2: apply to p_* via Projector (L2 projection cache, I-PROJ-1)
    with Projector(pg_url) as projector:
        _apply_projector_safe(projector, [ev])

    row = _query_task(pg_url, task_id)
    assert row is not None and row[2] == "DONE", (
        f"TX2: p_tasks must have status='DONE' for {task_id!r} (I-PROJ-1)"
    )

    # YAML: rebuild State_index.yaml from event_log replay (L3 read interface, I-LAYER-1)
    state_yaml = tmp_path / "State_index.yaml"
    rebuild_state(pg_url, str(state_yaml), mode=RebuildMode.STRICT)
    assert state_yaml.exists(), (
        "YAML: rebuild_state must write State_index.yaml from event_log (I-LAYER-1)"
    )


# ---------------------------------------------------------------------------
# Test 17: Projector failure isolation (I-FAIL-1)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("_pg_el_schema")
def test_17_projector_failure_isolation(pg_url: str) -> None:
    """I-FAIL-1: Projector.apply() failure must not rollback event_log TX1."""
    from sdd.commands.registry import _apply_projector_safe

    task_id = "T-EL-17"
    ev = _task_event(task_id)

    # TX1: commit event to event_log
    pg_el = PostgresEventLog(pg_url)
    pg_el.append([ev], source="test", allow_outside_kernel="test")
    seq_before = pg_el.max_seq()
    assert seq_before is not None, "TX1 must be committed before Projector failure"

    # TX2: Projector raises — _apply_projector_safe must swallow it (I-PROJ-SAFE-1)
    with Projector(pg_url) as projector:
        with patch.object(projector, "apply", side_effect=RuntimeError("simulated failure")):
            _apply_projector_safe(projector, [ev])  # must not raise

    # TX1 must remain intact (I-FAIL-1)
    seq_after = pg_el.max_seq()
    assert seq_after == seq_before, (
        f"I-FAIL-1: event_log seq changed after Projector failure: "
        f"before={seq_before}, after={seq_after}"
    )
    replayed = pg_el.replay()
    task_events = [r for r in replayed if r.get("payload", {}).get("task_id") == task_id]
    assert task_events, (
        "I-FAIL-1: event_log must retain TaskImplemented after Projector failure"
    )


# ---------------------------------------------------------------------------
# Test 18: no direct mutations — grep/ast check (I-EVENT-1, I-PROJ-WRITE-1)
# ---------------------------------------------------------------------------

def test_18_no_direct_mutations() -> None:
    """I-EVENT-1, I-PROJ-WRITE-1: static analysis — only Projector writes p_* tables.

    Scans src/sdd/ for SQL string literals that directly mutate p_tasks/p_phases/
    p_sessions/p_decisions/p_invariants/p_specs outside projector.py, or that
    UPDATE/DELETE from event_log (append-only invariant, I-EVENT-1).
    """
    src_root = Path(__file__).parent.parent.parent / "src" / "sdd"
    assert src_root.is_dir(), f"src/sdd not found at {src_root}"

    violations: list[str] = []

    for py_file in sorted(src_root.rglob("*.py")):
        # projector.py is the ONLY allowed writer of p_* projection tables
        if py_file.name == "projector.py":
            continue

        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            val = node.value
            if not isinstance(val, str):
                continue

            sql = val.upper().strip()
            rel = py_file.relative_to(src_root.parent.parent)
            loc = f"{rel}:{node.lineno}"

            # I-PROJ-WRITE-1: projection tables must only be written via Projector.apply()
            for table in _PROJECTION_TABLES:
                if (
                    f"INSERT INTO {table}" in sql
                    or f"UPDATE {table}" in sql
                    or f"DELETE FROM {table}" in sql
                ):
                    violations.append(
                        f"{loc}: direct {table} mutation outside Projector "
                        f"(I-PROJ-WRITE-1): {val[:80]!r}"
                    )

            # I-EVENT-1: event_log is append-only; UPDATE and DELETE are forbidden
            if "UPDATE EVENT_LOG" in sql or "DELETE FROM EVENT_LOG" in sql:
                violations.append(
                    f"{loc}: event_log UPDATE/DELETE violates append-only I-EVENT-1: "
                    f"{val[:80]!r}"
                )

    assert not violations, (
        "I-EVENT-1 / I-PROJ-WRITE-1 violations found in src/sdd/:\n"
        + "\n".join(violations)
    )
