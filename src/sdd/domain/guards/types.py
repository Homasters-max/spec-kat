"""Guard type contract — Spec_v5 §4.5, I-GUARD-1."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from sdd.core.events import DomainEvent
    from sdd.domain.guards.context import GuardContext, GuardResult

Guard = Callable[["GuardContext"], "tuple[GuardResult, list[DomainEvent]]"]
