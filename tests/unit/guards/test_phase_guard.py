"""Unit tests for check_phase_activation_guard — I-PHASE-SEQ-FORWARD-1, I-PROJECTION-GUARD-1.

Invariants: I-GUARD-CLI-1, I-PHASE-SEQ-FORWARD-1, I-PROJECTION-GUARD-1, I-STATE-ACCESS-LAYER-1
Spec ref: Spec_v15 §2 BC-4 Guards (Amendment A-4); Phase_v15.5 §8 Q1
"""
from __future__ import annotations

import pytest

from sdd.core.errors import AlreadyActivated, InvalidPhaseSequence
from sdd.guards.phase import check_phase_activation_guard
from sdd.infra.event_log import sdd_append


def _advance_to_phase(phase_id: int, db_path: str) -> None:
    """Emit PhaseStarted events sequentially up to phase_id (A-8 soft guard requires order)."""
    for p in range(1, phase_id + 1):
        sdd_append(
            "PhaseStarted",
            {"phase_id": p, "actor": "human"},
            db_path=db_path,
            level="L1",
        )


def test_already_activated_raises_when_phase_id_le_current(tmp_db_path: str) -> None:
    """phase_id <= state.phase_current → AlreadyActivated (I-PHASE-SEQ-FORWARD-1)."""
    _advance_to_phase(phase_id=3, db_path=tmp_db_path)
    with pytest.raises(AlreadyActivated):
        check_phase_activation_guard(phase_id=3, db_path=tmp_db_path)


def test_invalid_phase_sequence_raises_when_skipping(tmp_db_path: str) -> None:
    """phase_id > state.phase_current + 1 → InvalidPhaseSequence (I-PHASE-SEQ-FORWARD-1)."""
    _advance_to_phase(phase_id=3, db_path=tmp_db_path)
    with pytest.raises(InvalidPhaseSequence):
        check_phase_activation_guard(phase_id=5, db_path=tmp_db_path)


def test_happy_path_passes_for_next_sequential_phase(tmp_db_path: str) -> None:
    """phase_id == state.phase_current + 1 → passes (I-PHASE-SEQ-FORWARD-1 happy path)."""
    _advance_to_phase(phase_id=3, db_path=tmp_db_path)
    check_phase_activation_guard(phase_id=4, db_path=tmp_db_path)
