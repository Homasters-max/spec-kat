"""Tests for core/payloads.py — registry, factory, and structural AST checks.

Invariants covered: I-CMD-ENV-1, I-CMD-ENV-2, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5
Spec ref: Spec_v9 §2 BC-CMD-ENV, BC-CMD-TEST, §9 Verification row 1
"""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from sdd.core.payloads import COMMAND_REGISTRY, build_command
from sdd.core.types import Command


# ---------------------------------------------------------------------------
# test_build_command_returns_command
# ---------------------------------------------------------------------------

def test_build_command_returns_command() -> None:
    """build_command() returns a Command with correct envelope fields."""
    cmd = build_command(
        "CompleteTask",
        task_id="T-901",
        phase_id=9,
        taskset_path=".sdd/tasks/TaskSet_v9.md",
        state_path=".sdd/runtime/State_index.yaml",
    )
    assert isinstance(cmd, Command)
    assert cmd.command_type == "CompleteTask"
    assert cmd.command_id  # non-empty UUID string
    assert cmd.payload["task_id"] == "T-901"
    assert cmd.payload["phase_id"] == 9


# ---------------------------------------------------------------------------
# test_build_command_missing_field  (I-CMD-ENV-3)
# ---------------------------------------------------------------------------

def test_build_command_missing_field() -> None:
    """build_command() raises TypeError when required payload fields are missing (I-CMD-ENV-3)."""
    with pytest.raises(TypeError):
        # CompleteTask requires task_id, phase_id, taskset_path, state_path
        build_command("CompleteTask", task_id="T-901")


# ---------------------------------------------------------------------------
# test_build_command_unknown_type  (I-CMD-ENV-4)
# ---------------------------------------------------------------------------

def test_build_command_unknown_type() -> None:
    """build_command() raises KeyError for an unregistered command_type (I-CMD-ENV-4)."""
    with pytest.raises(KeyError):
        build_command("NoSuchCommand", foo="bar")


# ---------------------------------------------------------------------------
# test_payload_dataclasses_frozen  (I-CMD-ENV-5)
# ---------------------------------------------------------------------------

def test_payload_dataclasses_frozen() -> None:
    """All payload dataclasses in COMMAND_REGISTRY are frozen=True (I-CMD-ENV-5)."""
    for name, cls in COMMAND_REGISTRY.items():
        assert dataclasses.is_dataclass(cls), f"{name}: {cls.__name__} is not a dataclass"
        assert cls.__dataclass_params__.frozen, (  # type: ignore[attr-defined]
            f"{name}: payload class {cls.__name__} must be frozen=True"
        )


# ---------------------------------------------------------------------------
# test_registry_coverage  (I-CMD-ENV-2)
# ---------------------------------------------------------------------------

def test_registry_coverage() -> None:
    """No COMMAND_REGISTRY key has more than one build_command() call-site in commands/ (I-CMD-ENV-2).

    Scans src/sdd/commands/*.py via AST and asserts each registered type appears
    at most once — duplicate call-sites signal conflicting usage.
    """
    commands_dir = Path("src/sdd/commands")

    # map command_type string → list of files that call build_command("TYPE", ...)
    usages: dict[str, list[str]] = {key: [] for key in COMMAND_REGISTRY}

    for py_file in sorted(commands_dir.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_command"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                key = node.args[0].value
                if key in usages:
                    usages[key].append(py_file.name)

    duplicates = {k: v for k, v in usages.items() if len(v) > 1}
    assert not duplicates, (
        "COMMAND_REGISTRY keys used by more than one build_command() call-site:\n"
        + "\n".join(f"  {k}: {v}" for k, v in duplicates.items())
    )


# ---------------------------------------------------------------------------
# test_no_command_subclasses  (I-CMD-ENV-1)
# ---------------------------------------------------------------------------

def test_no_command_subclasses() -> None:
    """src/sdd/commands/ contains no class *Command(Command) subclass definitions (I-CMD-ENV-1)."""
    commands_dir = Path("src/sdd/commands")
    violations: list[str] = []

    for py_file in sorted(commands_dir.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Command":
                        violations.append(
                            f"{py_file.name}: class {node.name}(Command)"
                        )

    assert violations == [], (
        "Found Command subclasses (must be removed per I-CMD-ENV-1):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
