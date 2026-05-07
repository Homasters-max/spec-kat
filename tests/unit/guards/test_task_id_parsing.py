"""Regression tests for task ID parsing in CLI guards.

These cover the Phase-10 scalability bug where T-10xx IDs were silently
mis-parsed due to digit{3}-bounded regexes. See I-KERNEL-REG (BC-REGRESS).
"""
import re

import pytest

from sdd.guards.phase import _extract_phase_from_task, _extract_task_id
from sdd.guards.task import _TASK_HDR


# ── _extract_task_id ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("command,expected", [
    ("Implement T-101",  "T-101"),
    ("Implement T-1001", "T-1001"),
    ("Implement T-10001", "T-10001"),
    ("Validate T-201",   "T-201"),
    ("Validate T-2001",  "T-2001"),
    ("no task here",     None),
])
def test_extract_task_id(command, expected):
    assert _extract_task_id(command) == expected


# ── _extract_phase_from_task ──────────────────────────────────────────────────

@pytest.mark.parametrize("task_id,expected_phase", [
    ("T-101",   1),
    ("T-201",   2),
    ("T-901",   9),
    ("T-1001",  10),   # regression: was returning 1
    ("T-1099",  10),   # regression: was returning 1
    ("T-1101",  11),
    ("T-10001", 100),
])
def test_extract_phase_from_task(task_id, expected_phase):
    assert _extract_phase_from_task(task_id) == expected_phase


@pytest.mark.parametrize("task_id", ["T-1", "T-12", "T-", "foo"])
def test_extract_phase_from_task_none(task_id):
    assert _extract_phase_from_task(task_id) is None


# ── _TASK_HDR (task.py header regex) ─────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "T-101: My task",
    "T-1001: Phase 10 task",    # regression: was not matched
    "T-10001: Phase 100 task",
    "## T-1001.",
    "## T-201:",
])
def test_task_hdr_matches(line):
    assert _TASK_HDR.match(line), f"_TASK_HDR should match: {line!r}"


@pytest.mark.parametrize("line", [
    "  T-101: indented",
    "### T-101:",
    "Description: something",
])
def test_task_hdr_no_match(line):
    assert not _TASK_HDR.match(line), f"_TASK_HDR should not match: {line!r}"
