"""show_spec — sdd show-spec --phase N.

Reads the spec for phase N from specs_dir(), using Phases_index.md as the
authoritative source for the spec filename (I-SPEC-RESOLVE-2). Filesystem
enumeration alone is insufficient — sorted()[0] is forbidden (I-SPEC-RESOLVE-1).

Invariants: I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-SPEC-RESOLVE-1,
            I-SPEC-RESOLVE-2, I-SCOPE-CLI-1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sdd.infra.paths import phases_index_file, specs_dir, state_file

_PHASES_ROW = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*(\S+\.md)\s*\|")


def _json_error(error_type: str, message: str, exit_code: int) -> None:
    json.dump({"error_type": error_type, "message": message, "exit_code": exit_code},
              sys.stderr)
    sys.stderr.write("\n")


def _detect_phase() -> int:
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(Path(state_file()).read_text(encoding="utf-8"))
        return int(data["tasks"]["version"])
    except Exception as exc:
        raise RuntimeError(f"Cannot detect phase from State_index.yaml: {exc}") from exc


def _resolve_spec_from_phases_index(phase: int) -> str | None:
    """Return the spec path recorded in Phases_index.md for phase N, or None."""
    pi_path = phases_index_file()
    try:
        content = pi_path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines():
        m = _PHASES_ROW.match(line)
        if m and int(m.group(1)) == phase:
            return m.group(2)
    return None


def show_spec(phase: int) -> int:
    """Output spec content for phase N to stdout. Returns exit code."""
    sd = specs_dir()

    # Enumerate Spec_vN_*.md files in specs_dir (I-SPEC-RESOLVE-1 guard)
    try:
        candidates = list(sd.glob(f"Spec_v{phase}_*.md"))
    except OSError as exc:
        _json_error("SpecNotFound", f"Cannot list specs dir: {exc}", 1)
        return 1

    if len(candidates) == 0:
        _json_error(
            "SpecNotFound",
            f"No Spec_v{phase}_*.md found in {sd}",
            1,
        )
        return 1

    if len(candidates) > 1:
        names = ", ".join(sorted(p.name for p in candidates))
        _json_error(
            "AmbiguousSpec",
            f"Multiple Spec_v{phase}_*.md found in {sd}: {names}",
            1,
        )
        return 1

    # Exactly one candidate — resolve authoritative path via Phases_index.md (I-SPEC-RESOLVE-2)
    # Phases_index.md stores paths like ".sdd/specs/Spec_vN_..." relative to the project root.
    authoritative_rel = _resolve_spec_from_phases_index(phase)
    if authoritative_rel is not None:
        # sd.parent = get_sdd_root(); sd.parent.parent = project root
        spec_path = sd.parent.parent / authoritative_rel
    else:
        # Phases_index.md missing or phase not listed — fall back to the single candidate
        spec_path = candidates[0]

    try:
        content = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        _json_error("SpecNotFound", f"Cannot read spec file {spec_path}: {exc}", 1)
        return 1

    sys.stdout.write(content)
    return 0


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="sdd show-spec",
                                     description="Show spec content for a phase")
    parser.add_argument("--phase", type=int, default=None,
                        help="Phase number (auto-detected from State_index.yaml if omitted)")
    try:
        parsed = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1

    try:
        phase = parsed.phase if parsed.phase is not None else _detect_phase()
    except Exception as exc:
        _json_error("MissingState", str(exc), 1)
        return 1

    try:
        return show_spec(phase)
    except Exception as exc:
        _json_error("InternalError", str(exc), 2)
        return 2
