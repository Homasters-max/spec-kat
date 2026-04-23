"""Tests for ValidateConfigHandler — Spec_v4 §9 Verification row 9.

Invariants: I-CMD-1
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from sdd.commands.validate_config import (
    ConfigValidationError,
    ValidateConfigCommand,
    ValidateConfigHandler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _command(config_path: str, phase_id: int = 4) -> ValidateConfigCommand:
    return ValidateConfigCommand(
        command_id=str(uuid.uuid4()),
        command_type="ValidateConfig",
        payload={},
        phase_id=phase_id,
        config_path=config_path,
    )


def _write_profile(path: Path, data: dict) -> str:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


_VALID_PROFILE = {
    "stack": {"language": "python"},
    "build": {"commands": {"lint": "ruff check src/", "test": "pytest tests/"}},
    "testing": {"coverage_threshold": 80},
}


@pytest.fixture
def handler(tmp_path):
    return ValidateConfigHandler(db_path=str(tmp_path / "test.duckdb"))


# ---------------------------------------------------------------------------
# test_valid_config_returns_empty
# ---------------------------------------------------------------------------

def test_valid_config_returns_empty(handler, tmp_path):
    profile = _write_profile(tmp_path / "project_profile.yaml", _VALID_PROFILE)
    result = handler.handle(_command(profile))
    assert result == []


# ---------------------------------------------------------------------------
# test_missing_required_field_raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field,profile_override", [
    (
        # stack.language has no base default — always missing if not in profile
        "stack.language",
        {
            "stack": {},
            "build": {"commands": {"test": "pytest"}},
            "testing": {"coverage_threshold": 80},
        },
    ),
    (
        # stack.language absent when stack key itself is missing
        "stack.language",
        {
            "build": {"commands": {"test": "pytest"}},
            "testing": {"coverage_threshold": 80},
        },
    ),
])
def test_missing_required_field_raises(handler, tmp_path, missing_field, profile_override):
    profile = _write_profile(tmp_path / "project_profile.yaml", profile_override)
    with pytest.raises(ConfigValidationError, match=missing_field):
        handler.handle(_command(profile))


def test_wrong_type_raises(handler, tmp_path):
    bad_profile = {
        "stack": {"language": 42},  # must be str
        "build": {"commands": {"test": "pytest"}},
        "testing": {"coverage_threshold": 80},
    }
    profile = _write_profile(tmp_path / "project_profile.yaml", bad_profile)
    with pytest.raises(ConfigValidationError, match="stack.language"):
        handler.handle(_command(profile))


# ---------------------------------------------------------------------------
# test_validate_config_idempotent
# ---------------------------------------------------------------------------

def test_validate_config_idempotent(handler, tmp_path):
    profile = _write_profile(tmp_path / "project_profile.yaml", _VALID_PROFILE)
    cmd = _command(profile)
    result1 = handler.handle(cmd)
    result2 = handler.handle(cmd)
    assert result1 == []
    assert result2 == []
