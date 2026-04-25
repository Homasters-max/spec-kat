"""Tests for acceptance check reuse — I-ACCEPT-REUSE-1, I-ACCEPT-1.

When multiple TestRunCompleted(name='test') events exist, main() must use
the last one (I-ACCEPT-REUSE-1): most-recent test result wins.
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import patch

from sdd.commands.validate_invariants import (
    _run_acceptance_check,
    _TestRunCompletedEvent,
    main,
)
from sdd.core.events import classify_event_level


def _test_run_event(returncode: int, task_id: str = "T-001") -> _TestRunCompletedEvent:
    return _TestRunCompletedEvent(
        event_type="TestRunCompleted",
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=classify_event_level("TestRunCompleted"),
        event_source="runtime",
        caused_by_meta_seq=None,
        command_id=str(uuid.uuid4()),
        name="test",
        returncode=returncode,
        stdout_normalized="",
        duration_ms=100,
        phase_id=22,
        task_id=task_id,
    )


class TestAcceptanceReuse:
    def test_skips_pytest_when_test_passed(self, tmp_path):
        """No subprocess call for pytest when test_returncode=0; returncode reused (I-ACCEPT-REUSE-1)."""
        with patch("sdd.commands.validate_invariants.subprocess.run") as mock_run:
            rc = _run_acceptance_check(
                outputs=[],
                cwd=str(tmp_path),
                env={},
                timeout=30,
                test_returncode=0,
            )
        assert rc == 0
        mock_run.assert_not_called()

    def test_returns_failure_from_test_returncode(self, tmp_path):
        """_run_acceptance_check returns 1 when test_returncode != 0 without subprocess (I-ACCEPT-REUSE-1)."""
        with patch("sdd.commands.validate_invariants.subprocess.run") as mock_run:
            rc = _run_acceptance_check(
                outputs=[],
                cwd=str(tmp_path),
                env={},
                timeout=30,
                test_returncode=1,
            )
        assert rc == 1
        mock_run.assert_not_called()

    def test_returns_1_when_no_test_result(self, tmp_path):
        """_run_acceptance_check returns 1 when test_returncode=None (NO_TEST_RESULT) (I-ACCEPT-REUSE-1)."""
        rc = _run_acceptance_check(
            outputs=[],
            cwd=str(tmp_path),
            env={},
            timeout=30,
            test_returncode=None,
        )
        assert rc == 1

    def test_uses_last_test_event_when_multiple(self, tmp_path):
        """main() passes the last TestRunCompleted(name='test') returncode to acceptance check (I-ACCEPT-REUSE-1)."""
        taskset = tmp_path / "TaskSet_v22.md"
        taskset.write_text("T-001: task\nOutputs: out.py\n")

        first_event = _test_run_event(returncode=1)  # earlier, fails
        last_event = _test_run_event(returncode=0)   # later, passes

        captured: list[int | None] = []

        def _fake_accept(outputs, cwd, env, timeout, test_returncode=None):
            captured.append(test_returncode)
            return 0

        with (
            patch("sdd.commands.validate_invariants.ValidateInvariantsHandler") as mock_h,
            patch("sdd.infra.event_store.EventStore"),
            patch("sdd.commands.validate_invariants._run_acceptance_check", side_effect=_fake_accept),
            patch("sdd.commands.validate_invariants.load_config") as mock_cfg,
        ):
            mock_h.return_value.handle.return_value = [first_event, last_event]
            mock_cfg.return_value = {"build": {"commands": {"acceptance": "echo ok"}}}

            main([
                "--phase", "22",
                "--task", "T-001",
                "--taskset", str(taskset),
                "--cwd", str(tmp_path),
            ])

        assert captured == [0], f"expected last event returncode=0, got {captured}"
