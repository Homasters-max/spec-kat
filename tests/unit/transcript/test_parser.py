"""Unit tests for sdd.transcript.parser."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from sdd.transcript.parser import (
    parse_session,
    find_tool_result,
    project_dir_from_cwd,
    latest_transcript,
    ToolPair,
    TranscriptSession,
)


def _assistant_line(tool_use_id: str, name: str = "Bash", uuid: str = "aaa") -> str:
    return json.dumps({
        "type": "assistant",
        "uuid": uuid,
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}]
        },
    })


def _user_line(tool_use_id: str, output: str, uuid: str = "bbb") -> str:
    return json.dumps({
        "type": "user",
        "uuid": uuid,
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                         "content": [{"type": "text", "text": output}]}]
        },
    })


class TestParseSessionOffsetBuffer:
    """Bug-2 regression: first command's assistant block is before the offset."""

    def test_first_command_enriched_when_tool_use_before_offset(self, tmp_path: Path) -> None:
        """tool_use written before transcript_offset, tool_result after — must be matched."""
        transcript = tmp_path / "session.jsonl"
        # Write the assistant message (tool_use) — this will be BEFORE the offset
        line_a = _assistant_line("toolu_FIRST") + "\n"
        transcript.write_bytes(line_a.encode())
        offset = transcript.stat().st_size  # simulate snapshot taken HERE
        # Write the tool_result AFTER the offset
        line_u = _user_line("toolu_FIRST", "hello world") + "\n"
        with transcript.open("ab") as f:
            f.write(line_u.encode())

        session = parse_session(str(transcript), start_offset=offset)
        pair = find_tool_result(session, tool_use_id="toolu_FIRST")

        assert pair is not None, "first-command ToolPair must be found despite offset cutoff"
        assert pair.tool_output == "hello world"
        assert pair.assistant_uuid == "aaa"

    def test_tool_use_well_before_offset_still_matched(self, tmp_path: Path) -> None:
        """tool_use written well before offset is also captured by the 8 KiB buffer."""
        transcript = tmp_path / "session.jsonl"
        line_a = _assistant_line("toolu_OLD") + "\n"
        # Pad with filler so offset > 8192 AND tool_use is within 8 KiB of offset
        filler = json.dumps({"type": "system", "data": "x" * 100}) + "\n"
        transcript.write_bytes(line_a.encode())
        # Add ~4 KB of filler lines
        with transcript.open("ab") as f:
            for _ in range(40):
                f.write(filler.encode())
        offset = transcript.stat().st_size
        line_u = _user_line("toolu_OLD", "result") + "\n"
        with transcript.open("ab") as f:
            f.write(line_u.encode())

        session = parse_session(str(transcript), start_offset=offset)
        pair = find_tool_result(session, tool_use_id="toolu_OLD")

        assert pair is not None
        assert pair.tool_output == "result"

    def test_normal_events_after_offset_still_found(self, tmp_path: Path) -> None:
        """Events fully after the offset are unaffected by the buffer change."""
        transcript = tmp_path / "session.jsonl"
        prefix = json.dumps({"type": "summary"}) + "\n"
        transcript.write_bytes(prefix.encode())
        offset = transcript.stat().st_size
        with transcript.open("ab") as f:
            f.write((_assistant_line("toolu_AFTER") + "\n").encode())
            f.write((_user_line("toolu_AFTER", "after output") + "\n").encode())

        session = parse_session(str(transcript), start_offset=offset)
        pair = find_tool_result(session, tool_use_id="toolu_AFTER")

        assert pair is not None
        assert pair.tool_output == "after output"


class TestFindToolResult:
    def _make_pair(self, tool_use_id: str, ts: str = "2026-01-01T00:00:00Z") -> ToolPair:
        return ToolPair(
            tool_use_id=tool_use_id,
            tool_name="Bash",
            tool_input={},
            tool_output="out",
            timestamp=ts,
            assistant_uuid="a",
            user_uuid="u",
        )

    def test_exact_match(self) -> None:
        from sdd.transcript.parser import TranscriptSession
        session = TranscriptSession(
            session_id="s",
            transcript_path="p",
            tool_pairs=[self._make_pair("toolu_X"), self._make_pair("toolu_Y")],
        )
        result = find_tool_result(session, tool_use_id="toolu_Y")
        assert result is not None
        assert result.tool_use_id == "toolu_Y"

    def test_no_match_returns_none(self) -> None:
        from sdd.transcript.parser import TranscriptSession
        session = TranscriptSession(
            session_id="s",
            transcript_path="p",
            tool_pairs=[self._make_pair("toolu_A")],
        )
        assert find_tool_result(session, tool_use_id="toolu_MISSING") is None

    def test_neither_id_nor_ts_returns_none(self) -> None:
        session = TranscriptSession(session_id="s", transcript_path="p", tool_pairs=[])
        assert find_tool_result(session) is None


# ── T-6308: 5 spec-named tests (§9 тесты 1, 2, 3, 4, 12) ──────────────────

def test_parse_session_extracts_tool_pairs(tmp_path: Path) -> None:
    """I-TRANSCRIPT-2: parse_session reads from start_offset and extracts ToolPairs."""
    transcript = tmp_path / "session.jsonl"
    line_a = _assistant_line("toolu_001") + "\n"
    line_u = _user_line("toolu_001", "output text") + "\n"
    transcript.write_text(line_a + line_u, encoding="utf-8")

    session = parse_session(str(transcript), start_offset=0)

    assert len(session.tool_pairs) == 1
    pair = session.tool_pairs[0]
    assert pair.tool_use_id == "toolu_001"
    assert pair.tool_name == "Bash"
    assert pair.tool_output == "output text"


def test_find_tool_result_by_command(tmp_path: Path) -> None:
    """Linking strategy: find_tool_result falls back to nearest timestamp when tool_use_id is None."""
    ts_str = "2026-01-01T00:00:01Z"
    pair = ToolPair(
        tool_use_id="toolu_T",
        tool_name="Bash",
        tool_input={},
        tool_output="result",
        timestamp=ts_str,
        assistant_uuid="a",
        user_uuid="u",
    )
    session = TranscriptSession(session_id="s", transcript_path="p", tool_pairs=[pair])

    from datetime import datetime, timezone
    target_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    found = find_tool_result(session, ts=target_ts + 0.5)

    assert found is not None
    assert found.tool_use_id == "toolu_T"


def test_project_dir_from_cwd() -> None:
    """BC-63-P2: project_dir_from_cwd converts absolute path to Claude Code project dir key."""
    result = project_dir_from_cwd("/root/project")

    expected = Path.home() / ".claude" / "projects" / "-root-project"
    assert result == expected


def test_latest_transcript_returns_newest(tmp_path: Path) -> None:
    """BC-63-P2: latest_transcript returns the .jsonl file with the greatest mtime."""
    old_file = tmp_path / "old.jsonl"
    old_file.write_text("{}")
    time.sleep(0.01)
    new_file = tmp_path / "new.jsonl"
    new_file.write_text("{}")

    result = latest_transcript(tmp_path)

    assert result == new_file


def test_find_tool_result_by_tool_use_id() -> None:
    """I-TRACE-REF-1: find_tool_result matches exactly by tool_use_id; no fuzzy matching."""
    pairs = [
        ToolPair("toolu_A", "Bash", {}, "out_a", "2026-01-01T00:00:00Z", "x", "y"),
        ToolPair("toolu_B", "Read", {}, "out_b", "2026-01-01T00:00:01Z", "x", "y"),
    ]
    session = TranscriptSession(session_id="s", transcript_path="p", tool_pairs=pairs)

    found = find_tool_result(session, tool_use_id="toolu_B")
    assert found is not None
    assert found.tool_use_id == "toolu_B"
    assert found.tool_output == "out_b"

    not_found = find_tool_result(session, tool_use_id="toolu_B_extra")
    assert not_found is None
