"""Tests for run_guard_pipeline — Spec_v3 §4.7, I-GRD-4.

Test cases (5):
  test_runner_stops_on_first_deny_default
  test_runner_runs_all_when_stop_false
  test_runner_returns_all_allow_results
  test_runner_empty_guards_returns_empty
  test_runner_is_pure_orchestrator
"""

from unittest.mock import MagicMock

from sdd.guards.runner import GuardOutcome, GuardResult, run_guard_pipeline


def _allow(name: str = "g") -> GuardResult:
    return GuardResult(GuardOutcome.ALLOW, name, "", None, None)


def _deny(name: str = "g") -> GuardResult:
    return GuardResult(GuardOutcome.DENY, name, "denied", None, None)


def test_runner_empty_guards_returns_empty():
    assert run_guard_pipeline([]) == []


def test_runner_returns_all_allow_results():
    results = run_guard_pipeline([lambda: _allow("a"), lambda: _allow("b"), lambda: _allow("c")])
    assert len(results) == 3
    assert all(r.outcome is GuardOutcome.ALLOW for r in results)


def test_runner_stops_on_first_deny_default():
    calls = []

    def g_deny():
        calls.append("deny")
        return _deny("first")

    def g_after():
        calls.append("after")
        return _allow("second")

    results = run_guard_pipeline([lambda: _allow("pre"), g_deny, g_after])
    assert len(results) == 2
    assert results[-1].outcome is GuardOutcome.DENY
    assert "after" not in calls


def test_runner_runs_all_when_stop_false():
    calls = []

    def g1():
        calls.append("g1")
        return _deny("g1")

    def g2():
        calls.append("g2")
        return _allow("g2")

    results = run_guard_pipeline([g1, g2], stop_on_deny=False)
    assert len(results) == 2
    assert calls == ["g1", "g2"]
    assert results[0].outcome is GuardOutcome.DENY
    assert results[1].outcome is GuardOutcome.ALLOW


def test_runner_is_pure_orchestrator():
    """Pipeline must not inspect guard logic — each callable is a black box."""
    mock_guard = MagicMock(return_value=_allow("mock"))
    results = run_guard_pipeline([mock_guard, mock_guard])
    assert mock_guard.call_count == 2
    assert all(r.outcome is GuardOutcome.ALLOW for r in results)
