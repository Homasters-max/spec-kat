"""sdd nav-get: resolve a spatial node by ID (BC-18-4)."""
from __future__ import annotations

import argparse
import json
import sys

from sdd.infra.paths import get_sdd_root, spatial_index_file
from sdd.spatial.index import load_index
from sdd.spatial.navigator import NavigationIntent, Navigator, load_session, save_session
from sdd.spatial.staleness import is_stale


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sdd nav-get")
    p.add_argument("node_id", help="Node ID to resolve (e.g. COMMAND:complete)")
    p.add_argument(
        "--mode",
        choices=["POINTER", "SUMMARY", "SIGNATURE", "FULL"],
        default="SUMMARY",
    )
    p.add_argument(
        "--intent",
        choices=["explore", "locate", "analyze", "code_write", "code_modify"],
        default=None,
    )
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    index_path = str(spatial_index_file())
    sdd_root = str(get_sdd_root())

    # I-SI-3: all index data is available after load_index; no open() needed below
    try:
        index = load_index(index_path)
    except FileNotFoundError:
        print(
            json.dumps({
                "status": "error",
                "error": "index_not_found",
                "message": "Spatial index not found. Run: sdd nav-rebuild",
            }),
            file=sys.stderr,
        )
        return 2

    stale = is_stale(index, sdd_root)

    # I-NAV-SESSION-1: load session per call
    session = load_session(sdd_root)

    intent = NavigationIntent(type=args.intent) if args.intent else None

    nav = Navigator(index, session, project_root=sdd_root)
    result = nav.resolve(args.node_id, mode=args.mode, intent=intent)

    status = result.get("status")

    if status == "not_found":
        print(json.dumps(result))
        return 1

    if status == "nav_invariant_violation":
        print(json.dumps(result), file=sys.stderr)
        return 2

    # Successful resolve: attach index-level context anchor (BC-18-4 output contract)
    result["git_tree_hash"] = index.git_tree_hash
    result["deterministic"] = True
    if stale:
        result["stale_warning"] = True  # WEAK-2 fix

    # I-NAV-SESSION-1: record load, save session per call
    session.record_load(args.node_id, args.mode)
    save_session(session, sdd_root)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run())
