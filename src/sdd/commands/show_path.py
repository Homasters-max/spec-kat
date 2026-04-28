"""sdd path — resolve canonical SDD resource paths (§BOOTSTRAP STATE RULE).

Reads State_index.yaml directly from filesystem (FS-direct).
MUST NOT use EventLog replay or projection pipeline — breaks bootstrap cycle.
Exit: 0 + path on stdout, 1 + JSON on stderr on failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse, urlunparse

import yaml

from sdd.infra.paths import (
    config_file,
    event_store_file,
    plan_file,
    state_file,
    taskset_file,
)


def _show_event_store_path() -> str:
    """Return event store path/URL for diagnostic output.

    BC-45-F: In PG mode, shows masked URL (no password). Fallback: DuckDB path.
    """
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if pg_url:
        parsed = urlparse(pg_url)
        safe = parsed._replace(netloc=parsed.netloc.rsplit("@", 1)[-1])
        return f"[PG] {urlunparse(safe)}"
    return str(event_store_file())


def _read_phase_from_state() -> int:
    """Read current phase from State_index.yaml via direct FS read (§BOOTSTRAP STATE RULE)."""
    path = state_file()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return int(data["tasks"]["version"])
    except FileNotFoundError:
        _fail("MissingState", f"State_index.yaml not found: {path}")
    except (KeyError, TypeError, ValueError) as e:
        _fail("MissingState", f"Cannot read phase from State_index.yaml: {e}")


def _fail(error_type: str, message: str) -> None:
    json.dump({"error_type": error_type, "message": message, "exit_code": 1}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="sdd path",
        description="Resolve canonical SDD resource paths (FS-direct, §BOOTSTRAP STATE RULE)",
    )
    parser.add_argument(
        "resource",
        choices=["state", "taskset", "eventlog", "plan", "config"],
        help="Resource to resolve: state | taskset | eventlog | plan | config",
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=None,
        help="Phase number (auto-detected from State_index.yaml if omitted)",
    )
    parsed = parser.parse_args(args)

    resource = parsed.resource
    phase = parsed.phase

    if resource == "state":
        print(str(state_file().resolve()))
        return 0

    if resource == "eventlog":
        print(_show_event_store_path())
        return 0

    if resource == "config":
        print(str(config_file().resolve()))
        return 0

    if resource in ("taskset", "plan"):
        if phase is None:
            phase = _read_phase_from_state()
        if resource == "taskset":
            print(str(taskset_file(phase).resolve()))
        else:
            print(str(plan_file(phase).resolve()))
        return 0

    _fail("UsageError", f"Unknown resource: {resource!r}")
    return 1  # unreachable; satisfies type checker
