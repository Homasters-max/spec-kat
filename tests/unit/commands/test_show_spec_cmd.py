"""Unit tests for sdd.commands.show_spec."""
from __future__ import annotations

import pytest


_PHASES_INDEX = """\
# Phases Index

| Phase | Status | Spec |
|---|---|---|
| 61 | ACTIVE | .sdd/specs/Spec_v61_GraphEnforcement.md |
| 55 | COMPLETE | .sdd/specs/Spec_v55_GraphGuidedImplement.md |
"""


@pytest.fixture(autouse=True)
def reset_sdd_root_after():
    yield
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()


# ── _resolve_spec_from_phases_index ──────────────────────────────────────────


def test_resolve_spec_found(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)
    (tmp_path / "plans" / "Phases_index.md").write_text(_PHASES_INDEX)

    from sdd.commands.show_spec import _resolve_spec_from_phases_index
    result = _resolve_spec_from_phases_index(61)
    assert result == ".sdd/specs/Spec_v61_GraphEnforcement.md"


def test_resolve_spec_second_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)
    (tmp_path / "plans" / "Phases_index.md").write_text(_PHASES_INDEX)

    from sdd.commands.show_spec import _resolve_spec_from_phases_index
    result = _resolve_spec_from_phases_index(55)
    assert result == ".sdd/specs/Spec_v55_GraphGuidedImplement.md"


def test_resolve_spec_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)
    (tmp_path / "plans" / "Phases_index.md").write_text(_PHASES_INDEX)

    from sdd.commands.show_spec import _resolve_spec_from_phases_index
    result = _resolve_spec_from_phases_index(99)
    assert result is None


def test_resolve_spec_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "plans").mkdir(parents=True)

    from sdd.commands.show_spec import _resolve_spec_from_phases_index
    result = _resolve_spec_from_phases_index(61)
    assert result is None


# ── show_spec: no candidates ──────────────────────────────────────────────────


def test_show_spec_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "specs").mkdir(parents=True)

    from sdd.commands.show_spec import show_spec
    rc = show_spec(99)
    assert rc == 1


# ── show_spec: single candidate, no phases_index ─────────────────────────────


def test_show_spec_single_candidate_fallback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "Spec_v61_GraphEnforcement.md").write_text("# Spec v61\n")

    from sdd.commands.show_spec import show_spec
    rc = show_spec(61)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Spec v61" in out


# ── show_spec: ambiguous candidates ──────────────────────────────────────────


def test_show_spec_ambiguous(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "Spec_v61_Alpha.md").write_text("# A")
    (specs_dir / "Spec_v61_Beta.md").write_text("# B")

    from sdd.commands.show_spec import show_spec
    rc = show_spec(61)
    assert rc == 1


# ── show_spec: with phases_index ──────────────────────────────────────────────


# ── main() ───────────────────────────────────────────────────────────────────


def test_main_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "specs").mkdir(parents=True)
    (tmp_path / "specs" / "Spec_v61_X.md").write_text("# Spec 61\n")

    from sdd.commands.show_spec import main
    rc = main(["--phase", "61"])
    assert rc == 0
    assert "Spec 61" in capsys.readouterr().out


def test_main_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    (tmp_path / "specs").mkdir(parents=True)

    from sdd.commands.show_spec import main
    rc = main(["--phase", "99"])
    assert rc == 1


def test_main_help():
    from sdd.commands.show_spec import main
    rc = main(["--help"])
    assert rc == 0


def test_show_spec_with_phases_index(tmp_path, monkeypatch, capsys):
    # Structure mirrors production: SDD_HOME = .sdd/, project root = parent
    sdd_root = tmp_path / ".sdd"
    monkeypatch.setenv("SDD_HOME", str(sdd_root))
    from sdd.infra.paths import reset_sdd_root
    reset_sdd_root()

    specs_dir = sdd_root / "specs"
    specs_dir.mkdir(parents=True)
    plans_dir = sdd_root / "plans"
    plans_dir.mkdir(parents=True)

    spec_content = "# Spec v61 via index\n"
    (specs_dir / "Spec_v61_GraphEnforcement.md").write_text(spec_content)
    (plans_dir / "Phases_index.md").write_text(
        "| 61 | ACTIVE | .sdd/specs/Spec_v61_GraphEnforcement.md |\n"
    )

    from sdd.commands.show_spec import show_spec
    rc = show_spec(61)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Spec v61 via index" in out
