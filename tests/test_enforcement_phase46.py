"""Phase 46 enforcement tests — I-NO-DUCKDB-1, I-DB-ENTRY-1, I-INVALIDATE-PG-1, I-SESSION-DEDUP-1.

BC-46-G: grep enforcement tests (no DB required).
BC-46-J: SessionDeclared idempotent dedup (I-SESSION-DEDUP-1).
BC-46-A: EventLogKernel unit tests (I-EL-KERNEL-WIRED-1).
Integration: PG pipeline & rebuild verification.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# §1 — grep enforcement (no DB, I-NO-DUCKDB-1)
# ---------------------------------------------------------------------------

def test_no_duckdb_imports_in_src() -> None:
    """I-NO-DUCKDB-1: DuckDB fully removed from src/sdd/.

    Allowlist:
    - paths.py: deprecated event_store_file() body retains the .duckdb path string
    - sync.py: comment/docstring lines explaining the no-duckdb invariant (negative refs)
    """
    result = subprocess.run(
        ["grep", "-rn", "duckdb", "src/sdd/", "--include=*.py"],
        capture_output=True, text=True,
    )
    violations = []
    for line in result.stdout.splitlines():
        # paths.py: deprecated event_store_file() stub — retains sdd_events.duckdb path
        if "paths.py" in line and "sdd_events.duckdb" in line:
            continue
        # comment/docstring lines explaining what NOT to call (e.g. sync.py I-EL-9 docs)
        code = line.split(":", 2)[-1].lstrip() if line.count(":") >= 2 else line
        if "duckdb.connect" in code and not code.startswith("import"):
            continue
        violations.append(line)
    assert not violations, (
        "I-NO-DUCKDB-1 violated. Unexpected duckdb references:\n" + "\n".join(violations)
    )


def test_duckdb_not_in_dependencies() -> None:
    """I-NO-DUCKDB-1: duckdb absent from pyproject.toml dependencies."""
    result = subprocess.run(
        ["grep", "duckdb", "pyproject.toml"],
        capture_output=True, text=True,
    )
    assert result.stdout == "", (
        f"I-NO-DUCKDB-1 violated. duckdb found in pyproject.toml:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# §2 — grep enforcement (no DB, I-DB-ENTRY-1)
# ---------------------------------------------------------------------------

def test_no_direct_psycopg_connect_in_src() -> None:
    """I-DB-ENTRY-1: all DB access via open_sdd_connection(), not psycopg.connect() directly.

    Exception: db/connection.py is the one allowed entry point — it IS open_db_connection().
    """
    result = subprocess.run(
        ["grep", "-rn", r"psycopg\.connect(", "src/sdd/", "--include=*.py"],
        capture_output=True, text=True,
    )
    violations = [
        l for l in result.stdout.splitlines()
        if "connection.py" not in l
    ]
    assert not violations, (
        "I-DB-ENTRY-1 violated. Direct psycopg.connect() calls outside entry point:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# §3 — grep enforcement (no DB, I-INVALIDATE-PG-1)
# ---------------------------------------------------------------------------

def test_invalidate_event_uses_pg_syntax() -> None:
    """I-INVALIDATE-PG-1: invalidate_event.py uses PG syntax (not DuckDB).

    Checks: no event_store_file(), no DuckDB table 'events', no '?' placeholder.
    """
    filepath = "src/sdd/commands/invalidate_event.py"
    for flags, pattern, description in [
        (["-n"], "event_store_file", "uses deprecated event_store_file() instead of event_store_url()"),
        (["-n"], '"events"', 'uses DuckDB table name "events" instead of event_log'),
        (["-Fn"], "= ?", "uses DuckDB placeholder '?' instead of '%s'"),
    ]:
        result = subprocess.run(
            ["grep"] + flags + [pattern, filepath],
            capture_output=True, text=True,
        )
        assert result.stdout == "", (
            f"I-INVALIDATE-PG-1 violated — {description}:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# §4 — EventLogKernel unit tests (no DB, I-EL-KERNEL-WIRED-1)
# ---------------------------------------------------------------------------

def test_el_kernel_resolve_batch_id() -> None:
    """I-EL-KERNEL-WIRED-1: multi-event → UUID4 batch_id; single-event → None."""
    from sdd.infra.el_kernel import EventLogKernel
    kernel = EventLogKernel()

    batch = kernel.resolve_batch_id([{"a": 1}, {"b": 2}])
    assert batch is not None
    assert len(batch) == 36 or len(batch) == 32  # UUID4 with or without dashes

    single = kernel.resolve_batch_id([{"a": 1}])
    assert single is None


def test_el_kernel_check_optimistic_lock() -> None:
    """I-EL-KERNEL-WIRED-1 / I-OPTLOCK-1: matching head → OK; mismatch → StaleStateError."""
    from sdd.core.errors import StaleStateError
    from sdd.infra.el_kernel import EventLogKernel
    kernel = EventLogKernel()

    # Both None → skip check
    kernel.check_optimistic_lock(None, None)

    # expected_head None → skip check unconditionally
    kernel.check_optimistic_lock(5, None)

    # current == expected → OK
    kernel.check_optimistic_lock(3, 3)

    # current != expected → StaleStateError
    with pytest.raises(StaleStateError):
        kernel.check_optimistic_lock(4, 3)


def test_el_kernel_filter_duplicates() -> None:
    """I-EL-KERNEL-WIRED-1 / I-IDEM-SCHEMA-1: known pairs → skipped; new pairs → to_insert."""
    from sdd.infra.el_kernel import EventLogKernel
    kernel = EventLogKernel()

    existing = {("cmd-abc", 0), ("cmd-abc", 1)}
    events = [
        {"command_id": "cmd-abc", "event_index": 0, "data": "dup"},
        {"command_id": "cmd-abc", "event_index": 1, "data": "dup2"},
        {"command_id": "cmd-xyz", "event_index": 0, "data": "new"},
        {"command_id": None, "event_index": 0, "data": "no-cmd-id"},
    ]
    to_insert, skipped = kernel.filter_duplicates(events, existing)

    assert len(skipped) == 2
    assert len(to_insert) == 2
    assert to_insert[0]["data"] == "new"
    assert to_insert[1]["data"] == "no-cmd-id"


# ---------------------------------------------------------------------------
# §5 — SessionDeclared dedup (I-SESSION-DEDUP-1, BC-46-J)
# ---------------------------------------------------------------------------

def test_stable_command_id_uses_utc() -> None:
    """BC-46-J: stable_session_command_id is deterministic for same inputs + UTC day."""
    from sdd.commands.record_session import stable_session_command_id

    id1 = stable_session_command_id("IMPLEMENT", 46)
    id2 = stable_session_command_id("IMPLEMENT", 46)
    assert id1 == id2, "Same inputs on same UTC day must yield identical hash"

    id_diff_type = stable_session_command_id("VALIDATE", 46)
    assert id1 != id_diff_type, "Different session_type → different hash"

    id_diff_phase = stable_session_command_id("IMPLEMENT", 45)
    assert id1 != id_diff_phase, "Different phase_id → different hash"

    assert len(id1) == 32, "Expected 32-hex SHA-256 truncation"


def test_session_dedup_same_utc_day(tmp_db_path: str) -> None:
    """BC-49-C / I-HANDLER-SESSION-PURE-1: handler is pure, always returns [SessionDeclaredEvent].

    Dedup is exclusively the kernel's responsibility (Step 2.5, I-DEDUP-KERNEL-AUTHORITY-1).
    handler.handle() MUST return an event even when a SessionDeclared already exists today.
    """
    from sdd.commands.record_session import RecordSessionCommand, RecordSessionHandler
    from sdd.infra.db import open_sdd_connection

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    payload = {
        "session_type": "IMPLEMENT",
        "phase_id": 46,
        "timestamp": f"{today}T00:00:00Z",
        "task_id": None,
        "plan_hash": "test-seed",
    }
    conn = open_sdd_connection(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO event_log "
            "(event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired) "
            "VALUES (%s, 'SessionDeclared', %s::jsonb, 'L1', 'runtime', NULL, FALSE)",
            [str(uuid.uuid4()), json.dumps(payload)],
        )
        conn.commit()
    finally:
        conn.close()

    cmd = RecordSessionCommand(
        command_id=str(uuid.uuid4()),
        command_type="RecordSessionCommand",
        payload={},
        session_type="IMPLEMENT",
        task_id=None,
        phase_id=46,
        plan_hash="test-dedup",
    )
    handler = RecordSessionHandler(db_path=tmp_db_path)
    events = handler.handle(cmd)
    assert len(events) == 1, (
        "I-HANDLER-SESSION-PURE-1 (BC-49-C): handler must always return [SessionDeclaredEvent];"
        " dedup is the kernel's responsibility, not the handler's"
    )
    assert events[0].event_type == "SessionDeclared"


def test_session_dedup_different_utc_day(tmp_db_path: str) -> None:
    """I-SESSION-DEDUP-1: yesterday's SessionDeclared does NOT suppress today's event."""
    from sdd.commands.record_session import RecordSessionCommand, RecordSessionHandler
    from sdd.infra.db import open_sdd_connection

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    payload = {
        "session_type": "IMPLEMENT",
        "phase_id": 46,
        "timestamp": f"{yesterday}T00:00:00Z",
        "task_id": None,
        "plan_hash": "test-yesterday",
    }
    conn = open_sdd_connection(tmp_db_path)
    try:
        conn.execute(
            "INSERT INTO event_log "
            "(event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired) "
            "VALUES (%s, 'SessionDeclared', %s::jsonb, 'L1', 'runtime', NULL, FALSE)",
            [str(uuid.uuid4()), json.dumps(payload)],
        )
        conn.commit()
    finally:
        conn.close()

    cmd = RecordSessionCommand(
        command_id=str(uuid.uuid4()),
        command_type="RecordSessionCommand",
        payload={},
        session_type="IMPLEMENT",
        task_id=None,
        phase_id=46,
        plan_hash="test-today",
    )
    handler = RecordSessionHandler(db_path=tmp_db_path)
    events = handler.handle(cmd)
    assert len(events) == 1
    assert events[0].event_type == "SessionDeclared"


# ---------------------------------------------------------------------------
# §6 — PG integration (I-NO-DUCKDB-1, I-REPLAY-1)
# ---------------------------------------------------------------------------

@pytest.mark.pg
def test_pg_full_pipeline_no_duckdb(tmp_db_path: str) -> None:
    """I-NO-DUCKDB-1: full append → replay cycle uses only PG; duckdb absent from sys.modules."""
    from sdd.infra.event_log import sdd_append, sdd_replay

    sdd_append(
        "ErrorOccurred",
        {"msg": "enforcement-test-event", "phase": 46},
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    events = sdd_replay(db_path=tmp_db_path, level="L1")
    assert any(e.get("event_type") == "ErrorOccurred" for e in events), (
        "Appended event not found in replay"
    )

    assert "duckdb" not in sys.modules, (
        "I-NO-DUCKDB-1: duckdb module was imported during PG pipeline execution"
    )


@pytest.mark.pg
def test_pg_rebuild_state_from_scratch(tmp_db_path: str) -> None:
    """I-REPLAY-1 / I-NO-DUCKDB-1: get_current_state() rebuilds correct state via pure replay.

    Appends a PhaseInitialized event then verifies reduce() reconstructs phase_current=46.
    duckdb must not appear in sys.modules after the operation.
    """
    from sdd.infra.event_log import sdd_append
    from sdd.infra.projections import get_current_state

    sdd_append(
        "PhaseInitialized",
        {
            "phase_id": 46,
            "tasks_total": 10,
            "plan_version": 46,
            "actor": "human",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        db_path=tmp_db_path,
        level="L1",
        event_source="runtime",
    )

    state = get_current_state(tmp_db_path)
    assert state.phase_current == 46, (
        f"I-REPLAY-1: expected phase_current=46 after replay, got {state.phase_current}"
    )
    assert state.phase_status == "ACTIVE", (
        f"I-REPLAY-1: expected phase_status=ACTIVE after replay, got {state.phase_status}"
    )

    assert "duckdb" not in sys.modules, (
        "I-NO-DUCKDB-1: duckdb module was imported during state rebuild"
    )
