"""Registry contract + kernel flow AST tests.

Invariants: I-REGISTRY-COMPLETE-1, I-READ-ONLY-EXCEPTION-1, I-READ-PATH-1, I-2, I-3,
            I-EVENT-FORMAT-1, I-KERNEL-FLOW-1, I-OPTLOCK-REPLAY-1, I-REPLAY-PATH-1
Spec ref: Spec_v15 §2; §9 checks; T-1520 acceptance
"""
from __future__ import annotations

import ast
from pathlib import Path


# ---------------------------------------------------------------------------
# I-REGISTRY-COMPLETE-1 / I-READ-PATH-1 / I-READ-ONLY-EXCEPTION-1 / I-2
# ---------------------------------------------------------------------------

_EXPECTED_REGISTRY_KEYS: frozenset[str] = frozenset({
    "complete",
    "validate",
    "check-dod",
    "activate-phase",
    "sync-state",
    "record-decision",
    "switch-phase",
    "invalidate-event",
    "record-session",
    "approve-spec",
    "amend-plan",
})

_READ_ONLY_COMMANDS: frozenset[str] = frozenset({
    "validate-config",
    "show-state",
    "show-task",
    "show-spec",
    "show-plan",
    "query-events",
})


def test_registry_write_commands_complete() -> None:
    """REGISTRY contains exactly the 6 write commands (I-REGISTRY-COMPLETE-1, I-READ-PATH-1).

    Read-only commands (validate-config, show-*, query-events) pass through
    execute_command flow — they are excluded from the registry (I-READ-ONLY-EXCEPTION-1).
    """
    from sdd.commands.registry import REGISTRY
    assert set(REGISTRY.keys()) == _EXPECTED_REGISTRY_KEYS, (
        f"REGISTRY mismatch (I-REGISTRY-COMPLETE-1).\n"
        f"Expected: {sorted(_EXPECTED_REGISTRY_KEYS)}\n"
        f"Got:      {sorted(REGISTRY.keys())}"
    )


def test_validate_config_is_not_in_registry() -> None:
    """validate-config is excluded from REGISTRY (I-READ-ONLY-EXCEPTION-1, I-2).

    validate_project_config is a read-only operation and must not pass through
    execute_command or the guard pipeline.
    """
    from sdd.commands.registry import REGISTRY
    assert "validate-config" not in REGISTRY, (
        "validate-config must not be in REGISTRY (I-READ-ONLY-EXCEPTION-1, I-2)"
    )


def test_show_commands_not_in_registry() -> None:
    """show-* commands are absent from REGISTRY (I-READ-PATH-1).

    All show-* and query-events commands are read-only and must not trigger
    guard execution or event persistence.
    """
    from sdd.commands.registry import REGISTRY
    for cmd in _READ_ONLY_COMMANDS:
        assert cmd not in REGISTRY, (
            f"{cmd!r} must not be in REGISTRY (I-READ-PATH-1)"
        )


# ---------------------------------------------------------------------------
# I-OPTLOCK-REPLAY-1: head_seq captured before get_current_state in execute_command
# ---------------------------------------------------------------------------


def test_optlock_replay_ordering() -> None:
    """In execute_command, head_seq = EventStore.max_seq() must precede get_current_state().

    I-OPTLOCK-REPLAY-1: head_seq and state are independent calls; head_seq is the
    optimistic lock token captured BEFORE replay to cover the full window to commit.
    """
    registry_path = Path("src/sdd/commands/registry.py").absolute()
    source = registry_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    head_seq_lineno: int | None = None
    get_current_state_lineno: int | None = None

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            nonlocal head_seq_lineno, get_current_state_lineno
            if node.name != "execute_command":
                self.generic_visit(node)
                return
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                # Detect EventStore(...).max_seq() — attribute call chain
                if (
                    isinstance(child.func, ast.Attribute)
                    and child.func.attr == "max_seq"
                ):
                    if head_seq_lineno is None or child.lineno < head_seq_lineno:
                        head_seq_lineno = child.lineno
                # Detect get_current_state(...)
                if (
                    isinstance(child.func, ast.Name)
                    and child.func.id == "get_current_state"
                ):
                    if get_current_state_lineno is None or child.lineno < get_current_state_lineno:
                        get_current_state_lineno = child.lineno
            self.generic_visit(node)

    _Visitor().visit(tree)

    assert head_seq_lineno is not None, (
        "execute_command must capture head_seq via EventStore.max_seq() (I-OPTLOCK-REPLAY-1)"
    )
    assert get_current_state_lineno is not None, (
        "execute_command must call get_current_state() (I-OPTLOCK-REPLAY-1)"
    )
    assert head_seq_lineno < get_current_state_lineno, (
        f"I-OPTLOCK-REPLAY-1: head_seq (line {head_seq_lineno}) must be captured "
        f"BEFORE get_current_state() (line {get_current_state_lineno}) in execute_command"
    )


# ---------------------------------------------------------------------------
# I-EVENT-FORMAT-1: no reduce(sdd_replay(...)) combined pattern in commands/
# ---------------------------------------------------------------------------

# activate_plan.py is exempt: I-CLI-REG-1 (internal-only, no user-facing CLI entry)
_EXEMPT_EVENT_FORMAT: frozenset[str] = frozenset({"activate_plan.py"})


def test_event_format_no_sdd_replay_direct_in_reduce() -> None:
    """No sdd_replay() used as direct argument to reduce() in command handlers.

    I-EVENT-FORMAT-1 (strict AST): detect pattern reduce(sdd_replay(...)).
    State reconstruction must go through get_current_state() (I-REPLAY-PATH-1).
    Exempt: activate_plan.py (I-CLI-REG-1 internal-only).
    """
    commands_path = Path("src/sdd/commands").absolute()
    assert commands_path.exists()

    violations: list[str] = []
    files_checked = 0

    for py_file in sorted(commands_path.glob("*.py")):
        if py_file.name in _EXEMPT_EVENT_FORMAT:
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                # Detect: reduce(sdd_replay(...)) or reduce(sdd_replay(..., ...))
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "reduce"
                    and node.args
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "sdd_replay"
                ):
                    violations.append(
                        f"  {py_file.name}:{node.lineno}: reduce(sdd_replay(...))"
                    )
                # Detect: .reduce(sdd_replay(...)) — method call form
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "reduce"
                    and node.args
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "sdd_replay"
                ):
                    violations.append(
                        f"  {py_file.name}:{node.lineno}: .reduce(sdd_replay(...))"
                    )
                self.generic_visit(node)

        _Visitor().visit(tree)

    assert files_checked > 0, "No command files checked"
    assert violations == [], (
        "I-EVENT-FORMAT-1 violations — reduce(sdd_replay(...)) in command handlers:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# I-3: no active CommandRunner callers outside sdd_run.py + __init__.py
# ---------------------------------------------------------------------------

# sdd_run.py defines CommandRunner (deprecated — deleted in T-1522)
# commands/__init__.py re-exports it for backwards compatibility
_EXEMPT_COMMANDRUNNER: frozenset[str] = frozenset({"sdd_run.py", "__init__.py"})


def test_no_commandrunner_active_callers() -> None:
    """No production code in src/sdd/ instantiates or calls CommandRunner (I-3).

    CommandRunner (sdd_run.py) is deprecated and will be deleted in T-1522.
    Pre-check: no active callers exist outside sdd_run.py and __init__.py.
    """
    sdd_root = Path("src/sdd").absolute()
    assert sdd_root.exists()

    violations: list[str] = []
    files_checked = 0

    for py_file in sorted(sdd_root.rglob("*.py")):
        if py_file.name in _EXEMPT_COMMANDRUNNER:
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                # Detect CommandRunner(...) instantiation
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "CommandRunner"
                ):
                    violations.append(
                        f"  {py_file.relative_to(sdd_root)}:{node.lineno}: "
                        f"CommandRunner(...) call"
                    )
                self.generic_visit(node)

        _Visitor().visit(tree)

    assert files_checked > 0, "No files checked"
    assert violations == [], (
        "I-3: CommandRunner active callers found (will block T-1522):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# I-KERNEL-FLOW-1: no EventStore constructor+append chain outside whitelist
# ---------------------------------------------------------------------------

# validate_invariants.py and report_error.py are whitelisted (I-PHASE16-MIGRATION-STRICT-1)
_KERNEL_FLOW_WHITELIST: frozenset[str] = frozenset({
    "validate_invariants.py",
    "report_error.py",
})


def test_kernel_flow_no_eventstore_append_bypass() -> None:
    """No EventStore(path).append(...) constructor chain outside execute_command.

    I-KERNEL-FLOW-1: execute_command (commands/registry.py) is the sole path for
    event persistence. Other components must not construct EventStore and call append.
    Whitelist: validate_invariants.py, report_error.py (I-PHASE16-MIGRATION-STRICT-1).
    Scan: src/sdd/ excluding registry.py (where execute_command lives).
    """
    sdd_root = Path("src/sdd").absolute()
    registry_py = Path("src/sdd/commands/registry.py").absolute()

    violations: list[str] = []
    files_checked = 0

    for py_file in sorted(sdd_root.rglob("*.py")):
        if py_file == registry_py:
            continue
        if py_file.name in _KERNEL_FLOW_WHITELIST:
            continue
        if py_file.name == "__init__.py":
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                # Detect EventStore(...).append(...) — constructor + method chain
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Name)
                    and node.func.value.func.id == "EventStore"
                ):
                    violations.append(
                        f"  {py_file.relative_to(sdd_root)}:{node.lineno}: "
                        f"EventStore(...).append(...)"
                    )
                self.generic_visit(node)

        _Visitor().visit(tree)

    assert files_checked > 0, "No files checked"
    assert violations == [], (
        "I-KERNEL-FLOW-1: EventStore(...).append() bypass detected:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# I-REPLAY-PATH-1: no EventReducer().reduce() with sdd_replay argument in production paths
# ---------------------------------------------------------------------------

# activate_plan.py: I-CLI-REG-1 exempt (internal-only, not user-facing)
# sdd_run.py: deprecated adapter (deleted in T-1522); uses _fetch_events_for_reduce pattern
_EXEMPT_REPLAY_PATH: frozenset[str] = frozenset({
    "activate_plan.py",
    "sdd_run.py",
})


def test_replay_path_no_direct_reduce_bypass() -> None:
    """No EventReducer().reduce(sdd_replay(...)) production bypass (I-REPLAY-PATH-1).

    Production state reconstruction MUST use get_current_state() (infra/projections.py).
    Direct EventReducer().reduce(sdd_replay(...)) pattern bypasses projections layer.
    Scan: src/sdd/ excluding projections.py (authoritative), activate_plan.py (exempt),
    sdd_run.py (deprecated).
    """
    sdd_root = Path("src/sdd").absolute()
    projections_py = Path("src/sdd/infra/projections.py").absolute()

    violations: list[str] = []
    files_checked = 0

    for py_file in sorted(sdd_root.rglob("*.py")):
        if py_file == projections_py:
            continue
        if py_file.name in _EXEMPT_REPLAY_PATH:
            continue
        if py_file.name == "__init__.py":
            continue
        files_checked += 1
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Visitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                # Detect sdd_replay() as direct argument to reduce(...)
                # Pattern A: reduce(sdd_replay(...)) — function call
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "reduce"
                    and node.args
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "sdd_replay"
                ):
                    violations.append(
                        f"  {py_file.relative_to(sdd_root)}:{node.lineno}: "
                        f"reduce(sdd_replay(...))"
                    )
                # Pattern B: .reduce(sdd_replay(...)) — method call
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "reduce"
                    and node.args
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "sdd_replay"
                ):
                    violations.append(
                        f"  {py_file.relative_to(sdd_root)}:{node.lineno}: "
                        f".reduce(sdd_replay(...))"
                    )
                self.generic_visit(node)

        _Visitor().visit(tree)

    assert files_checked > 0, "No files checked"
    assert violations == [], (
        "I-REPLAY-PATH-1: direct reduce(sdd_replay(...)) bypass in production paths:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# I-CMD-ACTION-1: every REGISTRY action declared in norm catalog
# ---------------------------------------------------------------------------

def test_registry_action_strings_are_unique() -> None:
    """All CommandSpec.action values in REGISTRY are unique (I-CMD-ACTION-1).

    Duplicate action strings would make norm catalog authorization ambiguous —
    two commands sharing one action string are indistinguishable to NormGuard.
    """
    from sdd.commands.registry import REGISTRY

    actions = [spec.action for spec in REGISTRY.values()]
    duplicates = {a for a in actions if actions.count(a) > 1}
    assert not duplicates, (
        f"I-CMD-ACTION-1: duplicate action strings in REGISTRY: {sorted(duplicates)}"
    )


def test_registry_actions_covered_by_norm_catalog() -> None:
    """Every CommandSpec.action in REGISTRY must appear in norm_catalog.yaml (I-CMD-ACTION-1).

    Catches the failure mode where a new command is added to REGISTRY but the
    corresponding action is not declared in norm_catalog.yaml — which causes
    validate_registry_actions() to panic at CLI startup.
    """
    from sdd.commands.registry import REGISTRY
    from sdd.domain.norms.catalog import load_catalog
    from sdd.infra.paths import norm_catalog_file

    registry_actions = frozenset(s.action for s in REGISTRY.values())
    catalog = load_catalog(str(norm_catalog_file()))
    missing = registry_actions - catalog.known_actions
    assert not missing, (
        f"I-CMD-ACTION-1: REGISTRY action(s) not declared in norm_catalog.yaml: "
        f"{sorted(missing)}\n"
        f"Add an allowed_actions or forbidden_actions entry for each missing action."
    )
