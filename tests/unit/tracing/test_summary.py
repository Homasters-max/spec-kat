"""Unit tests for sdd.tracing.summary — TraceSummary + violation detection (BC-62-L4)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sdd.tracing.summary import (
    TraceSummary,
    build_context,
    compute_summary,
    detect_behavioral_violations,
    detect_violations,
    write_summary,
)
from sdd.tracing.trace_event import TraceEvent


def _ev(ts: float, typ: str, payload: dict | None = None, session_id: str = "s1", task_id: str = "T-001") -> TraceEvent:
    return TraceEvent(ts=ts, type=typ, payload=payload or {}, session_id=session_id, task_id=task_id)


class TestBuildContextCheckScope:

    def test_check_scope_read_grants_path(self) -> None:
        events = [_ev(1.0, "COMMAND", {"command": "sdd check-scope read src/new.py"})]
        with patch("sdd.tracing.summary._load_task_inputs", return_value=frozenset()):
            result = build_context("T-001", events)
        assert "src/new.py" in result

    def test_check_scope_write_grants_path(self) -> None:
        events = [_ev(1.0, "COMMAND", {"command": "sdd check-scope write src/out.py"})]
        with patch("sdd.tracing.summary._load_task_inputs", return_value=frozenset()):
            result = build_context("T-001", events)
        assert "src/out.py" in result

    def test_check_scope_shell_batch_grants_all_paths(self) -> None:
        cmd = 'INPUTS="src/a.py,src/b.py" && for f in $(echo $INPUTS | tr \',\' \'\\n\'); do sdd check-scope read $f; done'
        events = [_ev(1.0, "COMMAND", {"command": cmd})]
        with patch("sdd.tracing.summary._load_task_inputs", return_value=frozenset()):
            result = build_context("T-001", events)
        assert "src/a.py" in result
        assert "src/b.py" in result

    def test_non_check_scope_command_not_granted(self) -> None:
        events = [_ev(1.0, "COMMAND", {"command": "ls src/new.py"})]
        with patch("sdd.tracing.summary._load_task_inputs", return_value=frozenset()):
            result = build_context("T-001", events)
        assert "src/new.py" not in result

    def test_load_task_inputs_includes_outputs(self) -> None:
        from unittest.mock import MagicMock
        from sdd.tracing.summary import _load_task_inputs

        mock_task = MagicMock()
        mock_task.task_id = "T-001"
        mock_task.inputs = ("src/a.py",)
        mock_task.outputs = ("src/b.py",)

        with (
            patch("sdd.domain.tasks.parser.parse_taskset", return_value=[mock_task]),
            patch("sdd.infra.paths.taskset_file", return_value="fake.md"),
            patch("sdd.infra.paths.event_store_url", return_value="fake://"),
            patch("sdd.infra.projections.get_current_state") as mock_state,
        ):
            mock_state.return_value.phase_current = 1
            result = _load_task_inputs("T-001")

        assert "src/a.py" in result
        assert "src/b.py" in result

    def test_no_scope_violation_for_check_scope_granted_file(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd check-scope read src/extra.py"}),
            _ev(2.0, "GRAPH_CALL", {"command": "sdd resolve extra.py"}),
            _ev(3.0, "FILE_WRITE", {"path": "src/extra.py"}),
        ]
        with patch("sdd.tracing.summary._load_task_inputs", return_value=frozenset({"src/base.py"})):
            allowed = build_context("T-001", events)
            violations = detect_violations(events, allowed)
        assert not any("SCOPE_VIOLATION" in v and "src/extra.py" in v for v in violations)


class TestDetectViolations:

    def test_no_events_no_violations(self) -> None:
        assert detect_violations([], frozenset()) == []

    def test_file_write_without_prior_graph_call_is_hard_violation(self) -> None:
        events = [_ev(1.0, "FILE_WRITE", {"path": "src/foo.py"})]
        violations = detect_violations(events, frozenset())
        assert any("I-TRACE-COMPLETE-1" in v for v in violations)

    def test_file_write_after_graph_call_no_hard_violation(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL", {"cmd": "resolve"}),
            _ev(2.0, "FILE_WRITE", {"path": "src/foo.py"}),
        ]
        violations = detect_violations(events, frozenset())
        hard = [v for v in violations if "I-TRACE-COMPLETE-1" in v]
        assert hard == []

    def test_hard_violation_per_session_isolation(self) -> None:
        """GRAPH_CALL in s1 does not satisfy FILE_WRITE in s2."""
        events = [
            _ev(1.0, "GRAPH_CALL", {"cmd": "resolve"}, session_id="s1"),
            _ev(2.0, "FILE_WRITE", {"path": "src/foo.py"}, session_id="s2"),
        ]
        violations = detect_violations(events, frozenset())
        hard = [v for v in violations if "I-TRACE-COMPLETE-1" in v]
        assert len(hard) == 1
        assert "s2" in hard[0]

    def test_file_write_outside_allowed_files_is_soft_violation(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL"),
            _ev(2.0, "FILE_WRITE", {"path": "src/other.py"}),
        ]
        allowed = frozenset({"src/foo.py"})
        violations = detect_violations(events, allowed)
        soft = [v for v in violations if "SCOPE_VIOLATION" in v]
        assert any("src/other.py" in v for v in soft)

    def test_file_read_outside_allowed_files_is_soft_violation(self) -> None:
        events = [_ev(1.0, "FILE_READ", {"path": "src/other.py"})]
        allowed = frozenset({"src/foo.py"})
        violations = detect_violations(events, allowed)
        soft = [v for v in violations if "SCOPE_VIOLATION" in v]
        assert any("src/other.py" in v for v in soft)

    def test_empty_allowed_files_skips_scope_check(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL"),
            _ev(2.0, "FILE_WRITE", {"path": "anywhere.py"}),
            _ev(3.0, "FILE_READ", {"path": "anywhere.py"}),
        ]
        violations = detect_violations(events, frozenset())
        soft = [v for v in violations if "SCOPE_VIOLATION" in v]
        assert soft == []

    def test_file_write_in_allowed_files_no_scope_violation(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL"),
            _ev(2.0, "FILE_WRITE", {"path": "src/foo.py"}),
        ]
        allowed = frozenset({"src/foo.py"})
        violations = detect_violations(events, allowed)
        assert violations == []

    def test_multiple_writes_first_without_graph(self) -> None:
        """First FILE_WRITE violates I-TRACE-COMPLETE-1; second does not."""
        events = [
            _ev(1.0, "FILE_WRITE", {"path": "a.py"}),
            _ev(2.0, "GRAPH_CALL"),
            _ev(3.0, "FILE_WRITE", {"path": "b.py"}),
        ]
        violations = detect_violations(events, frozenset())
        hard = [v for v in violations if "I-TRACE-COMPLETE-1" in v]
        assert len(hard) == 1
        assert "a.py" in hard[0]


class TestComputeSummary:

    def test_counts_events_correctly(self, tmp_path) -> None:
        from sdd.tracing import writer

        events = [
            TraceEvent(ts=1.0, type="GRAPH_CALL", task_id="T-100"),
            TraceEvent(ts=2.0, type="FILE_READ", payload={"path": "x.py"}, task_id="T-100"),
            TraceEvent(ts=3.0, type="FILE_WRITE", payload={"path": "x.py"}, task_id="T-100"),
            TraceEvent(ts=4.0, type="COMMAND", task_id="T-100"),
        ]
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            for e in events:
                writer.append_event(e)

        with (
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.build_context", return_value=frozenset()),
        ):
            summary = compute_summary("T-100")

        assert summary.total_events == 4
        assert summary.graph_calls == 1
        assert summary.file_reads == 1
        assert summary.file_writes == 1
        assert summary.commands == 1

    def test_no_violations_when_graph_call_precedes_write(self, tmp_path) -> None:
        from sdd.tracing import writer

        events = [
            TraceEvent(ts=1.0, type="GRAPH_CALL", task_id="T-101"),
            TraceEvent(ts=2.0, type="FILE_WRITE", payload={"path": "f.py"}, task_id="T-101"),
        ]
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            for e in events:
                writer.append_event(e)

        with (
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.build_context", return_value=frozenset()),
        ):
            summary = compute_summary("T-101")

        assert summary.violations == []

    def test_empty_trace_produces_empty_summary(self, tmp_path) -> None:
        with (
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.build_context", return_value=frozenset()),
        ):
            summary = compute_summary("T-999")

        assert summary.total_events == 0
        assert summary.session_id == ""
        assert summary.violations == []


class TestWriteSummary:

    def test_creates_summary_json(self, tmp_path) -> None:
        summary = TraceSummary(
            task_id="T-200",
            session_id="s-abc",
            total_events=3,
            graph_calls=1,
            file_reads=1,
            file_writes=1,
            commands=0,
            violations=["I-TRACE-COMPLETE-1: FILE_WRITE on 'x.py' without prior GRAPH_CALL in session 's0'"],
        )
        with patch("sdd.tracing.summary.reports_dir", return_value=tmp_path):
            path = write_summary(summary)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["task_id"] == "T-200"
        assert data["total_events"] == 3
        assert len(data["violations"]) == 1

    def test_creates_parent_dirs(self, tmp_path) -> None:
        summary = TraceSummary(
            task_id="T-201", session_id="s", total_events=0,
            graph_calls=0, file_reads=0, file_writes=0, commands=0,
        )
        with patch("sdd.tracing.summary.reports_dir", return_value=tmp_path):
            path = write_summary(summary)

        assert path == tmp_path / "T-201" / "summary.json"


class TestDetectBehavioralViolations:

    def test_no_events_no_behavioral_violations(self) -> None:
        assert detect_behavioral_violations([]) == []

    def test_command_failure_ignored(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd complete T-001", "exit_code": 1}),
            _ev(2.0, "COMMAND", {"command": "ls", "exit_code": 0}),
            _ev(3.0, "COMMAND", {"command": "ls", "exit_code": 0}),
            _ev(4.0, "COMMAND", {"command": "ls", "exit_code": 0}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("COMMAND_FAILURE_IGNORED" in v for v in violations)

    def test_command_failure_not_ignored_when_graph_call_follows(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd complete T-001", "exit_code": 1}),
            _ev(2.0, "GRAPH_CALL", {"command": "sdd resolve X"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("COMMAND_FAILURE_IGNORED" in v for v in violations)

    def test_command_failure_not_ignored_when_file_write_follows(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest", "exit_code": 1}),
            _ev(2.0, "FILE_WRITE", {"path": "src/fix.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("COMMAND_FAILURE_IGNORED" in v for v in violations)

    def test_blind_write_detected(self) -> None:
        events = [
            _ev(1.0, "FILE_READ", {"path": "src/foo.py"}),
            _ev(2.0, "COMMAND", {"command": "ls"}),
            _ev(3.0, "FILE_WRITE", {"path": "src/bar.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("BLIND_WRITE" in v for v in violations)

    def test_blind_write_not_reported_when_graph_references_file(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL", {"command": "sdd resolve bar.py"}),
            _ev(2.0, "FILE_WRITE", {"path": "src/bar.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("BLIND_WRITE" in v for v in violations)

    def test_blind_write_reported_when_graph_does_not_reference_file(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL", {"command": "sdd resolve other.py"}),
            _ev(2.0, "FILE_WRITE", {"path": "src/bar.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("BLIND_WRITE" in v for v in violations)

    def test_blind_write_suppressed_beyond_window_of_5(self) -> None:
        events = (
            [_ev(float(i), "COMMAND", {"command": "make build"}) for i in range(10)]
            + [_ev(10.0, "GRAPH_CALL", {"command": "sdd explain bar.py"})]
            + [_ev(float(i + 11), "COMMAND", {"command": "make build"}) for i in range(7)]
            + [_ev(20.0, "FILE_WRITE", {"path": "src/bar.py"})]
        )
        violations = detect_behavioral_violations(events)
        assert not any("BLIND_WRITE" in v for v in violations)

    def test_thrashing_detected(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "make build"}),
            _ev(2.0, "COMMAND", {"command": "cargo test"}),
            _ev(3.0, "COMMAND", {"command": "npm install"}),
            _ev(4.0, "COMMAND", {"command": "tsc --noEmit"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("THRASHING" in v for v in violations)

    def test_thrashing_not_triggered_by_skip_commands(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(2.0, "COMMAND", {"command": "pytest tests/"}),
            _ev(3.0, "COMMAND", {"command": "git diff"}),
            _ev(4.0, "COMMAND", {"command": "grep -r foo src/"}),
            _ev(5.0, "COMMAND", {"command": "ls -la"}),
            _ev(6.0, "COMMAND", {"command": "cat file.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("THRASHING" in v for v in violations)

    def test_thrashing_not_triggered_by_python3_m_pytest(self) -> None:
        events = [_ev(float(i), "COMMAND", {"command": "python3 -m pytest tests/"}) for i in range(5)]
        violations = detect_behavioral_violations(events)
        assert not any("THRASHING" in v for v in violations)

    def test_thrashing_not_triggered_by_inputs_batch(self) -> None:
        cmd = 'INPUTS="src/a.py,src/b.py" && for f in $(echo $INPUTS | tr \',\' \'\\n\'); do sdd check-scope read $f; done'
        events = [_ev(float(i), "COMMAND", {"command": cmd}) for i in range(5)]
        violations = detect_behavioral_violations(events)
        assert not any("THRASHING" in v for v in violations)

    def test_thrashing_reset_by_graph_call(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "ls"}),
            _ev(2.0, "COMMAND", {"command": "pwd"}),
            _ev(3.0, "COMMAND", {"command": "echo hi"}),
            _ev(4.0, "GRAPH_CALL", {"command": "sdd resolve X"}),
            _ev(5.0, "COMMAND", {"command": "date"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("THRASHING" in v for v in violations)

    def test_loop_detected(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest tests/"}),
            _ev(2.0, "COMMAND", {"command": "pytest tests/"}),
            _ev(3.0, "COMMAND", {"command": "pytest tests/"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("LOOP_DETECTED" in v for v in violations)

    def test_loop_not_reported_for_two_repetitions(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest tests/"}),
            _ev(2.0, "COMMAND", {"command": "pytest tests/"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("LOOP_DETECTED" in v for v in violations)

    def test_explain_not_used_detected(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL", {"command": "sdd explain X"}),
            _ev(2.0, "COMMAND", {"command": "ls"}),
            _ev(3.0, "COMMAND", {"command": "ls"}),
            _ev(4.0, "COMMAND", {"command": "ls"}),
            _ev(5.0, "COMMAND", {"command": "ls"}),
            _ev(6.0, "COMMAND", {"command": "ls"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("EXPLAIN_NOT_USED" in v for v in violations)

    def test_explain_used_when_file_read_follows(self) -> None:
        events = [
            _ev(1.0, "GRAPH_CALL", {"command": "sdd explain X"}),
            _ev(2.0, "FILE_READ", {"path": "src/foo.py"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("EXPLAIN_NOT_USED" in v for v in violations)

    def test_false_success_detected_when_output_contains_failed(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest tests/", "exit_code": 0, "output_snippet": "1 FAILED"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("FALSE_SUCCESS" in v for v in violations)

    def test_false_success_detected_when_output_contains_error(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd complete T-001", "exit_code": 0, "output_snippet": "ERROR: something went wrong"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("FALSE_SUCCESS" in v for v in violations)

    def test_false_success_not_reported_when_exit_code_nonzero(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest", "exit_code": 1, "output_snippet": "1 FAILED"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("FALSE_SUCCESS" in v for v in violations)

    def test_false_success_not_reported_when_output_clean(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest", "exit_code": 0, "output_snippet": "1 passed in 0.12s"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("FALSE_SUCCESS" in v for v in violations)

    def test_false_success_not_reported_when_no_output_snippet(self) -> None:
        events = [
            _ev(1.0, "COMMAND", {"command": "ls", "exit_code": 0}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("FALSE_SUCCESS" in v for v in violations)

    def test_detect_false_success(self) -> None:
        """I-BEHAV-FALSE-SUCCESS-1: exit=0 with FAILED/ERROR in output_snippet is a violation."""
        events = [
            _ev(1.0, "COMMAND", {"command": "pytest tests/", "exit_code": 0, "output_snippet": "1 FAILED, 2 passed"}),
        ]
        violations = detect_behavioral_violations(events)
        assert any("FALSE_SUCCESS" in v for v in violations)

    def test_explain_not_used_not_applied_to_graph_call_in_last_5(self) -> None:
        """I-BEHAV-EXPLAIN-1: GRAPH_CALL among last 5 events must not trigger EXPLAIN_NOT_USED."""
        events = [
            _ev(1.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(2.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(3.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(4.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(5.0, "COMMAND", {"command": "sdd show-state"}),
            _ev(6.0, "GRAPH_CALL", {"command": "sdd explain X"}),
        ]
        violations = detect_behavioral_violations(events)
        assert not any("EXPLAIN_NOT_USED" in v for v in violations)

    def test_compute_summary_moves_explain_not_used_to_warnings(self, tmp_path) -> None:
        from sdd.tracing import writer

        events = [
            TraceEvent(ts=1.0, type="GRAPH_CALL", payload={"command": "sdd explain X"}, task_id="T-300"),
            TraceEvent(ts=2.0, type="COMMAND", payload={"command": "sdd show-state"}, task_id="T-300"),
            TraceEvent(ts=3.0, type="COMMAND", payload={"command": "sdd show-state"}, task_id="T-300"),
            TraceEvent(ts=4.0, type="COMMAND", payload={"command": "sdd show-state"}, task_id="T-300"),
            TraceEvent(ts=5.0, type="COMMAND", payload={"command": "sdd show-state"}, task_id="T-300"),
            TraceEvent(ts=6.0, type="COMMAND", payload={"command": "sdd show-state"}, task_id="T-300"),
        ]
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            for e in events:
                writer.append_event(e)

        with (
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.reports_dir", return_value=tmp_path),
            patch("sdd.tracing.summary.build_context", return_value=frozenset()),
        ):
            summary = compute_summary("T-300")

        assert not any("EXPLAIN_NOT_USED" in v for v in summary.behavioral_violations)
        assert any("EXPLAIN_NOT_USED" in w for w in summary.behavioral_warnings)
