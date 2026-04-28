from __future__ import annotations

import os
from typing import Any


def is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def resolve_pg_url(db_url: str | None = None) -> str:
    """Resolve DB URL from argument or SDD_DATABASE_URL env var (I-DB-1)."""
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


# Private alias — callers migrated in T-4203
_resolve_url = resolve_pg_url


def open_db_connection(
    db_url: str | None = None,
    project: str | None = None,
    schema: str | None = None,
) -> Any:
    """Open DB connection routing by URL scheme.

    URL resolution (I-DB-1):
      1. db_url argument (explicit non-empty)
      2. SDD_DATABASE_URL environment variable
      → ValueError if neither is set

    Routing:
      postgresql:// | postgres:// → psycopg3
      :memory: | file path        → DuckDB

    I-DB-TEST-2: postgres connections use timeout_secs=0.0 in test context.
    """
    resolved = resolve_pg_url(db_url)
    if is_postgres_url(resolved):
        # I-DB-TEST-2: fail-fast in test context
        timeout_secs: float | None = 0.0 if os.environ.get("PYTEST_CURRENT_TEST") else None
        return _open_postgres(resolved, project, schema, timeout_secs=timeout_secs)
    return _open_duckdb(resolved)


def _open_postgres(
    db_url: str,
    project: str | None,
    schema: str | None,
    timeout_secs: float | None = None,
) -> Any:
    """Connect via psycopg3; apply search_path."""
    try:
        import psycopg
    except ImportError as exc:
        raise ImportError(
            "psycopg3 is required for PostgreSQL support. "
            "Install with: pip install 'psycopg[binary]'"
        ) from exc

    resolved_project = project or os.environ.get("SDD_PROJECT", "")
    db_schema = schema or (f"p_{resolved_project}" if resolved_project else None)
    connect_timeout = int(timeout_secs) if timeout_secs is not None else None

    kwargs: dict[str, Any] = {}
    if connect_timeout is not None:
        kwargs["connect_timeout"] = connect_timeout
    conn = psycopg.connect(db_url, **kwargs)
    if db_schema:
        conn.execute(f"SET search_path = {db_schema}, shared")
        conn.commit()
    return conn


def _open_duckdb(db_url: str) -> Any:
    """Connect to DuckDB (file path or :memory:)."""
    import duckdb

    return duckdb.connect(db_url)


# Deprecated — callers migrated to open_db_connection in T-4203
open_sdd_connection = open_db_connection
