"""Unit tests for sdd.commands.enrich_trace — I-TRACE-CMD-1, I-TRACE-RAW-1."""
from __future__ import annotations

import json
from unittest.mock import patch

from sdd.tracing.trace_event import TraceEvent


def _assistant_line(tool_use_id: str, uuid: str = "aaa") -> str:
    return json.dumps({
        "type": "assistant", "uuid": uuid, "timestamp": "2026-01-01T00:00:00Z",
        "message": {"content": [{"type": "tool_use", "id": tool_use_id, "name": "Bash", "input": {}}]},
    })


def _user_line(tool_use_id: str, output: str, uuid: str = "bbb") -> str:
    return json.dumps({
        "type": "user", "uuid": uuid,
        "message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                                  "content": [{"type": "text", "text": output}]}]},
    })


class TestEnrichTrace:

    def test_enrich_trace_updates_exit_code(self, tmp_path) -> None:
        """I-TRACE-CMD-1: enrich-trace populates output_snippet/output_len from transcript."""
        from sdd.commands import enrich_trace

        task_id = "T-ENRICH"
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            _assistant_line("toolu_001") + "\n" +
            _user_line("toolu_001", "Build successful") + "\n",
            encoding="utf-8",
        )
        trace_dir = tmp_path / task_id
        trace_dir.mkdir()
        event = TraceEvent(
            ts=1.0, type="COMMAND", task_id=task_id,
            payload={"command": "make build", "transcript_ref": {"tool_use_id": "toolu_001"}},
        )
        (trace_dir / "trace.jsonl").write_text(event.to_json() + "\n", encoding="utf-8")

        session_data = {"transcript_path": str(transcript), "transcript_offset": 0}
        with (
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path),
            patch.object(enrich_trace, "_load_session_for_task", return_value=session_data),
        ):
            result = enrich_trace.main([task_id])

        assert result == 0
        enriched = json.loads((trace_dir / "trace_enriched.jsonl").read_text(encoding="utf-8"))
        assert enriched["payload"]["output_snippet"] == "Build successful"
        assert enriched["payload"]["output_len"] > 0

    def test_enrich_trace_writes_enriched_not_raw(self, tmp_path) -> None:
        """enrich-trace writes trace_enriched.jsonl, leaves trace.jsonl untouched — I-TRACE-RAW-1."""
        from sdd.commands import enrich_trace
        from sdd.tracing import writer

        task_id = "T-TEST2"
        event = TraceEvent(ts=1.0, type="COMMAND", payload={"cmd": "echo hi"}, task_id=task_id)
        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            writer.append_event(event)

        raw_path = tmp_path / task_id / "trace.jsonl"
        raw_content_before = raw_path.read_bytes()

        with patch("sdd.tracing.writer.reports_dir", return_value=tmp_path):
            with patch.object(enrich_trace, "_load_session_for_task", return_value={}):
                result = enrich_trace.main([task_id])

        assert result == 0
        assert raw_path.read_bytes() == raw_content_before, "trace.jsonl must not be modified (I-TRACE-RAW-1)"
        enriched_path = tmp_path / task_id / "trace_enriched.jsonl"
        assert enriched_path.exists(), "trace_enriched.jsonl must be written"
