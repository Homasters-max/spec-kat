"""sdd nav-search: fuzzy search over SpatialIndex (BC-18-4, I-SEARCH-2, I-FUZZY-1)."""
from __future__ import annotations

import argparse
import json
import sys

from sdd.infra.paths import get_sdd_root, spatial_index_file
from sdd.spatial.index import load_index
from sdd.spatial.navigator import Navigator


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sdd nav-search")
    p.add_argument("query", help="Search query string")
    p.add_argument(
        "--kind",
        default=None,
        help="Filter by node kind (FILE, COMMAND, TERM, etc.)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max number of results (default: 10)",
    )
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    index_path = str(spatial_index_file())
    sdd_root = str(get_sdd_root())

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

    nav = Navigator(index, session=None, project_root=sdd_root)
    results = nav.search(args.query, kind=args.kind, limit=args.limit)

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(run())
