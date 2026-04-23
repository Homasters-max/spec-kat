"""Tests for ValidateInvariantsHandler — Spec_v4 §9 Verification row 8, Spec_v8 §9 Test #5.

Invariants: I-CMD-1, I-CMD-6, I-CMD-13, I-M-1-CHECK, I-CHAIN-1, I-ACCEPT-1
"""
from __future__ import annotations

import subprocess
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from sdd.commands.validate_invariants import (
    InvariantCheckResult,
    ValidateInvariantsCommand,
    ValidateInvariantsHandler,
    _run_acceptance_check,
    check_im1_invariant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _command(
    *,
    phase_id: int = 4,
    task_id: str | None = "T-418",
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
    """Return a minimal config dict with named build commands."""
    return {"build": {"commands": {n: f"run-{n}" for n in names}}}


def _ok_result(returncode: int = 0) -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = b"ok\n"
    r.stderr = b""
    return r


@pytest.fixture
def handler(tmp_path):
    return ValidateInvariantsHandler(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# Runs all build.commands (I-CMD-6)
# ---------------------------------------------------------------------------

class TestRunsAllCommands:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_runs_all_build_commands(self, mock_run, mock_load, handler):
        """Handler invokes subprocess.run once per entry in build.commands (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_run.return_value = _ok_result()

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command())

        assert mock_run.call_count == 3
        called_cmds = [c.args[0] for c in mock_run.call_args_list]
        assert set(called_cmds) == {"run-lint", "run-typecheck", "run-test"}

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_emits_metric_per_command(self, mock_run, mock_load, handler):
        """Handler emits TestRunCompletedEvent + MetricRecorded for each build command."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_run.return_value = _ok_result()

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command())

        # 2 events per command → 6 total
        assert len(events) == 6
        event_types = [e.event_type for e in events]
        assert event_types.count("TestRunCompleted") == 3
        assert event_types.count("MetricRecorded") == 3

        metric_ids = {e.metric_id for e in events if e.event_type == "MetricRecorded"}
        assert metric_ids == {"quality.lint", "quality.typecheck", "quality.test"}

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_no_extra_commands(self, mock_run, mock_load, handler):
        """Handler runs only commands declared in build.commands — no additions (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint")
        mock_run.return_value = _ok_result()

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command())

        assert mock_run.call_count == 1
        assert len(events) == 2  # one TestRunCompleted + one MetricRecorded


# ---------------------------------------------------------------------------
# Continues on failure (I-CMD-6)
# ---------------------------------------------------------------------------

class TestContinuesOnFailure:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_continues_on_failure(self, mock_run, mock_load, handler):
        """Non-zero returncode does not abort the loop — all commands execute (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        # lint fails, rest succeed
        mock_run.side_effect = [
            _ok_result(returncode=1),
            _ok_result(returncode=0),
            _ok_result(returncode=0),
        ]

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(_command())

        assert mock_run.call_count == 3
        assert len(events) == 6

        lint_metric = next(
            e for e in events
            if e.event_type == "MetricRecorded" and e.metric_id == "quality.lint"
        )
        assert lint_metric.value == 1.0


# ---------------------------------------------------------------------------
# Idempotency (I-CMD-1)
# ---------------------------------------------------------------------------

class TestIdempotency:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_validate_inv_idempotent(self, mock_run, mock_load, handler):
        """Duplicate command_id returns [] without running any subprocess (I-CMD-1)."""
        mock_load.return_value = _fake_config("lint", "test")

        with patch.object(handler, "_check_idempotent", return_value=True):
            result = handler.handle(_command())

        assert result == []
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Subprocess determinism constraints (I-CMD-13)
# ---------------------------------------------------------------------------

class TestSubprocessConstraints:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_subprocess_uses_explicit_cwd(self, mock_run, mock_load, handler):
        """subprocess.run is called with cwd=command.cwd — never os.getcwd() (I-CMD-13)."""
        mock_load.return_value = _fake_config("lint")
        mock_run.return_value = _ok_result()
        cmd = _command(cwd="/explicit/project/root")

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(cmd)

        _, kwargs = mock_run.call_args
        assert kwargs["cwd"] == "/explicit/project/root"

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_subprocess_env_whitelist(self, mock_run, mock_load, handler):
        """subprocess.run env contains only vars from env_whitelist; no os.environ fallback (I-CMD-13)."""
        mock_load.return_value = _fake_config("lint")
        mock_run.return_value = _ok_result()

        with patch("sdd.commands.validate_invariants.os.environ", {"PATH": "/usr/bin", "HOME": "/root", "SECRET": "x"}):
            cmd = _command(env_whitelist=("PATH",))
            with patch.object(handler, "_check_idempotent", return_value=False):
                handler.handle(cmd)

        _, kwargs = mock_run.call_args
        assert kwargs["env"] == {"PATH": "/usr/bin"}
        assert "HOME" not in kwargs["env"]
        assert "SECRET" not in kwargs["env"]

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_subprocess_env_empty_when_whitelist_empty(self, mock_run, mock_load, handler):
        """Empty env_whitelist → subprocess receives empty env dict (I-CMD-13)."""
        mock_load.return_value = _fake_config("lint")
        mock_run.return_value = _ok_result()
        cmd = _command(env_whitelist=())

        with patch.object(handler, "_check_idempotent", return_value=False):
            handler.handle(cmd)

        _, kwargs = mock_run.call_args
        assert kwargs["env"] == {}

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_subprocess_timeout_raises(self, mock_run, mock_load, handler):
        """subprocess.TimeoutExpired propagates out of handle() (I-CMD-13)."""
        mock_load.return_value = _fake_config("test")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest tests/", timeout=30)

        with patch.object(handler, "_check_idempotent", return_value=False):
            with pytest.raises(subprocess.TimeoutExpired):
                handler.handle(_command(timeout_secs=30))


# ---------------------------------------------------------------------------
# I-M-1-CHECK: check_im1_invariant (Spec_v6 §4.8, §5)
# ---------------------------------------------------------------------------

class TestCheckIm1Invariant:
    @patch("sdd.commands.validate_invariants.MetricsAggregator")
    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_check_im1_pass(self, mock_querier_cls, mock_agg_cls):
        """Returns PASS when MetricsAggregator reports no im1_violations (I-M-1-CHECK)."""
        mock_summary = MagicMock()
        mock_summary.im1_violations = ()
        mock_agg_cls.return_value.aggregate.return_value = mock_summary
        mock_querier_cls.return_value.query.return_value = ()

        result = check_im1_invariant(db_path=":memory:", phase_id=6)

        assert result.status == "PASS"
        assert result.failing_task_ids == ()

    @patch("sdd.commands.validate_invariants.MetricsAggregator")
    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_check_im1_fail_missing_metric(self, mock_querier_cls, mock_agg_cls):
        """Returns FAIL when at least one TaskCompleted lacks a paired MetricRecorded (I-M-1-CHECK)."""
        mock_summary = MagicMock()
        mock_summary.im1_violations = ("T-601",)
        mock_agg_cls.return_value.aggregate.return_value = mock_summary
        mock_querier_cls.return_value.query.return_value = ()

        result = check_im1_invariant(db_path=":memory:", phase_id=6)

        assert result.status == "FAIL"

    @patch("sdd.commands.validate_invariants.MetricsAggregator")
    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_check_im1_fail_reports_task_ids(self, mock_querier_cls, mock_agg_cls):
        """FAIL result includes all task IDs that are missing MetricRecorded (I-M-1-CHECK)."""
        mock_summary = MagicMock()
        mock_summary.im1_violations = ("T-601", "T-603")
        mock_agg_cls.return_value.aggregate.return_value = mock_summary
        mock_querier_cls.return_value.query.return_value = ()

        result = check_im1_invariant(db_path=":memory:", phase_id=6)

        assert result.status == "FAIL"
        assert set(result.failing_task_ids) == {"T-601", "T-603"}

    def test_no_command_handler_in_im1_check(self):
        """check_im1_invariant does not import or use any other CommandHandler (I-CHAIN-1)."""
        import sdd.commands.validate_invariants as mod

        other_handlers = [
            name
            for name in dir(mod)
            if name.endswith("Handler") and name != "ValidateInvariantsHandler"
        ]
        assert other_handlers == [], (
            f"check_im1_invariant module imports unexpected handlers: {other_handlers}"
        )


# ---------------------------------------------------------------------------
# I-ACCEPT-1: per-task acceptance check enforcement (Spec_v8 §9 Test #5)
# ---------------------------------------------------------------------------

class TestAcceptanceEnforcement:
    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_acceptance_command_runs(self, mock_run, tmp_path):
        """_run_acceptance_check calls ruff and pytest when outputs exist and both pass."""
        output_file = tmp_path / "module.py"
        output_file.write_text("x = 1\n")
        mock_run.return_value = _ok_result(0)

        rc = _run_acceptance_check(
            outputs=[str(output_file)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
        )

        assert rc == 0
        assert mock_run.call_count == 2  # ruff + pytest

    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_acceptance_blocks_done_on_lint_failure(self, mock_run, tmp_path):
        """_run_acceptance_check returns 1 and stops when ruff exits non-zero (I-ACCEPT-1)."""
        output_file = tmp_path / "module.py"
        output_file.write_text("x = 1\n")
        mock_run.return_value = _ok_result(returncode=1)

        rc = _run_acceptance_check(
            outputs=[str(output_file)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
        )

        assert rc == 1
        assert mock_run.call_count == 1  # pytest not called after ruff failure

    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_acceptance_blocks_done_on_test_failure(self, mock_run, tmp_path):
        """_run_acceptance_check returns 1 when pytest exits non-zero (I-ACCEPT-1)."""
        output_file = tmp_path / "module.py"
        output_file.write_text("x = 1\n")
        mock_run.side_effect = [_ok_result(0), _ok_result(returncode=1)]

        rc = _run_acceptance_check(
            outputs=[str(output_file)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
        )

        assert rc == 1

    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_outputs_expansion(self, mock_run, tmp_path):
        """ruff receives output paths as list elements; shell=True is never used (I-ACCEPT-1)."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("")
        f2.write_text("")
        mock_run.return_value = _ok_result(0)

        _run_acceptance_check(
            outputs=[str(f1), str(f2)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
        )

        ruff_call = mock_run.call_args_list[0]
        cmd = ruff_call.args[0]
        assert isinstance(cmd, list), "subprocess must be called with a list, not a shell string"
        assert cmd[:2] == ["ruff", "check"]
        assert str(f1) in cmd
        assert str(f2) in cmd
        assert ruff_call.kwargs.get("shell") is not True
