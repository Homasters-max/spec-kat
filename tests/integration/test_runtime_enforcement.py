"""BC-VR-4: Runtime Enforcement — context-based traps.

Tests verify that kernel operations enforce the execution context contract
established by BC-VR-0 (execution_context.py):
  - Inside kernel_context("execute_command") → allowed
  - Outside → KernelContextError

Invariants: I-VR-STABLE-5, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1,
            I-STATE-ACCESS-LAYER-1, I-HANDLER-PURE-1
"""
from __future__ import annotations

import pytest

from sdd.core.execution_context import (
    KernelContextError,
    assert_in_kernel,
    current_execution_context,
    kernel_context,
)
from sdd.infra.event_log import EventLog


# ---------------------------------------------------------------------------
# Test 1: execute_and_project inside kernel_context → assert_in_kernel PASS
# ---------------------------------------------------------------------------


def test_assert_in_kernel_pass_inside_execute_command_context() -> None:
    """test 1: kernel_context("execute_command") → assert_in_kernel does not raise.

    Verifies that BC-VR-0 correctly identifies code running inside execute_command.
    execute_and_project wraps execute_command in kernel_context("execute_command"),
    so any assert_in_kernel call during execution passes (I-KERNEL-WRITE-1).
    """
    with kernel_context("execute_command"):
        assert current_execution_context() == "execute_command"
        assert_in_kernel("EventLog.append")
        assert_in_kernel("rebuild_state")
        assert_in_kernel("get_current_state")


def test_assert_in_kernel_fails_outside_any_context() -> None:
    """assert_in_kernel raises KernelContextError when no kernel_context is active."""
    assert current_execution_context() is None
    with pytest.raises(KernelContextError, match="outside execute_command"):
        assert_in_kernel("EventLog.append")


def test_assert_in_kernel_fails_in_wrong_context() -> None:
    """assert_in_kernel raises when ctx != "execute_command" (wrong context name)."""
    with kernel_context("project_all"):
        with pytest.raises(KernelContextError, match="outside execute_command"):
            assert_in_kernel("EventLog.append")


def test_kernel_context_resets_after_exit() -> None:
    """kernel_context token-based reset: no context leaks across test boundaries."""
    with kernel_context("execute_command"):
        assert current_execution_context() == "execute_command"
    assert current_execution_context() is None


# ---------------------------------------------------------------------------
# Test 2: EventLog.append outside context → KernelContextError (I-KERNEL-WRITE-1)
# ---------------------------------------------------------------------------


def test_event_store_append_trap_fires_outside_context(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test 2: EventLog.append enforcement trap raises KernelContextError outside context.

    Installs the I-KERNEL-WRITE-1 enforcement guard: EventLog.append MUST only
    be called from within execute_command (I-VR-STABLE-5).

    The trap fires before the empty-list short-circuit inside EventLog.append,
    so no real DB write occurs — only the enforcement check is exercised.
    """
    _original_append = EventLog.append

    def _enforced_append(
        self: EventLog,
        events: list,
        source: str,
        **kwargs: object,
    ) -> None:
        assert_in_kernel("EventLog.append")
        return _original_append(self, events, source, **kwargs)

    monkeypatch.setattr(EventLog, "append", _enforced_append)

    store = EventLog(tmp_db_path)
    with pytest.raises(KernelContextError, match="EventLog.append"):
        store.append([], "test_source")


def test_event_store_append_trap_passes_inside_context(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-KERNEL-WRITE-1 positive path: enforcement guard allows append inside kernel_context."""
    _original_append = EventLog.append

    def _enforced_append(
        self: EventLog,
        events: list,
        source: str,
        **kwargs: object,
    ) -> None:
        assert_in_kernel("EventLog.append")
        return _original_append(self, events, source, **kwargs)

    monkeypatch.setattr(EventLog, "append", _enforced_append)

    store = EventLog(tmp_db_path)
    with kernel_context("execute_command"):
        store.append([], "test_source")  # empty list → no-op; assert_in_kernel passes


def test_handler_pure_violation_caught_by_append_trap(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I-HANDLER-PURE-1: handler side-effects (EventLog calls) are caught by the trap.

    If a handler's handle() method were to call EventLog.append directly, the
    kernel_context trap would raise KernelContextError because handle() is called
    INSIDE the kernel_context, but any attempt to bypass the kernel and call
    EventLog.append from outside execute_command is caught.
    """
    _original_append = EventLog.append

    def _enforced_append(
        self: EventLog,
        events: list,
        source: str,
        **kwargs: object,
    ) -> None:
        assert_in_kernel("EventLog.append")
        return _original_append(self, events, source, **kwargs)

    monkeypatch.setattr(EventLog, "append", _enforced_append)

    store = EventLog(tmp_db_path)
    # Simulates a handler calling EventLog.append outside kernel_context — forbidden
    with pytest.raises(KernelContextError, match="EventLog.append"):
        store.append([], "handler_side_effect_violation")


# ---------------------------------------------------------------------------
# Test 3: rebuild_state outside project_all → trap (I-KERNEL-PROJECT-1)
# ---------------------------------------------------------------------------


def test_rebuild_state_trap_fires_outside_context(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test 3: rebuild_state enforcement trap raises KernelContextError outside context.

    I-KERNEL-PROJECT-1: rebuild_state MUST only be called from within project_all
    in registry.py. Direct calls from outside the kernel pipeline are violations.
    """
    import sdd.infra.projections as _proj

    _original_rebuild = _proj.rebuild_state

    def _enforced_rebuild(
        db_path: str | None = None,
        state_path: str | None = None,
        mode: object = None,
    ) -> None:
        assert_in_kernel("rebuild_state")
        from sdd.infra.projections import RebuildMode
        return _original_rebuild(
            db_path=db_path,
            state_path=state_path,
            mode=mode if mode is not None else RebuildMode.STRICT,
        )

    monkeypatch.setattr(_proj, "rebuild_state", _enforced_rebuild)

    with pytest.raises(KernelContextError, match="rebuild_state"):
        _proj.rebuild_state(db_path=tmp_db_path)


def test_rebuild_state_trap_passes_inside_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-KERNEL-PROJECT-1 positive path: enforcement allows rebuild_state inside kernel_context."""
    import sdd.infra.projections as _proj

    captured: list[bool] = []

    def _enforced_rebuild(
        db_path: str | None = None,
        state_path: str | None = None,
        mode: object = None,
    ) -> None:
        assert_in_kernel("rebuild_state")
        captured.append(True)  # execution reaches here only when context is valid

    monkeypatch.setattr(_proj, "rebuild_state", _enforced_rebuild)

    with kernel_context("execute_command"):
        _proj.rebuild_state(db_path="/unused")  # assert_in_kernel passes

    assert captured == [True], "enforced rebuild_state must execute inside kernel_context"


# ---------------------------------------------------------------------------
# Test 4: get_current_state outside guards/projections → trap (I-STATE-ACCESS-LAYER-1)
# ---------------------------------------------------------------------------


def test_get_current_state_trap_fires_outside_context(
    tmp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test 4: get_current_state enforcement trap raises KernelContextError outside context.

    I-STATE-ACCESS-LAYER-1: get_current_state is a kernel API function. Within the
    kernel pipeline it is always called from BUILD_CONTEXT stage (inside kernel_context).
    Direct calls bypassing execute_command are violations.
    """
    import sdd.infra.projections as _proj

    _original_get = _proj.get_current_state

    def _enforced_get(db_path: str) -> object:
        assert_in_kernel("get_current_state")
        return _original_get(db_path)

    monkeypatch.setattr(_proj, "get_current_state", _enforced_get)

    with pytest.raises(KernelContextError, match="get_current_state"):
        _proj.get_current_state(tmp_db_path)


def test_get_current_state_trap_passes_inside_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I-STATE-ACCESS-LAYER-1 positive path: enforcement allows get_current_state inside context."""
    import sdd.infra.projections as _proj

    captured: list[bool] = []

    def _enforced_get(db_path: str) -> object:
        assert_in_kernel("get_current_state")
        captured.append(True)
        return None  # not testing the actual state derivation here

    monkeypatch.setattr(_proj, "get_current_state", _enforced_get)

    with kernel_context("execute_command"):
        _proj.get_current_state("/unused")

    assert captured == [True], "enforced get_current_state must execute inside kernel_context"
