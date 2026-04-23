"""Tests for Task dataclass and parse_taskset — Spec_v2 §4.7, I-TS-1..3."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdd.core.errors import MissingContext
from sdd.domain.tasks.parser import Task, parse_taskset

_MINIMAL_TASKSET = textwrap.dedent("""\
    # TaskSet_v2 — Phase 2

    ---

    ## T-201: Task dataclass + parse_taskset() implementation

    Status:               TODO
    Spec ref:             Spec_v2 §4.7
    Invariants:           I-TS-1, I-TS-2, I-TS-3
    spec_refs:            Spec_v2 §4.7, I-TS-1, I-TS-2, I-TS-3
    produces_invariants:  I-TS-1, I-TS-2, I-TS-3
    requires_invariants:
    Inputs:               src/sdd/core/errors.py
    Outputs:              src/sdd/domain/tasks/parser.py
    Checks:               ruff check src/sdd/domain/tasks/parser.py, mypy src/sdd/domain/tasks/parser.py
    Depends on:           —

    ---
""")

_DONE_TASKSET = textwrap.dedent("""\
    # TaskSet

    ## T-301: Some task

    Status:               DONE
    Spec ref:             Spec_v3 §1
    Inputs:               src/foo.py
    Outputs:              src/bar.py
    Checks:               pytest tests/
""")


def test_parse_task_has_spec_fields(tmp_path: Path) -> None:
    """I-TS-1: Task dataclass has spec_refs, produces_invariants, requires_invariants fields."""
    f = tmp_path / "ts.md"
    f.write_text(_MINIMAL_TASKSET)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.task_id == "T-201"
    assert t.title == "Task dataclass + parse_taskset() implementation"
    assert isinstance(t.spec_refs, tuple)
    assert isinstance(t.produces_invariants, tuple)
    assert isinstance(t.requires_invariants, tuple)
    assert "I-TS-1" in t.spec_refs
    assert "I-TS-1" in t.produces_invariants
    assert t.requires_invariants == ()


def test_parse_missing_optional_fields_default_empty(tmp_path: Path) -> None:
    """I-TS-1: Missing optional tuple fields default to ()."""
    content = textwrap.dedent("""\
        ## T-501: Bare task

        Status: TODO
        Spec ref: Spec_v5 §1
        Inputs:
        Outputs:
        Checks:
    """)
    f = tmp_path / "bare.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.spec_refs == ()
    assert t.produces_invariants == ()
    assert t.requires_invariants == ()
    assert t.inputs == ()
    assert t.outputs == ()
    assert t.checks == ()


def test_parse_is_deterministic(tmp_path: Path) -> None:
    """I-TS-2: parse_taskset is deterministic — two calls on same file return equal result."""
    f = tmp_path / "ts.md"
    f.write_text(_MINIMAL_TASKSET)
    result1 = parse_taskset(str(f))
    result2 = parse_taskset(str(f))
    assert result1 == result2


def test_parse_missing_file_raises(tmp_path: Path) -> None:
    """parse_taskset raises MissingContext when file is absent."""
    with pytest.raises(MissingContext):
        parse_taskset(str(tmp_path / "nonexistent.md"))


def test_parse_malformed_no_headers_raises(tmp_path: Path) -> None:
    """I-TS-3: parse_taskset raises MissingContext when no ## T-NNN headers exist."""
    f = tmp_path / "malformed.md"
    f.write_text("# Just a title\n\nNo task headers here.\n")
    with pytest.raises(MissingContext):
        parse_taskset(str(f))


def test_parse_done_status(tmp_path: Path) -> None:
    """parse_taskset correctly parses Status: DONE."""
    f = tmp_path / "done.md"
    f.write_text(_DONE_TASKSET)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    assert tasks[0].status == "DONE"
    assert tasks[0].task_id == "T-301"


def test_parse_task_has_depends_on_field(tmp_path: Path) -> None:
    """I-TS-1: Task.depends_on is populated when 'Depends on' field is present."""
    content = textwrap.dedent("""\
        ## T-303: With deps

        Status:               TODO
        Spec ref:             Spec_v3 §4.9
        Inputs:               src/a.py
        Outputs:              src/b.py
        Depends on:           T-301, T-302
        Parallel group:       bc-extensions
    """)
    f = tmp_path / "deps.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert isinstance(t.depends_on, tuple)
    assert t.depends_on == ("T-301", "T-302")


def test_parse_task_has_parallel_group_field(tmp_path: Path) -> None:
    """I-TS-1: Task.parallel_group is populated when 'Parallel group' field is present."""
    content = textwrap.dedent("""\
        ## T-303: With group

        Status:               TODO
        Spec ref:             Spec_v3 §4.9
        Inputs:               src/a.py
        Outputs:              src/b.py
        Depends on:           T-301
        Parallel group:       bc-extensions
    """)
    f = tmp_path / "group.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.parallel_group == "bc-extensions"


def test_parse_missing_new_fields_default_empty(tmp_path: Path) -> None:
    """I-TS-1: Task.depends_on defaults to () and Task.parallel_group defaults to None when absent."""
    content = textwrap.dedent("""\
        ## T-501: No new fields

        Status: TODO
        Spec ref: Spec_v3 §1
        Inputs:
        Outputs:
    """)
    f = tmp_path / "no_new.md"
    f.write_text(content)
    tasks = parse_taskset(str(f))
    assert len(tasks) == 1
    t = tasks[0]
    assert t.depends_on == ()
    assert t.parallel_group is None
