"""Unit tests for sdd.core.incremental_reducer — IncrementalReducer."""
from __future__ import annotations

from sdd.core.incremental_reducer import IncrementalReducer
from sdd.domain.state.reducer import EMPTY_STATE


def test_apply_delta_empty_events():
    reducer = IncrementalReducer()
    result = reducer.apply_delta(EMPTY_STATE, [])
    assert result == EMPTY_STATE


def test_apply_delta_from_scratch_empty():
    reducer = IncrementalReducer()
    result = reducer.apply_delta_from_scratch([])
    assert result == EMPTY_STATE


def test_apply_delta_from_scratch_equals_apply_delta():
    reducer = IncrementalReducer()
    r1 = reducer.apply_delta(EMPTY_STATE, [])
    r2 = reducer.apply_delta_from_scratch([])
    assert r1 == r2


def test_apply_delta_strict_mode():
    reducer = IncrementalReducer()
    result = reducer.apply_delta(EMPTY_STATE, [], strict_mode=True)
    assert result == EMPTY_STATE
