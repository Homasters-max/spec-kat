"""sdd.guards.norm — NormGuard CLI (Phase 8 re-home of norm_guard logic).

Checks actor/action against the SENAR norm catalog.
Exit: 0 = allowed, 1 = denied. JSON to stdout.
"""
from __future__ import annotations

import json
import sys

from sdd.infra import paths as _paths


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: norm_guard.py check --actor llm|human --action <action> [--catalog path]")
        return 0

    if args[0] != "check":
        print(json.dumps({"error": f"Unknown subcommand: {args[0]}"}))
        return 1

    actor = action = catalog_path = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--actor" and i + 1 < len(args):
            actor = args[i + 1]; i += 2
        elif a == "--action" and i + 1 < len(args):
            action = args[i + 1]; i += 2
        elif a == "--catalog" and i + 1 < len(args):
            catalog_path = args[i + 1]; i += 2
        else:
            i += 1

    if not actor or not action:
        print(json.dumps({"error": "Missing --actor or --action"}))
        return 1

    try:
        from sdd.domain.norms.catalog import load_catalog
        catalog = load_catalog(catalog_path or str(_paths.norm_catalog_file()))
    except Exception as e:
        print(json.dumps({"error": f"Cannot load catalog: {e}"}))
        return 1

    allowed = catalog.is_allowed(actor, action)
    norm_id = None
    if not allowed:
        for entry in catalog.entries:
            if (
                (entry.actor == actor or entry.actor == "any")
                and entry.action == action
                and entry.result == "forbidden"
            ):
                norm_id = entry.norm_id
                break

    print(json.dumps({
        "allowed": allowed,
        "actor": actor,
        "action": action,
        "norm_id": norm_id,
        "reason": "allowed" if allowed else f"forbidden by {norm_id}",
    }))
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
