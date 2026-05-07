"""Unit tests for sdd.eval.eval_harness — ScenarioResult + run_graph_cmd."""
from unittest.mock import MagicMock, patch

import pytest

from sdd.eval.eval_harness import ScenarioResult, run_graph_cmd


def test_scenario_result_fields():
    r = ScenarioResult(
        scenario_id="S1",
        status="PASS",
        stdout="ok\n",
        stderr="",
        exit_code=0,
    )
    assert r.scenario_id == "S1"
    assert r.status == "PASS"
    assert r.stdout == "ok\n"
    assert r.stderr == ""
    assert r.exit_code == 0


def test_run_graph_cmd_pass():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "result output\n"
    mock_result.stderr = ""

    with patch("sdd.eval.eval_harness.subprocess.run", return_value=mock_result) as mock_run:
        result = run_graph_cmd("resolve", ["GraphSessionState", "--format", "json"])

    mock_run.assert_called_once_with(
        ["sdd", "resolve", "GraphSessionState", "--format", "json"],
        capture_output=True,
        text=True,
    )
    assert isinstance(result, ScenarioResult)
    assert result.status == "PASS"
    assert result.exit_code == 0
    assert result.stdout == "result output\n"


def test_run_graph_cmd_fail():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = '{"error_type": "GuardFailed"}'

    with patch("sdd.eval.eval_harness.subprocess.run", return_value=mock_result):
        result = run_graph_cmd("graph-guard", ["check", "--session-id", "bad-id"])

    assert result.status == "FAIL"
    assert result.exit_code == 1
    assert "GuardFailed" in result.stderr


def test_run_graph_cmd_no_args():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "[]"
    mock_result.stderr = ""

    with patch("sdd.eval.eval_harness.subprocess.run", return_value=mock_result) as mock_run:
        result = run_graph_cmd("trace", [])

    mock_run.assert_called_once_with(
        ["sdd", "trace"],
        capture_output=True,
        text=True,
    )
    assert result.status == "PASS"
