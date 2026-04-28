from __future__ import annotations

import os
import time
from typing import Any

from sdd.infra.paths import is_production_event_store

_LOCK_RETRY_INTERVAL = 0.25  # seconds between retries
_LOCK_ERROR_MARKER = "Could not set lock"


class DuckDBLockTimeoutError(RuntimeError):
    """Raised when open_sdd_connection cannot acquire DuckDB file lock within timeout_secs."""

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
    expired            BOOLEAN  NOT NULL DEFAULT FALSE,
    batch_id           TEXT     DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS sdd_schema_meta (
    key   VARCHAR NOT NULL PRIMARY KEY,
    value INTEGER NOT NULL
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

_MAX_SCHEMA_VERSION: int = max(v for v, _ in SDD_MIGRATION_REGISTRY)


def open_sdd_connection(
    db_path: str,
    timeout_secs: float = 10.0,
    read_only: bool = False,
) -> Any:
    """Open (or create) a DB connection and ensure schema is present.

    Routes PG URLs to sdd.db.connection.open_db_connection (BC-43-B).
    For DuckDB paths: idempotent schema setup, sequence restart, lock retry.

    read_only=True: skips _restart_sequence for callers that never INSERT.

    Retries up to timeout_secs if the file lock is held by another process,
    sleeping _LOCK_RETRY_INTERVAL between attempts. Non-lock errors raise immediately.
    """
    if not db_path:
        raise ValueError("I-DB-1 violated")
    from sdd.db.connection import is_postgres_url, open_db_connection
    if is_postgres_url(db_path):
        return open_db_connection(db_path)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        timeout_secs = 0.0
        if is_production_event_store(db_path):
            raise RuntimeError(
                f"I-DB-TEST-1 violated: test must not open production DB '{db_path}'"
            )
    import duckdb  # lazy — only reached in DuckDB branch (I-LAZY-DUCK-1)
    # In-memory connections have no file lock — skip retry entirely (I-LOCK-2)
    if db_path == ":memory:":
        conn = duckdb.connect(db_path)
        ensure_sdd_schema(conn)
        if not read_only:
            _restart_sequence(conn)
        return conn
    deadline = time.monotonic() + timeout_secs
    last_exc: Exception | None = None
    while True:
        try:
            conn = duckdb.connect(db_path)
            ensure_sdd_schema(conn)
            if not read_only:
                _restart_sequence(conn)
            return conn
        except duckdb.IOException as exc:
            if _LOCK_ERROR_MARKER not in str(exc):
                raise
            last_exc = exc
            if time.monotonic() >= deadline:
                raise DuckDBLockTimeoutError(
                    f"DuckDB lock timeout after {timeout_secs}s on '{db_path}': {last_exc}"
                )
            time.sleep(_LOCK_RETRY_INTERVAL)
    raise AssertionError("unreachable")  # noqa: unreachable


def _restart_sequence(conn: Any) -> None:
    """Recreate sdd_event_seq starting at max(SDD_SEQ_CHECKPOINT, current_max + 1)."""
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()
    current_max: int = row[0] if row and row[0] is not None else 0
    next_seq = max(SDD_SEQ_CHECKPOINT, current_max + 1)
    conn.execute(f"CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}")


def ensure_sdd_schema(conn: Any) -> None:
    """Create the events table + sequence if absent, then run pending migrations.

    Schema version is persisted in sdd_schema_meta so migrations run at most once
    per DB file (not on every open_sdd_connection call).  This prevents DDL-lock
    storms in Hypothesis tests where hundreds of connections are opened per run.
    """
    conn.execute(_SDD_DDL)

    # Fast path: read version from meta table written on a previous connection.
    need_meta_write = False
    try:
        row = conn.execute(
            "SELECT value FROM sdd_schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        stored_version: int = row[0] if row else -1
    except Exception:
        stored_version = -1

    if stored_version < 0:
        # Meta table absent or empty: first connection to this DB file.
        # Always fall back to MAX(schema_version) — covers both fresh DBs (returns 0,
        # migrations are no-ops via IF NOT EXISTS) and legacy DBs (runs pending ALTERs).
        need_meta_write = True
        try:
            ver_row = conn.execute(
                "SELECT COALESCE(MAX(schema_version), 0) FROM events"
            ).fetchone()
            stored_version = ver_row[0] if ver_row and ver_row[0] is not None else 0
        except Exception:
            stored_version = 0

    pending = [(v, ddl) for v, ddl in SDD_MIGRATION_REGISTRY if v > stored_version]
    if pending:
        # DuckDB forbids ALTER TABLE when an index exists; drop it first and recreate below.
        conn.execute("DROP INDEX IF EXISTS idx_event_type")
        for _, ddl in pending:
            conn.execute(ddl)
        need_meta_write = True

    if need_meta_write:
        # Index is created once per DB file alongside the meta record.
        # Subsequent connections skip both (fast path: index already present).
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON events (event_type)")
        conn.execute(
            "INSERT INTO sdd_schema_meta (key, value) VALUES ('schema_version', ?)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            [_MAX_SCHEMA_VERSION],
        )
