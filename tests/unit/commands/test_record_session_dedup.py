"""Unit tests for record-session command dedup behavior in execute_command.

Invariants: I-COMMAND-OBSERVABILITY-1, I-COMMAND-NOOP-2,
            I-SESSIONS-VIEW-LOCAL-1, I-GUARD-CONTEXT-UNCHANGED-1
"""
from __future__ import annotations

import dataclasses
import logging
from unittest.mock import MagicMock, patch

import pytest

from sdd.commands.registry import REGISTRY, CommandSpec, execute_command
from sdd.domain.guards.context import GuardContext, GuardOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_state() -> MagicMock:
    s = MagicMock()
    s.phase_current = 48
    s.phase_status = "ACTIVE"
    s.state_hash = "a" * 64
    return s


def _allow_guard_result() -> MagicMock:
    r = MagicMock()
    r.outcome = GuardOutcome.ALLOW
    r.reason = None
    return r


def _session_cmd() -> MagicMock:
    cmd = MagicMock(spec_set=["session_type", "phase_id", "payload"])
    cmd.session_type = "IMPLEMENT"
    cmd.phase_id = 48
    cmd.payload = {"session_type": "IMPLEMENT", "phase_id": 48}
    return cmd


def _dedup_spec(should_emit: bool) -> CommandSpec:
    """Return a record-session CommandSpec with a mock dedup_policy controlling should_emit."""
    mock_policy = MagicMock()
    mock_policy.should_emit.return_value = should_emit
    return dataclasses.replace(REGISTRY["record-session"], dedup_policy=mock_policy)


# ---------------------------------------------------------------------------
# test_dedup_logs_info_not_warning — I-COMMAND-OBSERVABILITY-1
# ---------------------------------------------------------------------------

def test_dedup_logs_info_not_warning(caplog):
    """Session dedup MUST log at INFO level, not WARNING (I-COMMAND-OBSERVABILITY-1)."""
    spec = _dedup_spec(should_emit=False)
    cmd = _session_cmd()
    mock_el = MagicMock()
    mock_el.max_seq.return_value = 5

    with (
        patch("sdd.commands.registry.get_current_state", return_value=_mock_state()),
        patch("sdd.commands.registry._run_domain_pipeline", return_value=(_allow_guard_result(), [])),
        patch("sdd.commands.registry.load_catalog", return_value=MagicMock()),
        patch("sdd.commands.registry.compute_command_id", return_value="cmd-id"),
        patch("sdd.commands.registry.compute_trace_id", return_value="trace-id"),
        patch.dict("os.environ", {"SDD_DATABASE_URL": "postgresql://test/db"}),
        patch("sdd.db.connection.open_db_connection", return_value=MagicMock()),
        patch("sdd.infra.projector._sync_p_sessions"),
        patch("sdd.infra.projector.build_sessions_view", return_value=MagicMock()),
        patch("sdd.infra.metrics.record_metric"),
    ):
        with caplog.at_level(logging.DEBUG, logger="sdd.commands.registry"):
            result = execute_command(spec, cmd, event_log=mock_el)

    assert result == []
    dedup_records = [r for r in caplog.records if "deduplicated" in r.message.lower()]
    assert dedup_records, "No log record containing 'deduplicated' found"
    assert all(r.levelno == logging.INFO for r in dedup_records), (
        f"Dedup MUST log at INFO (I-COMMAND-OBSERVABILITY-1), got: "
        f"{[r.levelname for r in dedup_records]}"
    )
    assert not any(r.levelno == logging.WARNING for r in caplog.records), (
        "Dedup path MUST NOT log at WARNING (I-COMMAND-OBSERVABILITY-1)"
    )


# ---------------------------------------------------------------------------
# test_dedup_increments_metric_with_labels — I-COMMAND-NOOP-2
# ---------------------------------------------------------------------------

def test_dedup_increments_metric_with_labels():
    """Session dedup MUST call record_metric with session_type and phase_id labels (I-COMMAND-NOOP-2)."""
    spec = _dedup_spec(should_emit=False)
    cmd = _session_cmd()
    mock_el = MagicMock()
    mock_el.max_seq.return_value = 5

    with (
        patch("sdd.commands.registry.get_current_state", return_value=_mock_state()),
        patch("sdd.commands.registry._run_domain_pipeline", return_value=(_allow_guard_result(), [])),
        patch("sdd.commands.registry.load_catalog", return_value=MagicMock()),
        patch("sdd.commands.registry.compute_command_id", return_value="cmd-id"),
        patch("sdd.commands.registry.compute_trace_id", return_value="trace-id"),
        patch.dict("os.environ", {"SDD_DATABASE_URL": "postgresql://test/db"}),
        patch("sdd.db.connection.open_db_connection", return_value=MagicMock()),
        patch("sdd.infra.projector._sync_p_sessions"),
        patch("sdd.infra.projector.build_sessions_view", return_value=MagicMock()),
        patch("sdd.infra.metrics.record_metric") as mock_metric,
    ):
        result = execute_command(spec, cmd, event_log=mock_el)

    assert result == []
    mock_metric.assert_called_once()
    args, kwargs = mock_metric.call_args
    assert args[0] == "session_dedup_skipped_total", (
        f"Expected metric 'session_dedup_skipped_total', got {args[0]!r}"
    )
    context = kwargs.get("context", {})
    assert "session_type" in context, f"Metric context must include 'session_type': {context}"
    assert "phase_id" in context, f"Metric context must include 'phase_id': {context}"


# ---------------------------------------------------------------------------
# test_noop_does_not_affect_projections — I-COMMAND-NOOP-2
# ---------------------------------------------------------------------------

def test_noop_does_not_affect_projections():
    """Dedup noop MUST return [] and MUST NOT append any events to EventLog (I-COMMAND-NOOP-2)."""
    spec = _dedup_spec(should_emit=False)
    cmd = _session_cmd()
    mock_el = MagicMock()
    mock_el.max_seq.return_value = 5

    with (
        patch("sdd.commands.registry.get_current_state", return_value=_mock_state()),
        patch("sdd.commands.registry._run_domain_pipeline", return_value=(_allow_guard_result(), [])),
        patch("sdd.commands.registry.load_catalog", return_value=MagicMock()),
        patch("sdd.commands.registry.compute_command_id", return_value="cmd-id"),
        patch("sdd.commands.registry.compute_trace_id", return_value="trace-id"),
        patch.dict("os.environ", {"SDD_DATABASE_URL": "postgresql://test/db"}),
        patch("sdd.db.connection.open_db_connection", return_value=MagicMock()),
        patch("sdd.infra.projector._sync_p_sessions"),
        patch("sdd.infra.projector.build_sessions_view", return_value=MagicMock()),
        patch("sdd.infra.metrics.record_metric"),
    ):
        result = execute_command(spec, cmd, event_log=mock_el)

    assert result == [], "Dedup noop MUST return [] (I-COMMAND-NOOP-2)"
    mock_el.append.assert_not_called()


# ---------------------------------------------------------------------------
# test_non_dedup_command_skips_step0 — I-SESSIONS-VIEW-LOCAL-1
# ---------------------------------------------------------------------------

def test_non_dedup_command_skips_step0():
    """Command with no dedup_policy MUST NOT build sessions_view even when SDD_DATABASE_URL is set
    (I-SESSIONS-VIEW-LOCAL-1).

    The Pre-Step (sessions_view construction) is gated on spec.dedup_policy is not None.
    Verified by halting at Step 1 (get_current_state) and asserting build_sessions_view was
    never reached.
    """
    spec = REGISTRY["complete"]
    assert spec.dedup_policy is None, "Precondition: 'complete' spec has no dedup_policy"

    cmd = MagicMock()
    cmd.payload = {"task_id": "T-0001", "phase_id": 48}
    mock_el = MagicMock()
    mock_el.max_seq.return_value = 5

    with (
        patch.dict("os.environ", {"SDD_DATABASE_URL": "postgresql://test/db"}),
        patch("sdd.commands.registry.compute_command_id", return_value="cmd-id"),
        patch("sdd.commands.registry.compute_trace_id", return_value="trace-id"),
        patch("sdd.commands.registry.get_current_state", side_effect=RuntimeError("stop")),
        patch("sdd.commands.registry._write_error_to_audit_log"),
        patch("sdd.db.connection.open_db_connection") as mock_open_db,
        patch("sdd.infra.projector.build_sessions_view") as mock_build_view,
    ):
        with pytest.raises(RuntimeError, match="stop"):
            execute_command(spec, cmd, event_log=mock_el)

    mock_open_db.assert_not_called()
    mock_build_view.assert_not_called()


# ---------------------------------------------------------------------------
# test_guard_context_has_no_sessions_view — I-GUARD-CONTEXT-UNCHANGED-1
# ---------------------------------------------------------------------------

def test_guard_context_has_no_sessions_view():
    """GuardContext MUST NOT contain a sessions_view field (I-GUARD-CONTEXT-UNCHANGED-1).

    sessions_view is a pre-guard concern; the domain guard pipeline receives only pure
    domain context with no dedup infrastructure.
    """
    field_names = {f.name for f in dataclasses.fields(GuardContext)}
    assert "sessions_view" not in field_names, (
        "GuardContext MUST NOT expose sessions_view — dedup is a pre-guard concern "
        "(I-GUARD-CONTEXT-UNCHANGED-1)"
    )
