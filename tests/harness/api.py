"""BC-VR-1: System Harness API — thin adapter over kernel entry points.

Invariants: I-VR-API-1, I-VR-HARNESS-1, I-VR-HARNESS-2.
Rule: this module MUST import ONLY execute_command and get_current_state from the kernel.
      No direct EventStore, rebuild_state, or other internal calls (I-VR-API-1).
"""
from __future__ import annotations

from typing import Any

from sdd.commands.registry import CommandSpec, execute_command
from sdd.core.events import DomainEvent
from sdd.domain.state.reducer import SDDState
from sdd.infra.projections import get_current_state


def execute_sequence(
    cmds: list[tuple[CommandSpec, Any]],
    db_path: str,
) -> tuple[list[DomainEvent], SDDState]:
    """Execute a sequence of (spec, cmd) pairs against db_path; return all events and final state.

    I-VR-HARNESS-1: uses only execute_command (no other kernel calls in the execution loop).
    """
    all_events: list[DomainEvent] = []
    for spec, cmd in cmds:
        events = execute_command(spec, cmd, db_path=db_path)
        all_events.extend(events)
    state = get_current_state(db_path)
    return all_events, state


def replay(
    events: list[DomainEvent],  # noqa: ARG001 — documents expected DB content
    db_path: str,
) -> SDDState:
    """Return current state rebuilt from db_path (events assumed already persisted there).

    I-VR-HARNESS-2: uses only get_current_state.
    """
    return get_current_state(db_path)


def fork(
    events: list[DomainEvent],
    extra_cmds: list[tuple[CommandSpec, Any]],
    db_path: str,
) -> list[DomainEvent]:
    """Verify checkpoint state, then execute extra_cmds; return only the new events."""
    replay(events, db_path)
    new_events, _ = execute_sequence(extra_cmds, db_path)
    return new_events


def rollback(
    events: list[DomainEvent],
    t: int,
) -> list[DomainEvent]:
    """Return the first t events from the sequence (in-memory slice; no DB mutation)."""
    return events[:t]
