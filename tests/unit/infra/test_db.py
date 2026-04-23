from __future__ import annotations

import pytest

from sdd.infra.db import open_sdd_connection

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
    import duckdb

    conn: duckdb.DuckDBPyConnection = in_memory_db  # type: ignore[assignment]
    rows = conn.execute("PRAGMA table_info('events')").fetchall()
    cols = {row[1] for row in rows}
    assert _V2_COLUMNS.issubset(cols), f"Missing columns: {_V2_COLUMNS - cols}"


def test_seq_monotonic(tmp_db_path: str) -> None:
    """I-EL-5b: seq must be strictly increasing across 3 separate reconnections."""
    seq_values: list[int] = []

    for _ in range(3):
        conn = open_sdd_connection(tmp_db_path)
        import json, time

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
