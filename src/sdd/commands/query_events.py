from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Protocol

from sdd.core.errors import SDDError
from sdd.infra.event_query import EventLogQuerier, EventRecord, QueryFilters
from sdd.infra.paths import event_store_file


class QueryHandler(Protocol):
    """Read-side handler protocol. Distinct from CommandHandler (write-side)."""

    def execute(self, query: QueryEventsCommand) -> QueryEventsResult: ...


@dataclass(frozen=True)
class QueryEventsCommand:
    filters: QueryFilters


@dataclass(frozen=True)
class QueryEventsResult:
    events: tuple[EventRecord, ...]
    total: int


class QueryEventsHandler:
    """
    Thin wrapper over EventLogQuerier. Conforms to QueryHandler Protocol.
    No state between calls (I-PROJ-CONST-2).
    No DB writes (I-PROJ-CONST-1).
    """

    def __init__(self, db_path: str) -> None:
        self._querier = EventLogQuerier(db_path)

    def execute(self, query: QueryEventsCommand) -> QueryEventsResult:
        """
        Calls EventLogQuerier.query(query.filters) → returns QueryEventsResult.
        Never calls CommandRunner or any other CommandHandler (I-CHAIN-1).
        """
        events = self._querier.query(query.filters)
        return QueryEventsResult(events=events, total=len(events))


# ---------------------------------------------------------------------------
# CLI entry point (I-CLI-2)
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="query-events")
    parser.add_argument("--phase", type=int, default=None)
    parser.add_argument("--event", default=None, dest="event_type")
    parser.add_argument("--source", default=None, dest="event_source")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--order", choices=["ASC", "DESC"], default="ASC")
    parser.add_argument("--replay", action="store_true", help="Filter to L1 domain events")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--db", default=str(event_store_file()))
    parsed = parser.parse_args(args)
    try:
        filters = QueryFilters(
            phase_id=parsed.phase,
            event_type=parsed.event_type,
            event_source=parsed.event_source,
            limit=parsed.limit,
            order=parsed.order,
        )
        result = QueryEventsHandler(parsed.db).execute(QueryEventsCommand(filters=filters))
        events = result.events
        if parsed.replay:
            events = tuple(e for e in events if e.level == "L1")
        if parsed.as_json:
            import dataclasses
            print(json.dumps([dataclasses.asdict(e) for e in events], default=str))
        else:
            for e in events:
                print(f"{e.seq}\t{e.event_type}\t{e.level}\t{e.event_source}")
        return 0
    except SDDError:
        return 1
    except Exception:
        return 2
