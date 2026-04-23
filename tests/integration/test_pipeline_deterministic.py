"""Integration test — Domain Determinism, Level B. Invariant: I-EXEC-ISOL-1."""
import pytest

from sdd.domain.state.reducer import reduce
from sdd.infra.event_log import sdd_append, sdd_replay


def test_activate_phase_deterministic(tmp_path):
    """Two sdd_replay() calls on the same isolated DB produce identical reduce() output.

    I-EXEC-ISOL-1: reduce() is a pure function of its input; sdd_replay() is stable
    across calls on the same unchanged DB; no hidden state mutations.
    Isolation: tmp_path DuckDB — never touches sdd_events.duckdb.
    """
    db = str(tmp_path / "test_events.duckdb")

    sdd_append(
        "PhaseActivated",
        {"phase_id": 10, "actor": "human", "timestamp": "2026-01-01T00:00:00Z"},
        db_path=db,
        level="L1",
        event_source="runtime",
    )

    state_1 = reduce(sdd_replay(db_path=db))
    state_2 = reduce(sdd_replay(db_path=db))

    assert state_1.state_hash == state_2.state_hash
