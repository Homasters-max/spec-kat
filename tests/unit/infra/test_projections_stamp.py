"""Tests for _stamp_yaml_seq — ProjectionType.STAMP write-path (I-YAML-STAMP-1).

Verifies that audit-only commands advance the snapshot_event_id sentinel in YAML
without triggering a full EventLog replay, eliminating the recurring stale WARNING.
"""
from __future__ import annotations

import dataclasses
import logging

import pytest

import sdd.infra.projections as _proj_mod
from sdd.domain.state.reducer import EMPTY_STATE
from sdd.infra.projections import _stamp_yaml_seq, get_current_state


def _make_yaml_state(snapshot_event_id: int | None):
    return dataclasses.replace(EMPTY_STATE, snapshot_event_id=snapshot_event_id)


_DB_URL = "postgresql://test/db"


# ── test S-1 ──────────────────────────────────────────────────────────────────


def test_stamp_yaml_seq_updates_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """_stamp_yaml_seq writes snapshot_event_id=max_seq to YAML without replay.

    Invariant: I-YAML-STAMP-1.
    """
    yaml_state = _make_yaml_state(snapshot_event_id=9)
    written: list = []
    replay_called: list = []

    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(
        _proj_mod,
        "read_state",
        lambda path: yaml_state,
    )
    monkeypatch.setattr(
        _proj_mod,
        "write_state",
        lambda state, path: written.append(state),
    )
    monkeypatch.setattr(
        _proj_mod,
        "_replay_from_event_log",
        lambda db_url: replay_called.append(1) or yaml_state,
    )

    _stamp_yaml_seq(_DB_URL, "/fake/State_index.yaml")

    assert replay_called == [], "_stamp_yaml_seq MUST NOT call _replay_from_event_log"
    assert len(written) == 1, "write_state must be called exactly once"
    assert written[0].snapshot_event_id == 10


# ── test S-2 ──────────────────────────────────────────────────────────────────


def test_stamp_yaml_seq_noop_when_already_current(monkeypatch: pytest.MonkeyPatch) -> None:
    """_stamp_yaml_seq is a no-op when snapshot_event_id already equals max_seq.

    Invariant: I-YAML-STAMP-1 (idempotency).
    """
    yaml_state = _make_yaml_state(snapshot_event_id=10)
    written: list = []

    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "read_state", lambda path: yaml_state)
    monkeypatch.setattr(_proj_mod, "write_state", lambda state, path: written.append(state))

    _stamp_yaml_seq(_DB_URL, "/fake/State_index.yaml")

    assert written == [], "write_state must NOT be called when YAML is already current"


# ── test S-3 ──────────────────────────────────────────────────────────────────


def test_stamp_yaml_seq_noop_when_yaml_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """_stamp_yaml_seq is a no-op when YAML does not exist (raises on read).

    Invariant: I-YAML-STAMP-1.
    """
    written: list = []

    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "read_state", lambda path: (_ for _ in ()).throw(FileNotFoundError("absent")))
    monkeypatch.setattr(_proj_mod, "write_state", lambda state, path: written.append(state))

    _stamp_yaml_seq(_DB_URL, "/fake/State_index.yaml")

    assert written == [], "write_state must NOT be called when YAML is absent"


# ── test S-4 ──────────────────────────────────────────────────────────────────


def test_get_current_state_no_warning_after_stamp(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """After _stamp_yaml_seq, get_current_state returns YAML directly — no stale WARNING.

    Simulates the full per-session pattern:
      record-session (STAMP) → snapshot_event_id advances → next get_current_state is fresh.

    Invariant: I-STATE-READ-1 + I-YAML-STAMP-1.
    """
    pre_stamp_state = _make_yaml_state(snapshot_event_id=9)
    stamped_state = _make_yaml_state(snapshot_event_id=10)
    replay_called: list = []

    monkeypatch.setattr(_proj_mod, "_pg_max_seq", lambda db_url: 10)
    monkeypatch.setattr(_proj_mod, "read_state", lambda path: pre_stamp_state)
    monkeypatch.setattr(_proj_mod, "write_state", lambda state, path: None)
    monkeypatch.setattr(_proj_mod, "_read_yaml", lambda: stamped_state)
    monkeypatch.setattr(
        _proj_mod,
        "_replay_from_event_log",
        lambda db_url: replay_called.append(1) or stamped_state,
    )

    _stamp_yaml_seq(_DB_URL, "/fake/State_index.yaml")

    with caplog.at_level(logging.WARNING, logger="sdd.infra.projections"):
        result = get_current_state(_DB_URL)

    assert result is stamped_state
    assert replay_called == [], "_replay_from_event_log must NOT be called after stamp"
    stale_warnings = [r for r in caplog.records if "stale" in r.message.lower()]
    assert stale_warnings == [], f"No stale WARNING expected, got: {stale_warnings}"
