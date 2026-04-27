#!/usr/bin/env python3
"""Migrate SDD events from DuckDB to PostgreSQL.

Modes:
  --export   Validate all DuckDB payloads as JSON; print count; exit 1 on invalid.
  --migrate  Full row-by-row copy DuckDB → PostgreSQL (requires --pg-url).
  --import   Copy DuckDB → PostgreSQL with JSONB payload column; verify count match.

Usage:
  python scripts/migrate_duckdb_to_pg.py --export --duckdb-url .sdd/state/sdd_events.duckdb
  python scripts/migrate_duckdb_to_pg.py --migrate \\
      --duckdb-url .sdd/state/sdd_events.duckdb \\
      --pg-url postgresql://user:pass@host/dbname \\
      [--pg-schema p_myproject]
  python scripts/migrate_duckdb_to_pg.py --import \\
      --duckdb-url .sdd/state/sdd_events.duckdb \\
      --pg-url postgresql://user:pass@host/dbname \\
      [--pg-schema p_myproject]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root without installing the package.
_repo_root = Path(__file__).parent.parent
if str(_repo_root / "src") not in sys.path:
    sys.path.insert(0, str(_repo_root / "src"))

from sdd.db.connection import open_sdd_connection  # noqa: E402

_COLUMNS = (
    "seq",
    "partition_key",
    "event_id",
    "event_type",
    "payload",
    "schema_version",
    "appended_at",
    "level",
    "expired",
    "event_source",
    "caused_by_meta_seq",
    "batch_id",
)

_SELECT_ALL = f"SELECT {', '.join(_COLUMNS)} FROM events ORDER BY seq"

_PG_CREATE = """
CREATE TABLE IF NOT EXISTS events (
    seq               BIGSERIAL PRIMARY KEY,
    partition_key     VARCHAR   NOT NULL DEFAULT 'default',
    event_id          VARCHAR   NOT NULL,
    event_type        VARCHAR   NOT NULL,
    payload           TEXT      NOT NULL,
    schema_version    INTEGER   NOT NULL DEFAULT 1,
    appended_at       BIGINT    NOT NULL,
    level             VARCHAR,
    expired           BOOLEAN   NOT NULL DEFAULT FALSE,
    event_source      VARCHAR   NOT NULL DEFAULT 'runtime',
    caused_by_meta_seq BIGINT,
    batch_id          VARCHAR
)
"""

_PG_INSERT = """
INSERT INTO events
    (seq, partition_key, event_id, event_type, payload,
     schema_version, appended_at, level, expired,
     event_source, caused_by_meta_seq, batch_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (seq) DO NOTHING
"""

_PG_CREATE_JSONB = """
CREATE TABLE IF NOT EXISTS events (
    seq               BIGSERIAL PRIMARY KEY,
    partition_key     VARCHAR   NOT NULL DEFAULT 'default',
    event_id          VARCHAR   NOT NULL,
    event_type        VARCHAR   NOT NULL,
    payload           JSONB     NOT NULL,
    schema_version    INTEGER   NOT NULL DEFAULT 1,
    appended_at       BIGINT    NOT NULL,
    level             VARCHAR,
    expired           BOOLEAN   NOT NULL DEFAULT FALSE,
    event_source      VARCHAR   NOT NULL DEFAULT 'runtime',
    caused_by_meta_seq BIGINT,
    batch_id          VARCHAR
)
"""

_PG_INSERT_JSONB = """
INSERT INTO events
    (seq, partition_key, event_id, event_type, payload,
     schema_version, appended_at, level, expired,
     event_source, caused_by_meta_seq, batch_id)
VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (seq) DO NOTHING
"""

_BATCH_SIZE = 500


def _fetch_all_rows(duck_conn: Any) -> list[tuple]:
    return duck_conn.execute(_SELECT_ALL).fetchall()


def _validate_payload(row: tuple, col_index: int) -> None:
    """Raise ValueError if payload is not valid JSON."""
    seq = row[0]
    payload = row[col_index]
    if not isinstance(payload, str):
        raise ValueError(
            f"Row seq={seq}: payload is not a string (got {type(payload).__name__!r})"
        )
    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Row seq={seq}: invalid JSON in payload — {exc}\n"
            f"  payload preview: {payload[:200]!r}"
        ) from exc


def cmd_export(duckdb_url: str) -> None:
    """Validate all payloads; print count; exit 1 on first invalid row."""
    duck_conn = open_sdd_connection(db_url=duckdb_url)
    try:
        rows = _fetch_all_rows(duck_conn)
    finally:
        duck_conn.close()

    payload_idx = _COLUMNS.index("payload")
    invalid: list[str] = []
    for row in rows:
        try:
            _validate_payload(row, payload_idx)
        except ValueError as exc:
            invalid.append(str(exc))

    exported = len(rows)
    print(f"DuckDB events: {exported}")
    print(f"Validated:     {exported}")

    if invalid:
        print(f"\nInvalid JSON payloads ({len(invalid)}):", file=sys.stderr)
        for msg in invalid:
            print(f"  {msg}", file=sys.stderr)
        sys.exit(1)

    print("All payloads are valid JSON.")


def cmd_migrate(duckdb_url: str, pg_url: str, pg_schema: str | None) -> None:
    """Copy all events from DuckDB to PostgreSQL."""
    duck_conn = open_sdd_connection(db_url=duckdb_url)
    try:
        rows = _fetch_all_rows(duck_conn)
    finally:
        duck_conn.close()

    payload_idx = _COLUMNS.index("payload")
    invalid: list[str] = []
    for row in rows:
        try:
            _validate_payload(row, payload_idx)
        except ValueError as exc:
            invalid.append(str(exc))

    if invalid:
        print(f"Aborting: {len(invalid)} row(s) have invalid JSON payload:", file=sys.stderr)
        for msg in invalid:
            print(f"  {msg}", file=sys.stderr)
        sys.exit(1)

    pg_conn = open_sdd_connection(db_url=pg_url, schema=pg_schema)
    try:
        cur = pg_conn.cursor()
        cur.execute(_PG_CREATE)

        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start : start + _BATCH_SIZE]
            cur.executemany(_PG_INSERT, batch)
            pg_conn.commit()
            end = min(start + _BATCH_SIZE, len(rows))
            print(f"  Inserted rows {start + 1}–{end} / {len(rows)}")

        print(f"Migration complete: {len(rows)} rows → PostgreSQL.")
    finally:
        pg_conn.close()


def cmd_import(duckdb_url: str, pg_url: str, pg_schema: str | None) -> None:
    """Copy all events from DuckDB to PostgreSQL with JSONB payload; verify count match."""
    duck_conn = open_sdd_connection(db_url=duckdb_url)
    try:
        rows = _fetch_all_rows(duck_conn)
    finally:
        duck_conn.close()

    payload_idx = _COLUMNS.index("payload")
    invalid: list[str] = []
    for row in rows:
        try:
            _validate_payload(row, payload_idx)
        except ValueError as exc:
            invalid.append(str(exc))

    if invalid:
        print(f"Aborting: {len(invalid)} row(s) have invalid JSON payload:", file=sys.stderr)
        for msg in invalid:
            print(f"  {msg}", file=sys.stderr)
        sys.exit(1)

    export_count = len(rows)

    pg_conn = open_sdd_connection(db_url=pg_url, schema=pg_schema)
    try:
        cur = pg_conn.cursor()
        cur.execute(_PG_CREATE_JSONB)

        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start : start + _BATCH_SIZE]
            cur.executemany(_PG_INSERT_JSONB, batch)
            pg_conn.commit()
            end = min(start + _BATCH_SIZE, len(rows))
            print(f"  Inserted rows {start + 1}–{end} / {len(rows)}")

        cur.execute("SELECT COUNT(*) FROM events")
        pg_count = cur.fetchone()[0]
        pg_conn.commit()
    finally:
        pg_conn.close()

    if pg_count != export_count:
        print(
            f"Count mismatch: DuckDB={export_count}, PostgreSQL={pg_count}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Import complete: {export_count} rows → PostgreSQL (JSONB payload).")
    print(f"count(Postgres)={pg_count} == count(export)={export_count}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate SDD events DuckDB → PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--export",
        action="store_true",
        help="Validate all DuckDB payloads as JSON and print count.",
    )
    mode.add_argument(
        "--migrate",
        action="store_true",
        help="Copy all rows from DuckDB to PostgreSQL.",
    )
    mode.add_argument(
        "--import",
        action="store_true",
        dest="import_mode",
        help="Copy all rows from DuckDB to PostgreSQL with JSONB payload; verify count match.",
    )
    p.add_argument(
        "--duckdb-url",
        required=True,
        help="DuckDB file path (passed to open_sdd_connection).",
    )
    p.add_argument(
        "--pg-url",
        help="PostgreSQL connection URL (required for --migrate).",
    )
    p.add_argument(
        "--pg-schema",
        default=None,
        help="PostgreSQL search_path schema (optional).",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.migrate and not args.pg_url:
        parser.error("--migrate requires --pg-url")
    if args.import_mode and not args.pg_url:
        parser.error("--import requires --pg-url")

    if args.export:
        cmd_export(args.duckdb_url)
    elif args.migrate:
        cmd_migrate(args.duckdb_url, args.pg_url, args.pg_schema)
    elif args.import_mode:
        cmd_import(args.duckdb_url, args.pg_url, args.pg_schema)


if __name__ == "__main__":
    main()
