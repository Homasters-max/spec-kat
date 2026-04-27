"""Command dataclass + CommandHandler Protocol — Spec_v1 §4.2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from sdd.core.events import DomainEvent


class CommandHandler(Protocol):
    def handle(self, command: Command) -> list[DomainEvent]: ...


@dataclass(frozen=True)
class Command:
    command_id: str
    command_type: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class ApproveSpecCommand:
    phase_id: int
    actor: str = "human"


@dataclass(frozen=True)
class AmendPlanCommand:
    phase_id: int
    reason: str
    actor: str = "human"
