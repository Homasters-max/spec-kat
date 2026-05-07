"""Tests for sdd nav-session command (T-1812, I-NAV-SESSION-1, I-NAV-6, I-NAV-9, I-SESSION-2)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.spatial.commands.nav_session import run
from sdd.spatial.navigator import NavigationIntent, NavigationSession, SessionLockTimeout

_FAKE_ROOT = Path("/fake/.sdd")


def _fresh_session() -> NavigationSession:
    return NavigationSession(step_id=0)


def _session_at_step(n: int) -> NavigationSession:
    s = NavigationSession(step_id=0)
    for _ in range(n):
        s.next_step()
    return s


# ---------------------------------------------------------------------------
# next: increment step_id (I-NAV-6, I-NAV-9)
# ---------------------------------------------------------------------------

def test_next_increments_step_id(capsys):
    """next subcommand increments step_id by 1 and saves session."""
    session = NavigationSession(step_id=3)
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=session),
        patch("sdd.spatial.commands.nav_session.save_session") as mock_save,
    ):
        rc = run(["next"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["step_id"] == 4
    saved = mock_save.call_args[0][0]
    assert saved.step_id == 4


def test_next_from_zero(capsys):
    """next from step_id=0 produces step_id=1."""
    session = _fresh_session()
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=session),
        patch("sdd.spatial.commands.nav_session.save_session"),
    ):
        rc = run(["next"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["step_id"] == 1


def test_next_resets_term_searched():
    """next resets term_searched to False (I-NAV-9 boundary semantics)."""
    session = NavigationSession(step_id=1, term_searched=True)
    saved_sessions: list[NavigationSession] = []
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=session),
        patch(
            "sdd.spatial.commands.nav_session.save_session",
            side_effect=lambda s, r: saved_sessions.append(s),
        ),
    ):
        run(["next"])

    assert saved_sessions[0].term_searched is False


def test_next_resets_intent():
    """next resets intent to None (I-NAV-9 step boundary)."""
    session = NavigationSession(
        step_id=1, intent=NavigationIntent(type="code_write")
    )
    saved_sessions: list[NavigationSession] = []
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=session),
        patch(
            "sdd.spatial.commands.nav_session.save_session",
            side_effect=lambda s, r: saved_sessions.append(s),
        ),
    ):
        run(["next"])

    assert saved_sessions[0].intent is None


def test_next_calls_save_session_exactly_once():
    """next persists session exactly once per call (I-NAV-SESSION-1)."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=_fresh_session()),
        patch("sdd.spatial.commands.nav_session.save_session") as mock_save,
    ):
        run(["next"])

    assert mock_save.call_count == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_calls_clear_session(capsys):
    """clear subcommand calls clear_session and returns status=ok."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.clear_session") as mock_clear,
    ):
        rc = run(["clear"])

    assert rc == 0
    mock_clear.assert_called_once_with(str(_FAKE_ROOT))
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["cleared"] is True


def test_clear_does_not_call_load_or_save():
    """clear skips load_session/save_session (only clear_session needed)."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.clear_session"),
        patch("sdd.spatial.commands.nav_session.load_session") as mock_load,
        patch("sdd.spatial.commands.nav_session.save_session") as mock_save,
    ):
        run(["clear"])

    mock_load.assert_not_called()
    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_show_prints_session_state(capsys):
    """show prints current session fields as JSON."""
    session = NavigationSession(
        step_id=2,
        resolved_nodes={"COMMAND:complete"},
        loaded_modes={"COMMAND:complete": "SUMMARY"},
        full_load_count_per_step={1: 1},
        term_searched=True,
        intent=NavigationIntent(type="analyze"),
    )
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=session),
    ):
        rc = run(["show"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["step_id"] == 2
    assert out["resolved_nodes"] == ["COMMAND:complete"]
    assert out["loaded_modes"] == {"COMMAND:complete": "SUMMARY"}
    assert out["full_load_count_per_step"] == {"1": 1}
    assert out["term_searched"] is True
    assert out["intent"] == "analyze"


def test_show_fresh_session(capsys):
    """show on fresh (empty) session returns step_id=0 and empty collections."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=_fresh_session()),
    ):
        rc = run(["show"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["step_id"] == 0
    assert out["resolved_nodes"] == []
    assert out["intent"] is None
    assert out["term_searched"] is False


def test_show_does_not_call_save_session():
    """show is read-only: save_session must not be called."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_session.load_session", return_value=_fresh_session()),
        patch("sdd.spatial.commands.nav_session.save_session") as mock_save,
    ):
        run(["show"])

    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Concurrency safety: lock timeout → nav_invariant_violation (I-SESSION-2)
# ---------------------------------------------------------------------------

def test_lock_timeout_on_next_returns_exit_2(capsys):
    """SessionLockTimeout during next → exit 2 + nav_invariant_violation on stderr (I-SESSION-2)."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch(
            "sdd.spatial.commands.nav_session.load_session",
            side_effect=SessionLockTimeout("session_lock_timeout"),
        ),
    ):
        rc = run(["next"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "nav_invariant_violation"
    assert err["invariant"] == "I-SESSION-2"
    assert err["reason"] == "session_lock_timeout"


def test_lock_timeout_on_show_returns_exit_2(capsys):
    """SessionLockTimeout during show → exit 2 + nav_invariant_violation on stderr (I-SESSION-2)."""
    with (
        patch("sdd.spatial.commands.nav_session.get_sdd_root", return_value=_FAKE_ROOT),
        patch(
            "sdd.spatial.commands.nav_session.load_session",
            side_effect=SessionLockTimeout("session_lock_timeout"),
        ),
    ):
        rc = run(["show"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "nav_invariant_violation"
    assert err["invariant"] == "I-SESSION-2"
