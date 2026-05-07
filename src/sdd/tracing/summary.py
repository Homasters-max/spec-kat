"""TraceSummary — replay trace.jsonl → violations (BC-62-L4).

Invariants: I-TRACE-COMPLETE-1 (hard), I-TRACE-SCOPE-1 (soft), I-TRACE-ORDER-1.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sdd.infra.paths import reports_dir
from sdd.tracing.trace_event import TraceEvent
from sdd.tracing.writer import read_events

_CHECK_SCOPE_RE = re.compile(r'\bsdd\s+check-scope\s+(?:read|write)\s+(\S+)')
_INPUTS_BATCH_RE = re.compile(r'\bINPUTS="([^"]+)"')

_THRASHING_SKIP_PREFIXES: frozenset[str] = frozenset({
    "pytest", "python -m pytest", "python3 -m", "grep", "find", "git",
    "ls", "cat", "sdd", "INPUTS=",
})


def _is_reasoning_command(cmd: str) -> bool:
    stripped = cmd.strip()
    return not any(stripped.startswith(p) for p in _THRASHING_SKIP_PREFIXES)


@dataclass
class TraceSummary:
    task_id: str
    session_id: str
    total_events: int
    graph_calls: int
    file_reads: int
    file_writes: int
    commands: int
    violations: list[str] = field(default_factory=list)
    command_failures: int = 0
    behavioral_violations: list[str] = field(default_factory=list)
    behavioral_warnings: list[str] = field(default_factory=list)


def _load_task_inputs(task_id: str) -> frozenset[str]:
    """Return task inputs+outputs from current TaskSet; empty frozenset on any failure."""
    try:
        from sdd.domain.tasks.parser import parse_taskset
        from sdd.infra.paths import event_store_url, taskset_file
        from sdd.infra.projections import get_current_state

        state = get_current_state(event_store_url())
        tasks = parse_taskset(str(taskset_file(state.phase_current)))
        for task in tasks:
            if task.task_id == task_id:
                return frozenset(task.inputs) | frozenset(task.outputs)
    except Exception:
        pass
    return frozenset()


def _extract_check_scope_grants(cmd: str) -> set[str]:
    """Extract granted paths from sdd check-scope commands, including shell batch patterns."""
    grants: set[str] = set()
    m = _CHECK_SCOPE_RE.search(cmd)
    if m:
        grants.add(m.group(1))
    if "check-scope" in cmd:
        bm = _INPUTS_BATCH_RE.search(cmd)
        if bm:
            grants.update(p.strip() for p in bm.group(1).split(",") if p.strip())
    return grants


def build_context(task_id: str, events: list[TraceEvent] | None = None) -> frozenset[str]:
    """Compute allowed_files = task_inputs ∪ task_outputs ∪ runtime check-scope grants.

    Parses COMMAND events for `sdd check-scope (read|write) <path>` and shell batch
    INPUTS="..." patterns to capture dynamic scope expansions at runtime.
    """
    base = _load_task_inputs(task_id)
    if not events:
        return base
    granted: set[str] = set()
    for e in events:
        if e.type == "COMMAND":
            granted |= _extract_check_scope_grants(e.payload.get("command", ""))
    return base | frozenset(granted)


def detect_violations(events: list[TraceEvent], allowed_files: frozenset[str]) -> list[str]:
    """Apply I-TRACE-COMPLETE-1 (hard) and I-TRACE-SCOPE-1 (soft) to ordered events."""
    violations: list[str] = []
    graph_call_seen: dict[str, bool] = {}

    for event in events:
        sid = event.session_id

        if event.type == "GRAPH_CALL":
            graph_call_seen[sid] = True

        elif event.type == "FILE_WRITE":
            path = event.payload.get("path", "<unknown>")
            if not graph_call_seen.get(sid, False):
                violations.append(
                    f"I-TRACE-COMPLETE-1: FILE_WRITE on {path!r} without prior GRAPH_CALL"
                    f" in session {sid!r}"
                )
            if allowed_files and path and path not in allowed_files:
                violations.append(
                    f"SCOPE_VIOLATION(I-TRACE-SCOPE-1): FILE_WRITE on {path!r} not in allowed_files"
                )

        elif event.type == "FILE_READ":
            path = event.payload.get("path", "")
            if allowed_files and path and path not in allowed_files:
                violations.append(
                    f"SCOPE_VIOLATION(I-TRACE-SCOPE-1): FILE_READ on {path!r} not in allowed_files"
                )

    return violations


def detect_behavioral_violations(events: list[TraceEvent]) -> list[str]:
    """Detect behavioral anomaly patterns in ordered event sequence (I-BEHAV-WINDOW-1: N=5)."""
    from collections import Counter  # noqa: PLC0415

    violations: list[str] = []

    # Rule 1: COMMAND_FAILURE_IGNORED — exit_code != 0, no recovery in next 3 events
    for i, event in enumerate(events):
        if event.type == "COMMAND":
            exit_code = event.payload.get("exit_code")
            if exit_code is not None and exit_code != 0:
                cmd = event.payload.get("command", "<unknown>")
                tail = events[i + 1 : i + 4]
                has_recovery = any(
                    e.type in ("GRAPH_CALL", "FILE_WRITE")
                    or (e.type == "COMMAND" and e.payload.get("command") == cmd)
                    for e in tail
                )
                if not has_recovery:
                    violations.append(
                        f"COMMAND_FAILURE_IGNORED: exit={exit_code} cmd={cmd[:80]!r}"
                    )

    # Rule 2: BLIND_WRITE — FILE_WRITE without causal GRAPH_CALL in session history
    # Checks full history (not just window) for a GRAPH_CALL referencing the same filename.
    for i, event in enumerate(events):
        if event.type == "FILE_WRITE":
            path = event.payload.get("path", "<unknown>")
            filename = Path(path).name if path and path != "<unknown>" else ""
            prior = events[:i]
            has_graph = any(
                e.type == "GRAPH_CALL" and (
                    (filename and filename in e.payload.get("command", ""))
                    or (not filename)
                )
                for e in prior
            )
            if not has_graph:
                violations.append(
                    f"BLIND_WRITE: {path!r} without GRAPH_CALL in session history"
                )

    # Rule 3: THRASHING — >3 reasoning COMMAND in a row without GRAPH_CALL
    # Skips tool/system commands (pytest, grep, git, sdd, etc.) that don't need GRAPH_CALL.
    consecutive_cmds = 0
    thrashing_reported = False
    for event in events:
        if event.type == "COMMAND" and _is_reasoning_command(event.payload.get("command", "")):
            consecutive_cmds += 1
            if consecutive_cmds > 3 and not thrashing_reported:
                violations.append("THRASHING: >3 COMMAND without GRAPH_CALL")
                thrashing_reported = True
        elif event.type == "GRAPH_CALL":
            consecutive_cmds = 0
            thrashing_reported = False

    # Rule 4: LOOP_DETECTED — same command repeated >2 times
    cmd_counts = Counter(
        e.payload.get("command", "") for e in events if e.type == "COMMAND"
    )
    for cmd, count in cmd_counts.items():
        if count > 2:
            violations.append(f"LOOP_DETECTED: {cmd[:60]!r} ×{count}")

    # Rule 5: EXPLAIN_NOT_USED — GRAPH_CALL without FILE_READ/FILE_WRITE in next 5 events
    # I-BEHAV-EXPLAIN-1: skip GRAPH_CALL in last 5 events (session may not be complete)
    for i, event in enumerate(events):
        if event.type == "GRAPH_CALL":
            if i >= len(events) - 5:
                continue
            tail = events[i + 1 : i + 6]
            if not any(e.type in ("FILE_READ", "FILE_WRITE") for e in tail):
                violations.append("EXPLAIN_NOT_USED: GRAPH_CALL without subsequent read/write")

    # Rule 6: FALSE_SUCCESS — exit_code==0 but output_snippet contains "FAILED" or "ERROR"
    for event in events:
        if event.type == "COMMAND":
            exit_code = event.payload.get("exit_code")
            if exit_code == 0:
                snippet = event.payload.get("output_snippet", "")
                if snippet and ("FAILED" in snippet or "ERROR" in snippet):
                    cmd = event.payload.get("command", "<unknown>")
                    violations.append(
                        f"FALSE_SUCCESS: exit=0 but output contains failure keyword, cmd={cmd[:80]!r}"
                    )

    return violations


def compute_summary(task_id: str) -> TraceSummary:
    """Parse trace.jsonl → build context → detect violations → return TraceSummary."""
    events = read_events(task_id)
    session_id = events[0].session_id if events else ""
    allowed_files = build_context(task_id, events)
    violations = detect_violations(events, allowed_files)

    behavioral_all = detect_behavioral_violations(events)
    behavioral = [v for v in behavioral_all if not v.startswith("EXPLAIN_NOT_USED")]
    behavioral_warnings = [v for v in behavioral_all if v.startswith("EXPLAIN_NOT_USED")]

    return TraceSummary(
        task_id=task_id,
        session_id=session_id,
        total_events=len(events),
        graph_calls=sum(1 for e in events if e.type == "GRAPH_CALL"),
        file_reads=sum(1 for e in events if e.type == "FILE_READ"),
        file_writes=sum(1 for e in events if e.type == "FILE_WRITE"),
        commands=sum(1 for e in events if e.type == "COMMAND"),
        violations=violations,
        command_failures=sum(
            1 for e in events
            if e.type == "COMMAND" and e.payload.get("exit_code") not in (None, 0)
        ),
        behavioral_violations=behavioral,
        behavioral_warnings=behavioral_warnings,
    )


def write_summary(summary: TraceSummary) -> Path:
    """Write summary.json to .sdd/reports/T-NNN/summary.json. Returns path written."""
    path = reports_dir() / summary.task_id / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(summary), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
