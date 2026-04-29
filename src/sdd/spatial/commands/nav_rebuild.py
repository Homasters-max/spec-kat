"""sdd nav-rebuild: build and save SpatialIndex (BC-18-4)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sdd.infra.paths import get_sdd_root, spatial_index_file
from sdd.spatial.index import build_index, load_index, save_index


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sdd nav-rebuild")
    p.add_argument(
        "--project-root",
        default=None,
        help="Project root directory (default: parent of SDD_HOME)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute index but do not write to disk",
    )
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    project_root = args.project_root or str(get_sdd_root().parent)
    index_path = str(spatial_index_file())

    new_index = build_index(project_root)

    # I-SI-4: detect node_id drift vs existing index (renamed = removed from old + new appeared)
    if os.path.isfile(index_path):
        try:
            old_index = load_index(index_path)
            old_ids = set(old_index.nodes)
            new_ids = set(new_index.nodes)
            removed = sorted(old_ids - new_ids)
            if removed:
                added = sorted(new_ids - old_ids)
                print(
                    json.dumps({
                        "status": "error",
                        "error": "I-SI-4_violation",
                        "message": "node_id drift detected: existing nodes absent in new index",
                        "removed": removed,
                        "added": added,
                    }, indent=2),
                    file=sys.stderr,
                )
                return 1
        except Exception:
            pass  # corrupt or missing old index: skip I-SI-4 check

    terms_written = sum(1 for n in new_index.nodes.values() if n.kind == "TERM")

    result: dict[str, Any] = {
        "status": "ok",
        "nodes_written": len(new_index.nodes),
        "terms_written": terms_written,
        "built_at": new_index.built_at,
        "git_tree_hash": new_index.git_tree_hash,
    }

    if new_index.meta.get("term_link_violations"):
        result["term_link_violations"] = new_index.meta["term_link_violations"]

    if new_index.meta.get("term_coverage_gaps"):
        result["coverage_warning"] = {
            "message": "Commands without TERM coverage (I-TERM-COVERAGE-1)",
            "uncovered": new_index.meta["term_coverage_gaps"],
        }

    if args.dry_run:
        result["dry_run"] = True
    else:
        save_index(new_index, index_path)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run())
