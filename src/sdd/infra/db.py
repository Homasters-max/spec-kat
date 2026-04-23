from __future__ import annotations

import duckdb

from sdd.infra.paths import event_store_file

# Safety floor for sequence restart — never let the sequence start below this.
# Update only when the DuckDB file is recreated or events are manually deleted:
# set to MAX(seq)+1 from the new DB state. See CLAUDE.md §0.12 SDD-SEQ-1.
SDD_SEQ_CHECKPOINT: int = 1

# v2 schema — all columns present on fresh install.
# Migrations below upgrade v1 databases to v2.
_SDD_DDL = """
CREATE SEQUENCE IF NOT EXISTS sdd_event_seq START 1;

CREATE TABLE IF NOT EXISTS events (
    seq                BIGINT   NOT NULL PRIMARY KEY,
    partition_key      VARCHAR  NOT NULL DEFAULT 'sdd',
    event_id           VARCHAR  NOT NULL UNIQUE,
    event_type         VARCHAR  NOT NULL,
    payload            VARCHAR  NOT NULL,
    schema_version     INTEGER  NOT NULL DEFAULT 1,
    appended_at        BIGINT   NOT NULL,
    level              VARCHAR  DEFAULT NULL,
    event_source       VARCHAR  NOT NULL DEFAULT 'runtime',
    caused_by_meta_seq BIGINT   DEFAULT NULL,
    expired            BOOLEAN  NOT NULL DEFAULT FALSE
)
"""

# Additive-only — never DROP or ALTER existing columns.
# Migration 2: level + expired (I-EL-7/expired TTL)
# Migration 3: event_source + caused_by_meta_seq (I-EL-1, I-EL-8)
SDD_MIGRATION_REGISTRY: list[tuple[int, str]] = [
    (2, "ALTER TABLE events ADD COLUMN IF NOT EXISTS level VARCHAR DEFAULT NULL"),
    (2, "ALTER TABLE events ADD COLUMN IF NOT EXISTS expired BOOLEAN DEFAULT FALSE"),
    (3, "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_source VARCHAR DEFAULT 'runtime'"),
    (3, "ALTER TABLE events ADD COLUMN IF NOT EXISTS caused_by_meta_seq BIGINT DEFAULT NULL"),
    (4, "ALTER TABLE events ADD COLUMN IF NOT EXISTS batch_id TEXT DEFAULT NULL"),
]


def open_sdd_connection(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) a DuckDB connection and ensure the v2 schema is present.

    Idempotent: N calls on the same path all succeed with identical schema (I-PK-1).
    Restarts the sequence on every call so seq is strictly increasing across
    reconnections (I-EL-5b). See CLAUDE.md §0.12 SDD-SEQ-1.
    """
    if db_path is None:
        db_path = str(event_store_file())
    conn = duckdb.connect(db_path)
    ensure_sdd_schema(conn)
    _restart_sequence(conn)
    return conn


def _restart_sequence(conn: duckdb.DuckDBPyConnection) -> None:
    """Recreate sdd_event_seq starting at max(SDD_SEQ_CHECKPOINT, current_max + 1)."""
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
    current_max: int = row[0] if row and row[0] is not None else 0
    next_seq = max(SDD_SEQ_CHECKPOINT, current_max + 1)
    conn.execute(f"CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}")


def ensure_sdd_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the events table + sequence if absent, then run pending migrations."""
    conn.execute(_SDD_DDL)

    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(schema_version), 0) FROM events"
        ).fetchone()
        stored_version: int = row[0] if row and row[0] is not None else 0
    except Exception:
        stored_version = 0

    for target_version, ddl in SDD_MIGRATION_REGISTRY:
        if target_version > stored_version:
            conn.execute(ddl)
