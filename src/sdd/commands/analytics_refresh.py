"""Handler for `sdd analytics-refresh` — BC-32-4.

Creates/replaces analytics schema views for a project (I-DB-SCHEMA-1).
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel
from sdd.db.connection import open_sdd_connection

# Explicit column maps — SELECT * forbidden (I-DB-SCHEMA-1)
_ALL_EVENTS_VIEW = (
    "CREATE OR REPLACE VIEW analytics.all_events AS "
    "SELECT e.seq, e.event_id, e.event_type, e.phase_id, e.task_id, "
    "e.actor, e.payload, e.recorded_at FROM {schema}.events e"
)
_ALL_TASKS_VIEW = (
    "CREATE OR REPLACE VIEW analytics.all_tasks AS "
    "SELECT t.task_id, t.phase_id, t.status, t.origin_seq, t.last_seq, "
    "t.recorded_at FROM {schema}.tasks t"
)
_ALL_PHASES_VIEW = (
    "CREATE OR REPLACE VIEW analytics.all_phases AS "
    "SELECT ph.phase_id, ph.status, ph.spec_file, ph.plan_file, "
    "ph.activated_at, ph.completed_at, ph.meta FROM {schema}.phases ph"
)
_ALL_INVARIANTS_VIEW = (
    "CREATE OR REPLACE VIEW analytics.all_invariants AS "
    "SELECT ic.invariant_id, ic.phase_id, ic.result, ic.detail, "
    "ic.event_seq, ic.recorded_at FROM {schema}.invariants_current ic"
)

_ANALYTICS_VIEWS = [
    _ALL_EVENTS_VIEW,
    _ALL_TASKS_VIEW,
    _ALL_PHASES_VIEW,
    _ALL_INVARIANTS_VIEW,
]


@dataclass(frozen=True)
class AnalyticsRefreshedEvent(DomainEvent):
    """Emitted when analytics views are refreshed for a project."""

    project_name: str
    db_schema: str


class AnalyticsRefreshHandler(CommandHandlerBase):
    """Refresh analytics views to reference project schema (BC-32-4, I-DB-SCHEMA-1).

    Expects cmd.payload: {"name": str, "db_url": str | None}
    Connection resolved via payload.db_url → SDD_DATABASE_URL (I-DB-1).
    """

    @error_event_boundary(__name__)
    def handle(self, cmd: Any) -> list[DomainEvent]:
        payload = getattr(cmd, "payload", {})
        name: str = payload.get("name", "") or ""
        db_url: str | None = payload.get("db_url") or None

        if not name:
            raise ValueError("I-DB-SCHEMA-1: --name must be non-empty")

        db_schema = f"p_{name}"

        conn = open_sdd_connection(db_url=db_url)
        try:
            cur = conn.cursor()
            cur.execute("CREATE SCHEMA IF NOT EXISTS analytics")
            for view_sql in _ANALYTICS_VIEWS:
                cur.execute(view_sql.format(schema=db_schema))
            conn.commit()
        finally:
            conn.close()

        return [
            AnalyticsRefreshedEvent(
                event_type="AnalyticsRefreshed",
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="analytics_refresh",
                caused_by_meta_seq=None,
                project_name=name,
                db_schema=db_schema,
            )
        ]


def main(args: list[str] | None = None) -> int:
    """CLI entry for `sdd analytics-refresh`."""
    import types as _types

    parser = argparse.ArgumentParser(
        prog="sdd analytics-refresh",
        description="Refresh analytics views for a project schema (BC-32-4)",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Project name — views will reference schema p_{name}",
    )
    parser.add_argument(
        "--db-url",
        dest="db_url",
        default=None,
        help="PostgreSQL URL (overrides SDD_DATABASE_URL)",
    )
    ns = parser.parse_args(args)

    from sdd.commands.registry import REGISTRY, execute_and_project

    cmd = _types.SimpleNamespace(
        command_id=str(uuid.uuid4()),
        command_type="AnalyticsRefresh",
        payload={"name": ns.name, "db_url": ns.db_url},
        name=ns.name,
        db_url=ns.db_url,
        actor="llm",
    )
    execute_and_project(REGISTRY["analytics-refresh"], cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
