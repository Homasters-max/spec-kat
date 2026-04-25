"""Tests for subprocess timeout semantics — Spec_v22 §2 BC-22-0.

Invariants: I-TIMEOUT-1, I-CMD-6, I-CMD-7
"""
from __future__ import annotations

import subprocess
import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.validate_invariants import (
    TIMEOUT_RETURN_CODE,
    ValidateInvariantsCommand,
    ValidateInvariantsHandler,
)


def _command(
    *,
    phase_id: int = 22,
    task_id: str | None = "T-2202",
    config_path: str = ".sdd/config/project_profile.yaml",
    cwd: str = "/project",
    env_whitelist: tuple[str, ...] = (),
    timeout_secs: int = 30,
    task_outputs: tuple[str, ...] = (),
) -> ValidateInvariantsCommand:
    return ValidateInvariantsCommand(
        command_id=str(uuid.uuid4()),
        command_type="ValidateInvariants",
        payload={},
        phase_id=phase_id,
        task_id=task_id,
        config_path=config_path,
        cwd=cwd,
        env_whitelist=env_whitelist,
        timeout_secs=timeout_secs,
        task_outputs=task_outputs,
    )


def _fake_config(*names: str) -> dict:
    return {"build": {"commands": {n: f"run-{n}" for n in names}}}


def _popen_mock(returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.pid = 12345
    proc.communicate.return_value = (b"ok\n", b"")
    return proc


@pytest.fixture
def handler(tmp_path):
    return ValidateInvariantsHandler(db_path=str(tmp_path / "test.duckdb"))


@patch("sdd.commands.validate_invariants.os.getpgid", return_value=12345)
@patch("sdd.commands.validate_invariants.os.killpg")
@patch("sdd.commands.validate_invariants.load_config")
@patch("sdd.commands.validate_invariants.subprocess.Popen")
def test_timeout_records_124_and_continues(
    mock_popen, mock_load, mock_killpg, mock_getpgid, handler
):
    """Timeout sets returncode=TIMEOUT_RETURN_CODE (124), loop continues (I-TIMEOUT-1, I-CMD-6)."""
    mock_load.return_value = _fake_config("lint", "test")

    timeout_proc = MagicMock()
    timeout_proc.pid = 12345
    timeout_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd="run-lint", timeout=30),
        (b"", b""),  # drain after killpg
    ]

    ok_proc = _popen_mock(returncode=0)
    mock_popen.side_effect = [timeout_proc, ok_proc]

    with patch.object(handler, "_check_idempotent", return_value=False):
        events = handler.handle(_command())

    assert mock_popen.call_count == 2

    test_events = [e for e in events if e.event_type == "TestRunCompleted"]
    assert len(test_events) == 2

    lint_event = next(e for e in test_events if e.name == "lint")
    assert lint_event.returncode == TIMEOUT_RETURN_CODE
    assert lint_event.returncode == 124

    test_event = next(e for e in test_events if e.name == "test")
    assert test_event.returncode == 0


@patch("sdd.commands.validate_invariants.load_config")
@patch("sdd.commands.validate_invariants.subprocess.Popen")
def test_uses_start_new_session(mock_popen, mock_load, handler):
    """All Popen calls in build loop MUST use start_new_session=True (I-CMD-7)."""
    mock_load.return_value = _fake_config("lint", "test")
    mock_popen.return_value = _popen_mock()

    with patch.object(handler, "_check_idempotent", return_value=False):
        handler.handle(_command())

    for i, c in enumerate(mock_popen.call_args_list):
        assert c.kwargs.get("start_new_session") is True, (
            f"Popen call {i} missing start_new_session=True"
        )
