"""Tests for BC-48-A SessionDedupPolicy.

Invariants: I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1, I-GUARD-PURE-1, I-DEDUP-DOMAIN-1
"""
from __future__ import annotations

import inspect
import types

from sdd.domain.session.policy import SessionDedupPolicy
from sdd.infra.projector import SessionRecord, SessionsView


def _make_cmd(session_type: str, phase_id: int | None) -> types.SimpleNamespace:
    return types.SimpleNamespace(session_type=session_type, phase_id=phase_id)


def _make_record(session_type: str, phase_id: int | None) -> SessionRecord:
    return SessionRecord(
        session_type=session_type,
        phase_id=phase_id,
        task_id=None,
        seq=1,
        timestamp="2026-01-01T00:00:00",
    )


def _make_view(*records: SessionRecord) -> SessionsView:
    index = {(r.session_type, r.phase_id): r for r in records}
    return SessionsView(_index=index)


_policy = SessionDedupPolicy()


def test_policy_no_view_returns_true():
    """I-SESSION-DEDUP-2: sessions_view=None → always emit."""
    assert _policy.should_emit(None, _make_cmd("IMPLEMENT", 48)) is True


def test_policy_no_matching_session_returns_true():
    """I-SESSION-DEDUP-2: view has sessions but none match cmd → emit."""
    view = _make_view(_make_record("VALIDATE", 48))
    assert _policy.should_emit(view, _make_cmd("IMPLEMENT", 48)) is True


def test_policy_matching_session_returns_false():
    """I-SESSION-DEDUP-2: exact (session_type, phase_id) match → suppress emit."""
    view = _make_view(_make_record("IMPLEMENT", 48))
    assert _policy.should_emit(view, _make_cmd("IMPLEMENT", 48)) is False


def test_policy_different_type_returns_true():
    """I-SESSION-DEDUP-SCOPE-1: same phase_id, different session_type → not a duplicate."""
    view = _make_view(_make_record("VALIDATE", 48))
    assert _policy.should_emit(view, _make_cmd("IMPLEMENT", 48)) is True


def test_policy_different_phase_returns_true():
    """I-SESSION-DEDUP-SCOPE-1: same session_type, different phase_id → not a duplicate."""
    view = _make_view(_make_record("IMPLEMENT", 47))
    assert _policy.should_emit(view, _make_cmd("IMPLEMENT", 48)) is True


def test_policy_pure_no_io():
    """I-GUARD-PURE-1 + I-DEDUP-DOMAIN-1: policy is a pure frozen dataclass with no DB access."""
    import sdd.domain.session.policy as _mod

    # Frozen dataclass: setattr must raise FrozenInstanceError (AttributeError subclass)
    try:
        setattr(_policy, "_x", 1)  # type: ignore[misc]
        assert False, "expected frozen dataclass to raise on setattr"
    except AttributeError:
        pass

    # Module must not pull in DB infrastructure (I-DEDUP-DOMAIN-1)
    src = inspect.getsource(_mod)
    assert "open_db_connection" not in src
    assert "open_sdd_connection" not in src
    assert "EventStore" not in src
