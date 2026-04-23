"""Kernel Contract Regression Suite — T-1005.

Verifies I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1.
Frozen interfaces declared in CLAUDE.md §0.15.
"""
from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Frozen module registry
# ---------------------------------------------------------------------------

FROZEN_MODULES = [
    "sdd.core.types",
    "sdd.core.events",
    "sdd.infra.event_log",
    "sdd.infra.event_store",
    "sdd.domain.state.reducer",
    "sdd.domain.guards.context",
]

# Source file paths relative to project root (for mypy invocation)
FROZEN_MODULE_FILES = [
    "src/sdd/core/types.py",
    "src/sdd/core/events.py",
    "src/sdd/infra/event_log.py",
    "src/sdd/infra/event_store.py",
    "src/sdd/domain/state/reducer.py",
    "src/sdd/domain/guards/context.py",
]

# ---------------------------------------------------------------------------
# FROZEN_SIGNATURES — populated from live inspect.signature() at write time (T-1005).
#
# Format: list of (param_name, annotation_str) per callable.
# Annotation strings are normalized: str(annotation).strip("'\"") — strips outer
# quotes that appear when from __future__ import annotations is active.
# Default values are intentionally excluded (db_path default contains an absolute
# path that is environment-specific and not a breaking-change indicator).
# ---------------------------------------------------------------------------

FROZEN_SIGNATURES: dict[str, list[tuple[str, str]]] = {
    "Command.__init__": [
        ("command_id", "str"),
        ("command_type", "str"),
        ("payload", "Mapping[str, Any]"),
    ],
    "CommandHandler.handle": [
        ("self", ""),
        ("command", "Command"),
    ],
    "DomainEvent.__init__": [
        ("event_type", "str"),
        ("event_id", "str"),
        ("appended_at", "int"),
        ("level", "str"),
        ("event_source", "str"),
        ("caused_by_meta_seq", "int | None"),
    ],
    "classify_event_level": [
        ("event_type", "str"),
    ],
    "sdd_append": [
        ("event_type", "str"),
        ("payload", "dict[str, Any]"),
        ("db_path", "str"),
        ("level", "str | None"),
        ("event_source", "str"),
        ("caused_by_meta_seq", "int | None"),
    ],
    "sdd_append_batch": [
        ("events", "list[EventInput]"),
        ("db_path", "str"),
    ],
    "sdd_replay": [
        ("after_seq", "int | None"),
        ("db_path", "str"),
        ("level", "str"),
        ("source", "str"),
        ("include_expired", "bool"),
    ],
    "EventStore.append": [
        ("self", ""),
        ("events", "list[DomainEvent]"),
        ("source", "str"),
    ],
    "reduce": [
        ("events", "list[dict[str, object]]"),
        ("strict_mode", "bool"),
    ],
    "GuardContext.__init__": [
        ("state", "SDDState"),
        ("phase", "PhaseState"),
        ("task", "Task | None"),
        ("norms", "NormCatalog"),
        ("event_log", "EventLogView"),
        ("task_graph", "DAG"),
        ("now", "str"),
    ],
    "GuardResult.__init__": [
        ("outcome", "GuardOutcome"),
        ("guard_name", "str"),
        ("message", "str"),
        ("norm_id", "str | None"),
        ("task_id", "str | None"),
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _extract_params(obj: Any) -> list[tuple[str, str]]:
    """Return (name, annotation_str) pairs for all parameters of obj."""
    sig = inspect.signature(obj)
    result = []
    for name, param in sig.parameters.items():
        ann = param.annotation
        ann_str = "" if ann is inspect.Parameter.empty else str(ann).strip("'\"")
        result.append((name, ann_str))
    return result


def _mypy_available() -> bool:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "mypy", "--version"],
            capture_output=True,
            check=False,
        )
        return r.returncode == 0
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_frozen_modules_mypy_strict() -> None:
    """I-REG-ENV-1: run mypy --strict on each frozen module; skip if mypy absent."""
    if not _mypy_available():
        pytest.skip("mypy not installed — I-REG-ENV-1")

    failed: list[str] = []
    for rel_path in FROZEN_MODULE_FILES:
        abs_path = str(_PROJECT_ROOT / rel_path)
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--strict", abs_path],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
        )
        if result.returncode != 0:
            failed.append(f"{rel_path}:\n{result.stdout}{result.stderr}")

    assert not failed, "mypy --strict failed on frozen modules:\n\n" + "\n\n".join(failed)


def test_frozen_modules_import_smoke() -> None:
    """I-KERNEL-REG: all frozen modules import cleanly."""
    for module_name in FROZEN_MODULES:
        mod = importlib.import_module(module_name)
        assert mod is not None, f"Failed to import {module_name}"


def test_frozen_modules_signatures() -> None:
    """I-KERNEL-SIG-1: frozen interface signatures have not changed."""
    from sdd.core.types import Command, CommandHandler
    from sdd.core.events import DomainEvent, classify_event_level
    from sdd.infra.event_log import sdd_append, sdd_append_batch, sdd_replay
    from sdd.infra.event_store import EventStore
    from sdd.domain.state.reducer import reduce
    from sdd.domain.guards.context import GuardContext, GuardResult

    targets: dict[str, Any] = {
        "Command.__init__": Command,
        "CommandHandler.handle": CommandHandler.handle,
        "DomainEvent.__init__": DomainEvent,
        "classify_event_level": classify_event_level,
        "sdd_append": sdd_append,
        "sdd_append_batch": sdd_append_batch,
        "sdd_replay": sdd_replay,
        "EventStore.append": EventStore.append,
        "reduce": reduce,
        "GuardContext.__init__": GuardContext,
        "GuardResult.__init__": GuardResult,
    }

    mismatches: list[str] = []
    for key, obj in targets.items():
        current = _extract_params(obj)
        frozen = FROZEN_SIGNATURES[key]
        if current != frozen:
            mismatches.append(
                f"{key}:\n  frozen:  {frozen}\n  current: {current}"
            )

    assert not mismatches, (
        "Frozen interface signatures have changed (I-KERNEL-SIG-1). "
        "Update CLAUDE.md §0.15 and open a new spec before merging:\n\n"
        + "\n\n".join(mismatches)
    )
