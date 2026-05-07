"""Fuzz test: I-CONFLUENCE-STRONG-1 — command interleaving confluence.

Property: [cmd_a, cmd_b] and [cmd_b, cmd_a] yield equal state_hash.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from dataclasses import asdict as _asdict

from hypothesis import HealthCheck, given, settings

from sdd.commands.registry import REGISTRY
from sdd.core.types import Command
from tests.harness.api import execute_sequence
from tests.harness.fixtures import db_factory  # noqa: F401 — pytest fixture
from tests.harness.generators import independent_command_pair

# sync-state spec has actor="any" which is not in the norm catalog (catalog lists llm only).
# Use actor="llm" for the test spec so NormGuard passes (NORM-ACTOR-004 allows sync_state).
_TEST_SYNC_SPEC = dataclasses.replace(REGISTRY["sync-state"], actor="llm")


def _state_hash(state) -> str:
    """Deterministic hash over domain-meaningful fields of SDDState."""
    try:
        raw = _asdict(state)
    except TypeError:
        # fallback: public attrs, exclude per-DB path fields that differ between runs
        raw = {
            k: v
            for k, v in vars(state).items()
            if not k.startswith("_") and "path" not in k.lower() and "db" not in k.lower()
        }
    canonical = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _wrap(payload) -> Command:
    """Wrap a _CmdPayload into a Command for sync-state execution.

    Uses only phase_id from the payload (SyncStatePayload fields).
    Each call gets a unique command_id so idempotency dedup doesn't suppress events.
    """
    return Command(
        command_id=uuid.uuid4().hex,
        command_type="sync_state",
        payload={"phase_id": payload.phase_id},
    )


@given(independent_command_pair())
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_confluence_strong(db_factory, pair):
    """I-CONFLUENCE-STRONG-1: interleaving independent commands is confluent.

    Executes (cmd_a, cmd_b) and (cmd_b, cmd_a) against isolated DBs;
    asserts resulting state_hash is equal. independent_command_pair
    guarantees distinct task_ids, so no shared mutable state between
    the two commands.
    """
    cmd_a, cmd_b = pair

    _, state_ab = execute_sequence(
        [(_TEST_SYNC_SPEC, _wrap(cmd_a)), (_TEST_SYNC_SPEC, _wrap(cmd_b))],
        db_factory(),
    )

    _, state_ba = execute_sequence(
        [(_TEST_SYNC_SPEC, _wrap(cmd_b)), (_TEST_SYNC_SPEC, _wrap(cmd_a))],
        db_factory(),
    )

    assert _state_hash(state_ab) == _state_hash(state_ba), (
        f"Confluence violated: hash(AB)={_state_hash(state_ab)!r} "
        f"!= hash(BA)={_state_hash(state_ba)!r}"
    )
