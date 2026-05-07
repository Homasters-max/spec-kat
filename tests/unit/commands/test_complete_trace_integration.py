"""Tests for _run_trace_summary (BC-62-L5, I-TRACE-COMPLETE-1).

Phase 62: sdd complete вызывает trace-summary как информационный шаг;
violations выводятся в stdout; complete не блокируется при ошибках.
"""
from __future__ import annotations

from unittest.mock import patch

from sdd.commands.complete import _run_trace_summary


class TestRunTraceSummary:
    def test_calls_trace_summary_main(self):
        """_run_trace_summary delegates to trace_summary.main with task_id (BC-62-L5)."""
        with patch("sdd.commands.trace_summary.main") as mock_main:
            mock_main.return_value = 0
            _run_trace_summary("T-6205")
        mock_main.assert_called_once_with(["T-6205"])

    def test_never_raises_on_hard_violations(self):
        """trace-summary exit 1 (hard violations) MUST NOT block complete (Phase 62 informative only)."""
        with patch("sdd.commands.trace_summary.main", return_value=1):
            _run_trace_summary("T-6205")  # must not raise

    def test_never_raises_on_exception(self):
        """Any exception from trace-summary is swallowed — complete is never blocked."""
        with patch("sdd.commands.trace_summary.main", side_effect=RuntimeError("boom")):
            _run_trace_summary("T-6205")  # must not raise

    def test_never_raises_on_import_error(self):
        """ImportError from trace_summary module is swallowed (defensive)."""
        with patch.dict("sys.modules", {"sdd.commands.trace_summary": None}):
            _run_trace_summary("T-6205")  # must not raise
