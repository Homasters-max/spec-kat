"""Import direction tests for Phase 51 (T-5120).

Verifies R-IMPORT-DIRECTION:
  - sdd.context_kernel  ↛  sdd.graph_navigation
  - sdd.policy          ↛  sdd.context_kernel
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "src"


def _collect_imports(package_dir: Path) -> dict[str, list[str]]:
    """Return {relative_path: [imported_module, ...]} for every .py in package_dir."""
    result: dict[str, list[str]] = {}
    for py_file in sorted(package_dir.rglob("*.py")):
        rel = str(py_file.relative_to(_REPO_ROOT))
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
        result[rel] = modules
    return result


# ---------------------------------------------------------------------------
# R-IMPORT-DIRECTION: context_kernel ↛ graph_navigation
# ---------------------------------------------------------------------------

def test_import_direction_phase51_context_kernel_no_graph_navigation() -> None:
    """sdd.context_kernel MUST NOT import from sdd.graph_navigation."""
    package_dir = _SRC / "sdd" / "context_kernel"
    violations: list[str] = []
    for rel_path, imports in _collect_imports(package_dir).items():
        for mod in imports:
            if mod == "sdd.graph_navigation" or mod.startswith("sdd.graph_navigation."):
                violations.append(f"{rel_path}: imports {mod!r}")
    assert not violations, (
        "sdd.context_kernel imports sdd.graph_navigation (R-IMPORT-DIRECTION violated):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# R-IMPORT-DIRECTION: policy ↛ context_kernel
# ---------------------------------------------------------------------------

def test_import_direction_phase51_policy_no_context_kernel() -> None:
    """sdd.policy MUST NOT import from sdd.context_kernel."""
    package_dir = _SRC / "sdd" / "policy"
    violations: list[str] = []
    for rel_path, imports in _collect_imports(package_dir).items():
        for mod in imports:
            if mod == "sdd.context_kernel" or mod.startswith("sdd.context_kernel."):
                violations.append(f"{rel_path}: imports {mod!r}")
    assert not violations, (
        "sdd.policy imports sdd.context_kernel (R-IMPORT-DIRECTION violated):\n"
        + "\n".join(violations)
    )
