#!/usr/bin/env python3
"""
Assert mutmut kill rate thresholds.

Usage:
    python scripts/assert_kill_rate.py --min 0.95 --critical-min 1.0

Exit 0 if both thresholds are met.
Exit 1 if any threshold is violated; surviving CRITICAL mutants are listed.
Exit 2 if no mutmut results are found (run `mutmut run` first).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

# CRITICAL modules per spec Appendix A (M1-M6, I-MUT-CRITICAL-1)
# projections.py is excluded — not in CRITICAL set
CRITICAL_MODULE_SUFFIXES = {
    "src/sdd/domain/state/reducer.py",       # M2, M3
    "src/sdd/domain/guards/pipeline.py",      # M1
    "src/sdd/infra/event_store.py",           # M4
    "src/sdd/commands/registry.py",           # M5
    "src/sdd/core/events.py",                 # M6
}

KILLED_STATUSES = {"killed", "timeout", "suspicious"}


def find_cache(start: Path) -> Path | None:
    for directory in [start, *start.parents]:
        candidate = directory / ".mutmut-cache"
        if candidate.exists():
            return candidate
    return None


def load_results(cache_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            m.id        AS mutant_id,
            m.status    AS status,
            m."index"   AS mut_index,
            l.line      AS line_text,
            l.line_number AS line_number,
            sf.filename AS filename
        FROM Mutant m
        JOIN Line l ON m.line = l.id
        JOIN SourceFile sf ON l.sourcefile = sf.id
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def is_critical(filename: str) -> bool:
    normalized = filename.replace("\\", "/")
    return any(normalized.endswith(suffix) for suffix in CRITICAL_MODULE_SUFFIXES)


def compute_rates(rows: list[dict]) -> tuple[float, float, list[dict]]:
    total_tested = [r for r in rows if r["status"] != "untested"]
    total_killed = [r for r in total_tested if r["status"] in KILLED_STATUSES]

    critical_tested = [r for r in total_tested if is_critical(r["filename"])]
    critical_killed = [r for r in critical_tested if r["status"] in KILLED_STATUSES]
    critical_survived = [
        r for r in critical_tested if r["status"] not in KILLED_STATUSES
    ]

    overall_rate = len(total_killed) / len(total_tested) if total_tested else 0.0
    critical_rate = (
        len(critical_killed) / len(critical_tested) if critical_tested else 0.0
    )

    return overall_rate, critical_rate, critical_survived


def format_surviving(mutants: list[dict]) -> str:
    lines = []
    for m in mutants:
        module = Path(m["filename"]).name
        lines.append(
            f"  mutant #{m['mutant_id']:>4} [{module}:{m['line_number']}]"
            f"  status={m['status']}  line={m['line_text'].strip()!r}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min",
        type=float,
        default=0.95,
        metavar="RATE",
        dest="min_rate",
        help="Minimum overall kill rate (default: 0.95)",
    )
    parser.add_argument(
        "--critical-min",
        type=float,
        default=1.0,
        metavar="RATE",
        dest="critical_min",
        help="Minimum kill rate for CRITICAL mutations (default: 1.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    cache = find_cache(Path.cwd())
    if cache is None:
        msg = "No .mutmut-cache found. Run `mutmut run` first."
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    rows = load_results(cache)
    tested = [r for r in rows if r["status"] != "untested"]
    if not tested:
        msg = "No tested mutants found. Run `mutmut run` first."
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    overall_rate, critical_rate, surviving_critical = compute_rates(rows)

    overall_ok = overall_rate >= args.min_rate
    critical_ok = critical_rate >= args.critical_min
    passed = overall_ok and critical_ok

    result = {
        "passed": passed,
        "overall_kill_rate": round(overall_rate, 4),
        "overall_threshold": args.min_rate,
        "overall_ok": overall_ok,
        "critical_kill_rate": round(critical_rate, 4),
        "critical_threshold": args.critical_min,
        "critical_ok": critical_ok,
        "surviving_critical_count": len(surviving_critical),
        "surviving_critical": [
            {
                "mutant_id": m["mutant_id"],
                "filename": m["filename"],
                "line_number": m["line_number"],
                "status": m["status"],
                "line": m["line_text"].strip(),
            }
            for m in surviving_critical
        ],
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if passed else 1

    print(f"Overall kill rate : {overall_rate:.1%}  (threshold: {args.min_rate:.0%})  {'PASS' if overall_ok else 'FAIL'}")
    print(f"CRITICAL kill rate: {critical_rate:.1%}  (threshold: {args.critical_min:.0%})  {'PASS' if critical_ok else 'FAIL'}")

    if not passed:
        if not overall_ok:
            total_tested = [r for r in rows if r["status"] != "untested"]
            survived_all = [r for r in total_tested if r["status"] not in KILLED_STATUSES]
            print(f"\nOverall threshold violated: {len(survived_all)} surviving mutants across all modules.")

        if not critical_ok and surviving_critical:
            print(f"\nCRITICAL threshold violated: {len(surviving_critical)} surviving CRITICAL mutants:")
            print(format_surviving(surviving_critical))

        return 1

    print("\nAll kill rate thresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
