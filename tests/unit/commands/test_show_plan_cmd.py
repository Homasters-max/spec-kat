"""Unit tests for sdd.commands.show_plan."""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def reset_sdd_root_after():
    yield
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()


def test_show_plan_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)
    (tmp_path / "plans" / "Plan_v61.md").write_text("# Plan v61\n")

    from sdd.commands.show_plan import show_plan
    show_plan(61)
    out = capsys.readouterr().out
    assert "Plan v61" in out


def test_show_plan_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)

    from sdd.commands.show_plan import show_plan
    with pytest.raises(SystemExit) as exc:
        show_plan(99)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    data = json.loads(err)
    assert data["error_type"] == "PlanNotFound"
