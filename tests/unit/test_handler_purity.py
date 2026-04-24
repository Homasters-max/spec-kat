"""AST-based handler purity + guard statelessness contract tests.

Invariants: I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1,
            I-GUARD-STATELESS-1, I-PIPELINE-SINGLE-SOURCE-1, I-STATE-ACCESS-LAYER-1
Spec ref: Spec_v15 §2 CI grep-rules; §9 checks; T-1520 acceptance
"""
from __future__ import annotations

import ast
from pathlib import Path


# ---------------------------------------------------------------------------
# Handler purity — constants
# ---------------------------------------------------------------------------

# Files whitelisted from handle() purity checks (I-PHASE16-MIGRATION-STRICT-1).
# Exactly these 2 files are allowed to call EventStore inside their handle() bodies.
_PURITY_WHITELIST: frozenset[str] = frozenset({
    "validate_invariants.py",
    "report_error.py",
})

# (text_pattern, invariant_id) — forbidden inside handle() method bodies
_PURITY_FORBIDDEN: list[tuple[str, str]] = [
    ("EventStore",        "I-CI-PURITY-1/I-KERNEL-WRITE-1"),
    ("rebuild_state",     "I-CI-PURITY-2/I-KERNEL-PROJECT-1"),
    ("get_current_state", "I-STATE-ACCESS-LAYER-1"),
    (".handle(",          "I-CI-PURITY-3/I-HANDLER-PURE-1"),
]


def _collect_handle_violations(source: str) -> list[str]:
    """Return violation messages for forbidden patterns inside handle() method bodies."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    violations: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node.name == "handle":
                end = getattr(node, "end_lineno", node.lineno)
                for lineno in range(node.lineno, end + 1):
                    if lineno > len(lines):
                        break
                    line = lines[lineno - 1]
                    for pattern, inv in _PURITY_FORBIDDEN:
                        if pattern in line:
                            violations.append(
                                f"  line {lineno} [{inv}]: {line.strip()}"
                            )
            self.generic_visit(node)

    _Visitor().visit(tree)
    return violations


# ---------------------------------------------------------------------------
# I-CI-PURITY-1/2/3 + I-STATE-ACCESS-LAYER-1
# ---------------------------------------------------------------------------


def test_handle_method_purity() -> None:
    """handle() bodies must not call EventStore.append, rebuild_state, get_current_state,
    or nested .handle(). (I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-STATE-ACCESS-LAYER-1)
    """
    commands_path = Path("src/sdd/commands").absolute()
    assert commands_path.exists(), f"src/sdd/commands not found: {commands_path}"

    all_violations: list[str] = []
    files_checked = 0

    for py_file in sorted(commands_path.glob("*.py")):
        if py_file.name in _PURITY_WHITELIST:
            continue
        files_checked += 1
        violations = _collect_handle_violations(py_file.read_text(encoding="utf-8"))
        for v in violations:
            all_violations.append(f"{py_file.name}:{v}")

    assert files_checked > 0, "No Python files checked — src/sdd/commands structure unexpected"
    assert all_violations == [], (
        "Handler purity violations found (I-CI-PURITY-1..3, I-STATE-ACCESS-LAYER-1):\n"
        + "\n".join(all_violations)
    )


# ---------------------------------------------------------------------------
# I-PHASE16-MIGRATION-STRICT-1
# ---------------------------------------------------------------------------


def test_ci_purity_whitelist_count_at_most_two() -> None:
    """Whitelist must contain exactly 2 files — no scope creep (I-PHASE16-MIGRATION-STRICT-1).

    Exactly validate_invariants.py and report_error.py are whitelisted.
    Adding a third file requires a new Spec amendment.
    """
    assert len(_PURITY_WHITELIST) == 2, (
        f"Expected exactly 2 whitelisted files (I-PHASE16-MIGRATION-STRICT-1), "
        f"got {len(_PURITY_WHITELIST)}: {sorted(_PURITY_WHITELIST)}"
    )
    assert "validate_invariants.py" in _PURITY_WHITELIST
    assert "report_error.py" in _PURITY_WHITELIST


# ---------------------------------------------------------------------------
# Amendment A-14: ActivatePhaseHandler idempotency via command_id UNIQUE, not _check_idempotent
# ---------------------------------------------------------------------------


def test_activate_phase_handler_has_no_check_idempotent() -> None:
    """ActivatePhaseHandler.handle() must not call _check_idempotent() (Amendment A-14).

    Idempotency for activate-phase is enforced via command_id UNIQUE constraint in
    EventStore, not by the handler itself (I-HANDLER-BATCH-PURE-1).
    """
    activate_path = Path("src/sdd/commands/activate_phase.py").absolute()
    source = activate_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    violations: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if node.name == "ActivatePhaseHandler":
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef) and item.name == "handle":
                        end = getattr(item, "end_lineno", item.lineno)
                        for lineno in range(item.lineno, end + 1):
                            if lineno > len(lines):
                                break
                            if "_check_idempotent" in lines[lineno - 1]:
                                violations.append(
                                    f"line {lineno}: {lines[lineno - 1].strip()}"
                                )
            self.generic_visit(node)

    _Visitor().visit(tree)
    assert violations == [], (
        "ActivatePhaseHandler.handle() calls _check_idempotent (violates A-14): "
        + str(violations)
    )


# ---------------------------------------------------------------------------
# I-GUARD-STATELESS-1: domain guards must not perform forbidden I/O
# ---------------------------------------------------------------------------

# Forbidden text patterns in domain guard source files
_GUARD_IO_FORBIDDEN: list[tuple[str, str]] = [
    ("EventStore(",     "I-GUARD-STATELESS-1: EventStore constructor in domain guard"),
    ("write_state(",    "I-GUARD-STATELESS-1: write_state in domain guard"),
    ("rebuild_state(",  "I-GUARD-STATELESS-1: rebuild_state in domain guard"),
]


def test_domain_guard_stateless_no_forbidden_io() -> None:
    """Domain guard files must not use EventStore, write_state, or rebuild_state.

    Guards receive a pre-built GuardContext; they must be pure functions over it.
    Scan scope: src/sdd/domain/guards/ (pure domain layer).
    I-GUARD-STATELESS-1 (extended, Phase 15 Architecture Remediation).
    """
    domain_guards_path = Path("src/sdd/domain/guards").absolute()
    assert domain_guards_path.exists(), f"src/sdd/domain/guards not found: {domain_guards_path}"

    all_violations: list[str] = []
    files_checked = 0

    for py_file in sorted(domain_guards_path.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        lines = source.splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # skip comments
            for pattern, msg in _GUARD_IO_FORBIDDEN:
                if pattern in line:
                    all_violations.append(f"  {py_file.name}:{lineno} [{msg}]: {stripped}")

    assert files_checked > 0, "No domain guard files checked — structure unexpected"
    assert all_violations == [], (
        "Domain guard I/O violations (I-GUARD-STATELESS-1):\n" + "\n".join(all_violations)
    )


def test_domain_guard_no_get_current_state() -> None:
    """Domain guard functions must not call get_current_state() (I-GUARD-STATELESS-1).

    Guards receive a pre-built GuardContext from execute_command STAGE BUILD_CONTEXT.
    Calling get_current_state() inside a guard function would bypass this design contract.
    AST check on src/sdd/domain/guards/ (excluding pipeline.py which is the orchestrator).
    """
    domain_guards_path = Path("src/sdd/domain/guards").absolute()
    assert domain_guards_path.exists()

    all_violations: list[str] = []
    files_checked = 0

    for py_file in sorted(domain_guards_path.glob("*.py")):
        if py_file.name in ("__init__.py", "pipeline.py"):
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "get_current_state"
                    ):
                        all_violations.append(
                            f"  {py_file.name}:{child.lineno}: "
                            f"get_current_state() in guard function {node.name!r}"
                        )
                self.generic_visit(node)

        _Visitor().visit(tree)

    assert files_checked > 0, "No domain guard files checked"
    assert all_violations == [], (
        "Guard statelessness violations (I-GUARD-STATELESS-1):\n" + "\n".join(all_violations)
    )


# ---------------------------------------------------------------------------
# I-PIPELINE-SINGLE-SOURCE-1: authoritative definition pre-check
# ---------------------------------------------------------------------------


def test_pipeline_canonical_definition_exists() -> None:
    """run_guard_pipeline is canonically defined in sdd.domain.guards.pipeline.

    Pre-check for I-PIPELINE-SINGLE-SOURCE-1 (T-1522 confirms adapter deletion).
    Verifies the authoritative source exists and has the correct function.
    """
    domain_pipeline = Path("src/sdd/domain/guards/pipeline.py").absolute()
    assert domain_pipeline.exists(), (
        "src/sdd/domain/guards/pipeline.py must exist (I-PIPELINE-SINGLE-SOURCE-1)"
    )
    source = domain_pipeline.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fn_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]
    assert "run_guard_pipeline" in fn_names, (
        "run_guard_pipeline must be defined in sdd.domain.guards.pipeline "
        "(I-PIPELINE-SINGLE-SOURCE-1)"
    )


def test_commands_registry_uses_domain_pipeline_directly() -> None:
    """execute_command in registry.py must import run_guard_pipeline from the domain layer.

    Verifies registry.py does not go through the guards adapter layer (I-PIPELINE-SINGLE-SOURCE-1).
    """
    registry_path = Path("src/sdd/commands/registry.py").absolute()
    source = registry_path.read_text(encoding="utf-8")
    assert "from sdd.domain.guards.pipeline import run_guard_pipeline" in source, (
        "registry.py must import run_guard_pipeline from sdd.domain.guards.pipeline, "
        "not from the adapter (I-PIPELINE-SINGLE-SOURCE-1)"
    )
