"""Tests for hooks/log_tool.py and hooks/log_bash.py.

All tests invoke scripts via subprocess.run only — no direct import (I-HOOKS-ISO).
Invariants covered: I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOK-API-1, I-HOOKS-ISO

I-HOOK-API-1: Hook MUST NOT accept positional CLI arguments. Only stdin JSON is supported.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_SRC = str(_REPO_ROOT / "src")
_LOG_TOOL = _REPO_ROOT / "src" / "sdd" / "hooks" / "log_tool.py"
_LOG_BASH = _REPO_ROOT / "src" / "sdd" / "hooks" / "log_bash.py"

# Canonical payload factories — match Claude Code hook JSON schema exactly.
_PRE = {"hook_event_name": "PreToolUse", "tool_name": "TestTool", "tool_input": {}}
_POST = {
    "hook_event_name": "PostToolUse",
    "tool_name": "TestTool",
    "tool_input": {},
    "tool_response": {"output": "ok", "interrupted": False},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(script: Path, payload: dict, db_path: str) -> subprocess.CompletedProcess[str]:
    """Invoke hook script with payload delivered via stdin JSON (I-HOOK-API-1)."""
    env = os.environ.copy()
    env["SDD_DB_PATH"] = db_path
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC}:{existing}" if existing else _SRC
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


def _query(db_path: str, event_type: str | None = None) -> list[dict[str, object]]:
    """Query events table; returns [] if DB file absent or table not yet created."""
    if not os.path.exists(db_path):
        return []
    conn = duckdb.connect(db_path)
    try:
        if event_type:
            rows = conn.execute(
                "SELECT event_type, level, event_source FROM events WHERE event_type = ?",
                [event_type],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT event_type, level, event_source FROM events"
            ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [{"event_type": r[0], "level": r[1], "event_source": r[2]} for r in rows]


def _make_constrained_db(db_path: str) -> None:
    """Create a DB that rejects ToolUseStarted/ToolUseCompleted via CHECK constraint.

    Used to force the main sdd_append to fail while allowing HookError writes through.
    """
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS sdd_event_seq START 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            seq                BIGINT   NOT NULL PRIMARY KEY DEFAULT nextval('sdd_event_seq'),
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


def _bad_db(tmp_path: Path) -> str:
    """Return path to a file that is not a valid DuckDB database."""
    p = tmp_path / "garbage.duckdb"
    p.write_bytes(b"this is not a duckdb file")
    return str(p)


# ---------------------------------------------------------------------------
# I-HOOK-API-1: only stdin JSON — positional args are silently ignored
# ---------------------------------------------------------------------------


def test_hook_rejects_argv(tmp_path: Path) -> None:
    """Hook ignores positional CLI args; exits 0 but writes no events (I-HOOK-API-1, I-HOOK-2)."""
    db = str(tmp_path / "events.duckdb")
    env = os.environ.copy()
    env["SDD_DB_PATH"] = db
    env["PYTHONPATH"] = _SRC
    result = subprocess.run(
        [sys.executable, str(_LOG_TOOL), "pre", "TestTool"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0  # I-HOOK-2: always exit 0
    assert _query(db) == []        # I-HOOK-API-1: no events for argv-only invocation


# ---------------------------------------------------------------------------
# I-HOOK-2: always exit 0
# ---------------------------------------------------------------------------


def test_hook_exits_zero_on_success(tmp_path: Path) -> None:
    """log_tool.py exits 0 when DB write succeeds (I-HOOK-2)."""
    db = str(tmp_path / "events.duckdb")
    result = _run(_LOG_TOOL, _PRE, db_path=db)
    assert result.returncode == 0


def test_hook_exits_zero_on_exception(tmp_path: Path) -> None:
    """log_tool.py exits 0 when main write fails but HookError write succeeds (I-HOOK-2)."""
    db = str(tmp_path / "constrained.duckdb")
    _make_constrained_db(db)
    result = _run(_LOG_TOOL, _PRE, db_path=db)
    assert result.returncode == 0


def test_hook_exits_zero_on_double_failure(tmp_path: Path) -> None:
    """log_tool.py exits 0 when both main write AND HookError write fail (I-HOOK-2)."""
    result = _run(_LOG_TOOL, _PRE, db_path=_bad_db(tmp_path))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# I-HOOK-1: event_source="meta"
# ---------------------------------------------------------------------------


def test_hook_uses_meta_source(tmp_path: Path) -> None:
    """ToolUseStarted is written with event_source='meta' (I-HOOK-1)."""
    db = str(tmp_path / "events.duckdb")
    _run(_LOG_TOOL, _PRE, db_path=db)
    events = _query(db, "ToolUseStarted")
    assert len(events) == 1
    assert events[0]["event_source"] == "meta"


# ---------------------------------------------------------------------------
# I-HOOK-3: level="L2" for ToolUseStarted/ToolUseCompleted
# ---------------------------------------------------------------------------


def test_hook_event_level_l2(tmp_path: Path) -> None:
    """ToolUseStarted and ToolUseCompleted are written with level='L2' (I-HOOK-3)."""
    db = str(tmp_path / "events.duckdb")
    _run(_LOG_TOOL, _PRE, db_path=db)
    _run(_LOG_TOOL, _POST, db_path=db)
    assert _query(db, "ToolUseStarted")[0]["level"] == "L2"
    assert _query(db, "ToolUseCompleted")[0]["level"] == "L2"


# ---------------------------------------------------------------------------
# I-HOOK-3: level="L3" for HookError
# ---------------------------------------------------------------------------


def test_hook_error_event_level_l3(tmp_path: Path) -> None:
    """HookError events are written with level='L3' (I-HOOK-3)."""
    db = str(tmp_path / "constrained.duckdb")
    _make_constrained_db(db)
    _run(_LOG_TOOL, _PRE, db_path=db)
    errors = _query(db, "HookError")
    assert len(errors) == 1
    assert errors[0]["level"] == "L3"


# ---------------------------------------------------------------------------
# Event type emission
# ---------------------------------------------------------------------------


def test_hook_pre_emits_tool_use_started(tmp_path: Path) -> None:
    """'PreToolUse' hook event emits ToolUseStarted event."""
    db = str(tmp_path / "events.duckdb")
    _run(_LOG_TOOL, _PRE, db_path=db)
    assert len(_query(db, "ToolUseStarted")) == 1


def test_hook_post_emits_tool_use_completed(tmp_path: Path) -> None:
    """'PostToolUse' hook event emits ToolUseCompleted event."""
    db = str(tmp_path / "events.duckdb")
    _run(_LOG_TOOL, _POST, db_path=db)
    assert len(_query(db, "ToolUseCompleted")) == 1


# ---------------------------------------------------------------------------
# I-HOOK-4: HookError on failure; stderr on double failure
# ---------------------------------------------------------------------------


def test_hook_emits_error_event_on_failure(tmp_path: Path) -> None:
    """On sdd_append failure, HookError event is written to DB (I-HOOK-4)."""
    db = str(tmp_path / "constrained.duckdb")
    _make_constrained_db(db)
    _run(_LOG_TOOL, _PRE, db_path=db)
    errors = _query(db, "HookError")
    assert len(errors) == 1
    assert errors[0]["event_source"] == "meta"


def test_hook_logs_stderr_on_double_failure(tmp_path: Path) -> None:
    """On double failure (both writes fail), full traceback is logged to stderr (I-HOOK-4)."""
    result = _run(_LOG_TOOL, _PRE, db_path=_bad_db(tmp_path))
    assert result.returncode == 0
    assert "double failure" in result.stderr
