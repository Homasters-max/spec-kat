"""ValidateConfigHandler — Spec_v4 §4.8.

Invariants: I-CMD-1
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import SDDError
from sdd.core.events import DomainEvent
from sdd.infra.config_loader import load_config


class ConfigValidationError(SDDError):
    """Raised when project_profile.yaml or phase_N.yaml fails schema validation."""


@dataclass(frozen=True)
class ValidateConfigCommand:
    command_id:  str
    command_type: str
    payload:     Mapping[str, Any]
    phase_id:    int
    config_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


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


class ValidateConfigHandler(CommandHandlerBase):
    """Validate project_profile.yaml + phases/phase_N.yaml structure.
    Pure validation — emits nothing on success.
    Raises ConfigValidationError on schema violation.
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ValidateConfigCommand) -> list[DomainEvent]:
        """
        Steps:
          1. _check_idempotent → return [] if already done
          2. load_config(command.config_path) with schema validation
          3. Check required fields: stack.language, build.commands, testing.coverage_threshold
          4. Check phases/phase_N.yaml if present
          5. Raise ConfigValidationError with field path on any violation
          6. Return [] on success (no events emitted)

        Idempotency note: this handler emits no events — _check_idempotent() will always
        return False (nothing to find in EventLog). Its idempotency is behavioral: the
        same config → same validation outcome. Re-running is safe by design; the handler
        is a pure read-only check with no side effects on success. The _check_idempotent
        call is retained for structural consistency with all other handlers only.
        """
        if self._check_idempotent(command):
            return []

        profile_path = Path(command.config_path)
        phase_n_path = profile_path.parent / "phases" / f"phase_{command.phase_id}.yaml"

        try:
            config = load_config(
                command.config_path,
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

        return []
