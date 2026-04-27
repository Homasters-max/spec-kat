"""DDL validation for migration 004_artifacts_schema — I-EVENT-DERIVE-1, I-DB-SCHEMA-1.

Acceptance (T-3207):
  test_artifacts_ddl: tables specs, specs_draft, invariants, invariants_current
  are defined; invariants_current is a VIEW referencing invariants.
"""
from __future__ import annotations

import pathlib
import re

_MIGRATION_FILE = pathlib.Path("src/sdd/db/migrations/004_artifacts_schema.sql")


def _load_sql() -> str:
    return _MIGRATION_FILE.read_text()


def test_artifacts_ddl_file_exists() -> None:
    """Migration file 004_artifacts_schema.sql must exist."""
    assert _MIGRATION_FILE.exists(), f"Migration file not found: {_MIGRATION_FILE}"


def test_specs_table_defined() -> None:
    """CREATE TABLE p_sdd.specs must be present in the migration."""
    sql = _load_sql()
    assert re.search(r"CREATE\s+TABLE\s+p_sdd\.specs\b", sql, re.IGNORECASE), (
        "p_sdd.specs table definition not found in 004_artifacts_schema.sql"
    )


def test_specs_draft_table_defined() -> None:
    """CREATE TABLE p_sdd.specs_draft must be present in the migration."""
    sql = _load_sql()
    assert re.search(r"CREATE\s+TABLE\s+p_sdd\.specs_draft\b", sql, re.IGNORECASE), (
        "p_sdd.specs_draft table definition not found in 004_artifacts_schema.sql"
    )


def test_invariants_table_defined() -> None:
    """CREATE TABLE p_sdd.invariants must be present in the migration."""
    sql = _load_sql()
    assert re.search(r"CREATE\s+TABLE\s+p_sdd\.invariants\b", sql, re.IGNORECASE), (
        "p_sdd.invariants table definition not found in 004_artifacts_schema.sql"
    )


def test_invariants_current_is_view() -> None:
    """invariants_current must be defined as a VIEW (not a standalone table)."""
    sql = _load_sql()
    assert re.search(r"CREATE\s+VIEW\s+p_sdd\.invariants_current\b", sql, re.IGNORECASE), (
        "p_sdd.invariants_current must be a VIEW in 004_artifacts_schema.sql"
    )


def test_invariants_current_references_invariants() -> None:
    """invariants_current VIEW body must reference p_sdd.invariants (FK semantics)."""
    sql = _load_sql()
    match = re.search(
        r"CREATE\s+VIEW\s+p_sdd\.invariants_current\b(.+)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, "p_sdd.invariants_current VIEW definition not found"
    view_body = match.group(1)
    assert re.search(r"\bp_sdd\.invariants\b", view_body, re.IGNORECASE), (
        "invariants_current VIEW must reference p_sdd.invariants in its body"
    )


def test_no_defaults_on_status_columns() -> None:
    """I-EVENT-DERIVE-1: status/result columns must have no DEFAULT in the migration."""
    sql = _load_sql()
    lines = sql.splitlines()
    violations: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lower = stripped.lower()
        if re.search(r"\b(status|result)\b", lower) and "default" in lower:
            violations.append(stripped)
    assert not violations, (
        "I-EVENT-DERIVE-1 violated: status/result columns must not have DEFAULT "
        f"(set explicitly from event):\n" + "\n".join(violations)
    )
