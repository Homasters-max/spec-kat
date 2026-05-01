"""Unit tests for sdd.commands.show_task."""
from __future__ import annotations

import pytest

from sdd.commands.show_task import _bullets, _parse_taskset, _render


_TASKSET = """\
T-6101: Implement foo
Status: TODO
Inputs: src/foo.py, tests/unit/test_foo.py
Outputs: src/foo.py
Invariants: I-FOO-1, I-BAR-2
Acceptance: foo must work correctly

---

T-6102: Implement bar
Status: DONE
Inputs: (none)
Outputs: src/bar.py
Invariants: —
Acceptance: bar must work
"""


# ── _bullets ─────────────────────────────────────────────────────────────────


def test_bullets_comma_separated():
    assert _bullets("a.py, b.py, c.py") == ["a.py", "b.py", "c.py"]


def test_bullets_single():
    assert _bullets("src/foo.py") == ["src/foo.py"]


def test_bullets_none_prefix():
    assert _bullets("(none)") == []


def test_bullets_none_with_text():
    assert _bullets("(none declared)") == []


def test_bullets_dash():
    assert _bullets("—") == []


def test_bullets_empty():
    assert _bullets("") == []


def test_bullets_strips_whitespace():
    result = _bullets("  a.py  ,  b.py  ")
    assert result == ["a.py", "b.py"]


# ── _parse_taskset ────────────────────────────────────────────────────────────


def test_parse_taskset_first_task():
    fields = _parse_taskset(_TASKSET, "T-6101")
    assert fields is not None
    assert fields["status"] == "TODO"
    assert "src/foo.py" in fields["inputs"]


def test_parse_taskset_second_task():
    fields = _parse_taskset(_TASKSET, "T-6102")
    assert fields is not None
    assert fields["status"] == "DONE"


def test_parse_taskset_not_found():
    result = _parse_taskset(_TASKSET, "T-9999")
    assert result is None


def test_parse_taskset_empty_content():
    result = _parse_taskset("", "T-6101")
    assert result is None


def test_parse_taskset_hash_header():
    content = "## T-6103: Hash style\nStatus: TODO\nInputs: (none)\nOutputs: (none)\n"
    fields = _parse_taskset(content, "T-6103")
    assert fields is not None
    assert fields["status"] == "TODO"


def test_parse_taskset_stops_at_separator():
    fields = _parse_taskset(_TASKSET, "T-6101")
    assert fields is not None
    # Acceptance from T-6101 only, not T-6102
    assert fields["acceptance"] == "foo must work correctly"


def test_parse_taskset_stops_at_next_task_header():
    content = "T-0001: First\nStatus: TODO\nOutputs: a.py\nT-0002: Second\nStatus: DONE\n"
    fields = _parse_taskset(content, "T-0001")
    assert fields is not None
    assert fields["status"] == "TODO"


# ── _render ───────────────────────────────────────────────────────────────────


def test_render_contains_task_id():
    fields = {"status": "TODO", "inputs": "src/foo.py", "outputs": "out.py",
              "invariants": "I-X-1", "acceptance": "pass"}
    output = _render("T-6101", fields)
    assert "T-6101" in output
    assert "TODO" in output


def test_render_no_inputs():
    fields = {"status": "TODO", "inputs": "(none)", "outputs": "(none)",
              "invariants": "", "acceptance": ""}
    output = _render("T-0001", fields)
    assert "- (none)" in output


def test_render_with_invariants():
    fields = {"status": "DONE", "inputs": "", "outputs": "",
              "invariants": "I-A-1, I-B-2", "acceptance": "ok"}
    output = _render("T-0002", fields)
    assert "I-A-1" in output
    assert "I-B-2" in output


def test_render_sections_present():
    fields = {"status": "TODO", "inputs": "a.py", "outputs": "b.py",
              "invariants": "", "acceptance": "test"}
    output = _render("T-0003", fields)
    assert "### Inputs" in output
    assert "### Outputs" in output
    assert "### Invariants Covered" in output
    assert "### Acceptance Criteria" in output


def test_render_missing_fields_defaults():
    output = _render("T-0004", {})
    assert "T-0004" in output
    assert "UNKNOWN" in output


# ── show_task integration ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_sdd_root_after():
    yield
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()


def test_show_task_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "tasks").mkdir(parents=True)
    (tmp_path / "tasks" / "TaskSet_v61.md").write_text(_TASKSET)

    from sdd.commands.show_task import show_task
    rc = show_task("T-6101", phase=61)
    assert rc == 0
    out = capsys.readouterr().out
    assert "T-6101" in out


def test_show_task_missing_taskset(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "tasks").mkdir(parents=True)

    from sdd.commands.show_task import show_task
    rc = show_task("T-6101", phase=61)
    assert rc == 1


def test_show_task_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "tasks").mkdir(parents=True)
    (tmp_path / "tasks" / "TaskSet_v61.md").write_text(_TASKSET)

    from sdd.commands.show_task import show_task
    rc = show_task("T-9999", phase=61)
    assert rc == 1


# ── main() ───────────────────────────────────────────────────────────────────


def test_main_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "tasks").mkdir(parents=True)
    (tmp_path / "tasks" / "TaskSet_v61.md").write_text(_TASKSET)

    from sdd.commands.show_task import main
    rc = main(["T-6101", "--phase", "61"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "T-6101" in out


def test_main_missing_taskset(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "tasks").mkdir(parents=True)

    from sdd.commands.show_task import main
    rc = main(["T-6101", "--phase", "61"])
    assert rc == 1


def test_main_help():
    from sdd.commands.show_task import main
    rc = main(["--help"])
    assert rc == 0
