"""3-level YAML config loader: base defaults ← project_profile ← phase override."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Base SDD defaults (lowest priority layer)
_BASE_DEFAULTS: dict[str, Any] = {
    "stack": {
        "python_version": "3.12",
        "linter": "ruff",
        "formatter": "ruff",
        "typecheck": "mypy",
    },
    "build": {
        "commands": {
            "lint": "ruff check src/",
            "typecheck": "mypy src/sdd/",
            "test": "pytest tests/",
        }
    },
    "testing": {
        "coverage_threshold": 80,
    },
    "code_rules": {
        "forbidden_patterns": [],
    },
    "scope": {
        "forbidden_dirs": [],
    },
    "domain": {
        "glossary": {},
    },
    "norms": {
        "custom": [],
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base; override wins on scalar conflicts."""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    project_profile_path: str | Path,
    phase_n_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load merged config from 3-level override chain.

    Priority (highest wins): phase_N.yaml > project_profile.yaml > base defaults.
    If phase_n_path is None or the file does not exist, falls back silently.
    """
    profile_path = Path(project_profile_path)
    with profile_path.open("r", encoding="utf-8") as fh:
        project_profile: dict[str, Any] = yaml.safe_load(fh) or {}

    merged = _deep_merge(_BASE_DEFAULTS, project_profile)

    if phase_n_path is not None:
        phase_path = Path(phase_n_path)
        if phase_path.exists():
            with phase_path.open("r", encoding="utf-8") as fh:
                phase_override: dict[str, Any] = yaml.safe_load(fh) or {}
            merged = _deep_merge(merged, phase_override)

    return merged
