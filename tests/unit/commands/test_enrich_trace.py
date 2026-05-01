"""Unit tests for sdd enrich-trace command — cross-session enrichment (Bug-1 regression)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.tracing.trace_event import TraceEvent


def _make_transcript(tmp_path: Path, tool_use_id: str, output: str) -> tuple[Path, int]:
    """Write a minimal transcript with one tool_use+tool_result pair.

    Returns (transcript_path, offset_before_tool_use) to simulate the
    offset captured at session start (tool_use not yet written).
    """
    f = tmp_path / "transcript.jsonl"
    pre = json.dumps({"type": "summary"}) + "\n"
    f.write_bytes(pre.encode())
    offset = f.stat().st_size  # offset captured before the tool call

    assistant = json.dumps({
        "type": "assistant",
        "uuid": "asst-uuid",
        "timestamp": "2026-01-01T00:00:01Z",
        "message": {
            "content": [{"type": "tool_use", "id": tool_use_id,
                         "name": "Bash", "input": {"command": "sdd complete T-0"}}]
        },
    })
    user = json.dumps({
        "type": "user",
        "uuid": "usr-uuid",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                         "content": [{"type": "text", "text": output}]}]
        },
    })
    with f.open("ab") as fh:
        fh.write((assistant + "\n").encode())
        fh.write((user + "\n").encode())

    return f, offset


def _make_trace_event(task_id: str, tool_use_id: str, ts: float = 1.0) -> TraceEvent:
    return TraceEvent(
        ts=ts,
        type="COMMAND",
        payload={
            "command": "sdd complete " + task_id,
            "category": "SDD",
            "exit_code": 0,
            "output_len": 0,
            "output_snippet": "",
            "transcript_ref": {"assistant_uuid": None, "tool_use_id": tool_use_id},
        },
        session_id="sess-001",
        task_id=task_id,
    )


class TestEnrichTraceCrossSession:
    """Bug-1: enrich-trace T-PREV must use the correct (past) transcript."""

    def test_cross_session_uses_session_meta(self, tmp_path: Path) -> None:
        """When session_meta.json exists for the task, use its transcript (not current)."""
        from sdd.commands.enrich_trace import main

        task_id = "T-0001"
        tool_use_id = "toolu_PREV"
        transcript, offset = _make_transcript(tmp_path, tool_use_id, "task done")

        # Per-task session_meta.json (simulates what record-session would have written)
        reports_dir = tmp_path / "reports" / task_id
        reports_dir.mkdir(parents=True)
        session_meta = reports_dir / "session_meta.json"
        session_meta.write_text(json.dumps({
            "session_id": "sess-prev",
            "transcript_path": str(transcript),
            "transcript_offset": offset,
        }))

        # trace.jsonl with one COMMAND event referencing the tool_use_id
        trace_file = reports_dir / "trace.jsonl"
        event = _make_trace_event(task_id, tool_use_id)
        trace_file.write_text(event.to_json() + "\n")

        # current_session.json points to a DIFFERENT (non-existent) transcript
        current_session_data = {
            "session_id": "sess-current",
            "task_id": "T-9999",
            "transcript_path": str(tmp_path / "other_transcript.jsonl"),
            "transcript_offset": 0,
        }

        with (
            patch("sdd.commands.enrich_trace._load_current_session",
                  return_value=current_session_data),
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path / "reports"),
            patch("sdd.infra.paths.get_sdd_root", return_value=tmp_path),
        ):
            result = main([task_id])

        assert result == 0
        enriched_path = reports_dir / "trace_enriched.jsonl"
        assert enriched_path.exists()
        enriched_events = [json.loads(line) for line in enriched_path.read_text().splitlines()]
        command_events = [e for e in enriched_events if e["type"] == "COMMAND"]
        assert len(command_events) == 1
        ev = command_events[0]
        assert ev["payload"]["output_len"] > 0, "COMMAND event must be enriched from correct transcript"
        assert ev["payload"]["output_snippet"] == "task done"
        assert ev["payload"]["transcript_ref"]["assistant_uuid"] == "asst-uuid"

    def test_fallback_to_current_session_when_no_meta(self, tmp_path: Path) -> None:
        """Without session_meta.json, falls back to current_session.json."""
        from sdd.commands.enrich_trace import main

        task_id = "T-0002"
        tool_use_id = "toolu_CUR"
        transcript, offset = _make_transcript(tmp_path, tool_use_id, "current output")

        reports_dir = tmp_path / "reports" / task_id
        reports_dir.mkdir(parents=True)
        trace_file = reports_dir / "trace.jsonl"
        event = _make_trace_event(task_id, tool_use_id)
        trace_file.write_text(event.to_json() + "\n")

        current_session_data = {
            "session_id": "sess-current",
            "task_id": task_id,
            "transcript_path": str(transcript),
            "transcript_offset": offset,
        }

        with (
            patch("sdd.commands.enrich_trace._load_current_session",
                  return_value=current_session_data),
            patch("sdd.tracing.writer.reports_dir", return_value=tmp_path / "reports"),
            patch("sdd.infra.paths.get_sdd_root", return_value=tmp_path),
        ):
            result = main([task_id])

        assert result == 0
        enriched_path = reports_dir / "trace_enriched.jsonl"
        lines = [json.loads(l) for l in enriched_path.read_text().splitlines()]
        cmd = next(e for e in lines if e["type"] == "COMMAND")
        assert cmd["payload"]["output_snippet"] == "current output"
