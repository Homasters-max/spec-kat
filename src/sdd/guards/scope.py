"""sdd.guards.scope — ScopeGuard CLI (migrated to src/ in Phase 8).

Invariants: NORM-SCOPE-001..004, NORM-SCOPE-003 (glob), I-PATH-1, I-RRL-1..3.
Exit: 0 = allowed, 1 = denied. JSON to stdout.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sdd.guards.scope_policy import ScopeDecision, resolve_scope

# Fallback list; authoritative source is norm_catalog.yaml norm_resolution_policy.overrides.
# Phase N+1: read from catalog at runtime.
_DEFAULT_OVERRIDABLE: frozenset[str] = frozenset({"NORM-SCOPE-001", "NORM-SCOPE-002"})


def _has_glob(path: str) -> bool:
    return "*" in path or "?" in path or "[" in path


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Path.is_relative_to() is Python 3.9+; str().startswith() fallback."""
    if sys.version_info >= (3, 9):
        return path.is_relative_to(parent)
    parent_str = str(parent)
    path_str = str(path)
    return path_str == parent_str or path_str.startswith(parent_str + os.sep)


def _contains_sdd_specs(resolved: Path) -> bool:
    """Return True if path is under .sdd/specs/ — by resolve or by path components."""
    try:
        specs_dir = (Path.cwd() / ".sdd" / "specs").resolve()
        if _is_relative_to(resolved, specs_dir):
            return True
    except (OSError, ValueError):
        pass
    parts = resolved.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".sdd" and parts[i + 1] == "specs":
            return True
    return False


def check_scope(
    operation: str,
    file_path: str,
    task_inputs: list[str] | None = None,
    allowed_overrides: frozenset[str] | None = None,
) -> dict:
    if allowed_overrides is None:
        allowed_overrides = _DEFAULT_OVERRIDABLE

    inputs = task_inputs or []

    if _has_glob(file_path):
        return ScopeDecision(
            allowed=False,
            norm_id="NORM-SCOPE-003",
            reason=f"Glob patterns forbidden: '{file_path}'. Use exact file paths only.",
            operation=operation,
            file_path=file_path,
        ).to_dict()

    resolved = Path(file_path).resolve()

    if operation == "read":
        tests_dir = (Path.cwd() / "tests").resolve()
        if _is_relative_to(resolved, tests_dir):
            deny = ScopeDecision(
                allowed=False,
                norm_id="NORM-SCOPE-001",
                reason=f"Reading from tests/ is forbidden (NORM-SCOPE-001). Path: '{file_path}'",
                operation=operation,
                file_path=file_path,
            )
            return resolve_scope(deny, inputs, allowed_overrides).to_dict()

        src_dir = (Path.cwd() / "src").resolve()
        if _is_relative_to(resolved, src_dir):
            deny = ScopeDecision(
                allowed=False,
                norm_id="NORM-SCOPE-002",
                reason=(
                    f"Reading from src/ is forbidden unless listed in Task Inputs "
                    f"(NORM-SCOPE-002). Path: '{file_path}'. "
                    f"Declared inputs: {inputs}"
                ),
                operation=operation,
                file_path=file_path,
            )
            return resolve_scope(deny, inputs, allowed_overrides).to_dict()

        if _contains_sdd_specs(resolved):
            # NORM-SCOPE-004 is non-overridable — NOT passed through resolve_scope
            return ScopeDecision(
                allowed=False,
                norm_id="NORM-SCOPE-004",
                reason=(
                    f"Reading from .sdd/specs/ directly is forbidden — use 'sdd show-spec' "
                    f"(NORM-SCOPE-004, I-PATH-1). Path: '{file_path}'"
                ),
                operation=operation,
                file_path=file_path,
            ).to_dict()

        return ScopeDecision(
            allowed=True,
            norm_id=None,
            reason=f"Read allowed: '{file_path}'",
            operation=operation,
            file_path=file_path,
        ).to_dict()

    if operation == "write":
        if _contains_sdd_specs(resolved):
            return ScopeDecision(
                allowed=False,
                norm_id="NORM-SCOPE-004",
                reason=(
                    f"Writing to .sdd/specs/ is forbidden — immutable "
                    f"(NORM-SCOPE-004, I-SDD-19). Path: '{file_path}'"
                ),
                operation=operation,
                file_path=file_path,
            ).to_dict()

        return ScopeDecision(
            allowed=True,
            norm_id=None,
            reason=f"Write allowed: '{file_path}'",
            operation=operation,
            file_path=file_path,
        ).to_dict()

    return ScopeDecision(
        allowed=False,
        norm_id=None,
        reason=f"Unknown operation: '{operation}'. Must be 'read' or 'write'.",
        operation=operation,
        file_path=file_path,
    ).to_dict()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: check_scope.py read|write <file_path> [--task T-NNN] [--inputs file1,file2]")
        return 0

    if len(args) < 2:
        print(json.dumps({"error": "Missing operation or file_path"}))
        return 1

    operation = args[0]
    file_path = args[1]
    task_inputs: list[str] = []

    i = 2
    while i < len(args):
        a = args[i]
        if a == "--inputs" and i + 1 < len(args):
            task_inputs = args[i + 1].split(","); i += 2
        elif a in ("--task", "--phase", "--catalog", "--log") and i + 1 < len(args):
            i += 2  # accepted but unused — kept for CLI compatibility
        else:
            i += 1

    result = check_scope(operation, file_path, task_inputs)
    print(json.dumps(result))
    return 0 if result["allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
