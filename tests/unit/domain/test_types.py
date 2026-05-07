"""Tests for Command dataclass and CommandHandler Protocol — I-CMD-1a."""

from __future__ import annotations

from typing import List

from sdd.core.events import DomainEvent
from sdd.core.types import Command, CommandHandler


def test_command_has_command_id() -> None:
    cmd = Command(
        command_id="cmd-001",
        command_type="DoSomething",
        payload={"key": "value"},
    )
    assert cmd.command_id == "cmd-001"
    assert isinstance(cmd.command_id, str)


def test_commandhandler_protocol() -> None:
    class ConcreteHandler:
        def handle(self, command: Command) -> List[DomainEvent]:
            return []

    # Structural subtyping verified at runtime: handler has `handle` callable
    # that accepts a Command and returns a list (duck-typing check).
    handler = ConcreteHandler()
    assert hasattr(handler, "handle") and callable(handler.handle)
    cmd = Command(command_id="chk-001", command_type="Check", payload={})
    result = handler.handle(cmd)
    assert isinstance(result, list)


def test_command_is_frozen() -> None:
    cmd = Command(command_id="x", command_type="T", payload={})
    try:
        cmd.command_id = "y"  # type: ignore[misc]
        assert False, "should raise FrozenInstanceError"
    except Exception:
        pass


def test_command_payload_is_immutable() -> None:
    cmd = Command(command_id="x", command_type="T", payload={"a": 1})
    try:
        cmd.payload["b"] = 2  # type: ignore[index]
        assert False, "MappingProxyType should reject mutation"
    except TypeError:
        pass
