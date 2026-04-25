"""Scope Rule Resolution Policy — I-RRL-1, I-RRL-2, I-RRL-3.

Resolves conflicts between SENAR norms and task-declared inputs.
Override is allowed ONLY for norms explicitly listed in allowed_overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class OverrideMetadata:
    type: str           # "TASK_INPUT_OVERRIDE"
    overrides_norm: str # e.g. "NORM-SCOPE-001"
    policy: str         # "explicit_override_only"


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    norm_id: str | None
    reason: str
    operation: str
    file_path: str
    override: OverrideMetadata | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "allowed": self.allowed,
            "reason": self.reason,
            "norm_id": self.norm_id,
            "operation": self.operation,
            "file_path": self.file_path,
        }
        if self.override is not None:
            d["override"] = {
                "type": self.override.type,
                "overrides_norm": self.override.overrides_norm,
                "policy": self.override.policy,
            }
        return d


def is_declared_input(file_path: str, declared_inputs: list[str]) -> bool:
    """Pure check: is resolved file_path in resolved declared_inputs?"""
    resolved = Path(file_path).resolve()
    return resolved in [Path(p).resolve() for p in declared_inputs]


def is_override_allowed(norm_id: str, allowed_overrides: frozenset[str]) -> bool:
    """Pure check: is this norm explicitly listed as overridable?"""
    return norm_id in allowed_overrides


def resolve_scope(
    norm_result: ScopeDecision,
    declared_inputs: list[str],
    allowed_overrides: frozenset[str],
) -> ScopeDecision:
    """Apply resolution policy. Never silently allows — override MUST emit metadata (I-RRL-3)."""
    if norm_result.allowed:
        return norm_result
    if norm_result.norm_id is None:
        return norm_result
    if not is_override_allowed(norm_result.norm_id, allowed_overrides):
        return norm_result
    if not is_declared_input(norm_result.file_path, declared_inputs):
        return norm_result
    return replace(
        norm_result,
        allowed=True,
        reason=f"TASK_INPUT_OVERRIDE({norm_result.norm_id}): file in declared task inputs",
        override=OverrideMetadata(
            type="TASK_INPUT_OVERRIDE",
            overrides_norm=norm_result.norm_id,
            policy="explicit_override_only",
        ),
    )
