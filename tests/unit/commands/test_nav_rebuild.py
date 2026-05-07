"""Tests for sdd nav-rebuild command (T-1811).

Covers: dry-run, I-SI-4 diff on rename, I-TERM-1/I-TERM-2 link violations,
I-TERM-COVERAGE-1 warning, output JSON contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdd.spatial.commands.nav_rebuild import run
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    node_id: str = "COMMAND:complete",
    kind: str = "COMMAND",
    label: str = "sdd complete",
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path="src/sdd/commands/update_state.py",
        summary="Mark task DONE.",
        signature="def complete(...): ...",
        meta={},
        git_hash="deadbeef",
        indexed_at="2026-04-24T12:00:00Z",
    )


def _term_node(term_id: str = "activate_phase") -> SpatialNode:
    return SpatialNode(
        node_id=f"TERM:{term_id}",
        kind="TERM",
        label=term_id,
        path=None,
        summary="Human-only gate.",
        signature="",
        meta={},
        git_hash=None,
        indexed_at="2026-04-24T12:00:00Z",
        definition="Human-only gate that transitions a PLANNED phase to ACTIVE.",
        aliases=("phase activation",),
        links=("COMMAND:activate-phase",),
    )


def _make_index(
    nodes: dict | None = None,
    meta: dict | None = None,
    git_tree_hash: str | None = "tree_abc123",
) -> SpatialIndex:
    if nodes is None:
        nodes = {"COMMAND:complete": _node()}
    return SpatialIndex(
        nodes=nodes,
        built_at="2026-04-24T12:00:00Z",
        git_tree_hash=git_tree_hash,
        meta=meta or {},
    )


_FAKE_IDX = Path("/fake/spatial_index.json")
_FAKE_ROOT = Path("/fake/.sdd")


# ---------------------------------------------------------------------------
# Basic success + output JSON contract
# ---------------------------------------------------------------------------

def test_exit_0_success(capsys):
    """exit 0 on success; output JSON contains required fields."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert "nodes_written" in out
    assert "terms_written" in out
    assert "built_at" in out
    assert "git_tree_hash" in out


def test_nodes_written_matches_index_size(capsys):
    """nodes_written equals the number of nodes in the built index."""
    nodes = {
        "COMMAND:complete": _node("COMMAND:complete"),
        "COMMAND:validate": _node("COMMAND:validate", label="sdd validate"),
    }
    new_index = _make_index(nodes=nodes)

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["nodes_written"] == 2


def test_terms_written_counts_only_term_nodes(capsys):
    """terms_written counts only TERM-kind nodes."""
    nodes = {
        "COMMAND:complete": _node("COMMAND:complete"),
        "TERM:activate_phase": _term_node("activate_phase"),
        "TERM:complete_task": _term_node("complete_task"),
    }
    new_index = _make_index(nodes=nodes)

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["terms_written"] == 2


def test_git_tree_hash_in_output(capsys):
    """git_tree_hash from built index is included in output."""
    new_index = _make_index(git_tree_hash="abc123def456")

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["git_tree_hash"] == "abc123def456"


# ---------------------------------------------------------------------------
# --dry-run: does not write file
# ---------------------------------------------------------------------------

def test_dry_run_does_not_call_save_index(capsys):
    """--dry-run: save_index is never called."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index") as mock_save,
    ):
        rc = run(["--dry-run"])

    assert rc == 0
    mock_save.assert_not_called()


def test_dry_run_output_has_dry_run_flag(capsys):
    """--dry-run: output JSON contains dry_run=true."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run(["--dry-run"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out.get("dry_run") is True


def test_no_dry_run_calls_save_index(capsys):
    """Without --dry-run, save_index is called once."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index") as mock_save,
    ):
        rc = run([])

    assert rc == 0
    mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# I-SI-4: node_id drift detection on rename
# ---------------------------------------------------------------------------

def test_si4_exit_1_when_old_node_ids_disappear(capsys):
    """I-SI-4: exit 1 with diff when existing node_ids are absent in new build."""
    old_index = _make_index(nodes={"COMMAND:old-name": _node("COMMAND:old-name")})
    new_index = _make_index(nodes={"COMMAND:new-name": _node("COMMAND:new-name")})

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=True),
        patch("sdd.spatial.commands.nav_rebuild.load_index", return_value=old_index),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "error"
    assert err["error"] == "I-SI-4_violation"
    assert "COMMAND:old-name" in err["removed"]
    assert "COMMAND:new-name" in err["added"]


def test_si4_exit_0_when_only_new_nodes_added(capsys):
    """I-SI-4: exit 0 when old node_ids still present; only new ones added."""
    shared_node = _node("COMMAND:complete")
    old_index = _make_index(nodes={"COMMAND:complete": shared_node})
    new_nodes = {
        "COMMAND:complete": shared_node,
        "COMMAND:validate": _node("COMMAND:validate"),
    }
    new_index = _make_index(nodes=new_nodes)

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=True),
        patch("sdd.spatial.commands.nav_rebuild.load_index", return_value=old_index),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"


def test_si4_no_check_when_no_existing_index(capsys):
    """I-SI-4: check skipped when no previous index exists (first run)."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0


def test_si4_corrupt_old_index_does_not_block(capsys):
    """I-SI-4: if old index is corrupt (load fails), rebuild proceeds without error."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=True),
        patch("sdd.spatial.commands.nav_rebuild.load_index", side_effect=ValueError("corrupt")),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0


# ---------------------------------------------------------------------------
# I-TERM-1 / I-TERM-2: term link violations in output
# ---------------------------------------------------------------------------

def test_term_link_violations_included_in_output(capsys):
    """I-TERM-2: meta.term_link_violations from index are reported in output."""
    violations = [
        {"term": "TERM:activate_phase", "missing": ["COMMAND:activate-phas"], "severity": "warning"}
    ]
    new_index = _make_index(meta={"term_link_violations": violations})

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "term_link_violations" in out
    assert out["term_link_violations"][0]["term"] == "TERM:activate_phase"
    assert out["term_link_violations"][0]["severity"] == "warning"


def test_no_term_link_violations_key_when_none(capsys):
    """term_link_violations key absent from output when no violations."""
    new_index = _make_index(meta={})

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "term_link_violations" not in out


# ---------------------------------------------------------------------------
# I-TERM-COVERAGE-1: coverage_warning for commands without TERM
# ---------------------------------------------------------------------------

def test_coverage_warning_included_when_gaps_present(capsys):
    """I-TERM-COVERAGE-1: coverage_warning in output when commands lack TERM coverage."""
    gaps = ["COMMAND:show-path", "COMMAND:show-state"]
    new_index = _make_index(meta={"term_coverage_gaps": gaps})

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "coverage_warning" in out
    assert "COMMAND:show-path" in out["coverage_warning"]["uncovered"]
    assert "I-TERM-COVERAGE-1" in out["coverage_warning"]["message"]


def test_no_coverage_warning_when_all_commands_covered(capsys):
    """coverage_warning absent from output when all commands have TERM coverage."""
    new_index = _make_index(meta={})

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index),
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "coverage_warning" not in out


# ---------------------------------------------------------------------------
# --project-root override
# ---------------------------------------------------------------------------

def test_custom_project_root_passed_to_build_index(capsys):
    """--project-root argument is forwarded to build_index."""
    new_index = _make_index()

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index) as mock_build,
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run(["--project-root", "/custom/root"])

    assert rc == 0
    mock_build.assert_called_once_with("/custom/root")


def test_default_project_root_is_sdd_root_parent(capsys):
    """Default project_root = get_sdd_root().parent when --project-root not given."""
    new_index = _make_index()
    fake_root = MagicMock()
    fake_root.parent = Path("/project")

    with (
        patch("sdd.spatial.commands.nav_rebuild.get_sdd_root", return_value=fake_root),
        patch("sdd.spatial.commands.nav_rebuild.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_rebuild.build_index", return_value=new_index) as mock_build,
        patch("sdd.spatial.commands.nav_rebuild.os.path.isfile", return_value=False),
        patch("sdd.spatial.commands.nav_rebuild.save_index"),
    ):
        rc = run([])

    assert rc == 0
    mock_build.assert_called_once_with(str(Path("/project")))
