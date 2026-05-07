from __future__ import annotations

from pathlib import Path

from sdd.infra.paths import reports_dir
from sdd.tracing.trace_event import TraceEvent


def trace_file(task_id: str) -> Path:
    return reports_dir() / task_id / "trace.jsonl"


def trace_enriched_file(task_id: str) -> Path:
    return reports_dir() / task_id / "trace_enriched.jsonl"


def append_event(event: TraceEvent) -> None:
    """Append a TraceEvent to the task's trace.jsonl (append-only, I-TRACE-ORDER-1)."""
    if not event.task_id:
        return
    path = trace_file(event.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(event.to_json() + "\n")


def write_output_file(task_id: str, ts: float, output: str) -> str:
    """Write full command output to cmd_outputs/<ts_ms>.txt. Returns relative path from project root."""
    ts_ms = int(ts * 1000)
    path = reports_dir() / task_id / "cmd_outputs" / f"{ts_ms}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    return str(path.relative_to(reports_dir().parent.parent))


def read_events(task_id: str) -> list[TraceEvent]:
    """Read all events for a task, sorted by ts (I-TRACE-ORDER-1).

    Prefers trace_enriched.jsonl over trace.jsonl when enriched file exists (I-TRACE-RAW-1).
    """
    import json

    enriched = trace_enriched_file(task_id)
    path = enriched if enriched.exists() else trace_file(task_id)
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(TraceEvent.from_dict(json.loads(line)))
    return sorted(events, key=lambda e: e.ts)
