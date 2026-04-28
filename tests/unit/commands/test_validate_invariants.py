"""Tests for ValidateInvariantsHandler — Spec_v4 §9 Verification row 8, Spec_v8 §9 Test #5.

Invariants: I-CMD-1, I-CMD-6, I-CMD-13, I-M-1-CHECK, I-CHAIN-1, I-ACCEPT-1
"""
from __future__ import annotations

import subprocess
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from sdd.infra.event_log import EventLog
from sdd.commands.validate_invariants import (
    InvariantCheckResult,
    ValidateInvariantsCommand,
    ValidateInvariantsHandler,
    _check_i_sdd_hash,
    _run_acceptance_check,
    check_im1_invariant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _command(
    *,
    command_id: str | None = None,
    phase_id: int = 4,
    task_id: str | None = "T-418",
    config_path: str = ".sdd/config/project_profile.yaml",
    cwd: str = "/project",
    env_whitelist: tuple[str, ...] = (),
    timeout_secs: int = 30,
    task_outputs: tuple[str, ...] = (),
    validation_mode: str = "system",  # existing tests exercise system (all-commands) behavior
) -> ValidateInvariantsCommand:
    return ValidateInvariantsCommand(
        command_id=command_id or str(uuid.uuid4()),
        command_type="ValidateInvariants",
        payload={},
        phase_id=phase_id,
        task_id=task_id,
        config_path=config_path,
        cwd=cwd,
        env_whitelist=env_whitelist,
        timeout_secs=timeout_secs,
        task_outputs=task_outputs,
        validation_mode=validation_mode,
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


def _popen_mock(returncode: int = 0, stdout: bytes = b"ok\n", stderr: bytes = b"") -> MagicMock:
    """Return a MagicMock that looks like a subprocess.Popen instance."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.pid = 12345
    proc.communicate.return_value = (stdout, stderr)
    return proc


@pytest.fixture
def handler(tmp_path):
    return ValidateInvariantsHandler(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# Runs all build.commands (I-CMD-6)
# ---------------------------------------------------------------------------

class TestRunsAllCommands:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_runs_all_build_commands(self, mock_popen, mock_load, handler):
        """Handler invokes subprocess.Popen once per entry in build.commands (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_popen.return_value = _popen_mock()

        events = handler.handle(_command())

        assert mock_popen.call_count == 3
        called_cmds = [c.args[0] for c in mock_popen.call_args_list]
        assert set(called_cmds) == {"run-lint", "run-typecheck", "run-test"}

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_emits_metric_per_command(self, mock_popen, mock_load, handler):
        """Handler emits TestRunCompletedEvent + MetricRecorded for each build command."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_popen.return_value = _popen_mock()

        events = handler.handle(_command())

        # 2 events per command → 6 total
        assert len(events) == 6
        event_types = [e.event_type for e in events]
        assert event_types.count("TestRunCompleted") == 3
        assert event_types.count("MetricRecorded") == 3

        metric_ids = {e.metric_id for e in events if e.event_type == "MetricRecorded"}
        assert metric_ids == {"quality.lint", "quality.typecheck", "quality.test"}

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_no_extra_commands(self, mock_popen, mock_load, handler):
        """Handler runs only commands declared in build.commands — no additions (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint")
        mock_popen.return_value = _popen_mock()

        events = handler.handle(_command())

        assert mock_popen.call_count == 1
        assert len(events) == 2  # one TestRunCompleted + one MetricRecorded


# ---------------------------------------------------------------------------
# Continues on failure (I-CMD-6)
# ---------------------------------------------------------------------------

class TestContinuesOnFailure:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_continues_on_failure(self, mock_popen, mock_load, handler):
        """Non-zero returncode does not abort the loop — all commands execute (I-CMD-6)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        # lint fails, rest succeed
        mock_popen.side_effect = [
            _popen_mock(returncode=1),
            _popen_mock(returncode=0),
            _popen_mock(returncode=0),
        ]

        events = handler.handle(_command())

        assert mock_popen.call_count == 3
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
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_validate_inv_idempotent(self, mock_popen, mock_load, handler):
        """Duplicate command_id returns [] without running any subprocess (I-CMD-1, I-TEST-IDEM-1)."""
        mock_load.return_value = _fake_config("lint", "test")
        mock_popen.return_value = _popen_mock()

        cmd_id = str(uuid.uuid4())
        cmd = _command(command_id=cmd_id)

        # First call: fresh DB → _check_idempotent returns False → handler runs normally
        first_result = handler.handle(cmd)
        assert len(first_result) > 0

        # Persist events so _check_idempotent finds command_id on the second call
        EventLog(handler._db_path).append(
            first_result, source="test", command_id=cmd_id, allow_outside_kernel="test"
        )

        # Second call: same command_id → _check_idempotent returns True → returns []
        mock_popen.reset_mock()
        result = handler.handle(cmd)

        assert result == []
        mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Subprocess determinism constraints (I-CMD-13)
# ---------------------------------------------------------------------------

class TestSubprocessConstraints:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_subprocess_uses_explicit_cwd(self, mock_popen, mock_load, handler):
        """subprocess.Popen is called with cwd=command.cwd — never os.getcwd() (I-CMD-13)."""
        mock_load.return_value = _fake_config("lint")
        mock_popen.return_value = _popen_mock()
        cmd = _command(cwd="/explicit/project/root")

        handler.handle(cmd)

        _, kwargs = mock_popen.call_args
        assert kwargs["cwd"] == "/explicit/project/root"

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_subprocess_env_whitelist(self, mock_popen, mock_load, handler):
        """subprocess.Popen env contains only vars from env_whitelist; no os.environ fallback (I-CMD-13)."""
        mock_load.return_value = _fake_config("lint")
        mock_popen.return_value = _popen_mock()

        with patch("sdd.commands.validate_invariants.os.environ", {"PATH": "/usr/bin", "HOME": "/root", "SECRET": "x"}):
            cmd = _command(env_whitelist=("PATH",))
            handler.handle(cmd)

        _, kwargs = mock_popen.call_args
        assert kwargs["env"] == {"PATH": "/usr/bin"}
        assert "HOME" not in kwargs["env"]
        assert "SECRET" not in kwargs["env"]

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_subprocess_env_no_full_passthrough_when_whitelist_empty(
        self, mock_popen, mock_load, handler, monkeypatch
    ):
        """Empty env_whitelist → subprocess env contains only _ALWAYS_PASSTHROUGH vars (I-CMD-13, I-SUBPROCESS-ENV-1).

        Full os.environ must NOT be forwarded; arbitrary vars not in whitelist or passthrough
        must be absent even when present in the parent process environment.
        """
        from sdd.commands.validate_invariants import _ALWAYS_PASSTHROUGH

        monkeypatch.setenv("SECRET_TOKEN", "should-not-leak")
        monkeypatch.setenv("RANDOM_VAR", "also-not-here")
        mock_load.return_value = _fake_config("lint")
        mock_popen.return_value = _popen_mock()
        cmd = _command(env_whitelist=())

        handler.handle(cmd)

        _, kwargs = mock_popen.call_args
        subprocess_env: dict = kwargs["env"]
        # Arbitrary env vars must not leak through (I-CMD-13)
        assert "SECRET_TOKEN" not in subprocess_env
        assert "RANDOM_VAR" not in subprocess_env
        # Only _ALWAYS_PASSTHROUGH vars (if set) may appear
        for key in subprocess_env:
            assert key in _ALWAYS_PASSTHROUGH, f"Unexpected env var leaked: {key!r}"

    @patch("sdd.commands.validate_invariants.os.killpg")
    @patch("sdd.commands.validate_invariants.os.getpgid", return_value=12345)
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_subprocess_timeout_records_failure_and_continues(
        self, mock_popen, mock_load, mock_getpgid, mock_killpg, handler
    ):
        """Timeout kills process group, records returncode=124 (TIMEOUT_RETURN_CODE), continues loop (I-CMD-6, I-TIMEOUT-1)."""
        mock_load.return_value = _fake_config("test")
        proc = _popen_mock()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="pytest tests/", timeout=30),
            (b"", b""),  # second communicate() call after kill
        ]
        mock_popen.return_value = proc

        events = handler.handle(_command(timeout_secs=30))

        mock_killpg.assert_called_once_with(12345, __import__("signal").SIGKILL)
        assert len(events) == 2
        metric = next(e for e in events if e.event_type == "MetricRecorded")
        assert metric.value == 124.0  # I-TIMEOUT-1: TIMEOUT_RETURN_CODE


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
        """_run_acceptance_check calls ruff and reuses test_returncode when both pass (BC-22-2)."""
        output_file = tmp_path / "module.py"
        output_file.write_text("x = 1\n")
        mock_run.return_value = _ok_result(0)

        rc = _run_acceptance_check(
            outputs=[str(output_file)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
            test_returncode=0,
        )

        assert rc == 0
        assert mock_run.call_count == 1  # ruff only; pytest reused via test_returncode

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
            test_returncode=0,
        )

        assert rc == 1
        assert mock_run.call_count == 1  # pytest not called after ruff failure

    @patch("sdd.commands.validate_invariants.subprocess.run")
    def test_acceptance_blocks_done_on_test_failure(self, mock_run, tmp_path):
        """_run_acceptance_check returns 1 when test_returncode != 0 (BC-22-2, I-ACCEPT-REUSE-1)."""
        output_file = tmp_path / "module.py"
        output_file.write_text("x = 1\n")
        mock_run.return_value = _ok_result(0)

        rc = _run_acceptance_check(
            outputs=[str(output_file)],
            cwd=str(tmp_path),
            env={},
            timeout=30,
            test_returncode=1,
        )

        assert rc == 1
        assert mock_run.call_count == 1  # only ruff called; no pytest subprocess

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
            test_returncode=0,
        )

        ruff_call = mock_run.call_args_list[0]
        cmd = ruff_call.args[0]
        assert isinstance(cmd, list), "subprocess must be called with a list, not a shell string"
        assert cmd[:2] == ["ruff", "check"]
        assert str(f1) in cmd
        assert str(f2) in cmd


# ---------------------------------------------------------------------------
# IMP-001: task mode vs system mode (SDD_Improvements.md §IMP-001)
# ---------------------------------------------------------------------------

class TestValidationModes:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_task_mode_skips_test_command(self, mock_popen, mock_load, handler):
        """Task mode (default): 'test' command is not executed (IMP-001)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_popen.return_value = _popen_mock()

        cmd = ValidateInvariantsCommand(
            command_id=str(uuid.uuid4()),
            command_type="ValidateInvariants",
            payload={},
            phase_id=25,
            task_id="T-2511",
            config_path=".sdd/config/project_profile.yaml",
            cwd="/project",
            env_whitelist=(),
            timeout_secs=30,
            task_outputs=(),
            validation_mode="task",
        )
        handler.handle(cmd)

        executed = [call.args[0] for call in mock_popen.call_args_list]
        assert all("run-test" not in c for c in executed), (
            "test command must not run in task mode"
        )
        assert any("run-lint" in c for c in executed), "lint must still run in task mode"
        assert any("run-typecheck" in c for c in executed), "typecheck must still run in task mode"

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_system_mode_runs_all_commands(self, mock_popen, mock_load, handler):
        """System mode (--system): all build commands including test are executed (IMP-001)."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test")
        mock_popen.return_value = _popen_mock()

        cmd = ValidateInvariantsCommand(
            command_id=str(uuid.uuid4()),
            command_type="ValidateInvariants",
            payload={},
            phase_id=25,
            task_id=None,
            config_path=".sdd/config/project_profile.yaml",
            cwd="/project",
            env_whitelist=(),
            timeout_secs=30,
            task_outputs=(),
            validation_mode="system",
        )
        handler.handle(cmd)

        assert mock_popen.call_count == 3, "all three commands must run in system mode"
        executed = [call.args[0] for call in mock_popen.call_args_list]
        assert any("run-test" in c for c in executed), "test must run in system mode"
        assert any("run-lint" in c for c in executed)
        assert any("run-typecheck" in c for c in executed)

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")  # subprocess boundary — intentional
    def test_task_mode_skips_all_pytest_commands(self, mock_popen, mock_load, handler):
        """Task mode skips ALL keys starting with 'test' (e.g. test, test_full) — I-TASK-MODE-1."""
        mock_load.return_value = _fake_config("lint", "typecheck", "test", "test_full")
        mock_popen.return_value = _popen_mock()

        cmd = _command(validation_mode="task")
        handler.handle(cmd)

        executed = [c.args[0] for c in mock_popen.call_args_list]
        assert "run-test_full" not in executed, "test_full must not run in task mode"
        assert any("run-lint" in c for c in executed), "lint must still run in task mode"
        assert any("run-typecheck" in c for c in executed), "typecheck must still run in task mode"

    def test_task_mode_is_default(self):
        """ValidateInvariantsCommand.validation_mode defaults to 'task' (IMP-001, CLI-2)."""
        cmd = ValidateInvariantsCommand(
            command_id=str(uuid.uuid4()),
            command_type="ValidateInvariants",
            payload={},
            phase_id=25,
            task_id="T-2511",
            config_path=".sdd/config/project_profile.yaml",
            cwd="/project",
            env_whitelist=(),
            timeout_secs=30,
            task_outputs=(),
            # validation_mode intentionally omitted — testing production default
        )
        assert cmd.validation_mode == "task"


# ---------------------------------------------------------------------------
# I-SDD-HASH: _check_i_sdd_hash (T-3110)
# ---------------------------------------------------------------------------

class TestCheckISddHash:
    def _make_record(self, payload: dict) -> MagicMock:
        import json as _json
        rec = MagicMock()
        rec.payload = _json.dumps(payload)
        return rec

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_skip_when_no_spec_approved(self, mock_querier_cls):
        """Returns SKIP when no SpecApproved event exists for phase_id (T-3110)."""
        mock_querier_cls.return_value.query.return_value = ()

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd="/project")

        assert result == "SKIP"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_pass_when_hash_matches(self, mock_querier_cls, tmp_path):
        """Returns PASS when sha256(spec_path)[:16] matches spec_hash in SpecApproved (T-3110)."""
        import hashlib as _hashlib
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(b"# Spec content")
        expected_hash = _hashlib.sha256(b"# Spec content").hexdigest()[:16]

        mock_querier_cls.return_value.query.return_value = (
            self._make_record({
                "phase_id": 31,
                "spec_hash": expected_hash,
                "spec_path": str(spec_file),
            }),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "PASS"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_fail_when_hash_diverges(self, mock_querier_cls, tmp_path):
        """Returns FAIL when spec file has been modified after approval (T-3110)."""
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(b"# Modified content")

        mock_querier_cls.return_value.query.return_value = (
            self._make_record({
                "phase_id": 31,
                "spec_hash": "0000000000000000",  # stale hash
                "spec_path": str(spec_file),
            }),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "FAIL"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_fail_when_spec_file_missing(self, mock_querier_cls, tmp_path):
        """Returns FAIL when spec_path in SpecApproved event points to a nonexistent file (T-3110)."""
        mock_querier_cls.return_value.query.return_value = (
            self._make_record({
                "phase_id": 31,
                "spec_hash": "abcd1234abcd1234",
                "spec_path": str(tmp_path / "missing_spec.md"),
            }),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "FAIL"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_skip_when_spec_path_empty(self, mock_querier_cls):
        """Returns SKIP when SpecApproved payload has empty spec_path (T-3110)."""
        mock_querier_cls.return_value.query.return_value = (
            self._make_record({"phase_id": 31, "spec_hash": "abc", "spec_path": ""}),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd="/project")

        assert result == "SKIP"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_uses_most_recent_spec_approved(self, mock_querier_cls, tmp_path):
        """Uses the last SpecApproved event when multiple exist (most recent wins, T-3110)."""
        import hashlib as _hashlib
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(b"# Latest spec")
        current_hash = _hashlib.sha256(b"# Latest spec").hexdigest()[:16]

        mock_querier_cls.return_value.query.return_value = (
            self._make_record({"phase_id": 31, "spec_hash": "stale00000000000", "spec_path": str(spec_file)}),
            self._make_record({"phase_id": 31, "spec_hash": current_hash, "spec_path": str(spec_file)}),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "PASS"
