"""Tests for sdd nav-get command (T-1809)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.spatial.commands.nav_get import run
from sdd.spatial.index import SpatialIndex
from sdd.spatial.navigator import NavigationSession
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    node_id: str = "COMMAND:complete",
    kind: str = "COMMAND",
    label: str = "sdd complete",
    path: str | None = "src/sdd/commands/update_state.py",
    summary: str = "Mark task T-NNN DONE.",
    git_hash: str | None = "deadbeef",
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path=path,
        summary=summary,
        signature="def complete(...): ...",
        meta={},
        git_hash=git_hash,
        indexed_at="2026-04-24T12:00:00Z",
    )


def _make_index(
    nodes: dict | None = None,
    git_tree_hash: str | None = "tree_abc123",
) -> SpatialIndex:
    if nodes is None:
        nodes = {"COMMAND:complete": _node()}
    return SpatialIndex(
        nodes=nodes,
        built_at="2026-04-24T12:00:00Z",
        git_tree_hash=git_tree_hash,
    )


_FAKE_IDX = Path("/fake/spatial_index.json")
_FAKE_ROOT = Path("/fake/.sdd")


def _patches(*, stale: bool = False):
    """Stack of patches shared by most tests."""
    return [
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=stale),
        patch("sdd.spatial.commands.nav_get.load_session"),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ]


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

def test_exit_0_on_found(capsys):
    """exit 0 when node found; response contains required fields."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete", "--mode", "SUMMARY"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["node_id"] == "COMMAND:complete"
    assert out["kind"] == "COMMAND"


def test_exit_1_on_not_found(capsys):
    """exit 1 when node_id is not in index; response has status=not_found."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:nonexistent"])

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "not_found"
    assert out["must_not_guess"] is True


def test_exit_2_when_index_missing(capsys):
    """exit 2 when spatial_index.json does not exist yet."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", side_effect=FileNotFoundError),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "error"
    assert err["error"] == "index_not_found"


# ---------------------------------------------------------------------------
# git_tree_hash in successful response
# ---------------------------------------------------------------------------

def test_git_tree_hash_present_in_success(capsys):
    """git_tree_hash from index is included in every successful nav-get response."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index(git_tree_hash="abc456")),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["git_tree_hash"] == "abc456"
    assert out["deterministic"] is True


def test_git_tree_hash_none_when_index_has_no_hash(capsys):
    """git_tree_hash=null is valid when index was built without git."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index(git_tree_hash=None)),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "git_tree_hash" in out
    assert out["git_tree_hash"] is None


# ---------------------------------------------------------------------------
# stale_warning (WEAK-2 fix)
# ---------------------------------------------------------------------------

def test_stale_warning_true_when_index_stale(capsys):
    """stale_warning=true added to response when is_stale() returns True."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=True),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stale_warning"] is True


def test_no_stale_warning_when_index_fresh(capsys):
    """stale_warning absent when index is current."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "stale_warning" not in out


# ---------------------------------------------------------------------------
# Session persistence (I-NAV-SESSION-1)
# ---------------------------------------------------------------------------

def test_session_loaded_and_saved_on_success():
    """I-NAV-SESSION-1: load_session and save_session called exactly once per successful call."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)) as mock_load,
        patch("sdd.spatial.commands.nav_get.save_session") as mock_save,
    ):
        rc = run(["COMMAND:complete"])

    assert rc == 0
    assert mock_load.call_count == 1
    assert mock_save.call_count == 1


def test_session_not_saved_on_not_found():
    """Session is not saved when node is not found (no record_load to persist)."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session") as mock_save,
    ):
        rc = run(["COMMAND:nonexistent"])

    assert rc == 1
    mock_save.assert_not_called()


def test_session_record_load_reflects_mode():
    """After resolve, session.loaded_modes contains the resolved node at the given mode."""
    session = NavigationSession(step_id=0)
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=session),
        patch("sdd.spatial.commands.nav_get.save_session") as mock_save,
    ):
        rc = run(["COMMAND:complete", "--mode", "SUMMARY"])

    assert rc == 0
    # Verify save_session was called with the updated session
    saved_session = mock_save.call_args[0][0]
    assert saved_session.loaded_modes.get("COMMAND:complete") == "SUMMARY"


# ---------------------------------------------------------------------------
# --intent flag forwarded to resolve()
# ---------------------------------------------------------------------------

def test_intent_flag_forwarded_to_resolve():
    """--intent flag is passed to Navigator.resolve() as NavigationIntent."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
        patch("sdd.spatial.commands.nav_get.Navigator") as mock_nav_cls,
    ):
        mock_nav_instance = mock_nav_cls.return_value
        mock_nav_instance.resolve.return_value = {
            "node_id": "COMMAND:complete",
            "kind": "COMMAND",
            "label": "sdd complete",
            "path": "src/sdd/commands/update_state.py",
            "summary": "Mark task DONE.",
            "git_hash": None,
            "indexed_at": "2026-04-24T12:00:00Z",
        }
        run(["COMMAND:complete", "--mode", "SUMMARY", "--intent", "code_write"])

    _, kwargs = mock_nav_instance.resolve.call_args
    assert "intent" in kwargs
    assert kwargs["intent"] is not None
    assert kwargs["intent"].type == "code_write"


def test_no_intent_passes_none_to_resolve():
    """Without --intent, resolve() receives intent=None."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
        patch("sdd.spatial.commands.nav_get.Navigator") as mock_nav_cls,
    ):
        mock_nav_instance = mock_nav_cls.return_value
        mock_nav_instance.resolve.return_value = {
            "node_id": "COMMAND:complete",
            "kind": "COMMAND",
            "label": "sdd complete",
            "path": None,
            "summary": "Mark task DONE.",
            "git_hash": None,
            "indexed_at": "2026-04-24T12:00:00Z",
        }
        run(["COMMAND:complete"])

    _, kwargs = mock_nav_instance.resolve.call_args
    assert kwargs["intent"] is None


# ---------------------------------------------------------------------------
# I-SI-3: no open() after load_index
# ---------------------------------------------------------------------------

def test_si3_no_open_after_load_index_for_summary(capsys):
    """I-SI-3: nav-get does not call open() after load_index returns for SUMMARY mode."""
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
        patch("builtins.open") as mock_open,
    ):
        rc = run(["COMMAND:complete", "--mode", "SUMMARY"])

    assert rc == 0
    mock_open.assert_not_called()


def test_si3_response_data_matches_index(capsys):
    """I-SI-3: response fields (git_hash, summary) match what was in the index."""
    specific_node = _node(git_hash="cafebabe", summary="Unique summary for test")
    index = _make_index(
        nodes={"COMMAND:complete": specific_node},
        git_tree_hash="tree_deadbeef",
    )

    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=index),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete", "--mode", "SUMMARY"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["git_hash"] == "cafebabe"
    assert out["summary"] == "Unique summary for test"
    assert out["git_tree_hash"] == "tree_deadbeef"


# ---------------------------------------------------------------------------
# nav_invariant_violation (exit 2)
# ---------------------------------------------------------------------------

def test_exit_2_on_nav_invariant_violation(capsys):
    """exit 2 when resolve() returns nav_invariant_violation (e.g. I-NAV-1 violated)."""
    # Fresh session + FULL mode → I-NAV-1 violation (no prior SUMMARY/SIGNATURE)
    with (
        patch("sdd.spatial.commands.nav_get.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_get.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_get.load_index", return_value=_make_index()),
        patch("sdd.spatial.commands.nav_get.is_stale", return_value=False),
        patch("sdd.spatial.commands.nav_get.load_session", return_value=NavigationSession(step_id=0)),
        patch("sdd.spatial.commands.nav_get.save_session"),
    ):
        rc = run(["COMMAND:complete", "--mode", "FULL", "--intent", "code_write"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "nav_invariant_violation"
