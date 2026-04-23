"""Integration tests for SDD_HOME path isolation.

Invariants covered: I-PATH-1, I-PATH-2, I-PATH-3, I-EXEC-ISOL-1
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC_SDD_INFRA = Path(__file__).parent.parent.parent / "src" / "sdd" / "infra"


def test_sdd_home_redirects_all_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """I-PATH-1: SDD_HOME env var redirects every path helper to the given root."""
    import sdd.infra.paths as paths_mod

    monkeypatch.setenv("SDD_HOME", str(tmp_path))
    monkeypatch.setattr(paths_mod, "_sdd_root", None)

    from sdd.infra.paths import (
        audit_log_file,
        config_file,
        event_store_file,
        norm_catalog_file,
        phases_index_file,
        plan_file,
        plans_dir,
        reports_dir,
        specs_dir,
        specs_draft_dir,
        state_file,
        taskset_file,
        tasks_dir,
        templates_dir,
    )

    root = tmp_path.resolve()

    assert event_store_file().is_relative_to(root), f"{event_store_file()} not under {root}"
    assert state_file().is_relative_to(root)
    assert audit_log_file().is_relative_to(root)
    assert norm_catalog_file().is_relative_to(root)
    assert config_file().is_relative_to(root)
    assert phases_index_file().is_relative_to(root)
    assert specs_dir().is_relative_to(root)
    assert specs_draft_dir().is_relative_to(root)
    assert plans_dir().is_relative_to(root)
    assert tasks_dir().is_relative_to(root)
    assert reports_dir().is_relative_to(root)
    assert templates_dir().is_relative_to(root)
    assert plan_file(14).is_relative_to(root)
    assert taskset_file(14).is_relative_to(root)


def test_no_hardcoded_sdd_paths_in_src() -> None:
    """I-PATH-2: No src/sdd/infra module (except paths.py) may hardcode a '.sdd/' literal."""
    paths_py = _SRC_SDD_INFRA / "paths.py"
    violations: list[str] = []

    for py_file in _SRC_SDD_INFRA.rglob("*.py"):
        if py_file == paths_py:
            continue
        source = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '".sdd/' in line or "'.sdd/" in line:
                rel = py_file.relative_to(_SRC_SDD_INFRA.parent.parent.parent)
                violations.append(f"{rel}:{lineno}: {stripped}")

    assert not violations, (
        "Hardcoded '.sdd/' path fragments found outside paths.py:\n"
        + "\n".join(violations)
    )


def test_paths_module_no_sdd_imports() -> None:
    """I-PATH-3: paths.py must not import from any sdd.* module (leaf module, no circular deps)."""
    paths_py = _SRC_SDD_INFRA / "paths.py"
    source = paths_py.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(paths_py))

    sdd_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("sdd"):
                    sdd_imports.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("sdd"):
                names = ", ".join(a.name for a in node.names)
                sdd_imports.append(f"line {node.lineno}: from {module} import {names}")

    assert not sdd_imports, (
        "paths.py must not import from sdd.*:\n" + "\n".join(sdd_imports)
    )
