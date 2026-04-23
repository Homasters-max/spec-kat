"""sdd.guards.scope — ScopeGuard CLI (migrated to src/ in Phase 8).

Invariants: NORM-SCOPE-001..004, NORM-SCOPE-003 (glob).
Exit: 0 = allowed, 1 = denied. JSON to stdout.
"""
from __future__ import annotations

import fnmatch
import json
import sys


def _has_glob(path: str) -> bool:
    return "*" in path or "?" in path or "[" in path


def check_scope(
    operation: str,
    file_path: str,
    task_inputs: list[str] | None = None,
) -> dict:
    path = file_path.lstrip("./").lstrip("/")

    if _has_glob(path):
        return {
            "allowed": False,
            "reason": f"Glob patterns forbidden: '{file_path}'. Use exact file paths only.",
            "norm_id": "NORM-SCOPE-003",
            "operation": operation,
            "file_path": file_path,
        }

    if operation == "read":
        if path.startswith("tests/") or path == "tests":
            return {
                "allowed": False,
                "reason": f"Reading from tests/ is forbidden (NORM-SCOPE-001). Path: '{file_path}'",
                "norm_id": "NORM-SCOPE-001",
                "operation": operation,
                "file_path": file_path,
            }
        if path.startswith("src/"):
            task_inputs_norm = [p.lstrip("./").lstrip("/") for p in (task_inputs or [])]
            if path not in task_inputs_norm:
                return {
                    "allowed": False,
                    "reason": (
                        f"Reading from src/ is forbidden unless listed in Task Inputs "
                        f"(NORM-SCOPE-002). Path: '{file_path}'. "
                        f"Declared inputs: {task_inputs or []}"
                    ),
                    "norm_id": "NORM-SCOPE-002",
                    "operation": operation,
                    "file_path": file_path,
                }
        return {
            "allowed": True,
            "reason": f"Read allowed: '{file_path}'",
            "norm_id": None,
            "operation": operation,
            "file_path": file_path,
        }

    if operation == "write":
        if path.startswith(".sdd/specs/") or path == ".sdd/specs":
            return {
                "allowed": False,
                "reason": (
                    f"Writing to .sdd/specs/ is forbidden — immutable "
                    f"(NORM-SCOPE-004, I-SDD-19). Path: '{file_path}'"
                ),
                "norm_id": "NORM-SCOPE-004",
                "operation": operation,
                "file_path": file_path,
            }
        return {
            "allowed": True,
            "reason": f"Write allowed: '{file_path}'",
            "norm_id": None,
            "operation": operation,
            "file_path": file_path,
        }

    return {
        "allowed": False,
        "reason": f"Unknown operation: '{operation}'. Must be 'read' or 'write'.",
        "norm_id": None,
        "operation": operation,
        "file_path": file_path,
    }


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
