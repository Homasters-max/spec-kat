"""Integration tests: full EventLog → reducer → state chain — Spec_v5 §7 UC-5-4, §9 row 9.

Invariants covered: Q1, Q3, I-ES-1 (final)

Uses tmp_path / a fresh temporary DuckDB — never the project's sdd_events.duckdb (R-5).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sdd.commands.activate_phase import ActivatePhaseCommand, ActivatePhaseHandler
from sdd.core.events import PhaseActivatedEvent
from sdd.domain.state.reducer import reduce
from sdd.infra.event_log import sdd_append, sdd_replay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append_phase_activated(db_path: str, phase_id: int = 5) -> None:
    sdd_append(
        "PhaseActivated",
        {"phase_id": phase_id, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=db_path,
        level="L1",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_chain_activate_phase(tmp_db_path: str) -> None:
    """Full chain: ActivatePhaseHandler → PhaseActivatedEvent → sdd_replay → reduce →
    state.phase_status == 'ACTIVE' (Q3, UC-5-4).

    Tests the command → event → EventLog → replay → state derivation chain
    without a tautological YAML round-trip.
    """
    import uuid

    # Empty DB — phase_status starts as "PLANNED" (EMPTY_STATE)
    cmd = ActivatePhaseCommand(
        command_id=str(uuid.uuid4()),
        command_type="ActivatePhaseCommand",
        payload={},
        phase_id=5,
        actor="human",
    )

    # Step 1: Handler emits PhaseActivatedEvent
    handler = ActivatePhaseHandler(tmp_db_path)
    events = handler.handle(cmd)

    # Step 2: Assert the correct event type is returned
    assert any(isinstance(e, PhaseActivatedEvent) for e in events), (
        "ActivatePhaseHandler must return a PhaseActivatedEvent"
    )

    # Step 3: Simulate CommandRunner appending the emitted event to EventLog
    for evt in events:
        sdd_append(
            evt.event_type,
            {
                "command_id": cmd.command_id,
                "phase_id": getattr(evt, "phase_id", None),
                "actor": getattr(evt, "actor", None),
                "timestamp": getattr(evt, "timestamp", ""),
            },
            db_path=tmp_db_path,
            level="L1",
        )

    # Step 4: Replay EventLog → reduce → derive state
    raw_events = sdd_replay(db_path=tmp_db_path)
    state = reduce(raw_events)

    assert state.phase_status == "ACTIVE", (
        "After PhaseActivatedEvent, state.phase_status must be 'ACTIVE' (Q1 + Q3)"
    )


def test_full_chain_phase_status_derivable(tmp_db_path: str) -> None:
    """Q1: phase_status is derivable from EventLog replay alone — no YAML dependency.

    Appends PhaseActivated directly to EventLog; reduces without any YAML file.
    State must show phase_status='ACTIVE'.
    """
    _append_phase_activated(tmp_db_path, phase_id=5)

    raw_events = sdd_replay(db_path=tmp_db_path)
    state = reduce(raw_events)

    assert state.phase_status == "ACTIVE", (
        "phase_status must be derivable from EventLog replay (Q1)"
    )


def test_replay_deterministic_after_commands(tmp_db_path: str) -> None:
    """Replay is deterministic: reduce(sdd_replay()) always produces the same state (Q3).

    Two consecutive calls to reduce(sdd_replay()) must return identical SDDState objects.
    """
    sdd_append(
        "PhaseInitialized",
        {"phase_id": 5, "tasks_total": 3, "plan_version": 5, "actor": "llm", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=tmp_db_path,
        level="L1",
    )
    sdd_append(
        "TaskImplemented",
        {"task_id": "T-501", "phase_id": 5},
        db_path=tmp_db_path,
        level="L1",
    )
    _append_phase_activated(tmp_db_path, phase_id=5)

    raw1 = sdd_replay(db_path=tmp_db_path)
    state1 = reduce(raw1)

    raw2 = sdd_replay(db_path=tmp_db_path)
    state2 = reduce(raw2)

    assert state1 == state2, (
        "reduce(sdd_replay()) must be deterministic — same result on every call"
    )
    assert state1.state_hash == state2.state_hash
