"""hooks/log_tool.py — PreToolUse / PostToolUse hook for Claude Code.

Canonical stdin-JSON implementation. Claude Code delivers hook data as JSON on stdin:
  hook_event_name == "PreToolUse"  → emits ToolUseStarted (L2)
  hook_event_name == "PostToolUse" → emits ToolUseCompleted (L2)
  on failure                       → emits HookError (L3)

Invariants: I-HOOK-1 (event_source="meta"), I-HOOK-2 (exit 0 always),
            I-HOOK-3 (ToolUseStarted/Completed at L2), I-HOOK-FAILSAFE-1 (stderr JSON on DuckDB failure)
"""
from __future__ import annotations

import json
import sys
import time


def _extract_inputs(tool_name: str, tool_input: dict) -> dict:
    """Extract compact, privacy-safe summary of tool inputs per CLAUDE.md §0.12 taxonomy."""
    if tool_name == "Bash":
        return {
            "command": tool_input.get("command", "")[:300],
            "description": tool_input.get("description", ""),
        }
    if tool_name == "Read":
        d: dict = {"file_path": tool_input.get("file_path", "")}
        if tool_input.get("offset"):
            d["offset"] = tool_input["offset"]
        if tool_input.get("limit"):
            d["limit"] = tool_input["limit"]
        return d
    if tool_name == "Edit":
        return {
            "file_path": tool_input.get("file_path", ""),
            "old_len": len(tool_input.get("old_string", "")),
            "new_len": len(tool_input.get("new_string", "")),
        }
    if tool_name == "Write":
        return {
            "file_path": tool_input.get("file_path", ""),
            "content_len": len(tool_input.get("content", "")),
        }
    if tool_name == "Glob":
        return {
            "pattern": tool_input.get("pattern", ""),
            "path": tool_input.get("path", ""),
        }
    if tool_name == "Grep":
        return {
            "pattern": tool_input.get("pattern", "")[:100],
            "glob": tool_input.get("glob", ""),
            "path": tool_input.get("path", ""),
            "output_mode": tool_input.get("output_mode", ""),
        }
    if tool_name == "Agent":
        return {
            "description": tool_input.get("description", "")[:120],
            "subagent_type": tool_input.get("subagent_type", ""),
        }
    if tool_name == "TodoWrite":
        return {"count": len(tool_input.get("todos", []))}
    # Generic fallback: record key names only, never values (privacy-safe)
    return {"keys": list(tool_input.keys())[:10]}


def _extract_output(tool_name: str, tool_response: dict) -> dict:
    """Extract compact summary of tool response for ToolUseCompleted payload."""
    output_raw = tool_response.get("output") or tool_response.get("error") or ""
    interrupted = bool(tool_response.get("interrupted", False))
    base: dict = {
        "output_len": len(str(output_raw)),
        "interrupted": interrupted,
    }
    if interrupted or tool_response.get("error"):
        base["error_snippet"] = str(output_raw)[:200]
    return base


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # I-HOOK-2: always exit 0

    tool_name: str = payload.get("tool_name", "")
    if not tool_name:
        sys.exit(0)  # I-HOOK-2

    hook_event_name: str = payload.get("hook_event_name", "")
    tool_input: dict = payload.get("tool_input") or {}
    timestamp_ms = int(time.time() * 1000)
    from sdd.infra.paths import event_store_file  # noqa: PLC0415
    db = str(event_store_file())

    event_type = ""
    event_payload: dict = {}

    try:
        from sdd.infra.event_log import sdd_append  # noqa: PLC0415

        if hook_event_name == "PreToolUse":
            event_type = "ToolUseStarted"
            event_payload = {
                "tool_name": tool_name,
                "timestamp_ms": timestamp_ms,
                **_extract_inputs(tool_name, tool_input),
            }
            sdd_append(
                event_type,
                event_payload,
                db_path=db,
                event_source="meta",  # I-HOOK-1
                level="L2",           # I-HOOK-3
            )
        elif hook_event_name == "PostToolUse":
            tool_response: dict = payload.get("tool_response") or {}
            event_type = "ToolUseCompleted"
            event_payload = {
                "tool_name": tool_name,
                "timestamp_ms": timestamp_ms,
                **_extract_inputs(tool_name, tool_input),
                **_extract_output(tool_name, tool_response),
            }
            sdd_append(
                event_type,
                event_payload,
                db_path=db,
                event_source="meta",  # I-HOOK-1
                level="L2",           # I-HOOK-3
            )
    except Exception as exc:
        # I-HOOK-4: on primary failure, attempt to write HookError event to DB
        try:
            from sdd.infra.event_log import sdd_append  # noqa: PLC0415
            sdd_append(
                "HookError",
                {"hook_error": str(exc), "original_event_type": event_type},
                db_path=db,
                event_source="meta",
                level="L3",
            )
        except Exception as exc2:
            # I-HOOK-FAILSAFE-1: double failure — both writes failed, log to stderr
            json.dump(
                {"double failure": True, "primary_error": str(exc), "secondary_error": str(exc2)},
                sys.stderr,
            )
            sys.stderr.write("\n")

    sys.exit(0)  # I-HOOK-2: always exit 0


if __name__ == "__main__":
    main()
