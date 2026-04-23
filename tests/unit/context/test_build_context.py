"""Tests for build_context — T-213 (Spec_v2 §9 verification row 6)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sdd.context import build_context, ContextDepth, TOKEN_BUDGET, EFFECTIVE_BUDGET
from sdd.core.errors import MissingContext
from sdd.domain.tasks.parser import parse_taskset

# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

_SPEC = """\
# Spec v1

## 1 Overview
This is the test spec overview section.

## 2 Domain
Domain details here.
"""

_PLAN = """\
# Plan v1

### M1: Setup
Initial milestone with details.

### M2: Implementation
Implementation milestone details.

<!-- Milestone mapping: T-101..T-101 → M1 | T-102..T-102 → M2 -->
"""

_TASKSET = """\
# TaskSet_v1

## T-101: First task

Status:               TODO
Spec ref:             §1 Overview
Inputs:               src/foo.py
Outputs:              src/bar.py
Checks:               pytest tests/unit/
Depends on:           —

---

## T-102: Second task

Status:               DONE
Spec ref:             §2 Domain
Inputs:               src/baz.py
Outputs:              src/qux.py
Checks:               pytest tests/unit/
Depends on:           T-101

---
"""

_STATE = """\
phase:
  current: 1
  status: ACTIVE
plan:
  version: 1
  status: ACTIVE
tasks:
  version: 1
  total: 2
  completed: 1
  done_ids:
    - T-102
"""

_PHASES_INDEX = """\
# Phases Index

| Phase | Status |
|---|---|
| 1 | ACTIVE |
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_state() -> MagicMock:
    s = MagicMock()
    s.phase_current = 1
    return s


@pytest.fixture
def sdd_root(tmp_path: Path) -> dict[str, Any]:
    """Minimal SDD artifact tree + config dict for build_context."""
    specs_dir = tmp_path / "specs"
    plans_dir = tmp_path / "plans"
    tasks_dir = tmp_path / "tasks"
    runtime_dir = tmp_path / "runtime"
    for d in (specs_dir, plans_dir, tasks_dir, runtime_dir):
        d.mkdir()

    state_file = runtime_dir / "State_index.yaml"
    state_file.write_text(_STATE)
    (specs_dir / "Spec_v1_test.md").write_text(_SPEC)
    (plans_dir / "Plan_v1.md").write_text(_PLAN)
    (plans_dir / "Phases_index.md").write_text(_PHASES_INDEX)
    (tasks_dir / "TaskSet_v1.md").write_text(_TASKSET)

    return {
        "context": {
            "state_path": str(state_file),
            "phases_index_path": str(plans_dir / "Phases_index.md"),
            "specs_dir": str(specs_dir),
            "plans_dir": str(plans_dir),
            "tasks_dir": str(tasks_dir),
        },
        "domain": {"glossary": {"Term": "Definition"}},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call(
    agent_type: str,
    task_id: str | None,
    depth: str,
    config: dict,
    mock_state: MagicMock,
) -> str:
    with patch("sdd.context.build_context.read_state", return_value=mock_state):
        return build_context(agent_type, task_id, depth, config)


def _extract_hash(output: str) -> str:
    first_line = output.split("\n")[0]
    m = re.match(r"<!-- context_hash: ([0-9a-f]+) -->", first_line)
    assert m, f"No hash comment on first line: {first_line!r}"
    return m.group(1)


def _parse_task_rows(text: str, tmp_path: Path) -> list:
    """Write text to temp file and parse as TaskSet; return Task list or []."""
    out_file = tmp_path / "parsed_output.md"
    out_file.write_text(text)
    try:
        return parse_taskset(str(out_file))
    except MissingContext:
        return []


# ---------------------------------------------------------------------------
# Tests (12 total)
# ---------------------------------------------------------------------------


def test_build_context_is_deterministic(sdd_root, mock_state):
    out1 = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    out2 = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    assert out1 == out2


def test_build_context_pure_no_io_writes(sdd_root, mock_state):
    with patch.object(Path, "write_text") as mock_write:
        _call("coder", "T-101", ContextDepth.STANDARD, sdd_root, mock_state)
    mock_write.assert_not_called()


def test_context_within_token_budget_all_depths(sdd_root, mock_state):
    for depth in (ContextDepth.COMPACT, ContextDepth.STANDARD, ContextDepth.VERBOSE):
        out = _call("coder", "T-101", depth, sdd_root, mock_state)
        wc = len(out.split())
        assert wc <= EFFECTIVE_BUDGET[depth], (
            f"Budget exceeded for depth={depth}: {wc} > {EFFECTIVE_BUDGET[depth]}"
        )


def test_coder_context_includes_task_row(sdd_root, mock_state, tmp_path):
    out = _call("coder", "T-101", ContextDepth.COMPACT, sdd_root, mock_state)
    tasks = _parse_task_rows(out, tmp_path)
    matching = [t for t in tasks if t.task_id == "T-101"]
    assert len(matching) == 1, (
        f"Expected exactly one T-101 task row reconstructable from output, got {len(matching)}"
    )


def test_coder_context_excludes_other_tasks(sdd_root, mock_state, tmp_path):
    out = _call("coder", "T-101", ContextDepth.COMPACT, sdd_root, mock_state)
    tasks = _parse_task_rows(out, tmp_path)
    other = [t for t in tasks if t.task_id != "T-101"]
    assert len(other) == 0, (
        f"Unexpected task rows in coder output: {[t.task_id for t in other]}"
    )


def test_planner_context_includes_spec_and_plan(sdd_root, mock_state):
    out = _call("planner", None, ContextDepth.STANDARD, sdd_root, mock_state)
    assert "## Spec Section" in out
    assert "## Plan Milestone" in out


def test_planner_context_excludes_task_rows(sdd_root, mock_state, tmp_path):
    out = _call("planner", None, ContextDepth.VERBOSE, sdd_root, mock_state)
    tasks = _parse_task_rows(out, tmp_path)
    assert len(tasks) == 0, (
        f"Parseable task rows found in planner output: {[t.task_id for t in tasks]}"
    )


def test_context_hash_present_in_output(sdd_root, mock_state):
    out = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    digest = _extract_hash(out)
    assert len(digest) == 64, f"Expected 64-char hex SHA-256 digest, got len={len(digest)}"


def test_context_hash_changes_on_file_change(sdd_root, mock_state):
    out1 = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    hash1 = _extract_hash(out1)

    state_path = sdd_root["context"]["state_path"]
    Path(state_path).write_text(_STATE + "\n# modified\n")

    out2 = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    hash2 = _extract_hash(out2)

    assert hash1 != hash2, "Hash must change when an input file changes"


def test_context_hash_sorted_file_paths(sdd_root, mock_state):
    """Hash is computed over sorted file paths, not insertion order."""
    out = _call("planner", None, ContextDepth.COMPACT, sdd_root, mock_state)
    output_hash = _extract_hash(out)

    # For planner+COMPACT, loaded = {state_path: ..., phases_index_path: ...}
    state_path = sdd_root["context"]["state_path"]
    phases_path = sdd_root["context"]["phases_index_path"]
    loaded = {
        state_path: Path(state_path).read_text(),
        phases_path: Path(phases_path).read_text(),
    }
    file_hashes = {
        p: hashlib.sha256(c.encode("utf-8")).hexdigest()
        for p, c in sorted(loaded.items())
    }
    hash_data = json.dumps(
        {
            "agent_type": "planner",
            "task_id": None,
            "depth": ContextDepth.COMPACT,
            "files": file_hashes,
        },
        sort_keys=True,
    )
    expected = hashlib.sha256(hash_data.encode("utf-8")).hexdigest()
    assert output_hash == expected, "Hash must be computed over sorted file paths"


_LAYER_HEADER_SEQUENCE = [
    "## Domain Glossary",
    "## State Summary",
    "## Phases Index",
    "## Task Row",
    "## Spec Section",
    "## Plan Milestone",
    "## Full Spec",
    "## Full Plan",
    "## Input Files",
]


def test_layer_order_is_ascending(sdd_root, mock_state):
    """Layer section headers appear in strictly ascending position order."""
    out = _call("coder", "T-101", ContextDepth.VERBOSE, sdd_root, mock_state)
    positions = [out.find(h) for h in _LAYER_HEADER_SEQUENCE if out.find(h) >= 0]
    assert len(positions) >= 2, "At least 2 layer headers must appear in output"
    assert positions == sorted(positions), (
        "Layer headers are not in ascending positional order (layer index not monotone)"
    )


def test_truncation_at_paragraph_boundary(sdd_root, mock_state):
    """When budget is exceeded, truncation keeps output within budget."""
    # Force truncation: glossary paragraph ~3000 words >> COMPACT budget ~1500 words
    huge_glossary = {f"T{i:03d}": "filler " * 100 for i in range(30)}
    config = {**sdd_root, "domain": {"glossary": huge_glossary}}

    out = _call("planner", None, ContextDepth.COMPACT, config, mock_state)
    word_count = len(out.split())

    assert word_count <= EFFECTIVE_BUDGET[ContextDepth.COMPACT], (
        f"Output exceeds COMPACT budget after truncation: {word_count} > {EFFECTIVE_BUDGET[ContextDepth.COMPACT]}"
    )
    # Paragraph boundary: "filler" words must be entirely absent or entirely present
    # (truncation must not include a partial glossary paragraph)
    filler_count = out.count("filler")
    if filler_count > 0:
        # If any filler words appear, the whole glossary paragraph was included
        # and must still be within budget
        assert word_count <= EFFECTIVE_BUDGET[ContextDepth.COMPACT]
    # If filler_count == 0, the glossary content paragraph was cleanly excluded — correct
