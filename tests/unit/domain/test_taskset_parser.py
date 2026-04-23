"""Tests for parse_taskset — both header format branches (I-LOGIC-COVER-1).

_HEADER_RE supports two formats:
  Branch A: ## T-NNN: Title   (markdown heading)
  Branch B:    T-NNN: Title   (plain line, no ## prefix)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdd.domain.tasks.parser import Task, parse_taskset


# ---------------------------------------------------------------------------
# Branch A: ## T-NNN: Title  (markdown heading format)
# ---------------------------------------------------------------------------


def test_branch_a_markdown_header(tmp_path: Path) -> None:
    """parse_taskset parses ## T-NNN: Title format (Branch A)."""
    content = textwrap.dedent("""\
        ## T-101: Markdown header task

        Status: TODO
        Spec ref: Spec_v1 §1
        Inputs: src/a.py
        Outputs: src/b.py
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.task_id == "T-101"
    assert t.title == "Markdown header task"
    assert t.status == "TODO"


def test_branch_a_suffix_id(tmp_path: Path) -> None:
    """I-TASK-ID-1: ## T-NNNa suffix variant parsed correctly in Branch A."""
    content = textwrap.dedent("""\
        ## T-201a: Suffixed task

        Status: DONE
        Spec ref: Spec_v2 §2
        Inputs:
        Outputs:
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    assert tasks[0].task_id == "T-201a"
    assert tasks[0].title == "Suffixed task"


def test_branch_a_multiple_tasks(tmp_path: Path) -> None:
    """Branch A: multiple ## T-NNN headers produce multiple Task objects."""
    content = textwrap.dedent("""\
        ## T-101: First task

        Status: TODO
        Spec ref: Spec_v1 §1
        Inputs: src/a.py
        Outputs: src/b.py

        ## T-102: Second task

        Status: DONE
        Spec ref: Spec_v1 §2
        Inputs: src/c.py
        Outputs: src/d.py
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 2
    assert tasks[0].task_id == "T-101"
    assert tasks[1].task_id == "T-102"
    assert tasks[1].status == "DONE"


# ---------------------------------------------------------------------------
# Branch B: T-NNN: Title  (plain line format, no ## prefix)
# ---------------------------------------------------------------------------


def test_branch_b_plain_header(tmp_path: Path) -> None:
    """parse_taskset parses T-NNN: Title plain line format (Branch B)."""
    content = textwrap.dedent("""\
        T-301: Plain line task

        Status: TODO
        Spec ref: Spec_v3 §1
        Inputs: src/x.py
        Outputs: src/y.py
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.task_id == "T-301"
    assert t.title == "Plain line task"
    assert t.status == "TODO"


def test_branch_b_suffix_id(tmp_path: Path) -> None:
    """I-TASK-ID-1: T-NNNb suffix variant parsed correctly in Branch B."""
    content = textwrap.dedent("""\
        T-401b: Suffixed plain task

        Status: TODO
        Spec ref: Spec_v4 §1
        Inputs:
        Outputs:
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    assert tasks[0].task_id == "T-401b"
    assert tasks[0].title == "Suffixed plain task"


def test_branch_b_multiple_tasks(tmp_path: Path) -> None:
    """Branch B: multiple plain T-NNN lines produce multiple Task objects."""
    content = textwrap.dedent("""\
        T-301: First plain task

        Status: TODO
        Spec ref: Spec_v3 §1
        Inputs: src/a.py
        Outputs: src/b.py

        T-302: Second plain task

        Status: DONE
        Spec ref: Spec_v3 §2
        Inputs: src/c.py
        Outputs: src/d.py
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 2
    assert tasks[0].task_id == "T-301"
    assert tasks[1].task_id == "T-302"


# ---------------------------------------------------------------------------
# Mixed: both formats in the same file
# ---------------------------------------------------------------------------


def test_mixed_formats_in_same_file(tmp_path: Path) -> None:
    """Branch A and Branch B headers can coexist in the same TaskSet file."""
    content = textwrap.dedent("""\
        ## T-101: Markdown task

        Status: TODO
        Spec ref: Spec_v1 §1
        Inputs: src/a.py
        Outputs: src/b.py

        T-102: Plain task

        Status: DONE
        Spec ref: Spec_v1 §2
        Inputs: src/c.py
        Outputs: src/d.py
    """)
    f = tmp_path / "ts.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 2
    assert tasks[0].task_id == "T-101"
    assert tasks[1].task_id == "T-102"
