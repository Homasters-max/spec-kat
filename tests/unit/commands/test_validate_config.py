"""Tests for validate_project_config — Spec_v4 §9 Verification row 9.

Invariants: I-READ-ONLY-EXCEPTION-1, I-2
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdd.commands.validate_config import (
    ConfigValidationError,
    validate_project_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_profile(path: Path, data: dict) -> str:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


_VALID_PROFILE = {
    "stack": {"language": "python"},
    "build": {"commands": {"lint": "ruff check src/", "test": "pytest tests/"}},
    "testing": {"coverage_threshold": 80},
}


# ---------------------------------------------------------------------------
# test_valid_config_returns_none
# ---------------------------------------------------------------------------

def test_valid_config_returns_none(tmp_path):
    profile = _write_profile(tmp_path / "project_profile.yaml", _VALID_PROFILE)
    result = validate_project_config(phase_id=4, config_path=profile)
    assert result is None


# ---------------------------------------------------------------------------
# test_missing_required_field_raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field,profile_override", [
    (
        "stack.language",
        {
            "stack": {},
            "build": {"commands": {"test": "pytest"}},
            "testing": {"coverage_threshold": 80},
        },
    ),
    (
        "stack.language",
        {
            "build": {"commands": {"test": "pytest"}},
            "testing": {"coverage_threshold": 80},
        },
    ),
])
def test_missing_required_field_raises(tmp_path, missing_field, profile_override):
    profile = _write_profile(tmp_path / "project_profile.yaml", profile_override)
    with pytest.raises(ConfigValidationError, match=missing_field):
        validate_project_config(phase_id=4, config_path=profile)


def test_wrong_type_raises(tmp_path):
    bad_profile = {
        "stack": {"language": 42},  # must be str
        "build": {"commands": {"test": "pytest"}},
        "testing": {"coverage_threshold": 80},
    }
    profile = _write_profile(tmp_path / "project_profile.yaml", bad_profile)
    with pytest.raises(ConfigValidationError, match="stack.language"):
        validate_project_config(phase_id=4, config_path=profile)


# ---------------------------------------------------------------------------
# test_validate_config_idempotent
# ---------------------------------------------------------------------------

def test_validate_config_idempotent(tmp_path):
    profile = _write_profile(tmp_path / "project_profile.yaml", _VALID_PROFILE)
    result1 = validate_project_config(phase_id=4, config_path=profile)
    result2 = validate_project_config(phase_id=4, config_path=profile)
    assert result1 is None
    assert result2 is None
