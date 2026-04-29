from __future__ import annotations

from typing import Any

from sdd.db.connection import is_postgres_url, open_db_connection


def open_sdd_connection(
    db_path: str,
    timeout_secs: float = 10.0,
    read_only: bool = False,
) -> Any:
    """Open a DB connection. Only PostgreSQL URLs are supported (I-NO-DUCKDB-1).

    Raises ValueError for non-PostgreSQL paths.
    """
    if not db_path:
        raise ValueError("I-DB-1 violated")
    if is_postgres_url(db_path):
        return open_db_connection(db_path)
    raise ValueError(
        f"I-NO-DUCKDB-1 violated: only PostgreSQL URLs are supported, got '{db_path}'"
    )
