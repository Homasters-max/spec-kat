"""show_plan — Spec_v14 §2 (BC-8 CLI additions), §6 (show-plan pre/post).

Invariants: I-CLI-READ-1, I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-SCOPE-CLI-1
"""
from __future__ import annotations

import json
import sys

from sdd.infra.paths import plan_file


def show_plan(phase: int) -> None:
    """Print the plan file for the given phase to stdout; exit 1 with JSON on missing."""
    path = plan_file(phase)
    if not path.exists():
        error = {
            "error_type": "PlanNotFound",
            "message": f"Plan file not found: {path}",
            "exit_code": 1,
        }
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(path.read_text())
