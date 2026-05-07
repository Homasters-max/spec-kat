"""Tests for sdd nav-search command (T-1810, I-SEARCH-2, I-FUZZY-1, I-NAV-4)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.spatial.commands.nav_search import run
from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    node_id: str,
    kind: str,
    label: str,
    summary: str = "A test node.",
    aliases: tuple[str, ...] = (),
) -> SpatialNode:
    return SpatialNode(
        node_id=node_id,
        kind=kind,
        label=label,
        path=None,
        summary=summary,
        signature="",
        meta={},
        git_hash=None,
        indexed_at="2026-04-24T12:00:00Z",
        aliases=aliases,
    )


def _make_index(nodes: dict | None = None) -> SpatialIndex:
    if nodes is None:
        nodes = {}
    return SpatialIndex(
        nodes=nodes,
        built_at="2026-04-24T12:00:00Z",
        git_tree_hash="tree_abc123",
    )


_FAKE_IDX = Path("/fake/spatial_index.json")
_FAKE_ROOT = Path("/fake/.sdd")


def _patches():
    return [
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
    ]


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

def test_exit_0_on_empty_results(capsys):
    """exit 0 even when no results match."""
    index = _make_index({"COMMAND:complete": _node("COMMAND:complete", "COMMAND", "sdd complete")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["zzzzzzzzunmatched"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list)


def test_exit_0_on_found(capsys):
    """exit 0 when results found; response is a list."""
    index = _make_index({"COMMAND:complete": _node("COMMAND:complete", "COMMAND", "complete")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["complete"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out, list)
    assert len(out) >= 1


def test_exit_2_when_index_missing(capsys):
    """exit 2 when spatial_index.json does not exist."""
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", side_effect=FileNotFoundError),
    ):
        rc = run(["anything"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["status"] == "error"
    assert err["error"] == "index_not_found"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

def test_result_contains_required_fields(capsys):
    """Each result item contains node_id, kind, label, score."""
    index = _make_index({"COMMAND:complete": _node("COMMAND:complete", "COMMAND", "complete")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["complete"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) >= 1
    item = items[0]
    assert "node_id" in item
    assert "kind" in item
    assert "label" in item
    assert "score" in item


# ---------------------------------------------------------------------------
# I-FUZZY-1: TERM aliases included in search keys
# ---------------------------------------------------------------------------

def test_fuzzy1_alias_match_finds_term(capsys):
    """I-FUZZY-1: a TERM node is found when query matches one of its aliases (not its suffix)."""
    # TERM:xyznode has suffix "xyznode" which is far from "done".
    # But alias "done" gives distance 0 — should be found.
    index = _make_index({
        "TERM:xyznode": _node(
            "TERM:xyznode", "TERM", "XYZ Node",
            aliases=("done",),
        ),
    })
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["done"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    node_ids = [i["node_id"] for i in items]
    assert "TERM:xyznode" in node_ids


def test_fuzzy1_alias_distance_leq2(capsys):
    """I-FUZZY-1: fuzzy threshold ≤ 2; alias 'actvate' (typo) still matches."""
    index = _make_index({
        "TERM:activate_phase": _node(
            "TERM:activate_phase", "TERM", "Activate Phase",
            aliases=("activate",),
        ),
    })
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["actvate"])  # distance = 1 from "activate"

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    node_ids = [i["node_id"] for i in items]
    assert "TERM:activate_phase" in node_ids


# ---------------------------------------------------------------------------
# Namespace priority: TERM > COMMAND > TASK > FILE (I-KIND-PRIORITY, I-NAV-4)
# ---------------------------------------------------------------------------

def test_term_ranked_before_command_with_same_query(capsys):
    """TERM node ranks before COMMAND when both match equally (kind priority)."""
    index = _make_index({
        "TERM:complete": _node("TERM:complete", "TERM", "complete"),
        "COMMAND:complete": _node("COMMAND:complete", "COMMAND", "complete"),
    })
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["complete"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) >= 2
    kinds = [i["kind"] for i in items]
    term_pos = kinds.index("TERM")
    command_pos = kinds.index("COMMAND")
    assert term_pos < command_pos


# ---------------------------------------------------------------------------
# I-SEARCH-2: pipeline collect → sort → limit → render
# ---------------------------------------------------------------------------

def test_search2_limit_applied_before_render(capsys):
    """I-SEARCH-2: --limit N returns at most N results."""
    nodes = {
        f"COMMAND:cmd{i}": _node(f"COMMAND:cmd{i}", "COMMAND", f"cmd{i}")
        for i in range(10)
    }
    index = _make_index(nodes)
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["cmd", "--limit", "3"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) <= 3


def test_search2_default_limit_10(capsys):
    """I-SEARCH-2: default limit is 10."""
    nodes = {
        f"COMMAND:cmd{i}": _node(f"COMMAND:cmd{i}", "COMMAND", f"cmd{i}")
        for i in range(20)
    }
    index = _make_index(nodes)
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["cmd"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) <= 10


def test_search2_sort_before_limit(capsys):
    """I-SEARCH-2: sort is applied to full candidate set before limit (best results first)."""
    nodes = {
        "TERM:exact": _node("TERM:exact", "TERM", "exact"),
        "COMMAND:exacts": _node("COMMAND:exacts", "COMMAND", "exacts"),
        "TASK:exactx": _node("TASK:exactx", "TASK", "exactx"),
    }
    index = _make_index(nodes)
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["exact", "--limit", "1"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    # With limit=1 and sort, the exact-match TERM should win (distance=0, kind_priority=0)
    assert len(items) == 1
    assert items[0]["node_id"] == "TERM:exact"


# ---------------------------------------------------------------------------
# --kind filter
# ---------------------------------------------------------------------------

def test_kind_filter_excludes_other_kinds(capsys):
    """--kind TERM returns only TERM nodes."""
    index = _make_index({
        "TERM:foo": _node("TERM:foo", "TERM", "foo"),
        "COMMAND:foo": _node("COMMAND:foo", "COMMAND", "foo"),
    })
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["foo", "--kind", "TERM"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert all(i["kind"] == "TERM" for i in items)
    assert any(i["node_id"] == "TERM:foo" for i in items)


def test_kind_filter_returns_empty_when_no_match(capsys):
    """--kind TERM returns empty list when only COMMAND nodes exist."""
    index = _make_index({"COMMAND:foo": _node("COMMAND:foo", "COMMAND", "foo")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        rc = run(["foo", "--kind", "TERM"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert items == []


# ---------------------------------------------------------------------------
# Score field correctness
# ---------------------------------------------------------------------------

def test_score_in_range_0_1(capsys):
    """score is a float in [0.0, 1.0]."""
    index = _make_index({"COMMAND:complete": _node("COMMAND:complete", "COMMAND", "complete")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        run(["complete"])

    items = json.loads(capsys.readouterr().out)
    for item in items:
        assert 0.0 <= item["score"] <= 1.0


def test_exact_match_has_score_1(capsys):
    """Exact match (distance=0) has score=1.0."""
    index = _make_index({"COMMAND:complete": _node("COMMAND:complete", "COMMAND", "complete")})
    with (
        patch("sdd.spatial.commands.nav_search.spatial_index_file", return_value=_FAKE_IDX),
        patch("sdd.spatial.commands.nav_search.get_sdd_root", return_value=_FAKE_ROOT),
        patch("sdd.spatial.commands.nav_search.load_index", return_value=index),
    ):
        run(["complete"])

    items = json.loads(capsys.readouterr().out)
    assert items[0]["score"] == 1.0
