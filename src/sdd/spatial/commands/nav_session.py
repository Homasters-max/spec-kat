"""sdd nav-session: manage NavigationSession lifecycle (BC-18-4, I-NAV-SESSION-1)."""
from __future__ import annotations

import argparse
import json
import sys

from sdd.infra.paths import get_sdd_root
from sdd.spatial.navigator import SessionLockTimeout, clear_session, load_session, save_session


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sdd nav-session")
    sub = p.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("next", help="Increment step_id (I-NAV-6/I-NAV-9)")
    sub.add_parser("clear", help="Remove nav_session.json")
    sub.add_parser("show", help="Print current session state")
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sdd_root = str(get_sdd_root())

    try:
        if args.subcommand == "next":
            session = load_session(sdd_root)
            session.next_step()
            save_session(session, sdd_root)
            print(json.dumps({"status": "ok", "step_id": session.step_id}))
            return 0

        if args.subcommand == "clear":
            clear_session(sdd_root)
            print(json.dumps({"status": "ok", "cleared": True}))
            return 0

        # show
        session = load_session(sdd_root)
        print(json.dumps({
            "step_id": session.step_id,
            "resolved_nodes": sorted(session.resolved_nodes),
            "loaded_modes": session.loaded_modes,
            "full_load_count_per_step": {
                str(k): v for k, v in session.full_load_count_per_step.items()
            },
            "intent": session.intent.type if session.intent else None,
            "term_searched": session.term_searched,
        }, indent=2))
        return 0

    except SessionLockTimeout:
        print(
            json.dumps({
                "status": "nav_invariant_violation",
                "invariant": "I-SESSION-2",
                "reason": "session_lock_timeout",
            }),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(run())
