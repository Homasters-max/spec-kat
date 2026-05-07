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

import psycopg
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


def _query(db_url: str, event_type: str | None = None) -> list[dict[str, object]]:
    """Query event_log table via PG; returns [] on any error."""
    try:
        conn = psycopg.connect(db_url)
        try:
            if event_type:
                rows = conn.execute(
                    "SELECT event_type, level, event_source FROM event_log WHERE event_type = %s",
                    [event_type],
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT event_type, level, event_source FROM event_log"
                ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()
    except Exception:
        rows = []
    return [{"event_type": r[0], "level": r[1], "event_source": r[2]} for r in rows]


def _make_constrained_db(db_url: str) -> None:
    """Add a CHECK constraint that rejects ToolUseStarted/ToolUseCompleted.

    Used to force the main sdd_append to fail while allowing HookError writes through.
    """
    conn = psycopg.connect(db_url)
    conn.execute(
        "ALTER TABLE event_log ADD CONSTRAINT no_tool_events "
        "CHECK (event_type NOT IN ('ToolUseStarted', 'ToolUseCompleted'))"
    )
    conn.commit()
    conn.close()


def _drop_constraint(db_url: str) -> None:
    """Remove the test constraint added by _make_constrained_db."""
    try:
        conn = psycopg.connect(db_url)
        conn.execute("ALTER TABLE event_log DROP CONSTRAINT IF EXISTS no_tool_events")
        conn.commit()
        conn.close()
    except Exception:
        pass


def _bad_db(tmp_path: Path) -> str:
    """Return an invalid PG URL that will fail to connect."""
    return "postgresql://localhost:1/nonexistent_test_db_garbage"


# ---------------------------------------------------------------------------
# I-HOOK-API-1: only stdin JSON — positional args are silently ignored
# ---------------------------------------------------------------------------


def test_hook_rejects_argv(pg_test_db: str) -> None:
    """Hook ignores positional CLI args; exits 0 but writes no events (I-HOOK-API-1, I-HOOK-2)."""
    env = os.environ.copy()
    env["SDD_DB_PATH"] = pg_test_db
    env["PYTHONPATH"] = _SRC
    result = subprocess.run(
        [sys.executable, str(_LOG_TOOL), "pre", "TestTool"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0  # I-HOOK-2: always exit 0
    assert _query(pg_test_db) == []  # I-HOOK-API-1: no events for argv-only invocation


# ---------------------------------------------------------------------------
# I-HOOK-2: always exit 0
# ---------------------------------------------------------------------------


def test_hook_exits_zero_on_success(pg_test_db: str) -> None:
    """log_tool.py exits 0 when DB write succeeds (I-HOOK-2)."""
    result = _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
    assert result.returncode == 0


def test_hook_exits_zero_on_exception(pg_test_db: str) -> None:
    """log_tool.py exits 0 when main write fails but HookError write succeeds (I-HOOK-2)."""
    _make_constrained_db(pg_test_db)
    try:
        result = _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
        assert result.returncode == 0
    finally:
        _drop_constraint(pg_test_db)


def test_hook_exits_zero_on_double_failure(tmp_path: Path) -> None:
    """log_tool.py exits 0 when both main write AND HookError write fail (I-HOOK-2)."""
    result = _run(_LOG_TOOL, _PRE, db_path=_bad_db(tmp_path))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# I-HOOK-1: event_source="meta"
# ---------------------------------------------------------------------------


def test_hook_uses_meta_source(pg_test_db: str) -> None:
    """ToolUseStarted is written with event_source='meta' (I-HOOK-1)."""
    _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
    events = _query(pg_test_db, "ToolUseStarted")
    assert len(events) == 1
    assert events[0]["event_source"] == "meta"


# ---------------------------------------------------------------------------
# I-HOOK-3: level="L2" for ToolUseStarted/ToolUseCompleted
# ---------------------------------------------------------------------------


def test_hook_event_level_l2(pg_test_db: str) -> None:
    """ToolUseStarted and ToolUseCompleted are written with level='L2' (I-HOOK-3)."""
    _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
    _run(_LOG_TOOL, _POST, db_path=pg_test_db)
    assert _query(pg_test_db, "ToolUseStarted")[0]["level"] == "L2"
    assert _query(pg_test_db, "ToolUseCompleted")[0]["level"] == "L2"


# ---------------------------------------------------------------------------
# I-HOOK-3: level="L3" for HookError
# ---------------------------------------------------------------------------


def test_hook_error_event_level_l3(pg_test_db: str) -> None:
    """HookError events are written with level='L3' (I-HOOK-3)."""
    _make_constrained_db(pg_test_db)
    try:
        _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
        errors = _query(pg_test_db, "HookError")
        assert len(errors) == 1
        assert errors[0]["level"] == "L3"
    finally:
        _drop_constraint(pg_test_db)


# ---------------------------------------------------------------------------
# Event type emission
# ---------------------------------------------------------------------------


def test_hook_pre_emits_tool_use_started(pg_test_db: str) -> None:
    """'PreToolUse' hook event emits ToolUseStarted event."""
    _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
    assert len(_query(pg_test_db, "ToolUseStarted")) == 1


def test_hook_post_emits_tool_use_completed(pg_test_db: str) -> None:
    """'PostToolUse' hook event emits ToolUseCompleted event."""
    _run(_LOG_TOOL, _POST, db_path=pg_test_db)
    assert len(_query(pg_test_db, "ToolUseCompleted")) == 1


# ---------------------------------------------------------------------------
# I-HOOK-4: HookError on failure; stderr on double failure
# ---------------------------------------------------------------------------


def test_hook_emits_error_event_on_failure(pg_test_db: str) -> None:
    """On sdd_append failure, HookError event is written to DB (I-HOOK-4)."""
    _make_constrained_db(pg_test_db)
    try:
        _run(_LOG_TOOL, _PRE, db_path=pg_test_db)
        errors = _query(pg_test_db, "HookError")
        assert len(errors) == 1
        assert errors[0]["event_source"] == "meta"
    finally:
        _drop_constraint(pg_test_db)


def test_hook_logs_stderr_on_double_failure(tmp_path: Path) -> None:
    """On double failure (both writes fail), full traceback is logged to stderr (I-HOOK-4)."""
    result = _run(_LOG_TOOL, _PRE, db_path=_bad_db(tmp_path))
    assert result.returncode == 0
    assert "double failure" in result.stderr


# ---------------------------------------------------------------------------
# I-CLI-DB-RESOLUTION-1: fallback to event_store_url() when no SDD_DB_PATH
# ---------------------------------------------------------------------------


def test_log_tool_uses_event_store_url() -> None:
    """BC-44-D: log_tool.py MUST use event_store_url() for DB routing, not event_store_file().

    Source check only — backend-specific fallback behavior is tested in test_paths.py.
    """
    source = _LOG_TOOL.read_text()
    assert "event_store_url" in source, "log_tool.py must use event_store_url() for DB routing"
    assert "event_store_file" not in source, "log_tool.py must not call event_store_file() directly"
