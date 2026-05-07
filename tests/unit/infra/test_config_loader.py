from __future__ import annotations

import pathlib

import pytest

from sdd.infra.config_loader import load_config


def _write(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_3level_override(tmp_path: pathlib.Path) -> None:
    """Phase overrides project which overrides base defaults (I-PK-4)."""
    profile = tmp_path / "project_profile.yaml"
    phase = tmp_path / "phase_1.yaml"

    _write(profile, "testing:\n  coverage_threshold: 70\n")
    _write(phase, "testing:\n  coverage_threshold: 90\n")

    cfg = load_config(profile, phase)

    # Phase wins over project and base
    assert cfg["testing"]["coverage_threshold"] == 90
    # Base default still present where not overridden
    assert cfg["stack"]["linter"] == "ruff"


def test_missing_phase_config_falls_back(tmp_path: pathlib.Path) -> None:
    """No exception when phase_N.yaml is absent; project profile is used."""
    profile = tmp_path / "project_profile.yaml"
    _write(profile, "testing:\n  coverage_threshold: 55\n")

    cfg = load_config(profile, tmp_path / "nonexistent_phase.yaml")

    assert cfg["testing"]["coverage_threshold"] == 55
    # Base defaults still present
    assert cfg["build"]["commands"]["lint"] == "ruff check src/"
