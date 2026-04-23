"""Tests for yaml_state.read_state / write_state — Spec_v2 §9 row 2."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sdd.core.errors import Inconsistency, MissingState
from sdd.domain.state.reducer import SDDState
from sdd.domain.state.yaml_state import read_state, write_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides: object) -> SDDState:
    defaults: dict[str, object] = dict(
        phase_current=2,
        plan_version=2,
        tasks_version=2,
        tasks_total=10,
        tasks_completed=3,
        tasks_done_ids=("T-201", "T-202", "T-203"),
        invariants_status="UNKNOWN",
        tests_status="UNKNOWN",
        last_updated="2026-04-20T12:00:00Z",
        schema_version=1,
        snapshot_event_id=None,
        phase_status="ACTIVE",
        plan_status="ACTIVE",
    )
    defaults.update(overrides)
    return SDDState(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_read_write_roundtrip(tmp_path):
    path = str(tmp_path / "State_index.yaml")
    state = _make_state()
    write_state(state, path)
    result = read_state(path)
    assert result == state


def test_read_missing_raises_missing_state(tmp_path):
    with pytest.raises(MissingState):
        read_state(str(tmp_path / "nonexistent.yaml"))


def test_write_uses_atomic_write(tmp_path):
    path = str(tmp_path / "State_index.yaml")
    state = _make_state()
    with patch("sdd.domain.state.yaml_state.atomic_write") as mock_write:
        write_state(state, path)
    mock_write.assert_called_once()
    call_path, call_content = mock_write.call_args[0]
    assert call_path == path
    assert isinstance(call_content, str)


def test_state_hash_verified_on_read(tmp_path):
    path = str(tmp_path / "State_index.yaml")
    state = _make_state()
    write_state(state, path)
    result = read_state(path)
    assert result.state_hash == state.state_hash


def test_state_hash_mismatch_raises_inconsistency(tmp_path):
    path = str(tmp_path / "State_index.yaml")
    state = _make_state()
    write_state(state, path)
    content = open(path, encoding="utf-8").read()
    tampered = content.replace(
        f"# state_hash: {state.state_hash}",
        "# state_hash: deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    open(path, "w", encoding="utf-8").write(tampered)
    with pytest.raises(Inconsistency):
        read_state(path)


def test_state_hash_excludes_human_fields():
    s1 = _make_state(phase_status="ACTIVE", plan_status="ACTIVE")
    s2 = _make_state(phase_status="COMPLETE", plan_status="COMPLETE")
    assert s1.state_hash == s2.state_hash


def test_state_hash_includes_reducer_version(monkeypatch):
    s1 = _make_state()
    original_hash = s1.state_hash
    monkeypatch.setattr(SDDState, "REDUCER_VERSION", 99)
    s2 = _make_state()
    assert s2.state_hash != original_hash


def test_human_fields_preserved_in_roundtrip(tmp_path):
    path = str(tmp_path / "State_index.yaml")
    state = _make_state(phase_status="COMPLETE", plan_status="COMPLETE")
    write_state(state, path)
    result = read_state(path)
    assert result.phase_status == "COMPLETE"
    assert result.plan_status == "COMPLETE"
