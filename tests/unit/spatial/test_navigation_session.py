"""Tests for NavigationSession — I-NAV-1, I-NAV-3, I-NAV-5, I-NAV-6, I-NAV-9,
I-NAV-SESSION-1, I-SESSION-2."""
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.spatial.navigator import (
    NavigationIntent,
    NavigationSession,
    SessionLockTimeout,
    _session_lock,
    clear_session,
    load_session,
    save_session,
)


@pytest.fixture
def sdd_root(tmp_path):
    root = tmp_path / ".sdd"
    (root / "state").mkdir(parents=True)
    return str(root)


# ---------------------------------------------------------------------------
# can_load_full — I-NAV-1
# ---------------------------------------------------------------------------


class TestCanLoadFull:
    def test_false_when_no_prior_load(self):
        session = NavigationSession(step_id=0)
        assert session.can_load_full("FILE:x") is False

    def test_false_when_only_pointer(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "POINTER")
        assert session.can_load_full("FILE:x") is False

    def test_true_after_summary(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SUMMARY")
        assert session.can_load_full("FILE:x") is True

    def test_true_after_signature(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SIGNATURE")
        assert session.can_load_full("FILE:x") is True

    def test_false_for_different_node(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SUMMARY")
        assert session.can_load_full("FILE:y") is False


# ---------------------------------------------------------------------------
# can_load_full_step — I-NAV-3, I-NAV-5, I-NAV-6
# ---------------------------------------------------------------------------


class TestCanLoadFullStep:
    def test_false_without_intent(self):
        session = NavigationSession(step_id=0)
        assert session.can_load_full_step(None) is False

    def test_false_with_explore_intent(self):
        session = NavigationSession(step_id=0)
        intent = NavigationIntent(type="explore")
        assert session.can_load_full_step(intent) is False

    def test_false_with_locate_intent(self):
        session = NavigationSession(step_id=0)
        intent = NavigationIntent(type="locate")
        assert session.can_load_full_step(intent) is False

    def test_false_with_analyze_intent(self):
        session = NavigationSession(step_id=0)
        intent = NavigationIntent(type="analyze")
        assert session.can_load_full_step(intent) is False

    def test_true_with_code_write_intent(self):
        session = NavigationSession(step_id=0)
        intent = NavigationIntent(type="code_write")
        assert session.can_load_full_step(intent) is True

    def test_true_with_code_modify_intent(self):
        session = NavigationSession(step_id=0)
        intent = NavigationIntent(type="code_modify")
        assert session.can_load_full_step(intent) is True

    def test_false_when_count_at_limit(self):
        session = NavigationSession(step_id=0)
        session.full_load_count_per_step[0] = 1
        intent = NavigationIntent(type="code_write")
        assert session.can_load_full_step(intent) is False

    def test_resets_after_next_step(self):
        session = NavigationSession(step_id=0)
        session.full_load_count_per_step[0] = 1
        session.next_step()
        intent = NavigationIntent(type="code_write")
        assert session.can_load_full_step(intent) is True


# ---------------------------------------------------------------------------
# next_step — I-NAV-6, I-NAV-9
# ---------------------------------------------------------------------------


class TestNextStep:
    def test_increments_step_id(self):
        session = NavigationSession(step_id=0)
        session.next_step()
        assert session.step_id == 1

    def test_resets_term_searched(self):
        session = NavigationSession(step_id=0, term_searched=True)
        session.next_step()
        assert session.term_searched is False

    def test_resets_intent(self):
        session = NavigationSession(step_id=0, intent=NavigationIntent(type="explore"))
        session.next_step()
        assert session.intent is None

    def test_preserves_resolved_nodes(self):
        session = NavigationSession(step_id=0)
        session.resolved_nodes.add("FILE:x")
        session.next_step()
        assert "FILE:x" in session.resolved_nodes

    def test_multiple_steps_accumulate(self):
        session = NavigationSession(step_id=5)
        session.next_step()
        session.next_step()
        assert session.step_id == 7


# ---------------------------------------------------------------------------
# record_load
# ---------------------------------------------------------------------------


class TestRecordLoad:
    def test_adds_to_resolved_nodes(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SUMMARY")
        assert "FILE:x" in session.resolved_nodes

    def test_updates_loaded_modes(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SUMMARY")
        assert session.loaded_modes["FILE:x"] == "SUMMARY"

    def test_full_increments_count_for_current_step(self):
        session = NavigationSession(step_id=2)
        session.record_load("FILE:x", "FULL")
        assert session.full_load_count_per_step[2] == 1

    def test_summary_does_not_increment_full_count(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "SUMMARY")
        assert session.full_load_count_per_step.get(0, 0) == 0

    def test_two_full_loads_same_step(self):
        session = NavigationSession(step_id=0)
        session.record_load("FILE:x", "FULL")
        session.record_load("FILE:y", "FULL")
        assert session.full_load_count_per_step[0] == 2


# ---------------------------------------------------------------------------
# load_session — I-NAV-SESSION-1
# ---------------------------------------------------------------------------


class TestLoadSession:
    def test_fresh_session_when_file_absent(self, sdd_root):
        session = load_session(sdd_root)
        assert isinstance(session, NavigationSession)
        assert session.step_id == 0

    def test_fresh_session_on_invalid_json(self, sdd_root, caplog):
        path = Path(sdd_root) / "state" / "nav_session.json"
        path.write_text("not valid json {{{{")
        with caplog.at_level(logging.WARNING, logger="sdd.spatial.navigator"):
            session = load_session(sdd_root)
        assert isinstance(session, NavigationSession)
        assert session.step_id == 0
        assert caplog.records  # warning was emitted

    def test_loads_saved_step_id(self, sdd_root):
        s = NavigationSession(step_id=3)
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.step_id == 3

    def test_loads_resolved_nodes(self, sdd_root):
        s = NavigationSession(step_id=0)
        s.record_load("FILE:x", "SUMMARY")
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert "FILE:x" in loaded.resolved_nodes

    def test_loads_loaded_modes(self, sdd_root):
        s = NavigationSession(step_id=0)
        s.record_load("FILE:x", "SIGNATURE")
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.loaded_modes.get("FILE:x") == "SIGNATURE"

    def test_loads_intent(self, sdd_root):
        s = NavigationSession(step_id=1, intent=NavigationIntent(type="code_write"))
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.intent is not None
        assert loaded.intent.type == "code_write"

    def test_none_intent_round_trips(self, sdd_root):
        s = NavigationSession(step_id=0, intent=None)
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.intent is None

    def test_loads_term_searched(self, sdd_root):
        s = NavigationSession(step_id=0, term_searched=True)
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.term_searched is True

    def test_loads_full_count_per_step(self, sdd_root):
        s = NavigationSession(step_id=2)
        s.record_load("FILE:x", "SUMMARY")
        s.record_load("FILE:x", "FULL")
        save_session(s, sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.full_load_count_per_step.get(2) == 1


# ---------------------------------------------------------------------------
# save_session — I-NAV-SESSION-1 (atomic write)
# ---------------------------------------------------------------------------


class TestSaveSession:
    def test_file_exists_after_save(self, sdd_root):
        session = NavigationSession(step_id=0)
        save_session(session, sdd_root)
        path = Path(sdd_root) / "state" / "nav_session.json"
        assert path.exists()

    def test_content_is_valid_json(self, sdd_root):
        session = NavigationSession(step_id=5)
        save_session(session, sdd_root)
        path = Path(sdd_root) / "state" / "nav_session.json"
        data = json.loads(path.read_text())
        assert data["step_id"] == 5

    def test_no_tmp_files_left_after_save(self, sdd_root):
        session = NavigationSession(step_id=0)
        save_session(session, sdd_root)
        tmp_files = list((Path(sdd_root) / "state").glob("*.tmp"))
        assert tmp_files == []

    def test_overwrite_existing_file(self, sdd_root):
        save_session(NavigationSession(step_id=1), sdd_root)
        save_session(NavigationSession(step_id=7), sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.step_id == 7

    def test_session_id_in_json(self, sdd_root):
        save_session(NavigationSession(step_id=0), sdd_root)
        data = json.loads(
            (Path(sdd_root) / "state" / "nav_session.json").read_text()
        )
        assert "session_id" in data
        assert data["session_id"]  # non-empty

    def test_updated_at_in_json(self, sdd_root):
        save_session(NavigationSession(step_id=0), sdd_root)
        data = json.loads(
            (Path(sdd_root) / "state" / "nav_session.json").read_text()
        )
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


class TestClearSession:
    def test_removes_file(self, sdd_root):
        save_session(NavigationSession(step_id=0), sdd_root)
        clear_session(sdd_root)
        assert not (Path(sdd_root) / "state" / "nav_session.json").exists()

    def test_noop_when_file_absent(self, sdd_root):
        clear_session(sdd_root)  # must not raise

    def test_fresh_session_after_clear(self, sdd_root):
        save_session(NavigationSession(step_id=5), sdd_root)
        clear_session(sdd_root)
        loaded = load_session(sdd_root)
        assert loaded.step_id == 0


# ---------------------------------------------------------------------------
# _session_lock — I-SESSION-2 (fcntl.flock)
# ---------------------------------------------------------------------------


class TestSessionLock:
    def test_uses_fcntl_flock(self, tmp_path):
        lock_path = str(tmp_path / "test.lock")
        with patch("sdd.spatial.navigator.fcntl.flock") as mock_flock:
            with _session_lock(lock_path):
                pass
        # at minimum: LOCK_EX|LOCK_NB acquire + LOCK_UN release
        assert mock_flock.call_count >= 2

    def test_lock_timeout_raises_session_lock_timeout(self, tmp_path):
        """I-SESSION-2: when lock cannot be acquired, SessionLockTimeout is raised."""
        lock_path = str(tmp_path / "timeout.lock")
        with patch(
            "sdd.spatial.navigator.fcntl.flock",
            side_effect=BlockingIOError("held"),
        ):
            with pytest.raises(SessionLockTimeout) as exc_info:
                with _session_lock(lock_path, timeout_secs=0):
                    pass
        assert exc_info.value.reason == "session_lock_timeout"

    def test_session_lock_timeout_has_reason_attribute(self):
        exc = SessionLockTimeout("session_lock_timeout")
        assert exc.reason == "session_lock_timeout"
