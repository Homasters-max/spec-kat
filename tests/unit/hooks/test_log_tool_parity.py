"""Parity tests: .sdd/_deprecated_tools/log_tool.py must be a thin wrapper of src/sdd/hooks/log_tool.py.

Invariants: I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1

All I-HOOKS-ISO parity tests run both scripts via subprocess and compare DB rows
(event_type, event_source, level, payload excluding timestamp_ms).
"""
from __future__ import annotations

import ast
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
_TOOLS_HOOK = _REPO_ROOT / ".sdd" / "_deprecated_tools" / "log_tool.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_constrained_db(db_path: str) -> None:
    """Create a DB that rejects ToolUseStarted/ToolUseCompleted; allows HookError."""
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


def _run_hook(script: Path, payload: dict, db_path: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SDD_DB_PATH"] = db_path
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{_SRC_STR}:{existing}" if existing else _SRC_STR
    return subprocess.run(
        [sys.executable, str(script)],
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


def _parity_rows(payload: dict, tmp_path: Path, db_suffix: str = "") -> tuple[list[dict], list[dict]]:
    """Run both hooks with payload; return (canonical_rows, tools_rows)."""
    db_c = str(tmp_path / f"canonical{db_suffix}.duckdb")
    db_t = str(tmp_path / f"tools{db_suffix}.duckdb")
    _run_hook(_CANONICAL_HOOK, payload, db_c)
    _run_hook(_TOOLS_HOOK, payload, db_t)
    return _query_rows(db_c), _query_rows(db_t)


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_tools_hook_is_thin_wrapper() -> None:
    """I-HOOK-WIRE-1: .sdd/_deprecated_tools/log_tool.py must not contain any sdd_append call (AST check)."""
    source = _TOOLS_HOOK.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "sdd_append":
            pytest.fail(f"sdd_append found as Name at line {node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr == "sdd_append":
            pytest.fail(f"sdd_append found as Attribute at line {node.lineno}")


def test_tools_hook_path_resolution() -> None:
    """I-HOOK-PATH-1: .sdd/_deprecated_tools/log_tool.py is a Pattern B adapter — delegates to sdd.hooks.log_tool.main."""
    source = _TOOLS_HOOK.read_text()
    assert "from sdd.hooks.log_tool import main" in source, (
        "Expected Pattern B delegation: from sdd.hooks.log_tool import main"
    )


# ---------------------------------------------------------------------------
# Parity: equal row count and identical fields (excl. timestamp_ms)
# ---------------------------------------------------------------------------


def test_parity_pre_bash(tmp_path: Path) -> None:
    """Parity: PreToolUse + Bash produces same DB rows from both hooks."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
    }
    canonical_rows, tools_rows = _parity_rows(payload, tmp_path)
    assert len(canonical_rows) == len(tools_rows), (
        f"Row count mismatch: canonical={len(canonical_rows)}, tools={len(tools_rows)}"
    )
    assert canonical_rows == tools_rows


def test_parity_post_bash(tmp_path: Path) -> None:
    """Parity: PostToolUse + Bash produces same DB rows from both hooks."""
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello", "description": "test cmd"},
        "tool_response": {"output": "hello\n", "interrupted": False},
    }
    canonical_rows, tools_rows = _parity_rows(payload, tmp_path)
    assert len(canonical_rows) == len(tools_rows), (
        f"Row count mismatch: canonical={len(canonical_rows)}, tools={len(tools_rows)}"
    )
    assert canonical_rows == tools_rows


def test_parity_pre_read(tmp_path: Path) -> None:
    """Parity: PreToolUse + Read produces same DB rows from both hooks."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/test.txt", "offset": 10, "limit": 50},
    }
    canonical_rows, tools_rows = _parity_rows(payload, tmp_path)
    assert len(canonical_rows) == len(tools_rows), (
        f"Row count mismatch: canonical={len(canonical_rows)}, tools={len(tools_rows)}"
    )
    assert canonical_rows == tools_rows


def test_parity_pre_write(tmp_path: Path) -> None:
    """Parity: PreToolUse + Write produces same DB rows from both hooks."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/out.txt", "content": "hello world"},
    }
    canonical_rows, tools_rows = _parity_rows(payload, tmp_path)
    assert len(canonical_rows) == len(tools_rows), (
        f"Row count mismatch: canonical={len(canonical_rows)}, tools={len(tools_rows)}"
    )
    assert canonical_rows == tools_rows


def test_parity_failure_path(tmp_path: Path) -> None:
    """Parity: on sdd_append failure both hooks emit HookError with identical fields."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo fail", "description": "trigger failure"},
    }
    db_c = str(tmp_path / "canonical_fail.duckdb")
    db_t = str(tmp_path / "tools_fail.duckdb")
    _make_constrained_db(db_c)
    _make_constrained_db(db_t)

    _run_hook(_CANONICAL_HOOK, payload, db_c)
    _run_hook(_TOOLS_HOOK, payload, db_t)

    canonical_rows = [r for r in _query_rows(db_c) if r["event_type"] == "HookError"]
    tools_rows = [r for r in _query_rows(db_t) if r["event_type"] == "HookError"]

    assert len(canonical_rows) == len(tools_rows), (
        f"HookError count mismatch: canonical={len(canonical_rows)}, tools={len(tools_rows)}"
    )
    for c_row, t_row in zip(canonical_rows, tools_rows):
        assert c_row["event_type"] == t_row["event_type"]
        assert c_row["event_source"] == t_row["event_source"]
        assert c_row["level"] == t_row["level"]
        assert c_row["payload"].get("hook_name") == t_row["payload"].get("hook_name")
        assert c_row["payload"].get("error_type") == t_row["payload"].get("error_type")
