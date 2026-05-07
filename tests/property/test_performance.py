"""I-PERF-SCALING-1: replay scales O(N) — t(2N)/t(N) < 2.5 at N >= 1000 (P-10)."""
from __future__ import annotations

import statistics
import time

from sdd.infra.event_log import EventLog
from sdd.infra.projections import get_current_state
from tests.harness.fixtures import db_factory, make_minimal_event  # noqa: F401

_N = 1000
_REPS = 5


def _seed_events(db_path: str, n: int, batch_size: int = 200) -> None:
    """Insert n events into db_path using EventLog directly."""
    store = EventLog(db_path)
    count = 0
    batch_num = 0
    while count < n:
        size = min(batch_size, n - count)
        events = [make_minimal_event(f"_perf_{count + i}") for i in range(size)]
        store.append(events, source="test_perf", command_id=f"perf_{batch_num:08d}")
        count += size
        batch_num += 1


def _measure_replay(db_path: str, reps: int) -> float:
    """Return median wall-clock time (seconds) for get_current_state over reps runs."""
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        get_current_state(db_path)
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def test_replay_linear_scaling(db_factory):
    """Replay slope ratio t(2N)/t(N) must be < 2.5 at N=1000 (I-PERF-SCALING-1)."""
    db_n = db_factory()
    db_2n = db_factory()

    _seed_events(db_n, _N)
    _seed_events(db_2n, 2 * _N)

    # Warmup
    get_current_state(db_n)
    get_current_state(db_2n)

    t_n = _measure_replay(db_n, _REPS)
    t_2n = _measure_replay(db_2n, _REPS)

    if t_n == 0:
        return  # avoid division by zero on extremely fast machines

    ratio = t_2n / t_n
    assert ratio < 2.5, (
        f"Slope ratio {ratio:.3f} >= 2.5: replay is not O(N) "
        f"(t({_N})={t_n:.4f}s, t({2*_N})={t_2n:.4f}s)"
    )
