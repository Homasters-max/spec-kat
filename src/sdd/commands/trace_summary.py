"""sdd trace-summary T-NNN — replay trace.jsonl → summary.json + violations (BC-62-L4).

Exit codes:
  0 — no hard violations (I-TRACE-COMPLETE-1 clean)
  1 — hard violations found (list in JSON stderr)
Soft violations (SCOPE_VIOLATION) always appear in stdout; do not affect exit code.
"""
from __future__ import annotations

import json
import sys


def main(args: list[str]) -> int:
    if not args:
        json.dump(
            {"error_type": "UsageError", "message": "Usage: sdd trace-summary T-NNN", "exit_code": 1},
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1

    task_id = args[0]

    from sdd.tracing.summary import compute_summary, write_summary

    summary = compute_summary(task_id)
    path = write_summary(summary)

    hard_violations = [v for v in summary.violations if v.startswith("I-TRACE-COMPLETE-1")]
    soft_violations = [v for v in summary.violations if v.startswith("SCOPE_VIOLATION")]

    print(
        f"Trace summary for {task_id}: "
        f"{summary.total_events} events "
        f"(graph={summary.graph_calls} reads={summary.file_reads} "
        f"writes={summary.file_writes} cmds={summary.commands})"
    )
    print(f"Command failures: {summary.command_failures}")
    print(f"Behavioral violations: {json.dumps(summary.behavioral_violations)}")
    if summary.behavioral_warnings:
        print(f"Behavioral warnings (informational): {json.dumps(summary.behavioral_warnings)}")

    if soft_violations:
        print("Soft violations (informational):")
        for v in soft_violations:
            print(f"  {v}")

    if hard_violations:
        print("Hard violations:")
        for v in hard_violations:
            print(f"  {v}")
        json.dump(
            {
                "error_type": "TraceViolation",
                "violated_invariant": "I-TRACE-COMPLETE-1",
                "violations": hard_violations,
                "task_id": task_id,
            },
            sys.stderr,
        )
        sys.stderr.write("\n")
        return 1

    print(f"Written to {path}")
    return 0
