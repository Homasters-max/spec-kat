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

import duckdb
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_STR = str(_REPO_ROOT / "src")
_CANONICAL_HOOK = _REPO_ROOT / "src" / "sdd" / "hooks" / "log_tool.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_constrained_db(db_path: str) -> None:
    """Create a DB that rejects ToolUseStarted/ToolUseCompleted; allows HookError.

    seq has no DEFAULT so open_sdd_connection can CREATE OR REPLACE SEQUENCE freely.
    """
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS sdd_event_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            seq                BIGINT   NOT NULL PRIMARY KEY,
            partition_key      VARCHAR  NOT NULL DEFAULT 'sdd',
            event_id           VARCHAR  NOT NULL UNIQUE,
            event_type         VARCHAR  NOT NULL
                               CHECK (event_type NOT IN ('ToolUseStarted', 'ToolUseCompleted')),
            payload            VARCHAR  NOT NULL,
            schema_version     INTEGER  NOT NULL DEFAULT 1,
            appended_at        BIGINT   NOT NULL,
            level              VARCHAR  DEFAULT NULL,
            event_source       VARCHAR  NOT NULL DEFAULT 'runtime',
            caused_by_meta_seq BIGINT   DEFAULT NULL,
            expired            BOOLEAN  NOT NULL DEFAULT FALSE
        )
        """
    )
    conn.close()


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


def _query_rows(db_path: str) -> list[dict]:
    """Return all event rows with payload timestamp_ms stripped for comparison."""
    conn = duckdb.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, event_source, level, payload FROM events ORDER BY seq"
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    result = []
    for event_type, event_source, level, payload_json in rows:
        payload = json.loads(payload_json) if payload_json else {}
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


def test_pre_bash_emits_tool_use_started(tmp_path: Path) -> None:
    """I-HOOK-WIRE-1: PreToolUse + Bash emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
    }
    db_path = str(tmp_path / "hook.duckdb")
    _run_hook(payload, db_path)
    rows = _query_rows(db_path)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_post_bash_emits_tool_use_completed(tmp_path: Path) -> None:
    """PostToolUse + Bash emits ToolUseCompleted."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
        "tool_response": {"output": "hello\n", "interrupted": False},
    }
    db_path = str(tmp_path / "hook.duckdb")
    _run_hook(payload, db_path)
    rows = _query_rows(db_path)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseCompleted"


def test_pre_read_emits_tool_use_started(tmp_path: Path) -> None:
    """PreToolUse + Read emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/test.txt", "offset": 10, "limit": 50},
    }
    db_path = str(tmp_path / "hook.duckdb")
    _run_hook(payload, db_path)
    rows = _query_rows(db_path)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_pre_write_emits_tool_use_started(tmp_path: Path) -> None:
    """PreToolUse + Write emits ToolUseStarted."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/out.txt", "content": "hello world"},
    }
    db_path = str(tmp_path / "hook.duckdb")
    _run_hook(payload, db_path)
    rows = _query_rows(db_path)
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "ToolUseStarted"


def test_failure_path_emits_hook_error(tmp_path: Path) -> None:
    """On sdd_append failure, hook emits HookError with hook_name field."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo fail", "description": "trigger failure"},
    }
    db_path = str(tmp_path / "fail.duckdb")
    _make_constrained_db(db_path)
    _run_hook(payload, db_path)
    rows = [r for r in _query_rows(db_path) if r["event_type"] == "HookError"]
    assert len(rows) >= 1
    assert rows[0]["payload"].get("hook_error") is not None
