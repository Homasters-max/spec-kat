"""Tests for event_log query extensions: exists_command, exists_semantic, get_error_count.

Invariants covered: I-CMD-10, I-CMD-2b, I-EL-9
Spec ref: Spec_v4 §4.14, §9 Verification row 2b
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from sdd.infra.db import open_sdd_connection
from sdd.core.json_utils import canonical_json
from sdd.infra.event_log import (
    exists_command,
    exists_semantic,
    get_error_count,
    sdd_append,
)


def test_exists_command_returns_false_when_absent(tmp_db_path: str) -> None:
    """exists_command returns False when no event carries that command_id."""
    assert exists_command(tmp_db_path, "cmd-absent") is False


def test_exists_command_returns_true_after_append(tmp_db_path: str) -> None:
    """exists_command returns True after an event with matching payload.command_id is appended."""
    sdd_append(
        "TaskImplemented",
        {"command_id": "cmd-001", "task_id": "T-001"},
        db_path=tmp_db_path,
        level="L1",
    )
    assert exists_command(tmp_db_path, "cmd-001") is True


def test_exists_semantic_returns_false_when_absent(tmp_db_path: str) -> None:
    """exists_semantic returns False when no matching (command_type, task_id, phase_id, hash) event exists."""
    assert exists_semantic(tmp_db_path, "TaskImplemented", "T-001", 4, "no-such-hash") is False


def test_exists_semantic_prevents_duplicate_effect(tmp_db_path: str) -> None:
    """exists_semantic returns True after a matching event is stored, blocking semantic duplicates (I-CMD-2b)."""
    fields = {"phase_id": 4, "result": "DONE", "task_id": "T-002"}
    payload_hash = hashlib.sha256(canonical_json(fields).encode()).hexdigest()
    sdd_append(
        "TaskImplemented",
        {
            "command_id": "cmd-002",
            "task_id": "T-002",
            "phase_id": 4,
            "payload_hash": payload_hash,
        },
        db_path=tmp_db_path,
        level="L1",
    )
    assert exists_semantic(tmp_db_path, "TaskImplemented", "T-002", 4, payload_hash) is True


def test_exists_semantic_different_hash_not_blocked(tmp_db_path: str) -> None:
    """A retry with changed meaningful fields (different hash) is NOT blocked (I-CMD-2b)."""
    pass_hash = hashlib.sha256(canonical_json({"result": "PASS"}).encode()).hexdigest()
    fail_hash = hashlib.sha256(canonical_json({"result": "FAIL"}).encode()).hexdigest()
    sdd_append(
        "TaskValidated",
        {"command_id": "cmd-003", "task_id": "T-003", "phase_id": 4, "payload_hash": pass_hash},
        db_path=tmp_db_path,
        level="L1",
    )
    assert exists_semantic(tmp_db_path, "TaskValidated", "T-003", 4, pass_hash) is True
    assert exists_semantic(tmp_db_path, "TaskValidated", "T-003", 4, fail_hash) is False


def test_get_error_count_zero_on_no_errors(tmp_db_path: str) -> None:
    """get_error_count returns 0 when no ErrorEvent exists for the given command_id."""
    assert get_error_count(tmp_db_path, "cmd-no-errors") == 0


def test_get_error_count_increments(tmp_db_path: str) -> None:
    """get_error_count increments for each ErrorEvent with matching command_id."""
    sdd_append(
        "ErrorEvent",
        {"command_id": "cmd-004", "error": "first failure"},
        db_path=tmp_db_path,
        level="L2",
    )
    assert get_error_count(tmp_db_path, "cmd-004") == 1

    sdd_append(
        "ErrorEvent",
        {"command_id": "cmd-004", "error": "second failure"},
        db_path=tmp_db_path,
        level="L2",
    )
    assert get_error_count(tmp_db_path, "cmd-004") == 2


def test_exists_command_no_side_effects(tmp_db_path: str) -> None:
    """exists_command is a pure read — it does not write any events to the DB (I-CMD-10)."""
    conn = open_sdd_connection(tmp_db_path)
    before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    exists_command(tmp_db_path, "cmd-pure-read")

    conn = open_sdd_connection(tmp_db_path)
    after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    assert before == after


def test_no_direct_duckdb_connect() -> None:
    """event_log.py must not call duckdb.connect directly — all DB access via infra/db.py (I-EL-9, I-CMD-10)."""
    import sdd.infra.event_log as _el_module

    event_log_path = Path(_el_module.__file__)
    result = subprocess.run(
        ["grep", "-n", "duckdb.connect", str(event_log_path)],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", (
        f"duckdb.connect found in event_log.py:\n{result.stdout}"
    )
