"""tests/unit/test_cli_contracts.py — CLI behavioural contracts (I-SHIM-CONTRACT-1).

Tests that sdd CLI commands exit with correct codes, emit correct JSON stderr on error,
and produce deterministic output. Covers contracts formerly validated by test_adapters.py
shim-pattern tests.

Invariants: I-SHIM-CONTRACT-1, I-CLI-API-1, I-HOOK-FAILSAFE-1, I-FAIL-1
"""
from __future__ import annotations

import json
import os  # used by hook payload tests
import subprocess


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def test_sdd_help_exits_0() -> None:
    """sdd --help exits 0 and prints usage."""
    r = _run(["sdd", "--help"])
    assert r.returncode == 0
    assert "Usage:" in r.stdout


def test_sdd_version_exits_0() -> None:
    """sdd --version exits 0."""
    r = _run(["sdd", "--version"])
    assert r.returncode == 0


def test_all_subcommands_help_exit_0() -> None:
    """All registered sdd subcommands respond to --help with exit 0."""
    subcmds = [
        "complete", "validate", "show-state", "activate-phase",
        "replay", "query-events", "metrics-report", "sync-state",
        "validate-invariants", "report-error", "validate-config",
        "phase-guard", "task-guard", "check-scope", "norm-guard",
        "show-task", "show-spec", "show-plan", "record-decision",
    ]
    for sub in subcmds:
        r = _run(["sdd", sub, "--help"])
        assert r.returncode == 0, f"sdd {sub} --help exited {r.returncode}: {r.stderr}"


def test_error_json_schema_on_usage_error() -> None:
    """I-CLI-API-1: CLI error → JSON stderr with error_type, message, exit_code; exit 1."""
    r = _run(["sdd", "validate-config"])  # missing required --phase
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stderr}"
    err = json.loads(r.stderr.strip())
    assert "error_type" in err, f"Missing error_type: {err}"
    assert "message" in err, f"Missing message: {err}"
    assert "exit_code" in err, f"Missing exit_code: {err}"
    assert err["exit_code"] == 1


def test_hook_log_pre_exits_0_empty_stdin() -> None:
    """I-HOOK-FAILSAFE-1: sdd-hook-log pre exits 0 even with empty (invalid JSON) stdin."""
    r = _run(["sdd-hook-log", "pre"], input="")
    assert r.returncode == 0, f"sdd-hook-log pre exited {r.returncode}: {r.stderr}"


def test_hook_log_post_exits_0_empty_stdin() -> None:
    """I-HOOK-FAILSAFE-1: sdd-hook-log post exits 0 even with empty (invalid JSON) stdin."""
    r = _run(["sdd-hook-log", "post"], input="")
    assert r.returncode == 0, f"sdd-hook-log post exited {r.returncode}: {r.stderr}"


def test_hook_log_pre_exits_0_valid_payload(tmp_path) -> None:
    """I-HOOK-FAILSAFE-1: sdd-hook-log pre exits 0 with a well-formed PreToolUse payload."""
    env = {**os.environ, "SDD_DB_PATH": str(tmp_path / "test.duckdb")}
    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo test", "description": "test"},
    })
    r = _run(["sdd-hook-log", "pre"], input=payload, env=env)
    assert r.returncode == 0, f"sdd-hook-log pre exited {r.returncode}: {r.stderr}"


def test_hook_log_post_exits_0_valid_payload(tmp_path) -> None:
    """I-HOOK-FAILSAFE-1: sdd-hook-log post exits 0 with a well-formed PostToolUse payload."""
    env = {**os.environ, "SDD_DB_PATH": str(tmp_path / "test.duckdb")}
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo test", "description": "test"},
        "tool_response": {"output": "test", "interrupted": False},
    })
    r = _run(["sdd-hook-log", "post"], input=payload, env=env)
    assert r.returncode == 0, f"sdd-hook-log post exited {r.returncode}: {r.stderr}"
