"""hooks/trace_tool.py — PostToolUse hook for execution tracing.

Canonical stdin-JSON implementation (same pattern as log_tool.py).
Emits TraceEvent to trace.jsonl:
  - tool_name == "Read"         → FILE_READ
  - tool_name in ("Edit","Write") → FILE_WRITE  (I-TRACE-COMPLETE-1)
  - tool_name == "Bash" and command contains sdd graph command → GRAPH_CALL

Reads task_id/session_id from current_session.json (set by record-session --task).
Invariant: I-HOOK-2 (always exit 0)
"""
from __future__ import annotations

import json
import sys
import time


_CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("pytest", "coverage"), "TEST"),
    (("sdd ",), "SDD"),
    (("git ",), "GIT"),
    (("grep", "find", "cat", "ls"), "SYSTEM"),
]


def _categorize_command(cmd: str) -> str:
    for keywords, cat in _CATEGORY_RULES:
        if any(kw in cmd for kw in keywords):
            return cat
    return "SYSTEM"


def _read_session_ids() -> tuple[str, str]:
    try:
        from sdd.infra.paths import get_sdd_root  # noqa: PLC0415

        data = json.loads((get_sdd_root() / "runtime" / "current_session.json").read_text())
        return data.get("task_id", ""), data.get("session_id", "")
    except Exception:
        return "", ""


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # I-HOOK-2

    hook_event_name: str = payload.get("hook_event_name", "")
    if hook_event_name != "PostToolUse":
        sys.exit(0)

    tool_name: str = payload.get("tool_name", "")
    tool_input: dict = payload.get("tool_input") or {}
    tool_use_id: str | None = payload.get("tool_use_id") or None
    assistant_uuid: str | None = payload.get("message_id") or payload.get("uuid") or None

    event_type: str | None = None
    event_payload: dict = {}
    output_raw: str = ""

    if tool_name == "Read":
        event_type = "FILE_READ"
        event_payload = {"path": tool_input.get("file_path", ""), "tool": tool_name}
    elif tool_name in ("Edit", "Write"):
        event_type = "FILE_WRITE"
        event_payload = {"path": tool_input.get("file_path", ""), "tool": tool_name}
    elif tool_name == "Bash":
        command: str = tool_input.get("command", "")
        if any(kw in command for kw in ("sdd resolve", "sdd explain", "sdd trace")):
            event_type = "GRAPH_CALL"
            event_payload = {"command": command[:300]}
        else:
            tool_response: dict = payload.get("tool_response") or {}
            output_raw = str(tool_response.get("output") or "")
            exit_code = tool_response.get("exit_code")
            event_type = "COMMAND"
            transcript_ref: dict | None = (
                {"assistant_uuid": assistant_uuid, "tool_use_id": tool_use_id}
                if tool_use_id
                else None
            )
            event_payload = {
                "command": command[:300],
                "category": _categorize_command(command),
                "exit_code": exit_code,
                "output_len": len(output_raw),
                "output_snippet": output_raw[:500] if output_raw else "",
                "transcript_ref": transcript_ref,
            }

    if event_type is None:
        sys.exit(0)

    task_id, session_id = _read_session_ids()

    if event_type == "COMMAND" and task_id and output_raw:
        try:
            from sdd.tracing.writer import write_output_file  # noqa: PLC0415

            ref = write_output_file(task_id, time.time(), output_raw)
            event_payload["output_ref"] = ref
        except Exception:
            pass  # I-HOOK-2

    try:
        from sdd.tracing.trace_event import TraceEvent  # noqa: PLC0415
        from sdd.tracing.writer import append_event  # noqa: PLC0415

        append_event(
            TraceEvent(
                ts=time.time(),
                type=event_type,
                payload=event_payload,
                task_id=task_id,
                session_id=session_id,
            )
        )
        label = event_payload.get("path") or event_payload.get("command", "")[:60]
        print(f"[TRACE] {event_type} → {task_id or '?'} | {label}", flush=True)
    except Exception:
        pass  # I-HOOK-2: never propagate failures

    sys.exit(0)  # I-HOOK-2


if __name__ == "__main__":
    main()
