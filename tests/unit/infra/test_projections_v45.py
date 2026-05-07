"""Tests for get_current_state() YAML-first + staleness guard (BC-45-D, I-STATE-READ-1).

Tests 6-9 from Spec_v45 §10 verification table.
"""
from __future__ import annotations

import dataclasses
import logging

import pytest

import sdd.infra.projections as _proj_mod
from sdd.domain.state.reducer import EMPTY_STATE
from sdd.infra.projections import get_current_state


def _make_yaml_state(snapshot_event_id: int | None):
    return dataclasses.replace(EMPTY_STATE, snapshot_event_id=snapshot_event_id)


_REPLAY_RESULT = dataclasses.replace(EMPTY_STATE, snapshot_event_id=10)


# ── test 6 ────────────────────────────────────────────────────────────────────


def test_get_current_state_yaml_path_when_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """yaml.snapshot_event_id == max_seq → YAML returned, _replay_from_event_log NOT called.

    Invariant: I-STATE-READ-1 (O(1) path confirmed).
    """
    yaml_state = _make_yaml_state(snapshot_event_id=10)
    replay_called = []

    monkeypatch.setattr(_proj_mod, "_read_yaml", lambda: yaml_state)
    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "_replay_from_event_log", lambda db_url: replay_called.append(1) or _REPLAY_RESULT)

    result = get_current_state("postgresql://test/db")

    assert result is yaml_state
    assert replay_called == [], "_replay_from_event_log must NOT be called when YAML is fresh"


# ── test 7 ────────────────────────────────────────────────────────────────────


def test_get_current_state_replays_when_stale(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """yaml.snapshot_event_id < max_seq → WARNING logged + replay triggered.

    Invariant: I-STATE-READ-1 (staleness guard).
    """
    yaml_state = _make_yaml_state(snapshot_event_id=9)
    replay_called = []

    monkeypatch.setattr(_proj_mod, "_read_yaml", lambda: yaml_state)
    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "_replay_from_event_log", lambda db_url: replay_called.append(1) or _REPLAY_RESULT)

    with caplog.at_level(logging.WARNING, logger="sdd.infra.projections"):
        result = get_current_state("postgresql://test/db")

    assert result is _REPLAY_RESULT
    assert replay_called == [1], "_replay_from_event_log must be called when YAML is stale"
    assert any("stale" in record.message.lower() for record in caplog.records), (
        "WARNING about stale YAML must be emitted"
    )


# ── test 8 ────────────────────────────────────────────────────────────────────


def test_get_current_state_replays_when_yaml_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """YAML absent (_read_yaml returns None) → replay triggered.

    Invariant: I-STATE-READ-1.
    """
    replay_called = []

    monkeypatch.setattr(_proj_mod, "_read_yaml", lambda: None)
    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "_replay_from_event_log", lambda db_url: replay_called.append(1) or _REPLAY_RESULT)

    result = get_current_state("postgresql://test/db")

    assert result is _REPLAY_RESULT
    assert replay_called == [1]


# ── test 9 ────────────────────────────────────────────────────────────────────


def test_get_current_state_full_replay_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """full_replay=True → replay regardless of YAML freshness.

    Invariant: I-STATE-READ-1.
    """
    yaml_state = _make_yaml_state(snapshot_event_id=10)
    replay_called = []

    monkeypatch.setattr(_proj_mod, "_read_yaml", lambda: yaml_state)
    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "_replay_from_event_log", lambda db_url: replay_called.append(1) or _REPLAY_RESULT)

    result = get_current_state("postgresql://test/db", full_replay=True)

    assert result is _REPLAY_RESULT
    assert replay_called == [1], "_replay_from_event_log must be called when full_replay=True"
