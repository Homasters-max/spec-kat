"""ActivatePlanCommand + ActivatePlanHandler — Spec_v5 §4.1, §4.3.

Invariants: I-ACT-1, I-CMD-1, I-DOMAIN-1
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, cast

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.errors import AlreadyActivated, InvalidActor
from sdd.core.events import DomainEvent, PlanActivatedEvent, classify_event_level
from sdd.core.types import Command
from sdd.domain.state.reducer import reduce
from sdd.infra.event_log import sdd_replay


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ActivatePlanCommand:
    command_id: str
    command_type: str
    payload: Mapping[str, Any]
    plan_version: int
    actor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class ActivatePlanHandler(CommandHandlerBase):
    """Transition plan_status PLANNED → ACTIVE by emitting PlanActivatedEvent.

    Actor constraint: command.actor MUST be "human" (I-ACT-1).
    Guard: NormGuard must ALLOW actor="human", action="activate_plan".
    Idempotency:
      - command-level: based on command_id (I-CMD-1) — duplicate command_id → return []
      - domain rule: if plan_status already "ACTIVE" → raise AlreadyActivated (I-DOMAIN-1)
    """

    @error_event_boundary(source=__name__)
    def handle(self, command: ActivatePlanCommand) -> list[DomainEvent]:
        if self._check_idempotent(cast(Command, command)):
            return []

        if command.actor != "human":
            raise InvalidActor(
                f"ActivatePlanCommand requires actor='human', got {command.actor!r}"
            )

        state = reduce(sdd_replay(db_path=self._db_path))
        if state.plan_status == "ACTIVE":
            raise AlreadyActivated(command.plan_version)

        event = PlanActivatedEvent(
            event_type="PlanActivated",
            event_id=str(uuid.uuid4()),
            appended_at=int(time.time() * 1000),
            level=classify_event_level("PlanActivated"),
            event_source="runtime",
            caused_by_meta_seq=None,
            plan_version=command.plan_version,
            actor=command.actor,
            timestamp=_utc_now_iso(),
        )
        return [event]
