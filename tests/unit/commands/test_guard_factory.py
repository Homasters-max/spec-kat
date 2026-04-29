"""Tests for CommandSpec.build_guards and _default_build_guards.

Invariants: I-CMD-GUARD-FACTORY-1, I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from sdd.commands._base import NoOpHandler
from sdd.commands.registry import (
    CommandSpec,
    ProjectionType,
    _default_build_guards,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(
    *,
    requires_active_phase: bool = True,
    apply_task_guard: bool = True,
    uses_task_id: bool = False,
    guard_factory=None,
) -> CommandSpec:
    return CommandSpec(
        name="test-cmd",
        handler_class=NoOpHandler,
        actor="any",
        action="test_action",
        projection=ProjectionType.NONE,
        uses_task_id=uses_task_id,
        event_schema=(),
        preconditions=(),
        postconditions=(),
        requires_active_phase=requires_active_phase,
        apply_task_guard=apply_task_guard,
        guard_factory=guard_factory,
    )


class _Cmd:
    """Minimal command stub."""
    def __init__(self, task_id: str | None = None) -> None:
        self.task_id = task_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_guards_default_delegates_to_default_factory() -> None:
    """When guard_factory is None, build_guards delegates to _default_build_guards(spec, cmd).

    I-CMD-GUARD-FACTORY-2.
    """
    spec = _make_spec(guard_factory=None)
    cmd = _Cmd()
    sentinel: list = [object()]

    with patch(
        "sdd.commands.registry._default_build_guards",
        return_value=sentinel,
    ) as mock_default:
        result = spec.build_guards(cmd)

    mock_default.assert_called_once_with(spec, cmd)
    assert result is sentinel


def test_build_guards_custom_delegates_to_guard_factory() -> None:
    """When guard_factory is set, build_guards calls guard_factory(cmd) and returns its result.

    I-CMD-GUARD-FACTORY-2.
    """
    custom_guards = [object(), object()]
    factory = MagicMock(return_value=custom_guards)

    spec = _make_spec(guard_factory=factory)
    cmd = _Cmd()
    result = spec.build_guards(cmd)

    factory.assert_called_once_with(cmd)
    assert result is custom_guards


def test_default_factory_reads_spec_flags() -> None:
    """_default_build_guards respects requires_active_phase and apply_task_guard flags.

    requires_active_phase=False → make_phase_guard not called, no phase guard in list.
    apply_task_guard=False → make_task_guard not called, no task guard in list.
    I-CMD-GUARD-FACTORY-3.
    """
    _PHASE_SENTINEL = object()
    _TASK_SENTINEL = object()
    _NORM_SENTINEL = object()

    with (
        patch("sdd.commands.registry.make_phase_guard", return_value=_PHASE_SENTINEL) as mock_phase,
        patch("sdd.commands.registry.make_task_guard", return_value=_TASK_SENTINEL) as mock_task,
        patch("sdd.commands.registry.make_norm_guard", return_value=_NORM_SENTINEL),
        patch("sdd.commands.registry.DependencyGuard"),
    ):
        # requires_active_phase=False → make_phase_guard must not be called
        spec_no_phase = _make_spec(requires_active_phase=False, uses_task_id=False)
        guards_no_phase = _default_build_guards(spec_no_phase, _Cmd())

        mock_phase.assert_not_called()
        assert _PHASE_SENTINEL not in guards_no_phase

        # apply_task_guard=False with task_id → make_task_guard must not be called
        spec_no_task_guard = _make_spec(
            requires_active_phase=False,
            apply_task_guard=False,
            uses_task_id=True,
        )
        guards_no_task = _default_build_guards(spec_no_task_guard, _Cmd(task_id="T-0001"))

        mock_task.assert_not_called()
        assert _TASK_SENTINEL not in guards_no_task


# ---------------------------------------------------------------------------
# I-CMD-GUARD-FACTORY-1: execute_command delegates to spec.build_guards(cmd)
# ---------------------------------------------------------------------------


def test_execute_command_calls_build_guards() -> None:
    """execute_command calls spec.build_guards(cmd) exactly once (I-CMD-GUARD-FACTORY-1).

    Guard assembly must be delegated to spec.build_guards — execute_command must not
    inline guard construction logic that bypasses the factory contract.
    """
    from sdd.commands.registry import execute_command

    spec = MagicMock()
    spec.uses_task_id = False
    spec.idempotent = True
    spec.build_guards.return_value = []
    spec.handler_class.return_value.handle.return_value = []

    cmd = _Cmd()

    fake_state = MagicMock()
    fake_state.phase_current = 1
    fake_state.phase_status = "ACTIVE"
    fake_state.state_hash = "a" * 64

    # guard_result.outcome is a MagicMock — `is GuardOutcome.DENY` is False → ALLOW path
    fake_guard_result = MagicMock()

    with (
        patch("sdd.commands.registry.compute_command_id", return_value="deadbeef"),
        patch("sdd.commands.registry.compute_trace_id", return_value="cafebabe"),
        patch("sdd.commands.registry.get_current_state", return_value=fake_state),
        patch("sdd.commands.registry.EventLog"),
        patch("sdd.commands.registry.open_event_log"),
        patch("sdd.commands.registry.load_catalog"),
        patch("sdd.commands.registry._run_domain_pipeline", return_value=(fake_guard_result, [])),
        patch("sdd.commands.registry.GuardContext"),
    ):
        execute_command(spec, cmd, db_path="postgresql://localhost/fake")

    spec.build_guards.assert_called_once_with(cmd)


# ---------------------------------------------------------------------------
# I-CMD-GUARD-FACTORY-4: _switch_phase_guard_factory returns full guard list
# ---------------------------------------------------------------------------


def test_custom_guard_factory_receives_full_guard_list() -> None:
    """_switch_phase_guard_factory returns exactly [switch_guard, norm_guard].

    BC-41-A: make_phase_guard removed — PG-3 (phase.status == ACTIVE) blocked navigation
    from COMPLETE phases, making switch-phase unusable after phase completion.
    I-CMD-GUARD-FACTORY-4.
    """
    from sdd.commands.switch_phase import _switch_phase_guard_factory

    _SWITCH_SENTINEL = object()
    _NORM_SENTINEL = object()

    cmd = MagicMock()
    cmd.phase_id = 7

    with (
        patch(
            "sdd.commands.switch_phase.make_switch_phase_guard",
            return_value=_SWITCH_SENTINEL,
        ),
        patch(
            "sdd.commands.switch_phase.make_norm_guard",
            return_value=_NORM_SENTINEL,
        ),
    ):
        guards = _switch_phase_guard_factory(cmd)

    assert len(guards) == 2, f"Expected 2 guards, got {len(guards)}"
    assert guards[0] is _SWITCH_SENTINEL
    assert guards[1] is _NORM_SENTINEL


def test_switch_phase_guard_factory_extracts_phase_id() -> None:
    """_switch_phase_guard_factory passes cmd.phase_id to make_switch_phase_guard.

    I-CMD-GUARD-FACTORY-4.
    """
    from sdd.commands.switch_phase import _switch_phase_guard_factory

    cmd = MagicMock()
    cmd.phase_id = 5

    with (
        patch("sdd.domain.guards.phase_guard.make_phase_guard"),
        patch(
            "sdd.commands.switch_phase.make_switch_phase_guard",
        ) as mock_switch,
        patch("sdd.commands.switch_phase.make_norm_guard"),
    ):
        _switch_phase_guard_factory(cmd)

    mock_switch.assert_called_once_with(5)


def test_registry_no_conditional_on_spec_name() -> None:
    """execute_command contains no Compare node with spec.name (I-CMD-GUARD-FACTORY-1).

    Guard routing via spec.name inside execute_command violates the guard factory contract:
    all specialisation must live in spec.build_guards / guard_factory, not in the kernel.
    """
    registry_path = Path("src/sdd/commands/registry.py").absolute()
    source = registry_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    execute_func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute_command":
            execute_func = node
            break

    assert execute_func is not None, "execute_command not found in registry.py"

    violations: list[str] = []
    for node in ast.walk(execute_func):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id == "spec"
            and left.attr == "name"
        ):
            violations.append(f"line {node.lineno}: spec.name in Compare")

    assert violations == [], (
        "I-CMD-GUARD-FACTORY-1: spec.name conditionals found in execute_command "
        "(guard routing must use spec.build_guards, not inline name checks):\n"
        + "\n".join(violations)
    )
