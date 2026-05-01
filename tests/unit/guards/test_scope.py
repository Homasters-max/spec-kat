"""Unit tests for sdd.guards.scope — check_scope and helpers."""
from __future__ import annotations

import json

import pytest

from sdd.guards.scope import _contains_sdd_specs, _has_glob, _is_relative_to, check_scope


# ── _has_glob ─────────────────────────────────────────────────────────────────


def test_has_glob_star():
    assert _has_glob("src/*.py")


def test_has_glob_question():
    assert _has_glob("src/?.py")


def test_has_glob_bracket():
    assert _has_glob("src/[abc].py")


def test_has_glob_plain():
    assert not _has_glob("src/foo/bar.py")


def test_has_glob_empty():
    assert not _has_glob("")


# ── _is_relative_to ───────────────────────────────────────────────────────────


def test_is_relative_to_child(tmp_path):
    child = tmp_path / "sub" / "file.py"
    assert _is_relative_to(child, tmp_path)


def test_is_relative_to_same_path(tmp_path):
    assert _is_relative_to(tmp_path, tmp_path)


def test_is_relative_to_unrelated(tmp_path):
    from pathlib import Path
    other = Path("/some/other/path")
    assert not _is_relative_to(tmp_path, other)


def test_is_relative_to_parent_not_child(tmp_path):
    parent = tmp_path.parent
    assert _is_relative_to(tmp_path, parent)
    assert not _is_relative_to(parent, tmp_path)


# ── _contains_sdd_specs ───────────────────────────────────────────────────────


def test_contains_sdd_specs_via_path_parts():
    from pathlib import Path
    p = Path("/project/.sdd/specs/Spec_v1.md")
    assert _contains_sdd_specs(p)


def test_contains_sdd_specs_false_specs_draft():
    from pathlib import Path
    p = Path("/project/.sdd/specs_draft/Spec_v2.md")
    assert not _contains_sdd_specs(p)


def test_contains_sdd_specs_false_src():
    from pathlib import Path
    p = Path("/project/src/foo.py")
    assert not _contains_sdd_specs(p)


def test_contains_sdd_specs_true_from_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / ".sdd" / "specs"
    specs.mkdir(parents=True)
    spec_file = specs / "Spec_v1.md"
    spec_file.touch()
    assert _contains_sdd_specs(spec_file.resolve())


# ── check_scope: glob forbidden ───────────────────────────────────────────────


def test_check_scope_glob_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = check_scope("read", "src/*.py")
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-003"


def test_check_scope_glob_write_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = check_scope("write", "*.md")
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-003"


# ── check_scope: read tests/ ──────────────────────────────────────────────────


def test_check_scope_read_tests_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_foo.py"
    f.touch()
    result = check_scope("read", str(f))
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-001"


def test_check_scope_read_tests_override_with_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_foo.py"
    f.touch()
    result = check_scope("read", str(f), task_inputs=[str(f)])
    assert result["allowed"] is True


# ── check_scope: read src/ ────────────────────────────────────────────────────


def test_check_scope_read_src_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    f = src_dir / "module.py"
    f.touch()
    result = check_scope("read", str(f))
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-002"


def test_check_scope_read_src_override_with_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    f = src_dir / "module.py"
    f.touch()
    result = check_scope("read", str(f), task_inputs=[str(f)])
    assert result["allowed"] is True


def test_check_scope_read_src_no_override_wrong_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    f = src_dir / "module.py"
    other = src_dir / "other.py"
    f.touch()
    other.touch()
    result = check_scope("read", str(f), task_inputs=[str(other)])
    assert result["allowed"] is False


# ── check_scope: read .sdd/specs/ ────────────────────────────────────────────


def test_check_scope_read_sdd_specs_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / ".sdd" / "specs"
    specs.mkdir(parents=True)
    f = specs / "Spec_v1.md"
    f.touch()
    result = check_scope("read", str(f))
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-004"


def test_check_scope_read_sdd_specs_not_overridable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / ".sdd" / "specs"
    specs.mkdir(parents=True)
    f = specs / "Spec_v1.md"
    f.touch()
    result = check_scope("read", str(f), task_inputs=[str(f)])
    assert result["allowed"] is False


# ── check_scope: read other (allowed) ────────────────────────────────────────


def test_check_scope_read_other_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "CLAUDE.md"
    f.touch()
    result = check_scope("read", str(f))
    assert result["allowed"] is True


def test_check_scope_read_sdd_non_specs_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plans = tmp_path / ".sdd" / "plans"
    plans.mkdir(parents=True)
    f = plans / "Plan_v1.md"
    f.touch()
    result = check_scope("read", str(f))
    assert result["allowed"] is True


# ── check_scope: write ────────────────────────────────────────────────────────


def test_check_scope_write_sdd_specs_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / ".sdd" / "specs"
    specs.mkdir(parents=True)
    f = specs / "Spec_v1.md"
    result = check_scope("write", str(f))
    assert result["allowed"] is False
    assert result["norm_id"] == "NORM-SCOPE-004"


def test_check_scope_write_other_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "output.md"
    result = check_scope("write", str(f))
    assert result["allowed"] is True


def test_check_scope_write_src_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f = src / "module.py"
    result = check_scope("write", str(f))
    assert result["allowed"] is True


# ── check_scope: unknown operation ────────────────────────────────────────────


def test_check_scope_unknown_operation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = check_scope("delete", "foo.py")
    assert result["allowed"] is False
    assert "Unknown operation" in result["reason"]


# ── main (CLI interface) ──────────────────────────────────────────────────────


def test_main_no_args(capsys):
    from sdd.guards.scope import main
    rc = main([])
    assert rc == 0


def test_main_help(capsys):
    from sdd.guards.scope import main
    rc = main(["--help"])
    assert rc == 0


def test_main_missing_file_path(capsys):
    from sdd.guards.scope import main
    rc = main(["read"])
    assert rc == 1


def test_main_read_allowed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "doc.md"
    f.touch()
    from sdd.guards.scope import main
    rc = main(["read", str(f)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["allowed"] is True
    assert rc == 0


def test_main_read_denied_glob(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    from sdd.guards.scope import main
    rc = main(["read", "src/*.py"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["allowed"] is False
    assert rc == 1


def test_main_with_inputs_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    f = src / "module.py"
    f.touch()
    from sdd.guards.scope import main
    rc = main(["read", str(f), "--inputs", str(f)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["allowed"] is True
    assert rc == 0


def test_main_task_flag_accepted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "readme.md"
    f.touch()
    from sdd.guards.scope import main
    rc = main(["read", str(f), "--task", "T-6101"])
    assert rc == 0
