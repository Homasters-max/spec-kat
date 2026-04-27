"""SwitchPhaseCommand + SwitchPhaseHandler + SwitchPhaseGuard — Spec_v24 §3 BC-PC-3,5.

Invariants: I-PHASE-CONTEXT-1, I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from sdd.commands._base import CommandHandlerBase
from sdd.core.errors import InvalidActor, MissingContext, SDDError
from sdd.core.events import DomainEvent, PhaseContextSwitchedEvent, classify_event_level
from sdd.domain.guards.context import GuardContext, GuardOutcome, GuardResult
from sdd.domain.guards.norm_guard import make_norm_guard
from sdd.domain.guards.types import Guard
from sdd.infra.paths import event_store_file

if TYPE_CHECKING:
    pass


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# SwitchPhaseGuard (I-PHASE-CONTEXT-2,3,4)
# ---------------------------------------------------------------------------

def make_switch_phase_guard(phase_id: int) -> Guard:
    """Guard factory: validates target phase is known, exists, and differs from current."""

    def guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        known = ctx.state.phases_known
        current = ctx.state.phase_current
        if not known:
            raise MissingContext(
                "I-PHASE-CONTEXT-3: switch-phase requires at least one activated phase;"
                " phases_known is empty"
            )
        if phase_id not in known:
            raise MissingContext(
                f"I-PHASE-CONTEXT-2: phase {phase_id} not in phases_known={sorted(known)}"
            )
        if phase_id == current:
            raise MissingContext(
                f"I-PHASE-CONTEXT-4: phase {phase_id} is already the current context;"
                f" no switch needed"
            )
        return GuardResult(GuardOutcome.ALLOW, "SwitchPhaseGuard", "I-PHASE-CONTEXT-2,3,4 pass", None, None), []

    return guard


# ---------------------------------------------------------------------------
# Guard factory (BC-33-SWITCH)
# ---------------------------------------------------------------------------

def _switch_phase_guard_factory(cmd: Any) -> list[Guard]:
    """Guard list for switch-phase: navigation guards only (I-GUARD-NAV-1).
    make_phase_guard removed: PG-3 (phase.status == ACTIVE) blocks navigation from COMPLETE phases.
    """
    phase_id = getattr(cmd, "phase_id", 0)
    return [
        make_switch_phase_guard(phase_id),
        make_norm_guard("human", "switch_phase", None),
    ]


# ---------------------------------------------------------------------------
# SwitchPhaseCommand
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwitchPhaseCommand:
    command_id: str
    command_type: str
    payload: Mapping[str, Any]
    phase_id: int    # to_phase
    from_phase: int  # resolved from current state before command construction
    actor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


# ---------------------------------------------------------------------------
# SwitchPhaseHandler
# ---------------------------------------------------------------------------

class SwitchPhaseHandler(CommandHandlerBase):
    """Emit exactly one PhaseContextSwitchedEvent (I-PHASE-CONTEXT-1).

    Pure handler (I-HANDLER-PURE-1): no I/O, no EventStore calls, no replay.
    Actor constraint: actor MUST be 'human'.
    """

    def handle(self, command: SwitchPhaseCommand) -> list[DomainEvent]:  # type: ignore[override]
        if command.actor != "human":
            raise InvalidActor(
                f"SwitchPhaseCommand requires actor='human', got {command.actor!r}"
            )
        now_iso = _utc_now_iso()
        now_ms = int(time.time() * 1000)
        event = PhaseContextSwitchedEvent(
            event_type="PhaseContextSwitched",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("PhaseContextSwitched"),
            event_source="runtime",
            caused_by_meta_seq=None,
            from_phase=command.from_phase,
            to_phase=command.phase_id,
            actor=command.actor,
            timestamp=now_iso,
        )
        return [event]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="switch-phase")
    parser.add_argument("phase_id", type=int)
    parser.add_argument("--actor", default="human")
    parser.add_argument("--db", default=None)
    parsed = parser.parse_args(args)
    db = parsed.db or str(event_store_file())
    try:
        from sdd.commands.registry import REGISTRY, execute_and_project
        from sdd.infra.projections import get_current_state

        state = get_current_state(db)
        from_phase = state.phase_current
        cmd = SwitchPhaseCommand(
            command_id=str(uuid.uuid4()),
            command_type="SwitchPhaseCommand",
            payload={"phase_id": parsed.phase_id, "from_phase": from_phase},
            phase_id=parsed.phase_id,
            from_phase=from_phase,
            actor=parsed.actor,
        )
        execute_and_project(REGISTRY["switch-phase"], cmd, db_path=db)
        return 0
    except SDDError as e:
        print(json.dumps({"error_type": type(e).__name__, "message": str(e)}), file=sys.stderr)
        return 1
    except Exception:
        return 2
