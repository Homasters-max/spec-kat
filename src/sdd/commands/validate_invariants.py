"""ValidateInvariantsHandler — Spec_v4 §4.7, Spec_v8 §2.4.

Invariants: I-CMD-1, I-CMD-6, I-CMD-13, I-ES-2, I-M-1-CHECK, I-CHAIN-1, I-ACCEPT-1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import SDDError
from sdd.core.execution_context import kernel_context
from sdd.core.events import DomainEvent, classify_event_level
from sdd.domain.metrics.aggregator import MetricsAggregator
from sdd.infra.config_loader import load_config
from sdd.infra.event_query import EventLogQuerier, QueryFilters
from sdd.infra.paths import config_file, event_store_url, taskset_file

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_DEFAULT_TIMEOUT_SECS = 300
_STDOUT_MAX_CHARS = 4096
TIMEOUT_RETURN_CODE = 124  # follows GNU timeout(1) convention (I-TIMEOUT-1)


# ---------------------------------------------------------------------------
# Command dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidateInvariantsCommand:
    """Legacy command envelope shim (I-CMD-ENV-1).

    NOT a Command subclass — standalone dataclass whose __post_init__
    auto-populates payload so handlers can use payload uniformly.
    Name preserved for backward-compatible imports.
    """

    command_id:    str
    command_type:  str
    payload:       Mapping[str, Any]
    phase_id:      int
    task_id:       str | None
    config_path:   str
    cwd:           str
    env_whitelist: tuple[str, ...]
    timeout_secs:  int
    task_outputs:    tuple[str, ...]
    validation_mode: str = "task"  # "task" | "system"

    def __post_init__(self) -> None:
        if not self.payload:
            object.__setattr__(self, "payload", {
                "phase_id":      self.phase_id,
                "task_id":       self.task_id,
                "config_path":   self.config_path,
                "cwd":           self.cwd,
                "env_whitelist": self.env_whitelist,
            })


# ---------------------------------------------------------------------------
# Internal event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TestRunCompletedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "TestRunCompleted"
    command_id:        str
    name:              str
    returncode:        int
    stdout_normalized: str
    duration_ms:       int
    phase_id:          int | None
    task_id:           str | None


@dataclass(frozen=True)
class _MetricRecordedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "MetricRecorded"
    command_id: str
    metric_id:  str
    value:      float
    task_id:    str | None
    phase_id:   int | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_output(raw: bytes) -> str:
    """Decode bytes, strip ANSI codes, truncate to _STDOUT_MAX_CHARS."""
    decoded = raw.decode("utf-8", errors="replace")
    stripped = _ANSI_ESCAPE.sub("", decoded)
    return stripped[:_STDOUT_MAX_CHARS]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class ValidateInvariantsHandler(CommandHandlerBase):
    """Run build.commands from project_profile.yaml as subprocesses.

    Emits TestRunCompletedEvent (L1) + MetricRecorded(quality.*) (L2) per command.
    Pure emitter — does NOT call EventLog; caller dispatches (I-ES-2).
    Individual subprocess failures do not abort the loop (I-CMD-6).
    Timeout raises subprocess.TimeoutExpired — propagates via error_event_boundary.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ValidateInvariantsCommand) -> list[DomainEvent]:
        if self._check_idempotent(command):  # type: ignore[arg-type]
            return []

        config = load_config(command.config_path)
        build_commands: dict[str, str] = config.get("build", {}).get("commands", {})
        if command.validation_mode == "task":
            build_commands = {k: v for k, v in build_commands.items() if not k.startswith("test")}

        timeout = command.timeout_secs if command.timeout_secs > 0 else _DEFAULT_TIMEOUT_SECS

        # Build env from whitelist + mandatory passthrough (I-CMD-13, I-SUBPROCESS-ENV-1)
        env: dict[str, str] = {
            k: os.environ[k]
            for k in (_ALWAYS_PASSTHROUGH | set(command.env_whitelist))
            if k in os.environ
        }

        events: list[DomainEvent] = []

        for name, cmd_str in build_commands.items():
            if name == "acceptance":
                # Handled separately via _run_acceptance_check (I-ACCEPT-1)
                continue
            t0 = time.monotonic()
            proc = subprocess.Popen(
                cmd_str,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=command.cwd,
                env=env,
                start_new_session=True,  # new process group → killpg on timeout
            )
            try:
                stdout_b, stderr_b = proc.communicate(timeout=timeout)
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                # Kill entire process group so grandchildren (e.g. pytest) also die
                # and release any DuckDB file locks before we continue (I-CMD-6).
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                stdout_b, stderr_b = proc.communicate()
                returncode = TIMEOUT_RETURN_CODE
            duration_ms = int((time.monotonic() - t0) * 1000)

            stdout_normalized = _normalize_output(stdout_b + stderr_b)
            now_ms = int(time.time() * 1000)

            test_event = _TestRunCompletedEvent(
                event_type="TestRunCompleted",
                event_id=str(uuid.uuid4()),
                appended_at=now_ms,
                level=classify_event_level("TestRunCompleted"),
                event_source="runtime",
                caused_by_meta_seq=None,
                command_id=command.command_id,
                name=name,
                returncode=returncode,
                stdout_normalized=stdout_normalized,
                duration_ms=duration_ms,
                phase_id=command.phase_id,
                task_id=command.task_id,
            )

            metric_event = _MetricRecordedEvent(
                event_type="MetricRecorded",
                event_id=str(uuid.uuid4()),
                appended_at=now_ms,
                level=classify_event_level("MetricRecorded"),
                event_source="runtime",
                caused_by_meta_seq=None,
                command_id=command.command_id,
                metric_id=f"quality.{name}",
                value=float(returncode),
                task_id=command.task_id,
                phase_id=command.phase_id,
            )

            events.extend([test_event, metric_event])

        return events


# ---------------------------------------------------------------------------
# I-M-1-CHECK: standalone invariant check (Spec_v6 §4.8, §5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InvariantCheckResult:
    status: str  # "PASS" | "FAIL"
    failing_task_ids: tuple[str, ...]


def check_im1_invariant(db_path: str, phase_id: int) -> InvariantCheckResult:
    """Return FAIL if any TaskCompleted event lacks a paired MetricRecorded(task.lead_time).

    Calls EventLogQuerier + MetricsAggregator directly — no CommandHandler calls (I-CHAIN-1).
    Deterministic: same db_path + phase_id → same result (I-PROJ-CONST-1).
    """
    querier = EventLogQuerier(db_path)
    tc_events = querier.query(QueryFilters(phase_id=phase_id, event_type="TaskCompleted"))
    mr_events = querier.query(QueryFilters(phase_id=phase_id, event_type="MetricRecorded"))

    summary = MetricsAggregator().aggregate(tc_events, mr_events, phase_id)

    if summary.im1_violations:
        return InvariantCheckResult(status="FAIL", failing_task_ids=summary.im1_violations)
    return InvariantCheckResult(status="PASS", failing_task_ids=())


# ---------------------------------------------------------------------------
# I-SDD-HASH: spec content hash invariant check (T-3110)
# ---------------------------------------------------------------------------

def _check_i_sdd_hash(db_path: str, phase_id: int, cwd: str) -> str:
    """Return PASS | FAIL | SKIP for I-SDD-HASH invariant.

    SKIP  — no SpecApproved event found for phase_id (spec never approved).
    PASS  — sha256(spec_path)[:16] matches spec_hash stored in SpecApproved.
    FAIL  — hashes diverge (spec file modified after approval) or file missing.
    Deterministic: same db_path + phase_id + cwd → same result (I-PROJ-CONST-1).
    """
    querier = EventLogQuerier(db_path)
    records = querier.query(QueryFilters(phase_id=phase_id, event_type="SpecApproved"))
    if not records:
        return "SKIP"

    # Most recent SpecApproved wins (records ordered ASC by seq)
    payload = json.loads(records[-1].payload)
    spec_hash_stored: str = payload.get("spec_hash", "")
    spec_path_rel: str = payload.get("spec_path", "")

    if not spec_path_rel or not spec_hash_stored:
        return "SKIP"

    full_path = os.path.join(cwd, spec_path_rel)
    try:
        with open(full_path, "rb") as fh:
            content = fh.read()
    except OSError:
        return "FAIL"

    computed = hashlib.sha256(content).hexdigest()[:16]
    return "PASS" if computed == spec_hash_stored else "FAIL"


# ---------------------------------------------------------------------------
# Acceptance check helpers (I-ACCEPT-1)
# ---------------------------------------------------------------------------

def _read_task_outputs(taskset_path: str, task_id: str) -> list[str]:
    """Parse Outputs field for task_id from a TaskSet markdown file."""
    with open(taskset_path, encoding="utf-8") as f:
        content = f.read()
    pattern = re.compile(
        rf"^{re.escape(task_id)}:.*?(?=^T-\d+[a-z]*:|\Z)",  # I-TASK-ID-1
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        return []
    outputs_match = re.search(r"^Outputs:\s*(.+)$", match.group(0), re.MULTILINE)
    if not outputs_match:
        return []
    raw = outputs_match.group(1).strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def _run_acceptance_check(
    outputs: list[str],
    cwd: str,
    env: dict[str, str],
    timeout: int,
    test_returncode: int | None = None,
) -> int:
    """Run ruff+acceptance check per I-ACCEPT-1.

    Reuses test_returncode from build loop (I-ACCEPT-REUSE-1).
    If test_returncode is None: emits ACCEPTANCE_FAILED/NO_TEST_RESULT, returns 1.
    Returns 0 on pass, 1 on fail.
    """
    # I-ACCEPT-REUSE-1: no test result from build loop → deterministic fail
    if test_returncode is None:
        print(
            json.dumps({"error": "ACCEPTANCE_FAILED", "reason": "NO_TEST_RESULT"}),
            file=sys.stderr,
        )
        return 1

    # Rule 2: missing output files → structured error + fail
    for rel_path in outputs:
        full_path = os.path.join(cwd, rel_path)
        if not os.path.exists(full_path):
            print(
                json.dumps({"error": "ACCEPTANCE_FAILED", "reason": "OUTPUT_MISSING", "path": rel_path}),
                file=sys.stderr,
            )
            return 1

    # Rule 1: empty outputs or no Python outputs → skip ruff, warn
    py_outputs = [p for p in outputs if p.endswith(".py")]
    if not outputs:
        print(
            json.dumps({"warning": "ACCEPTANCE_RUFF_SKIPPED", "reason": "empty task outputs"}),
            file=sys.stderr,
        )
    elif not py_outputs:
        print(
            json.dumps({"warning": "ACCEPTANCE_RUFF_SKIPPED", "reason": "no Python outputs to lint"}),
            file=sys.stderr,
        )
    else:
        # Rule 3: subprocess list API — no shell (I-ACCEPT-1)
        ruff = subprocess.run(
            ["ruff", "check", *py_outputs],
            capture_output=True,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )
        if ruff.returncode != 0:
            print(
                json.dumps({
                    "error": "ACCEPTANCE_FAILED",
                    "reason": "LINT_FAILURE",
                    "returncode": ruff.returncode,
                    "output": _normalize_output(ruff.stdout + ruff.stderr)[:512],
                }),
                file=sys.stderr,
            )
            return 1

    # Reuse test returncode from build loop — no subprocess (I-ACCEPT-REUSE-1)
    pytest_rc = test_returncode
    if pytest_rc != 0:
        print(
            json.dumps({
                "error": "ACCEPTANCE_FAILED",
                "reason": "TEST_FAILURE",
                "returncode": pytest_rc,
            }),
            file=sys.stderr,
        )
        return 1

    return 0


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------

_DEFAULT_ENV_WHITELIST = ("PATH", "HOME", "PYTHONPATH", "VIRTUAL_ENV")

# I-SUBPROCESS-ENV-1: always passed to subprocess without explicit --env
_ALWAYS_PASSTHROUGH: frozenset[str] = frozenset({
    "SDD_DATABASE_URL",
    "SDD_PROJECT",
    "SDD_HOME",
})


def _run_full_src_check(invariant_id: str, config: dict[str, Any], cwd: str) -> int:
    """Scan source_root for the forbidden pattern matching invariant_id.

    Returns 0 if no violations, 1 if violations found, 2 if invariant not in catalog.
    Pattern lookup: first entry in code_rules.forbidden_patterns whose message starts
    with '<invariant_id>:' or '<invariant_id> '.
    """
    source_root: str = config.get("scope", {}).get("source_root", "src/sdd/")
    patterns: list[dict[str, Any]] = config.get("code_rules", {}).get("forbidden_patterns", [])

    matched: dict[str, Any] | None = None
    for entry in patterns:
        msg: str = entry.get("message", "")
        if msg.startswith(f"{invariant_id}:") or msg.startswith(f"{invariant_id} "):
            matched = entry
            break

    if matched is None:
        print(
            json.dumps({"error": "INVARIANT_NOT_FOUND", "invariant": invariant_id}),
            file=sys.stderr,
        )
        return 2

    pattern_re = re.compile(matched["pattern"])
    excludes: set[str] = set(matched.get("exclude", []))
    src_path = os.path.join(cwd, source_root)

    violations: list[dict[str, Any]] = []
    for dirpath, _, filenames in os.walk(src_path):
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, cwd).replace("\\", "/")
            if rel_path in excludes:
                continue
            try:
                with open(full_path, encoding="utf-8") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                if pattern_re.search(line):
                    violations.append({"file": rel_path, "line": lineno, "text": line.rstrip()})

    if violations:
        print(
            json.dumps({"error": "FORBIDDEN_PATTERN", "invariant": invariant_id, "violations": violations}),
            file=sys.stderr,
        )
        return 1

    return 0


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="validate-invariants")
    parser.add_argument("--phase", type=int, required=False, default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--taskset", default=None, help="Path to TaskSet_vN.md for {outputs} expansion")
    parser.add_argument("--config", default=None)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--env", nargs="*", default=list(_DEFAULT_ENV_WHITELIST))
    parser.add_argument("--db", default=None)
    parser.add_argument("--system", action="store_true", default=False,
                        help="System mode: run all build commands including test (full suite gate)")
    parser.add_argument("--check", default=None,
                        help="Invariant ID to check against forbidden_patterns (e.g. I-LEGACY-0a)")
    parser.add_argument("--scope", default=None, choices=["full-src"],
                        help="Scan scope; full-src scans source_root for the given --check pattern")
    parsed = parser.parse_args(args)

    config_path = parsed.config or str(config_file())
    db_path = parsed.db or event_store_url()

    # --scope full-src + --check: dedicated invariant scan, no --phase required
    if parsed.scope == "full-src" and parsed.check:
        config = load_config(config_path)
        return _run_full_src_check(parsed.check, config, parsed.cwd)

    # --check I-SDD-HASH: spec content hash verification (T-3110)
    if parsed.check == "I-SDD-HASH":
        if parsed.phase is None:
            parser.error("--phase is required for --check I-SDD-HASH")
        result = _check_i_sdd_hash(db_path, parsed.phase, parsed.cwd)
        print(json.dumps({"check": "I-SDD-HASH", "phase_id": parsed.phase, "result": result}))
        return 0 if result != "FAIL" else 1

    # Default mode: --phase is required
    if parsed.phase is None:
        parser.error("--phase is required")

    task_outputs: list[str] = []
    if parsed.task:
        taskset_path = parsed.taskset or str(taskset_file(parsed.phase))
        taskset_full = os.path.join(parsed.cwd, taskset_path)
        if os.path.exists(taskset_full):
            task_outputs = _read_task_outputs(taskset_full, parsed.task)

    try:
        from sdd.infra.event_log import EventLog
        cmd = ValidateInvariantsCommand(
            command_id=str(uuid.uuid4()),
            command_type="ValidateInvariants",
            payload={},
            phase_id=parsed.phase,
            task_id=parsed.task,
            config_path=config_path,
            cwd=parsed.cwd,
            env_whitelist=tuple(parsed.env),
            timeout_secs=parsed.timeout,
            task_outputs=tuple(task_outputs),
            validation_mode="system" if parsed.system else "task",
        )
        with kernel_context("execute_command"):
            events = ValidateInvariantsHandler(db_path).handle(cmd)
            if events:
                EventLog(db_path).append(events, source=__name__)

        # Acceptance check (I-ACCEPT-1): only when --task given and acceptance field present
        if parsed.task:
            config = load_config(config_path)
            if config.get("build", {}).get("commands", {}).get("acceptance"):
                env = {k: os.environ[k] for k in (_ALWAYS_PASSTHROUGH | set(parsed.env)) if k in os.environ}
                timeout = parsed.timeout if parsed.timeout > 0 else _DEFAULT_TIMEOUT_SECS
                # Extract test result from build loop events (I-ACCEPT-REUSE-1)
                # In task mode, test is intentionally skipped — treat as 0 (not failed)
                # COUPLING: hardcoded to evt.name == "test". If the "test" build command
                # is renamed, acceptance reuse breaks (falls back to None → ACCEPTANCE_FAILED).
                # The test tier contract guarantees "test" key always exists in project_profile.yaml.
                test_returncode: int | None = 0 if cmd.validation_mode == "task" else None
                for evt in events:
                    if isinstance(evt, _TestRunCompletedEvent) and evt.name == "test":
                        test_returncode = evt.returncode
                rc = _run_acceptance_check(task_outputs, parsed.cwd, env, timeout, test_returncode)
                if rc != 0:
                    return rc

        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
