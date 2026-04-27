"""rebuild-state command handler (I-STATE-REBUILD-1, I-1).

Triggers full projection rebuild from seq=0 via project_all(ProjectionType.FULL).
I-STATE-REBUILD-1 equivalence is verified by tests:
    reduce(all_events) == IncrementalReducer().apply_delta_from_scratch(all_events)
"""
from __future__ import annotations

from sdd.commands._base import CommandHandlerBase
from sdd.core.events import DomainEvent


class RebuildStateHandler(CommandHandlerBase):
    """Returns empty events — State_index rebuild delegated to project_all (I-HANDLER-PURE-1, I-1)."""

    def __init__(self, db_path: str) -> None:
        self._db = db_path

    def handle(self, cmd: object) -> list[DomainEvent]:
        return []
