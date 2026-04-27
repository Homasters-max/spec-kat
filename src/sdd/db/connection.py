from __future__ import annotations

import os
from typing import Any


def open_sdd_connection(
    db_url: str | None = None,
    project: str | None = None,
    schema: str | None = None,
) -> Any:
    """Open SDD connection routing by URL scheme.

    URL resolution (I-DB-1):
      1. db_url argument (explicit non-empty)
      2. SDD_DATABASE_URL environment variable
      → ValueError if neither is set

    Routing:
      postgresql:// | postgres:// → psycopg3 (psycopg2 fallback)
      :memory: | file path        → DuckDB
    """
    resolved = _resolve_url(db_url)
    if _is_postgres(resolved):
        return _open_postgres(resolved, project, schema)
    return _open_duckdb(resolved)


def _resolve_url(db_url: str | None) -> str:
    if db_url is not None:
        if not db_url:
            raise ValueError("I-DB-1 violated: db_url must be non-empty")
        return db_url
    env = os.environ.get("SDD_DATABASE_URL", "")
    if env:
        return env
    raise ValueError(
        "I-DB-1 violated: db_url is None and SDD_DATABASE_URL is not set"
    )


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def _open_postgres(db_url: str, project: str | None, schema: str | None) -> Any:
    """Connect via psycopg3 (preferred) or psycopg2 fallback; apply search_path."""
    resolved_project = project or os.environ.get("SDD_PROJECT", "")
    db_schema = schema or (f"p_{resolved_project}" if resolved_project else None)

    try:
        import psycopg  # psycopg3
        conn = psycopg.connect(db_url)
        if db_schema:
            conn.execute(f"SET search_path = {db_schema}, shared")
            conn.commit()
        return conn
    except ImportError:
        pass

    import psycopg2
    conn = psycopg2.connect(db_url)
    if db_schema:
        cur = conn.cursor()
        cur.execute(f"SET search_path = {db_schema}, shared")
        conn.commit()
    return conn


def _open_duckdb(db_url: str) -> Any:
    """Connect to DuckDB (file path or :memory:)."""
    import duckdb
    return duckdb.connect(db_url)
