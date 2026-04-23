"""BC-GUARDS public API — Spec_v5 §2.3 (Phase 3 guards removed; canonical: domain/guards/)."""

from sdd.guards.runner import (
    EmitFn,
    GuardContext,
    GuardOutcome,
    GuardResult,
    run_guard_pipeline,
)

__all__ = [
    "EmitFn",
    "GuardContext",
    "GuardOutcome",
    "GuardResult",
    "run_guard_pipeline",
]
