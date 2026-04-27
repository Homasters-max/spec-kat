"""Tests for validate_invariants — Spec_v31 §9 + I-2, I-DB-TEST-1, I-DB-TEST-2.

Invariants: I-2, I-DB-TEST-1, I-DB-TEST-2
Spec ref: Spec_v31 §9 #7 (hash match → PASS), #8 (hash diverge → FAIL с деталями)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from sdd.commands.validate_invariants import (
    ValidateInvariantsCommand,
    ValidateInvariantsHandler,
    _check_i_sdd_hash,
    main,
)
from sdd.infra.db import DuckDBLockTimeoutError, open_sdd_connection
from sdd.infra.paths import event_store_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec_approved_record(payload: dict) -> MagicMock:
    rec = MagicMock()
    rec.payload = json.dumps(payload)
    return rec


def _command(
    *,
    phase_id: int = 31,
    task_id: str | None = "T-3114",
    cwd: str = "/project",
    db_path: str = ":memory:",
    validation_mode: str = "task",
) -> ValidateInvariantsCommand:
    return ValidateInvariantsCommand(
        command_id=str(uuid.uuid4()),
        command_type="ValidateInvariants",
        payload={},
        phase_id=phase_id,
        task_id=task_id,
        config_path=".sdd/config/project_profile.yaml",
        cwd=cwd,
        env_whitelist=(),
        timeout_secs=30,
        task_outputs=(),
        validation_mode=validation_mode,
    )


# ---------------------------------------------------------------------------
# §9 #7, #8, SKIP: _check_i_sdd_hash acceptance criteria (I-SDD-HASH)
# ---------------------------------------------------------------------------

class TestSpecHashAcceptance:
    """Spec_v31 §9 acceptance tests for the I-SDD-HASH invariant check."""

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_no_spec_approved_returns_skip(self, mock_querier_cls) -> None:
        """§9 SKIP: no SpecApproved event → SKIP (not FAIL)."""
        mock_querier_cls.return_value.query.return_value = ()

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd="/project")

        assert result == "SKIP"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_hash_match_returns_pass(self, mock_querier_cls, tmp_path) -> None:
        """§9 #7: sha256(spec_path)[:16] matches stored spec_hash → PASS."""
        content = b"# Spec v31 content"
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(content)
        stored_hash = hashlib.sha256(content).hexdigest()[:16]

        mock_querier_cls.return_value.query.return_value = (
            _make_spec_approved_record({
                "phase_id": 31,
                "spec_hash": stored_hash,
                "spec_path": str(spec_file),
            }),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "PASS"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_hash_diverge_returns_fail(self, mock_querier_cls, tmp_path) -> None:
        """§9 #8: spec file modified after approval — hash diverges → FAIL."""
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(b"# Content modified after approval")

        mock_querier_cls.return_value.query.return_value = (
            _make_spec_approved_record({
                "phase_id": 31,
                "spec_hash": "0000000000000000",  # stale
                "spec_path": str(spec_file),
            }),
        )

        result = _check_i_sdd_hash(db_path=":memory:", phase_id=31, cwd=str(tmp_path))

        assert result == "FAIL"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_cli_fail_outputs_json_details_and_exits_1(
        self, mock_querier_cls, tmp_path, capsys
    ) -> None:
        """§9 #8: CLI --check I-SDD-HASH on mismatch prints JSON details and exits 1."""
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(b"# Modified after approval")

        mock_querier_cls.return_value.query.return_value = (
            _make_spec_approved_record({
                "phase_id": 31,
                "spec_hash": "0000000000000000",
                "spec_path": str(spec_file),
            }),
        )

        rc = main([
            "--check", "I-SDD-HASH",
            "--phase", "31",
            "--cwd", str(tmp_path),
            "--db", ":memory:",
        ])

        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["result"] == "FAIL"
        assert out["check"] == "I-SDD-HASH"
        assert out["phase_id"] == 31

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_cli_pass_outputs_json_and_exits_0(
        self, mock_querier_cls, tmp_path, capsys
    ) -> None:
        """§9 #7: CLI --check I-SDD-HASH on hash match prints JSON and exits 0."""
        content = b"# Spec v31"
        spec_file = tmp_path / "Spec_v31.md"
        spec_file.write_bytes(content)
        stored_hash = hashlib.sha256(content).hexdigest()[:16]

        mock_querier_cls.return_value.query.return_value = (
            _make_spec_approved_record({
                "phase_id": 31,
                "spec_hash": stored_hash,
                "spec_path": str(spec_file),
            }),
        )

        rc = main([
            "--check", "I-SDD-HASH",
            "--phase", "31",
            "--cwd", str(tmp_path),
            "--db", ":memory:",
        ])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["result"] == "PASS"

    @patch("sdd.commands.validate_invariants.EventLogQuerier")
    def test_cli_skip_exits_0_not_1(self, mock_querier_cls, tmp_path, capsys) -> None:
        """§9 SKIP: no SpecApproved → CLI exits 0 (SKIP is not a failure)."""
        mock_querier_cls.return_value.query.return_value = ()

        rc = main([
            "--check", "I-SDD-HASH",
            "--phase", "31",
            "--cwd", str(tmp_path),
            "--db", ":memory:",
        ])

        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["result"] == "SKIP"


# ---------------------------------------------------------------------------
# I-DB-TEST-1: test context must not open production DB
# ---------------------------------------------------------------------------

class TestDbIsolation:
    """I-DB-TEST-1: tests use isolated DB, never production DB."""

    def test_handler_db_path_differs_from_production(self, tmp_db_path: str) -> None:
        """ValidateInvariantsHandler initialized with isolated tmp DB (I-DB-TEST-1)."""
        prod_path = event_store_file().resolve()
        test_path = Path(tmp_db_path).resolve()

        assert test_path != prod_path, (
            "tmp_db_path must not resolve to production DB (I-DB-TEST-1)"
        )
        handler = ValidateInvariantsHandler(db_path=tmp_db_path)
        assert handler is not None

    def test_production_db_raises_in_test_context(self) -> None:
        """open_sdd_connection on production DB path raises RuntimeError in test context (I-DB-TEST-1)."""
        assert os.environ.get("PYTEST_CURRENT_TEST"), (
            "PYTEST_CURRENT_TEST must be set — this test must run inside pytest"
        )
        prod_path = str(event_store_file())

        with pytest.raises(RuntimeError, match="I-DB-TEST-1"):
            open_sdd_connection(prod_path)


# ---------------------------------------------------------------------------
# I-DB-TEST-2: test context forces timeout_secs = 0.0 (fail-fast on lock)
# ---------------------------------------------------------------------------

class TestDbTestTimeout:
    """I-DB-TEST-2: open_sdd_connection uses timeout_secs=0.0 in PYTEST_CURRENT_TEST context."""

    def test_lock_fails_immediately_in_test_context(
        self, tmp_path, monkeypatch
    ) -> None:
        """Caller-supplied timeout is ignored in test context; lock contention fails fast (I-DB-TEST-2)."""
        db_path = str(tmp_path / "locked.duckdb")

        def _raise_lock(*args, **kwargs):
            raise duckdb.IOException("Could not set lock on file 'x'")

        monkeypatch.setattr(duckdb, "connect", _raise_lock)

        start = time.monotonic()
        with pytest.raises(DuckDBLockTimeoutError):
            open_sdd_connection(db_path, timeout_secs=60.0)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"Expected immediate failure (timeout forced 0.0 via I-DB-TEST-2), "
            f"took {elapsed:.2f}s — PYTEST_CURRENT_TEST not applied"
        )


# ---------------------------------------------------------------------------
# I-2: handler is a pure emitter — EventLog.append called by caller, not handler
# ---------------------------------------------------------------------------

class TestHandlerPurity:
    """I-2: ValidateInvariantsHandler.handle() returns events; it does not call EventLog.append."""

    @patch("sdd.commands.validate_invariants.load_config")
    @patch("sdd.commands.validate_invariants.subprocess.Popen")
    def test_handle_returns_events_without_appending(
        self, mock_popen, mock_load, tmp_db_path: str
    ) -> None:
        """handler.handle() emits events but does not write to DB — pure emitter (I-2, I-ES-2).

        Verified by: DB has zero rows after handle(); all events are returned to the caller.
        """
        from sdd.infra.db import open_sdd_connection

        mock_load.return_value = {"build": {"commands": {"lint": "echo lint"}}}
        proc = MagicMock()
        proc.returncode = 0
        proc.pid = 1234
        proc.communicate.return_value = (b"ok", b"")
        mock_popen.return_value = proc

        handler = ValidateInvariantsHandler(db_path=tmp_db_path)
        cmd = _command(cwd="/project")

        with patch.object(handler, "_check_idempotent", return_value=False):
            events = handler.handle(cmd)

        # Handler is a pure emitter — DB must be empty after handle()
        conn = open_sdd_connection(tmp_db_path, read_only=True)
        row_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()

        assert row_count == 0, (
            f"Handler must not write to DB directly (I-2, I-ES-2); found {row_count} row(s)"
        )
        assert len(events) >= 2, "Handler must return at least TestRunCompleted + MetricRecorded"
        event_types = {e.event_type for e in events}
        assert "TestRunCompleted" in event_types
        assert "MetricRecorded" in event_types
