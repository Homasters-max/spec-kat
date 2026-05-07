"""Tests for phases_known ⊆ Phases_index.md consistency.

Invariants covered:
- I-PHASES-INDEX-1: phases_known ⊆ Phases_index.ids
- I-PHASES-KNOWN-1: phases_known is frozenset[int]; updated only by PhaseInitialized
- I-PHASES-KNOWN-2: phases_known == {s.phase_id for s in phases_snapshots}
- I-DB-TEST-1: no production DB opened; tmp_path used for any file I/O
"""
from __future__ import annotations

import pathlib
import re

from sdd.domain.state.reducer import EMPTY_STATE, reduce

_PHASES_INDEX_PATH = pathlib.Path(".sdd/plans/Phases_index.md")


def _parse_phase_ids(path: pathlib.Path) -> frozenset[int]:
    """Extract integer IDs from table rows of a Phases_index.md file."""
    ids: set[int] = set()
    for line in path.read_text().splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|", line)
        if m:
            ids.add(int(m.group(1)))
    return frozenset(ids)


def _phase_initialized(phase_id: int, tasks_total: int = 3) -> dict:
    return {
        "event_type": "PhaseInitialized",
        "event_source": "runtime",
        "level": "L1",
        "phase_id": phase_id,
        "tasks_total": tasks_total,
        "plan_version": phase_id,
        "actor": "human",
        "timestamp": "2024-01-01T00:00:00Z",
    }


def _phase_context_switched(from_phase: int, to_phase: int) -> dict:
    return {
        "event_type": "PhaseContextSwitched",
        "event_source": "runtime",
        "level": "L1",
        "from_phase": from_phase,
        "to_phase": to_phase,
        "actor": "human",
        "timestamp": "2024-01-01T00:00:00Z",
    }


class TestPhasesIndexConsistency:
    """I-PHASES-INDEX-1: phases_known ⊆ Phases_index.ids."""

    def test_phases_index_parseable(self) -> None:
        """Phases_index.md must exist and contain at least one integer ID."""
        ids = _parse_phase_ids(_PHASES_INDEX_PATH)
        assert len(ids) >= 1
        assert all(isinstance(i, int) for i in ids)

    def test_phases_known_subset_of_synthetic_index(self, tmp_path: pathlib.Path) -> None:
        """phases_known from replay ⊆ IDs in a synthetic Phases_index.md (tmp_path)."""
        index_file = tmp_path / "Phases_index.md"
        index_file.write_text(
            "# Phases Index\n\n"
            "| ID | Title | Spec | Status |\n"
            "|----|-------|------|--------|\n"
            "| 1 | Phase One | spec1.md | COMPLETE |\n"
            "| 2 | Phase Two | spec2.md | ACTIVE |\n"
            "| 3 | Phase Three | spec3.md | PLANNED |\n"
        )
        index_ids = _parse_phase_ids(index_file)
        events = [_phase_initialized(1), _phase_initialized(2)]
        state = reduce(events)

        assert state.phases_known <= index_ids, (
            f"I-PHASES-INDEX-1: phases_known={state.phases_known}"
            f" not ⊆ index_ids={index_ids}"
        )

    def test_phases_known_subset_of_real_index(self) -> None:
        """phases_known built from real index IDs must satisfy I-PHASES-INDEX-1."""
        index_ids = _parse_phase_ids(_PHASES_INDEX_PATH)
        sample = sorted(index_ids)[:3]
        events = [_phase_initialized(pid) for pid in sample]
        state = reduce(events)

        assert state.phases_known <= index_ids, (
            f"I-PHASES-INDEX-1: phases_known={state.phases_known}"
            f" not ⊆ index_ids={index_ids}"
        )

    def test_phase_outside_index_detected(self, tmp_path: pathlib.Path) -> None:
        """Confirms that a phase absent from the index is detectable as a violation."""
        index_file = tmp_path / "Phases_index.md"
        index_file.write_text(
            "| ID | Title |\n"
            "|----|-------|\n"
            "| 1 | Foundation |\n"
        )
        index_ids = _parse_phase_ids(index_file)
        events = [_phase_initialized(1), _phase_initialized(99)]
        state = reduce(events)

        # Phase 99 is not in the index — invariant violation must be detectable.
        assert not (state.phases_known <= index_ids), (
            "Expected I-PHASES-INDEX-1 violation not detected: "
            "phase 99 is in phases_known but not in index"
        )


class TestPhasesKnown1:
    """I-PHASES-KNOWN-1: phases_known is frozenset[int]; PhaseContextSwitched must not modify it."""

    def test_empty_state_is_frozenset(self) -> None:
        assert isinstance(EMPTY_STATE.phases_known, frozenset)
        assert len(EMPTY_STATE.phases_known) == 0

    def test_type_and_values_after_replay(self) -> None:
        state = reduce([_phase_initialized(1), _phase_initialized(2)])
        assert isinstance(state.phases_known, frozenset)
        assert state.phases_known == frozenset({1, 2})
        assert all(isinstance(i, int) for i in state.phases_known)

    def test_context_switch_does_not_modify_phases_known(self) -> None:
        """PhaseContextSwitched MUST NOT add or remove entries from phases_known."""
        events = [
            _phase_initialized(1),
            _phase_initialized(2),
            _phase_context_switched(2, 1),
        ]
        state = reduce(events)
        assert state.phases_known == frozenset({1, 2}), (
            f"I-PHASES-KNOWN-1: PhaseContextSwitched must not modify phases_known, "
            f"got {state.phases_known}"
        )
        assert state.phase_current == 1

    def test_repeated_context_switch_phases_known_unchanged(self) -> None:
        events = [
            _phase_initialized(5),
            _phase_initialized(6),
            _phase_context_switched(6, 5),
            _phase_context_switched(5, 6),
            _phase_context_switched(6, 5),
        ]
        state = reduce(events)
        assert state.phases_known == frozenset({5, 6})


class TestPhasesKnown2:
    """I-PHASES-KNOWN-2: phases_known == {s.phase_id for s in phases_snapshots}."""

    def test_coherence_after_phase_initialized(self) -> None:
        state = reduce([_phase_initialized(1), _phase_initialized(2)])
        snapshot_ids = frozenset(s.phase_id for s in state.phases_snapshots)
        assert state.phases_known == snapshot_ids, (
            f"I-PHASES-KNOWN-2: phases_known={state.phases_known}"
            f" != snapshot_ids={snapshot_ids}"
        )

    def test_coherence_after_context_switch(self) -> None:
        events = [
            _phase_initialized(3),
            _phase_initialized(4),
            _phase_context_switched(4, 3),
        ]
        state = reduce(events)
        snapshot_ids = frozenset(s.phase_id for s in state.phases_snapshots)
        assert state.phases_known == snapshot_ids, (
            f"I-PHASES-KNOWN-2 after context switch: "
            f"phases_known={state.phases_known} != snapshot_ids={snapshot_ids}"
        )

    def test_empty_state_coherent(self) -> None:
        snapshot_ids = frozenset(s.phase_id for s in EMPTY_STATE.phases_snapshots)
        assert EMPTY_STATE.phases_known == snapshot_ids
        assert len(EMPTY_STATE.phases_known) == 0

    def test_single_phase(self) -> None:
        state = reduce([_phase_initialized(7)])
        snapshot_ids = frozenset(s.phase_id for s in state.phases_snapshots)
        assert state.phases_known == snapshot_ids == frozenset({7})


class TestDbTest1:
    """I-DB-TEST-1: tests MUST NOT open production DB."""

    def test_tmp_path_distinct_from_production_db(self, tmp_path: pathlib.Path) -> None:
        """tmp_path must resolve to a path different from the production DB."""
        prod_db = pathlib.Path(".sdd/state/sdd_events.duckdb").resolve()
        test_db = (tmp_path / "test_sdd_events.duckdb").resolve()
        assert test_db != prod_db, (
            f"I-DB-TEST-1: tmp_path resolves to production DB: {prod_db}"
        )

    def test_reducer_is_pure_no_db(self, tmp_path: pathlib.Path) -> None:
        """EventReducer.reduce() must return correct state without any DB access."""
        events = [_phase_initialized(1), _phase_initialized(2)]
        state = reduce(events)
        assert state.phases_known == frozenset({1, 2})
        assert isinstance(state.phases_known, frozenset)
        snapshot_ids = frozenset(s.phase_id for s in state.phases_snapshots)
        assert state.phases_known == snapshot_ids
        # Verify tmp_path was not touched (pure reducer has no file I/O)
        assert list(tmp_path.iterdir()) == []
