"""BC-VR-1: Hypothesis generators for Validation Runtime property tests.

Invariants: I-VR-NO-LOGIC-1 (generators create INPUTS only — no domain logic).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from hypothesis import strategies as st

from sdd.commands.registry import REGISTRY, CommandSpec


@dataclass
class _CmdPayload:
    """Minimal command payload; supports _extract_task_id via .task_id attribute."""

    task_id: str
    phase_id: int = 17


@st.composite
def valid_command_sequence(draw, max_cmds: int = 10) -> list[tuple[CommandSpec, Any]]:
    """Generate a list of (spec, cmd) pairs suitable for execute_sequence.

    Uses sync-state (requires_active_phase=False — I-SYNC-NO-PHASE-GUARD-1) so the
    sequence is valid against any DB state without domain setup.
    """
    n = draw(st.integers(min_value=0, max_value=max_cmds))
    spec = REGISTRY["sync-state"]
    return [(spec, SimpleNamespace()) for _ in range(n)]


@st.composite
def edge_payload(draw, command_spec: CommandSpec) -> _CmdPayload:
    """Generate boundary task IDs for command_spec edge-case testing (I-VR-NO-LOGIC-1)."""
    task_id = draw(
        st.one_of(
            st.just("T-0000"),
            st.just("T-9999"),
            st.from_regex(r"T-\d{4}", fullmatch=True),
            st.text(min_size=0, max_size=16).map(lambda s: f"T-{s}"),
        )
    )
    return _CmdPayload(task_id=task_id)


@st.composite
def adversarial_sequence(draw) -> list[tuple[CommandSpec, Any]]:
    """Generate adversarial sequences: empty, duplicate, or oversized (I-VR-NO-LOGIC-1)."""
    kind = draw(st.sampled_from(["empty", "single", "duplicate", "oversized"]))
    spec = REGISTRY["sync-state"]
    if kind == "empty":
        return []
    if kind == "single":
        return [(spec, SimpleNamespace())]
    if kind == "duplicate":
        cmd = SimpleNamespace()
        return [(spec, cmd), (spec, cmd)]
    # oversized: reduced from (20, 100) — each open_sdd_connection costs ~50ms;
    # 20+ commands × 2 execute_sequences × 20 examples exceeds pytest --timeout=30.
    n = draw(st.integers(min_value=5, max_value=10))
    return [(spec, SimpleNamespace()) for _ in range(n)]


@st.composite
def independent_command_pair(draw) -> tuple[_CmdPayload, _CmdPayload]:
    """Generate two commands with distinct task IDs for G5 interleaving tests."""
    ids = draw(
        st.lists(
            st.from_regex(r"T-\d{4}", fullmatch=True),
            min_size=2,
            max_size=2,
            unique=True,
        )
    )
    return _CmdPayload(task_id=ids[0]), _CmdPayload(task_id=ids[1])
