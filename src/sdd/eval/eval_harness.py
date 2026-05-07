# EVAL ONLY — harness for running graph-guided implement evaluation scenarios
"""sdd.eval.eval_harness — ScenarioResult + run_graph_cmd for Phase 61 eval scenarios.

Keywords: eval harness scenario result graph-guided resolve explain trace write
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str  # "PASS" | "FAIL"
    stdout: str
    stderr: str
    exit_code: int


def run_graph_cmd(cmd: str, args: List[str]) -> ScenarioResult:
    """Run an sdd graph navigation command and return a ScenarioResult.

    cmd: the sdd subcommand (e.g. "resolve", "explain", "trace", "write", "graph-guard")
    args: additional CLI arguments
    """
    full_cmd = ["sdd", cmd] + args
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    return ScenarioResult(
        scenario_id=cmd,
        status=status,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode,
    )
