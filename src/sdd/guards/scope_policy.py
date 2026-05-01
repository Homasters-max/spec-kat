"""Scope Rule Resolution Policy — I-RRL-1, I-RRL-2, I-RRL-3, I-SCOPE-STRICT-1.

Resolves conflicts between SENAR norms and task-declared inputs.
Override is allowed ONLY for norms explicitly listed in allowed_overrides.
When session_id is given, loads GraphSessionState and uses allowed_files (I-SCOPE-STRICT-1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sdd.graph_navigation.session_state import GraphSessionState
from sdd.infra.paths import get_sdd_root


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

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
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


def load_graph_session(session_id: str) -> GraphSessionState | None:
    """Load GraphSessionState from runtime sessions dir. Returns None if not found."""
    session_file = get_sdd_root() / "runtime" / "sessions" / f"{session_id}.json"
    if not session_file.exists():
        return None
    data = json.loads(session_file.read_text())
    return GraphSessionState(
        session_id=data["session_id"],
        phase_id=data["phase_id"],
        allowed_files=frozenset(data.get("allowed_files", [])),
        trace_path=data.get("trace_path", []),
    )


def resolve_scope(
    norm_result: ScopeDecision,
    declared_inputs: list[str],
    allowed_overrides: frozenset[str],
    session_id: str | None = None,
) -> ScopeDecision:
    """Apply resolution policy. Never silently allows — override MUST emit metadata (I-RRL-3).

    When session_id is given, loads GraphSessionState and uses allowed_files (I-SCOPE-STRICT-1).
    Session not found → DENY (I-RRL-2: same inputs → same decision).
    """
    if norm_result.allowed:
        return norm_result
    if norm_result.norm_id is None:
        return norm_result
    if not is_override_allowed(norm_result.norm_id, allowed_overrides):
        return norm_result

    # I-SCOPE-STRICT-1: session_id → use graph session's allowed_files
    if session_id is not None:
        state = load_graph_session(session_id)
        if state is None:
            return norm_result  # session not found → DENY
        if not is_declared_input(norm_result.file_path, list(state.allowed_files)):
            return norm_result
        return replace(
            norm_result,
            allowed=True,
            reason=f"TASK_INPUT_OVERRIDE({norm_result.norm_id}): file in session allowed_files (I-SCOPE-STRICT-1)",
            override=OverrideMetadata(
                type="TASK_INPUT_OVERRIDE",
                overrides_norm=norm_result.norm_id,
                policy="explicit_override_only",
            ),
        )

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
