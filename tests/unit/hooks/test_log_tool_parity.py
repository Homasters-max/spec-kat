"""Behavioural tests for src/sdd/hooks/log_tool.py.

Invariants: I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1, I-DEPRECATED-RM-2

Tests verify that the canonical hook (src/sdd/hooks/log_tool.py) emits the
expected event types for each PreToolUse / PostToolUse scenario.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_STR = str(_REPO_ROOT / "src")
_CANONICAL_HOOK = _REPO_ROOT / "src" / "sdd" / "hooks" / "log_tool.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_constrained_db(db_url: str) -> None:
    """Add CHECK constraint that rejects ToolUseStarted/ToolUseCompleted."""
    conn = psycopg.connect(db_url)
    conn.execute(
        "ALTER TABLE event_log ADD CONSTRAINT no_tool_events "
        "CHECK (event_type NOT IN ('ToolUseStarted', 'ToolUseCompleted'))"
    )
    conn.commit()
    conn.close()


def _drop_constraint(db_url: str) -> None:
    try:
        conn = psycopg.connect(db_url)
        conn.execute("ALTER TABLE event_log DROP CONSTRAINT IF EXISTS no_tool_events")
        conn.commit()
        conn.close()
    except Exception:
        pass


def _run_hook(payload: dict, db_path: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SDD_DB_PATH"] = db_path
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_STR}:{existing}" if existing else _SRC_STR
    return subprocess.run(
        [sys.executable, str(_CANONICAL_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _query_rows(db_url: str) -> list[dict]:
    """Return all event rows with payload timestamp_ms stripped for comparison."""
    try:
        conn = psycopg.connect(db_url)
        try:
            rows = conn.execute(
                "SELECT event_type, event_source, level, payload FROM event_log ORDER BY sequence_id"
            ).fetchall()
        except Exception:
            return []
        finally:
            conn.close()
    except Exception:
        return []

    result = []
    for event_type, event_source, level, payload_data in rows:
        payload = payload_data if isinstance(payload_data, dict) else (json.loads(payload_data) if payload_data else {})
        payload.pop("timestamp_ms", None)
        result.append(
            {
                "event_type": event_type,
                "event_source": event_source,
                "level": level,
                "payload": payload,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Behavioural tests: canonical hook emits expected events
# ---------------------------------------------------------------------------


def test_pre_bash_emits_tool_use_started(pg_test_db: str) -> None:
    """I-HOOK-WIRE-1: PreToolUse + Bash emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
    }
    _run_hook(payload, pg_test_db)
    rows = _query_rows(pg_test_db)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_post_bash_emits_tool_use_completed(pg_test_db: str) -> None:
    """PostToolUse + Bash emits ToolUseCompleted."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
        "tool_response": {"output": "hello\n", "interrupted": False},
    }
    _run_hook(payload, pg_test_db)
    rows = _query_rows(pg_test_db)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseCompleted"


def test_pre_read_emits_tool_use_started(pg_test_db: str) -> None:
    """PreToolUse + Read emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/test.txt", "offset": 10, "limit": 50},
    }
    _run_hook(payload, pg_test_db)
    rows = _query_rows(pg_test_db)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_pre_write_emits_tool_use_started(pg_test_db: str) -> None:
    """PreToolUse + Write emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/out.txt", "content": "hello world"},
    }
    _run_hook(payload, pg_test_db)
    rows = _query_rows(pg_test_db)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_failure_path_emits_hook_error(pg_test_db: str) -> None:
    """On sdd_append failure, hook emits HookError with hook_name field."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo fail", "description": "trigger failure"},
    }
    _make_constrained_db(pg_test_db)
    try:
        _run_hook(payload, pg_test_db)
        rows = [r for r in _query_rows(pg_test_db) if r["event_type"] == "HookError"]
        assert len(rows) >= 1
        assert rows[0]["payload"].get("hook_error") is not None
    finally:
        _drop_constraint(pg_test_db)
