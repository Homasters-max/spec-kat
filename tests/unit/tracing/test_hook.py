"""Unit tests for sdd.hooks.trace_tool — PostToolUse hook."""
from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest


def _run_main(payload: dict) -> None:
    """Invoke trace_tool.main() with payload on stdin."""
    from sdd.hooks import trace_tool

    stdin_data = json.dumps(payload)
    with patch("sys.stdin", io.StringIO(stdin_data)), patch("sys.exit") as mock_exit:
        trace_tool.main()
    return mock_exit


class TestTraceToolHook:

    def test_exits_0_on_non_post_tool_use_event(self) -> None:
        mock_exit = _run_main({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}})
        mock_exit.assert_called_with(0)

    def test_exits_0_on_invalid_json(self) -> None:
        from sdd.hooks import trace_tool

        with patch("sys.stdin", io.StringIO("not-json")), pytest.raises(SystemExit) as exc_info:
            trace_tool.main()
        assert exc_info.value.code == 0

    def test_exits_0_on_untracked_tool(self) -> None:
        mock_exit = _run_main({
            "hook_event_name": "PostToolUse",
            "tool_name": "TodoWrite",
            "tool_input": {},
        })
        mock_exit.assert_called_with(0)

    def test_read_tool_emits_file_read(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "src/foo.py"},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-001", "s1")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        assert captured[0].type == "FILE_READ"
        assert captured[0].payload.get("path") == "src/foo.py"
        assert captured[0].task_id == "T-001"
        assert captured[0].session_id == "s1"

    def test_write_tool_emits_file_write(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/bar.py"},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-002", "s2")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        assert captured[0].type == "FILE_WRITE"

    def test_edit_tool_emits_file_write(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/baz.py"},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-003", "s3")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        assert captured[0].type == "FILE_WRITE"

    def test_bash_with_sdd_resolve_emits_graph_call(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        cmd = "sdd resolve 'GraphCallLog' --format json"
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-004", "s4")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        assert captured[0].type == "GRAPH_CALL"
        assert cmd[:300] in captured[0].payload.get("command", "")

    def test_bash_without_sdd_graph_command_emits_command(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-005", "s5")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        assert captured[0].type == "COMMAND"
        p = captured[0].payload
        assert p["command"] == "ls -la"
        assert p["category"] == "SYSTEM"
        assert p["exit_code"] is None
        assert "output_len" in p
        assert "output_snippet" in p
        assert captured[0].task_id == "T-005"

    def test_bash_command_captures_exit_code_and_snippet(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": {
                "output": "===== 7 passed =====\n",
                "exit_code": 0,
                "interrupted": False,
            },
        }
        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-007", "s7")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
            patch("sdd.tracing.writer.write_output_file", return_value=".sdd/reports/T-007/cmd_outputs/123.txt"),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert len(captured) == 1
        p = captured[0].payload
        assert p["category"] == "TEST"
        assert p["exit_code"] == 0
        assert "7 passed" in p["output_snippet"]
        assert p["output_len"] > 0
        assert "output_ref" in p

    def test_bash_sdd_command_gets_sdd_category(self) -> None:
        captured: list = []

        def fake_append(event) -> None:
            captured.append(event)

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sdd complete T-001 2>&1"},
            "tool_response": {"output": "OK\n", "exit_code": 0},
        }
        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("sys.exit"),
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-001", "s1")),
            patch("sdd.tracing.writer.append_event", side_effect=fake_append),
            patch("sdd.tracing.writer.write_output_file", return_value="ref"),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        assert captured[0].payload["category"] == "SDD"

    def test_hook_survives_append_failure(self) -> None:
        """I-HOOK-2: errors in append_event must not propagate."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "x.py"},
        }
        stdin_data = json.dumps(payload)
        with (
            patch("sys.stdin", io.StringIO(stdin_data)),
            patch("sys.exit") as mock_exit,
            patch("sdd.hooks.trace_tool._read_session_ids", return_value=("T-006", "s6")),
            patch("sdd.tracing.writer.append_event", side_effect=RuntimeError("disk full")),
        ):
            from sdd.hooks import trace_tool
            trace_tool.main()

        mock_exit.assert_called_with(0)
