"""Integration test: sdd nav-rebuild on real project root (T-1813).

Covers: I-SI-1, I-SI-4, I-DDD-0, I-GIT-OPTIONAL, BUG-4 regression guard.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _run_nav_rebuild(*extra_args: str) -> tuple[int, dict]:
    """Call nav_rebuild.run() with captured stdout; return (exit_code, parsed_json)."""
    from sdd.spatial.commands.nav_rebuild import run

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run(["--dry-run", "--project-root", str(PROJECT_ROOT), *extra_args])
    out = buf.getvalue().strip()
    data = json.loads(out) if out else {}
    return rc, data


# ---------------------------------------------------------------------------
# BUG-4 regression guard
# ---------------------------------------------------------------------------

def test_no_term_node_class() -> None:
    """BUG-4: class TermNode must not exist anywhere in src/sdd/."""
    src_sdd = PROJECT_ROOT / "src" / "sdd"
    violations: list[str] = []
    for py_file in src_sdd.rglob("*.py"):
        if "class TermNode" in py_file.read_text(encoding="utf-8"):
            violations.append(str(py_file.relative_to(PROJECT_ROOT)))
    assert not violations, f"BUG-4: class TermNode found in: {violations}"


# ---------------------------------------------------------------------------
# CLI entry point: exit 0 on real project root
# ---------------------------------------------------------------------------

def test_nav_rebuild_exit_zero() -> None:
    """sdd nav-rebuild exits 0 on real project root (--dry-run)."""
    rc, _ = _run_nav_rebuild()
    assert rc == 0, f"nav_rebuild.run() returned {rc} (expected 0)"


def test_nav_rebuild_nodes_written_gt_100() -> None:
    """nodes_written > 100."""
    rc, data = _run_nav_rebuild()
    assert rc == 0, f"run() failed with exit {rc}"
    assert data["nodes_written"] > 100, (
        f"nodes_written={data['nodes_written']} — expected > 100"
    )


def test_nav_rebuild_terms_written_ge_8() -> None:
    """terms_written >= 8 (I-DDD-0: glossary covers >= 8 domain concepts)."""
    rc, data = _run_nav_rebuild()
    assert rc == 0, f"run() failed with exit {rc}"
    assert data["terms_written"] >= 8, (
        f"terms_written={data['terms_written']} — expected >= 8"
    )


def test_nav_rebuild_git_tree_hash_key_present() -> None:
    """git_tree_hash key present in output (I-GIT-OPTIONAL: value may be None)."""
    rc, data = _run_nav_rebuild()
    assert rc == 0, f"run() failed with exit {rc}"
    assert "git_tree_hash" in data, "git_tree_hash key missing from nav-rebuild output"


# ---------------------------------------------------------------------------
# I-SI-1: no duplicate node_ids
# ---------------------------------------------------------------------------

def test_si1_no_duplicate_node_ids() -> None:
    """I-SI-1: build_index must produce unique node_ids (ValueError on violation)."""
    from sdd.spatial.index import build_index

    index = build_index(str(PROJECT_ROOT))
    ids = list(index.nodes.keys())
    assert len(ids) == len(set(ids)), (
        f"I-SI-1: duplicate node_ids: "
        f"{sorted(i for i in ids if ids.count(i) > 1)}"
    )


# ---------------------------------------------------------------------------
# I-SI-4: two consecutive rebuilds → identical node_ids
# ---------------------------------------------------------------------------

def test_si4_consecutive_rebuilds_identical_node_ids() -> None:
    """I-SI-4: two consecutive build_index calls produce the same node_id set."""
    from sdd.spatial.index import build_index

    index1 = build_index(str(PROJECT_ROOT))
    index2 = build_index(str(PROJECT_ROOT))
    ids1 = set(index1.nodes.keys())
    ids2 = set(index2.nodes.keys())
    removed = sorted(ids1 - ids2)
    added = sorted(ids2 - ids1)
    assert ids1 == ids2, (
        f"I-SI-4: node_id sets differ between two consecutive rebuilds\n"
        f"  removed: {removed}\n"
        f"  added:   {added}"
    )


# ---------------------------------------------------------------------------
# spatial_index.json: git_tree_hash persisted to disk
# ---------------------------------------------------------------------------

def test_git_tree_hash_in_saved_json() -> None:
    """git_tree_hash must be present in the persisted spatial_index.json."""
    from sdd.spatial.index import build_index, save_index

    index = build_index(str(PROJECT_ROOT))
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w"
    ) as f:
        tmp_path = f.name
    try:
        save_index(index, tmp_path)
        with open(tmp_path) as f:
            raw = json.load(f)
        assert "git_tree_hash" in raw, (
            "git_tree_hash key absent from saved spatial_index.json"
        )
    finally:
        os.unlink(tmp_path)
