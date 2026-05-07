"""Unit tests for sdd.tracing.writer — append_event and trace_file."""
from __future__ import annotations

from unittest.mock import patch

from sdd.tracing.trace_event import TraceEvent


class TestTraceWriter:

    def test_append_event_creates_file(self, tmp_path) -> None:
        """append_event writes a JSON line to the trace file."""
        from sdd.tracing import writer

        event = TraceEvent(ts=1.0, type="FILE_READ", payload={"file": "foo.py"}, task_id="T-001")
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            writer.append_event(event)

        trace = tmp_path / "T-001" / "trace.jsonl"
        assert trace.exists()
        content = trace.read_text()
        assert "FILE_READ" in content
        assert "foo.py" in content

    def test_append_event_appends_multiple(self, tmp_path) -> None:
        """Multiple append_event calls result in multiple lines."""
        from sdd.tracing import writer

        e1 = TraceEvent(ts=1.0, type="FILE_READ", task_id="T-002")
        e2 = TraceEvent(ts=2.0, type="FILE_WRITE", task_id="T-002")
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            writer.append_event(e1)
            writer.append_event(e2)

        trace = tmp_path / "T-002" / "trace.jsonl"
        lines = trace.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_trace_file_path(self, tmp_path) -> None:
        """trace_file returns path under reports_dir/<task_id>/trace.jsonl."""
        from sdd.tracing import writer

        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            path = writer.trace_file("T-003")

        assert path == tmp_path / "T-003" / "trace.jsonl"

    def test_read_events_returns_empty_when_no_file(self, tmp_path) -> None:
        """read_events returns [] when trace file does not exist."""
        from sdd.tracing import writer

        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            result = writer.read_events("T-004")

        assert result == []

    def test_read_events_reads_and_sorts_by_ts(self, tmp_path) -> None:
        """read_events returns TraceEvents sorted by ts."""
        from sdd.tracing import writer

        e1 = TraceEvent(ts=2.0, type="FILE_WRITE", task_id="T-005")
        e2 = TraceEvent(ts=1.0, type="FILE_READ", task_id="T-005")
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            writer.append_event(e1)
            writer.append_event(e2)
            result = writer.read_events("T-005")

        assert len(result) == 2
        assert result[0].ts == 1.0
        assert result[1].ts == 2.0
