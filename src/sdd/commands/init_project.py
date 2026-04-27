"""Handler for `sdd init-project` — BC-32-0, BC-32-1.

Invariants: I-DB-SCHEMA-1, I-DB-1
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sdd.commands._base import CommandHandlerBase, error_event_boundary
from sdd.core.events import DomainEvent, EventLevel
from sdd.db.connection import open_sdd_connection

_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_SHARED_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS shared.projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    db_schema  TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta       JSONB NOT NULL DEFAULT '{}'
)
"""


@dataclass(frozen=True)
class ProjectInitializedEvent(DomainEvent):
    """Emitted when a PostgreSQL project schema is successfully created."""
    project_name: str
    db_schema: str    # always p_{project_name} — I-DB-SCHEMA-1
    project_id: str


class InitProjectHandler(CommandHandlerBase):
    """Create PostgreSQL project schema and register in shared.projects.

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
        if not _VALID_NAME.match(name):
            raise ValueError(
                f"I-DB-SCHEMA-1: project name {name!r} must match [a-z][a-z0-9_]*"
            )

        db_schema = f"p_{name}"
        project_id = str(uuid.uuid4())

        conn = open_sdd_connection(db_url=db_url)
        try:
            cur = conn.cursor()
            # BC-32-0: shared schema + projects table
            cur.execute("CREATE SCHEMA IF NOT EXISTS shared")
            cur.execute(_SHARED_PROJECTS_DDL)
            # BC-32-1: project-isolated schema (I-DB-SCHEMA-1)
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {db_schema}")
            cur.execute(
                "INSERT INTO shared.projects (id, name, db_schema)"
                " VALUES (%s, %s, %s)"
                " ON CONFLICT (db_schema) DO NOTHING",
                (project_id, name, db_schema),
            )
            conn.commit()
        finally:
            conn.close()

        return [
            ProjectInitializedEvent(
                event_type="ProjectInitialized",
                event_id=str(uuid.uuid4()),
                appended_at=int(time.time() * 1000),
                level=EventLevel.L1,
                event_source="init_project",
                caused_by_meta_seq=None,
                project_name=name,
                db_schema=db_schema,
                project_id=project_id,
            )
        ]
