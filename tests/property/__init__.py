"""Property test package — shared helpers for norm-aware test execution."""
from __future__ import annotations

import atexit
import os
import tempfile
from typing import Any

from sdd.commands.registry import CommandSpec, execute_command
from sdd.core.events import DomainEvent
from sdd.core.types import Command
from sdd.domain.state.reducer import SDDState
from sdd.infra.projections import get_current_state

# Temp norm catalog that allows actor='any' for sync_state.
# Required because the production catalog is strict=True and has no 'any' actor rule,
# while the sync-state CommandSpec carries actor='any' (I-SYNC-NO-PHASE-GUARD-1).
_NORM_YAML = """\
norms:
  - norm_id: TEST-ALLOW-ANY-SYNC
    description: "Test-only: allow actor=any for sync_state property tests"
    actor: any
    enforcement: hard
    allowed_actions:
      - sync_state
"""
_norm_file = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
_norm_file.write(_NORM_YAML)
_norm_file.close()
NORM_PATH: str = _norm_file.name
atexit.register(os.unlink, NORM_PATH)


def wrap(pairs: list[tuple[CommandSpec, Any]]) -> list[tuple[CommandSpec, Command]]:
    """Convert (spec, placeholder) generator output into (spec, Command) pairs."""
    return [
        (spec, Command(command_id=f"{i:08x}", command_type=spec.action, payload={}))
        for i, (spec, _) in enumerate(pairs)
    ]


def execute_sequence(
    cmds: list[tuple[CommandSpec, Command]],
    db_path: str,
) -> tuple[list[DomainEvent], SDDState]:
    """Run a command sequence with test-permissive norm catalog; return events + final state."""
    all_events: list[DomainEvent] = []
    for spec, cmd in cmds:
        events = execute_command(spec, cmd, db_path=db_path, norm_path=NORM_PATH)
        all_events.extend(events)
    return all_events, get_current_state(db_path)
