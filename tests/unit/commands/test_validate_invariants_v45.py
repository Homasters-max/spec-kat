"""Tests for I-SUBPROCESS-ENV-1 — Spec_v45 BC-45-C verification row 5."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.validate_invariants import (
    _ALWAYS_PASSTHROUGH,
    ValidateInvariantsCommand,
    ValidateInvariantsHandler,
)


def _command(
    *,
    env_whitelist: tuple[str, ...] = (),
    validation_mode: str = "system",
) -> ValidateInvariantsCommand:
    return ValidateInvariantsCommand(
        command_id=str(uuid.uuid4()),
        command_type="ValidateInvariants",
        payload={},
        phase_id=45,
        task_id="T-4503",
        config_path=".sdd/config/project_profile.yaml",
        cwd="/project",
        env_whitelist=env_whitelist,
        timeout_secs=10,
        task_outputs=(),
        validation_mode=validation_mode,
    )


def _popen_mock() -> MagicMock:
    proc = MagicMock()
    proc.returncode = 0
    proc.pid = 12345
    proc.communicate.return_value = (b"ok\n", b"")
    return proc


@pytest.fixture
def handler(pg_test_db: str):
    return ValidateInvariantsHandler(db_path=pg_test_db)


class TestAlwaysPassthrough:
    def test_always_passthrough_is_frozenset(self) -> None:
        """_ALWAYS_PASSTHROUGH must be a frozenset constant (I-SUBPROCESS-ENV-1)."""
        assert isinstance(_ALWAYS_PASSTHROUGH, frozenset)

    def test_always_passthrough_contains_required_vars(self) -> None:
        assert "SDD_DATABASE_URL" in _ALWAYS_PASSTHROUGH
        assert "SDD_PROJECT" in _ALWAYS_PASSTHROUGH
        assert "SDD_HOME" in _ALWAYS_PASSTHROUGH


class TestSubprocessEnvPassthrough:
    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")
    def test_validate_invariants_subprocess_gets_pg_url(
        self, mock_popen, mock_load, handler, monkeypatch
    ) -> None:
        """I-SUBPROCESS-ENV-1: SDD_DATABASE_URL passes to subprocess with empty env_whitelist."""
        pg_url = "postgresql://sdd:sdd@localhost:5432/sdd_test"
        monkeypatch.setenv("SDD_DATABASE_URL", pg_url)

        mock_load.return_value = {"build": {"commands": {"lint": "echo ok"}}}
        mock_popen.return_value = _popen_mock()

        handler.handle(_command(env_whitelist=()))

        assert mock_popen.call_count == 1
        _, kwargs = mock_popen.call_args
        subprocess_env: dict = kwargs["env"]
        assert subprocess_env.get("SDD_DATABASE_URL") == pg_url

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")
    def test_subprocess_env_merges_whitelist_and_passthrough(
        self, mock_popen, mock_load, handler, monkeypatch
    ) -> None:
        """_ALWAYS_PASSTHROUGH ∪ env_whitelist both reach subprocess env."""
        pg_url = "postgresql://sdd:sdd@localhost:5432/sdd_test"
        monkeypatch.setenv("SDD_DATABASE_URL", pg_url)
        monkeypatch.setenv("PYTHONPATH", "/custom")

        mock_load.return_value = {"build": {"commands": {"lint": "echo ok"}}}
        mock_popen.return_value = _popen_mock()

        handler.handle(_command(env_whitelist=("PYTHONPATH",)))

        _, kwargs = mock_popen.call_args
        subprocess_env: dict = kwargs["env"]
        assert subprocess_env.get("SDD_DATABASE_URL") == pg_url
        assert subprocess_env.get("PYTHONPATH") == "/custom"

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")
    def test_subprocess_env_skips_unset_passthrough_vars(
        self, mock_popen, mock_load, handler, monkeypatch
    ) -> None:
        """Unset _ALWAYS_PASSTHROUGH vars are not injected (no KeyError)."""
        monkeypatch.delenv("SDD_DATABASE_URL", raising=False)
        monkeypatch.delenv("SDD_PROJECT", raising=False)
        monkeypatch.delenv("SDD_HOME", raising=False)

        mock_load.return_value = {"build": {"commands": {"lint": "echo ok"}}}
        mock_popen.return_value = _popen_mock()

        # Must not raise
        handler.handle(_command(env_whitelist=()))

        _, kwargs = mock_popen.call_args
        subprocess_env: dict = kwargs["env"]
        assert "SDD_DATABASE_URL" not in subprocess_env
