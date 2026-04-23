from __future__ import annotations

import json
import subprocess
import time
import uuid

import duckdb
import pytest

from sdd.infra.db import SDD_SEQ_CHECKPOINT, _restart_sequence, ensure_sdd_schema, open_sdd_connection

_V2_COLUMNS = {
    "seq",
    "partition_key",
    "event_id",
    "event_type",
    "payload",
    "schema_version",
    "appended_at",
    "level",
    "event_source",
    "caused_by_meta_seq",
    "expired",
}


def test_open_connection_idempotent(tmp_db_path: str) -> None:
    """I-PK-1: opening the same path twice yields identical schema without error."""
    conn1 = open_sdd_connection(tmp_db_path)
    cols1 = {row[1] for row in conn1.execute("PRAGMA table_info('events')").fetchall()}
    conn1.close()

    conn2 = open_sdd_connection(tmp_db_path)
    cols2 = {row[1] for row in conn2.execute("PRAGMA table_info('events')").fetchall()}
    conn2.close()

    assert cols1 == cols2
    assert _V2_COLUMNS.issubset(cols1)


def test_schema_has_v2_columns(in_memory_db: object) -> None:
    """All v2 columns must be present on a fresh connection."""
    conn: duckdb.DuckDBPyConnection = in_memory_db  # type: ignore[assignment]
    rows = conn.execute("PRAGMA table_info('events')").fetchall()
    cols = {row[1] for row in rows}
    assert _V2_COLUMNS.issubset(cols), f"Missing columns: {_V2_COLUMNS - cols}"


def test_seq_monotonic(tmp_db_path: str) -> None:
    """I-EL-5b: seq must be strictly increasing across 3 separate reconnections."""
    seq_values: list[int] = []

    for _ in range(3):
        conn = open_sdd_connection(tmp_db_path)
        ts = int(time.time() * 1000)
        event_id = f"test-{ts}-{len(seq_values)}"
        conn.execute(
            "INSERT INTO events (seq, event_id, event_type, payload, appended_at) "
            "VALUES (nextval('sdd_event_seq'), ?, 'TestEvent', ?, ?)",
            [event_id, json.dumps({}), ts],
        )
        row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
        assert row is not None
        seq_values.append(row[0])
        conn.close()

    assert seq_values == sorted(seq_values), f"seq not monotonic: {seq_values}"
    assert len(set(seq_values)) == 3, f"seq values not unique: {seq_values}"


def _insert_event(conn: duckdb.DuckDBPyConnection, seq: int) -> None:
    """Insert a minimal event row with an explicit seq value."""
    conn.execute(
        "INSERT INTO events (seq, event_id, event_type, payload, appended_at) "
        "VALUES (?, ?, 'TestEvent', '{}', ?)",
        [seq, str(uuid.uuid4()), int(time.time() * 1000)],
    )


def test_restart_sequence_continues_from_latest_seq(tmp_db_path: str) -> None:
    """_restart_sequence restarts the sequence above the current MAX(seq) (sdd_latest_seq equivalent)."""
    conn = open_sdd_connection(tmp_db_path)
    latest_seq = 50
    _insert_event(conn, latest_seq)

    _restart_sequence(conn)

    next_val = conn.execute("SELECT nextval('sdd_event_seq')").fetchone()[0]
    assert next_val == latest_seq + 1, (
        f"Sequence should restart at latest_seq+1 ({latest_seq + 1}), got {next_val}"
    )
    conn.close()


def test_restart_sequence_respects_checkpoint_floor(tmp_path) -> None:
    """_restart_sequence uses SDD_SEQ_CHECKPOINT as the minimum floor when events table is empty."""
    db_path = str(tmp_path / "floor_test.duckdb")
    conn = duckdb.connect(db_path)
    ensure_sdd_schema(conn)

    _restart_sequence(conn)

    next_val = conn.execute("SELECT nextval('sdd_event_seq')").fetchone()[0]
    assert next_val >= SDD_SEQ_CHECKPOINT, (
        f"Sequence {next_val} is below SDD_SEQ_CHECKPOINT floor ({SDD_SEQ_CHECKPOINT})"
    )
    conn.close()


def test_restart_sequence_above_checkpoint_when_db_has_higher_seq(tmp_path) -> None:
    """_restart_sequence picks max(SDD_SEQ_CHECKPOINT, latest_seq+1)."""
    db_path = str(tmp_path / "high_seq_test.duckdb")
    conn = duckdb.connect(db_path)
    ensure_sdd_schema(conn)

    latest_seq = SDD_SEQ_CHECKPOINT + 100
    _insert_event(conn, latest_seq)
    _restart_sequence(conn)

    next_val = conn.execute("SELECT nextval('sdd_event_seq')").fetchone()[0]
    assert next_val == latest_seq + 1, (
        f"Expected latest_seq+1 ({latest_seq + 1}), got {next_val}"
    )
    conn.close()


def test_dep_audit_no_sdd_db_in_src() -> None:
    """I-DEP-AUDIT-1: no live src/ code references legacy sdd_db or sdd_event_log modules."""
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", r"sdd_db\|sdd_event_log", "src/"],
        capture_output=True, text=True,
    )
    # Filter out any _deprecated_tools references (they are historical, not live callers)
    live_matches = [
        line for line in result.stdout.splitlines()
        if "_deprecated_tools" not in line and "__pycache__" not in line
    ]
    assert not live_matches, (
        f"I-DEP-AUDIT-1: live src/ references to sdd_db/sdd_event_log found:\n"
        + "\n".join(live_matches)
    )
