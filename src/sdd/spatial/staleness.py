"""Staleness detection for SpatialIndex via git tree hash comparison (BC-18-2)."""
from __future__ import annotations

import subprocess

from sdd.spatial.index import SpatialIndex


def current_git_hash(path: str, project_root: str) -> str | None:
    """Return blob SHA for path via git ls-files -s (O(1)); fallback git hash-object."""
    try:
        r = subprocess.run(
            ["git", "ls-files", "-s", path],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            if len(parts) >= 2:
                return parts[1]
        r2 = subprocess.run(
            ["git", "hash-object", path],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if r2.returncode == 0 and r2.stdout.strip():
            return r2.stdout.strip()
    except Exception:
        pass
    return None


def _head_tree_hash(project_root: str) -> str | None:
    """Return current HEAD commit hash; None if git unavailable (I-GIT-OPTIONAL)."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def is_stale(index: SpatialIndex, project_root: str) -> bool:
    """True if HEAD changed since index was built; False if git unavailable (I-GIT-OPTIONAL).

    I-SI-5: index.git_tree_hash != current HEAD → index is stale, rebuild required.
    I-GIT-OPTIONAL: git unavailable or index built without git → False (never blocks work).
    """
    if index.git_tree_hash is None:
        return False
    head = _head_tree_hash(project_root)
    if head is None:
        return False
    return index.git_tree_hash != head


def staleness_report(index: SpatialIndex, project_root: str) -> dict:
    """Return staleness metadata: stale, index_tree, head_tree, reason."""
    head = _head_tree_hash(project_root)
    stale = is_stale(index, project_root)
    if head is None:
        reason = "git_unavailable"
    elif index.git_tree_hash is None:
        reason = "index_built_without_git"
    elif stale:
        reason = "head_changed"
    else:
        reason = "up_to_date"
    return {
        "stale": stale,
        "index_tree": index.git_tree_hash,
        "head_tree": head,
        "reason": reason,
    }
