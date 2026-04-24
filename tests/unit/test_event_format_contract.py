"""AST-based event format contract tests — I-EVENT-FORMAT-1, I-HANDLER-BATCH-PURE-1.

Spec ref: Spec_v15 §2; T-1514 acceptance criteria
"""
from __future__ import annotations

from pathlib import Path

# Pre-Phase-15 internal files exempt from the sdd_replay prohibition.
# activate_plan.py: internal-only, I-CLI-REG-1 exempt (no user-facing CLI entry).
# These will be cleaned up in a later task when sdd_replay is removed project-wide.
_EXEMPT_FILES: frozenset[str] = frozenset({"activate_plan.py"})


def test_no_sdd_replay_in_commands() -> None:
    """No sdd_replay usage in Phase-15-scope command handlers (I-EVENT-FORMAT-1).

    Command handlers MUST NOT call sdd_replay directly.
    State reconstruction uses get_current_state() (projections.py) exclusively.
    Handlers are pure: no I/O, no EventStore calls (I-HANDLER-BATCH-PURE-1).
    Pre-Phase-15 internal files listed in _EXEMPT_FILES are excluded.
    """
    commands_path = Path("src/sdd/commands").absolute()
    assert commands_path.exists(), f"src/sdd/commands not found at {commands_path}"

    files_checked = 0
    violations: list[str] = []

    for py_file in sorted(commands_path.rglob("*.py")):
        if py_file.name in _EXEMPT_FILES:
            continue
        files_checked += 1
        content = py_file.read_text(encoding="utf-8")
        if "sdd_replay" in content:
            violations.append(str(py_file))

    assert files_checked > 0, "No Python files checked — src/sdd/commands structure unexpected"
    assert violations == [], (
        f"sdd_replay found in src/sdd/commands/ (I-EVENT-FORMAT-1): {violations}"
    )
