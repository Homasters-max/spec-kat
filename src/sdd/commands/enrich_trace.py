"""sdd enrich-trace T-NNN — обогащает COMMAND events из транскрипта (BC-63-P3).

Читает current_session.json → transcript_path/offset → парсит TranscriptSession.
Для каждого COMMAND event в trace.jsonl: находит ToolPair, пишет cmd_outputs/*.txt,
добавляет output_snippet/output_len/output_ref в обогащённую копию события.
Пишет trace_enriched.jsonl. НЕ изменяет trace.jsonl.

Invariants: I-TRACE-RAW-1 (trace.jsonl immutable), I-TRACE-CMD-1 (выход 0 всегда).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _current_session_path() -> Path:
    from sdd.infra.paths import get_sdd_root
    return get_sdd_root() / "runtime" / "current_session.json"


def _load_current_session() -> dict:
    path = _current_session_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_session_for_task(task_id: str) -> dict:
    """Return session anchor for task_id.

    Prefers per-task session_meta.json (written by record-session) so that
    enriching a past task uses the correct transcript, not the current one.
    Falls back to current_session.json when session_meta.json is absent.
    """
    from sdd.infra.paths import get_sdd_root
    meta = get_sdd_root() / "reports" / task_id / "session_meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _load_current_session()


_SNIPPET_LEN = 300


def main(args: list[str]) -> int:
    if not args:
        print("Usage: sdd enrich-trace T-NNN", file=sys.stderr)
        return 0

    task_id = args[0]

    from sdd.tracing.writer import trace_file, write_output_file, read_events

    raw_path = trace_file(task_id)
    if not raw_path.exists():
        print(f"Enriched 0/0 COMMAND events from transcript")
        return 0

    session_data = _load_session_for_task(task_id)
    transcript_path = session_data.get("transcript_path")
    transcript_offset = session_data.get("transcript_offset") or 0

    transcript_session = None
    if transcript_path and Path(transcript_path).exists():
        try:
            from sdd.transcript.parser import parse_session
            transcript_session = parse_session(transcript_path, start_offset=transcript_offset)
        except Exception:
            pass

    events = read_events(task_id)
    command_events = [e for e in events if e.type == "COMMAND"]
    total = len(command_events)

    link_violations: list[str] = []

    if transcript_session is None:
        enriched_count = 0
        enriched_events = events
    else:
        from sdd.transcript.parser import find_tool_result

        enriched_count = 0
        enriched_events = []
        for event in events:
            if event.type != "COMMAND":
                enriched_events.append(event)
                continue

            payload = dict(event.payload)
            existing_ref = payload.get("transcript_ref")
            tool_use_id = existing_ref.get("tool_use_id") if isinstance(existing_ref, dict) else None

            pair = find_tool_result(
                transcript_session,
                tool_use_id=tool_use_id,
                ts=event.ts if tool_use_id is None else None,
            )

            if pair is not None:
                output = pair.tool_output
                output_ref = write_output_file(task_id, event.ts, output)
                payload["output_len"] = len(output)
                payload["output_snippet"] = output[:_SNIPPET_LEN]
                payload["output_ref"] = output_ref
                # Update transcript_ref with assistant_uuid (I-TRACE-LINK-1)
                updated_ref = dict(existing_ref) if isinstance(existing_ref, dict) else {}
                if pair.assistant_uuid:
                    updated_ref["assistant_uuid"] = pair.assistant_uuid
                if not updated_ref.get("tool_use_id") and pair.tool_use_id:
                    updated_ref["tool_use_id"] = pair.tool_use_id
                payload["transcript_ref"] = updated_ref
                enriched_count += 1
            elif tool_use_id:
                # tool_use_id set but no matching pair found (I-TRACE-REF-1)
                link_violations.append(f"TRANSCRIPT_LINK_MISSING: tool_use_id={tool_use_id}")

            from sdd.tracing.trace_event import TraceEvent
            enriched_events.append(
                TraceEvent(
                    ts=event.ts,
                    type=event.type,
                    payload=payload,
                    session_id=event.session_id,
                    task_id=event.task_id,
                )
            )

    enriched_path = raw_path.parent / "trace_enriched.jsonl"
    with enriched_path.open("w", encoding="utf-8") as f:
        for event in enriched_events:
            f.write(event.to_json() + "\n")

    if link_violations:
        summary_path = raw_path.parent / "summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary = {}
        else:
            summary = {}
        existing_violations = summary.get("violations") or []
        # Avoid duplicate entries on repeated runs
        for v in link_violations:
            if v not in existing_violations:
                existing_violations.append(v)
        summary["violations"] = existing_violations
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Enriched {enriched_count}/{total} COMMAND events from transcript")
    return 0
