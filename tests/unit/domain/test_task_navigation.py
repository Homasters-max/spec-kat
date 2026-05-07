"""Tests for TaskNavigationSpec — I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdd.domain.tasks.navigation import ResolveKeyword, TaskNavigationSpec
from sdd.domain.tasks.parser import parse_taskset


# ---------------------------------------------------------------------------
# I-DECOMPOSE-RESOLVE-1: parse() with resolve_keywords + write_scope
# ---------------------------------------------------------------------------

def test_parse_with_resolve_keywords_and_write_scope() -> None:
    """TaskNavigationSpec.parse() with resolve_keywords + write_scope → correct result."""
    raw = {
        "write_scope": "src/sdd/graph_navigation/cli/explain.py, src/sdd/domain/tasks/navigation.py",
        "resolve_keywords": [
            {"keyword": "explain", "expected_kinds": ["COMMAND", "HANDLER"]},
            {"keyword": "TaskNavigationSpec", "expected_kinds": ["CLASS"]},
        ],
    }
    spec = TaskNavigationSpec.parse(raw)

    assert spec.write_scope == (
        "src/sdd/graph_navigation/cli/explain.py",
        "src/sdd/domain/tasks/navigation.py",
    )
    assert len(spec.resolve_keywords) == 2
    assert spec.resolve_keywords[0] == ResolveKeyword(
        keyword="explain", expected_kinds=("COMMAND", "HANDLER")
    )
    assert spec.resolve_keywords[1] == ResolveKeyword(
        keyword="TaskNavigationSpec", expected_kinds=("CLASS",)
    )


def test_parse_resolve_keywords_as_plain_strings() -> None:
    """resolve_keywords entries as plain strings → ResolveKeyword with empty expected_kinds."""
    raw = {
        "write_scope": "src/foo.py",
        "resolve_keywords": ["foo_cmd", "bar_handler"],
    }
    spec = TaskNavigationSpec.parse(raw)
    assert spec.resolve_keywords == (
        ResolveKeyword(keyword="foo_cmd", expected_kinds=()),
        ResolveKeyword(keyword="bar_handler", expected_kinds=()),
    )


def test_parse_write_scope_as_list() -> None:
    """write_scope as list (not CSV string) → parsed correctly."""
    raw = {
        "write_scope": ["src/a.py", "src/b.py"],
        "resolve_keywords": [],
    }
    spec = TaskNavigationSpec.parse(raw)
    assert spec.write_scope == ("src/a.py", "src/b.py")


def test_parse_empty_resolve_keywords() -> None:
    """Empty resolve_keywords → empty tuple; write_scope still parsed."""
    raw = {"write_scope": "src/sdd/foo.py", "resolve_keywords": []}
    spec = TaskNavigationSpec.parse(raw)
    assert spec.resolve_keywords == ()
    assert spec.write_scope == ("src/sdd/foo.py",)


# ---------------------------------------------------------------------------
# I-DECOMPOSE-RESOLVE-2: navigation = None when no Navigation section
# ---------------------------------------------------------------------------

_TASKSET_NO_NAVIGATION = textwrap.dedent("""\
    # TaskSet_v55 — Phase 55

    ## T-5501: Some task without navigation

    Status:               TODO
    Spec ref:             Spec_v55 §1
    Inputs:               src/sdd/core/errors.py
    Outputs:              src/sdd/domain/tasks/navigation.py
    Checks:               pytest tests/
""")

_TASKSET_WITH_NAVIGATION = textwrap.dedent("""\
    # TaskSet_v55 — Phase 55

    ## T-5502: Task with navigation

    Status:               TODO
    Spec ref:             Spec_v55 §2
    Inputs:               src/sdd/domain/tasks/navigation.py
    Outputs:              tests/unit/domain/test_task_navigation.py
    Checks:               pytest tests/
    Navigation:
        write_scope: src/sdd/domain/tasks/navigation.py
        resolve_keywords: TaskNavigationSpec, ResolveKeyword
""")


def test_task_navigation_none_when_no_section(tmp_path: Path) -> None:
    """TaskSet without Navigation section → task.navigation is None (I-DECOMPOSE-RESOLVE-2)."""
    f = tmp_path / "ts.md"
    f.write_text(_TASKSET_NO_NAVIGATION)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    assert tasks[0].navigation is None


def test_task_navigation_parsed_when_section_present(tmp_path: Path) -> None:
    """TaskSet with Navigation section → task.navigation is TaskNavigationSpec."""
    f = tmp_path / "ts.md"
    f.write_text(_TASKSET_WITH_NAVIGATION)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    nav = tasks[0].navigation
    assert nav is not None
    assert isinstance(nav, TaskNavigationSpec)
    assert "src/sdd/domain/tasks/navigation.py" in nav.write_scope


# ---------------------------------------------------------------------------
# is_anchor_mode()
# ---------------------------------------------------------------------------

def test_is_anchor_mode_false_for_v55_task() -> None:
    """is_anchor_mode() returns False for v55 tasks (resolve_keywords era, no anchor_nodes)."""
    spec = TaskNavigationSpec(
        write_scope=("src/sdd/domain/tasks/navigation.py",),
        resolve_keywords=(ResolveKeyword(keyword="TaskNavigationSpec", expected_kinds=("CLASS",)),),
        anchor_nodes=(),
    )
    assert spec.is_anchor_mode() is False


def test_is_anchor_mode_true_when_anchor_nodes_present() -> None:
    """is_anchor_mode() returns True when anchor_nodes is non-empty."""
    spec = TaskNavigationSpec(
        write_scope=("src/sdd/foo.py",),
        anchor_nodes=("CMD:explain", "CLASS:TaskNavigationSpec"),
    )
    assert spec.is_anchor_mode() is True


def test_is_anchor_mode_false_when_anchor_nodes_empty() -> None:
    """is_anchor_mode() returns False when anchor_nodes is empty tuple."""
    spec = TaskNavigationSpec(write_scope=())
    assert spec.is_anchor_mode() is False
