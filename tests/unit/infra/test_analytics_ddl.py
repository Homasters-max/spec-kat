"""DDL validation for migration 005_analytics_schema — I-DB-SCHEMA-1.

Acceptance (T-3214):
  test_analytics_ddl: CREATE SCHEMA analytics; views all_events, all_tasks, all_phases,
  all_invariants created with explicit col_map (SELECT * forbidden).
"""
from __future__ import annotations

import pathlib
import re

_MIGRATION_FILE = pathlib.Path("src/sdd/db/migrations/005_analytics_schema.sql")


def _load_sql() -> str:
    return _MIGRATION_FILE.read_text()


def test_analytics_ddl_file_exists() -> None:
    assert _MIGRATION_FILE.exists(), f"Migration file not found: {_MIGRATION_FILE}"


def test_analytics_schema_created() -> None:
    sql = _load_sql()
    assert re.search(r"CREATE\s+SCHEMA\s+analytics\b", sql, re.IGNORECASE), (
        "CREATE SCHEMA analytics not found in 005_analytics_schema.sql"
    )


def test_all_events_view_defined() -> None:
    sql = _load_sql()
    assert re.search(r"CREATE\s+VIEW\s+analytics\.all_events\b", sql, re.IGNORECASE), (
        "analytics.all_events VIEW not found in 005_analytics_schema.sql"
    )


def test_all_tasks_view_defined() -> None:
    sql = _load_sql()
    assert re.search(r"CREATE\s+VIEW\s+analytics\.all_tasks\b", sql, re.IGNORECASE), (
        "analytics.all_tasks VIEW not found in 005_analytics_schema.sql"
    )


def test_all_phases_view_defined() -> None:
    sql = _load_sql()
    assert re.search(r"CREATE\s+VIEW\s+analytics\.all_phases\b", sql, re.IGNORECASE), (
        "analytics.all_phases VIEW not found in 005_analytics_schema.sql"
    )


def test_all_invariants_view_defined() -> None:
    sql = _load_sql()
    assert re.search(r"CREATE\s+VIEW\s+analytics\.all_invariants\b", sql, re.IGNORECASE), (
        "analytics.all_invariants VIEW not found in 005_analytics_schema.sql"
    )


def test_no_select_star() -> None:
    """I-DB-SCHEMA-1: SELECT * is forbidden — all views must use explicit col_map."""
    sql = _load_sql()
    lines = sql.splitlines()
    violations: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        if re.search(r"\bSELECT\s+\*", stripped, re.IGNORECASE):
            violations.append(stripped)
    assert not violations, (
        "I-DB-SCHEMA-1 violated: SELECT * is forbidden — use explicit column list:\n"
        + "\n".join(violations)
    )


def test_all_views_reference_p_sdd_tables() -> None:
    """All analytics views must source from p_sdd schema tables."""
    sql = _load_sql()
    assert re.search(r"\bp_sdd\.", sql, re.IGNORECASE), (
        "No p_sdd schema references found — views must be derived from p_sdd tables"
    )
