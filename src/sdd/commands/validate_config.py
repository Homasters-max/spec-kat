"""validate_project_config — plain config validation function (I-READ-ONLY-EXCEPTION-1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sdd.core.errors import SDDError
from sdd.infra.config_loader import load_config


class ConfigValidationError(SDDError):
    """Raised when project_profile.yaml or phase_N.yaml fails schema validation."""


# (dotted field path, expected type(s))
_REQUIRED_FIELDS: list[tuple[list[str], type | tuple[type, ...]]] = [
    (["stack", "language"], str),
    (["build", "commands"], dict),
    (["testing", "coverage_threshold"], (int, float)),
]


def _get_nested(config: dict[str, Any], path: list[str]) -> Any:
    node: Any = config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(".".join(path))
        node = node[key]
    return node


def validate_project_config(phase_id: int, config_path: str) -> None:
    """Validate project_profile.yaml + phases/phase_N.yaml structure.

    Raises ConfigValidationError on schema violation. Returns None on success.
    """
    profile_path = Path(config_path)
    phase_n_path = profile_path.parent / "phases" / f"phase_{phase_id}.yaml"

    try:
        config = load_config(
            config_path,
            phase_n_path if phase_n_path.exists() else None,
        )
    except Exception as exc:
        raise ConfigValidationError(f"config load failed: {exc}") from exc

    for field_parts, expected_type in _REQUIRED_FIELDS:
        field_path = ".".join(field_parts)
        try:
            value = _get_nested(config, field_parts)
        except KeyError:
            raise ConfigValidationError(f"missing required field: {field_path}")
        if not isinstance(value, expected_type):
            type_name = (
                expected_type.__name__
                if isinstance(expected_type, type)
                else " | ".join(t.__name__ for t in expected_type)
            )
            raise ConfigValidationError(
                f"field {field_path!r} must be {type_name}, got {type(value).__name__}"
            )
