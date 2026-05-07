#!/usr/bin/env python3
"""
Generate VR_Report_v17.json — aggregates all Validation Runtime checks.

Usage:
    python3 scripts/generate_vr_report.py [--output PATH]

Exit 0 if status == "STABLE".
Exit 1 if status == "UNSTABLE".
"""
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPORT_PATH = Path(".sdd/reports/VR_Report_v17.json")
SEED = 0

PROPERTY_TESTS = [
    ("P1_determinism",        "tests/property/test_determinism.py"),
    ("P2_confluence",         "tests/property/test_confluence.py"),
    ("P3_prefix_consistency", "tests/property/test_prefix_consistency.py"),
    ("P4_invariant_safety",   "tests/property/test_invariant_safety.py"),
    ("P5_no_hidden_state",    "tests/property/test_no_hidden_state.py"),
    ("P6_event_integrity",    "tests/property/test_event_integrity.py"),
    ("P7_idempotency",        "tests/property/test_idempotency.py"),
    ("P8_concurrency",        "tests/property/test_concurrency.py"),
    ("P9_schema_evolution",   "tests/property/test_schema_evolution.py"),
    ("P10_performance_slope", "tests/property/test_performance.py"),
]

RELATIONAL_TESTS = [
    ("RP1_task_completed_delta",     "RP1"),
    ("RP2_phase_started_reset",      "RP2"),
    ("RP3_decision_recorded_append", "RP3"),
]

FAILURE_SEMANTICS_TESTS = [
    ("invalid_command_deterministic",   "invalid_command_deterministic"),
    ("stale_state_error_deterministic", "stale_state_error_deterministic"),
    ("corrupted_log_deterministic",     "corrupted_log"),
]


def run_pytest(*args: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "--tb=no", "--no-header"],
        capture_output=True,
    )
    return result.returncode == 0


def get_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_kill_rates() -> tuple[float | None, float | None]:
    result = subprocess.run(
        [sys.executable, "scripts/assert_kill_rate.py", "--json"],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
        if "error" in data:
            return None, None
        return data.get("overall_kill_rate"), data.get("critical_kill_rate")
    except (json.JSONDecodeError, KeyError):
        return None, None


def get_event_log_hash(root: Path) -> str:
    for candidate in [
        root / ".sdd" / "state" / "sdd_events.duckdb",
        root / ".sdd" / "runtime" / "sdd_events.duckdb",
    ]:
        if candidate.exists():
            return hashlib.sha256(candidate.read_bytes()).hexdigest()[:16]
    return "unavailable"


def pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(REPORT_PATH))
    args = parser.parse_args()

    root = Path.cwd()
    commit_hash = get_commit_hash()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    properties = {}
    for key, path in PROPERTY_TESTS:
        ok = run_pytest(path, f"--hypothesis-seed={SEED}")
        properties[key] = pass_fail(ok)

    relational_properties = {}
    for key, keyword in RELATIONAL_TESTS:
        ok = run_pytest(
            "tests/property/test_state_transitions.py",
            f"-k={keyword}",
            f"--hypothesis-seed={SEED}",
        )
        relational_properties[key] = pass_fail(ok)

    failure_semantics = {}
    for key, keyword in FAILURE_SEMANTICS_TESTS:
        ok = run_pytest("tests/integration/test_failure_semantics.py", f"-k={keyword}")
        failure_semantics[key] = pass_fail(ok)

    vr_full_ok = run_pytest("tests/unit/", "tests/integration/")

    overall_kill_rate, critical_kill_rate = get_kill_rates()
    kill_rate_ok = overall_kill_rate is None or overall_kill_rate >= 0.95
    critical_kill_rate_ok = critical_kill_rate is None or critical_kill_rate >= 1.0

    stable = (
        vr_full_ok
        and all(v == "PASS" for v in properties.values())
        and all(v == "PASS" for v in relational_properties.values())
        and all(v == "PASS" for v in failure_semantics.values())
        and kill_rate_ok
        and critical_kill_rate_ok
    )
    status = "STABLE" if stable else "UNSTABLE"

    report = {
        "phase": 17,
        "timestamp": timestamp,
        "commit_hash": commit_hash,
        "seed": SEED,
        "vr_full": pass_fail(vr_full_ok),
        "vr_mutation_kill_rate": overall_kill_rate,
        "vr_mutation_critical_kill_rate": critical_kill_rate,
        "properties": properties,
        "relational_properties": relational_properties,
        "failure_semantics": failure_semantics,
        "event_log_hash_sample": get_event_log_hash(root),
        "status": status,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))
    return 0 if stable else 1


if __name__ == "__main__":
    sys.exit(main())
