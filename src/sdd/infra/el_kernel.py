"""EventLogKernel — pure Python business logic for event log writes (BC-46-A).

No SQL, no psycopg. PostgresEventLog delegates here.
I-EL-KERNEL-1 (Phase 47): enforcement grep-test for no psycopg imports added in BC-47-A.
"""
from __future__ import annotations

import uuid
from typing import Any

from sdd.core.errors import StaleStateError


class EventLogKernel:
    """Business logic for event log writes: optimistic lock, idempotency, batch ID.

    I-EL-KERNEL-WIRED-1: PostgresEventLog.append() delegates to all three methods.
    Phase 46: module created and wired; Phase 47: no-psycopg enforcement verified.
    """

    def resolve_batch_id(self, events: list[Any]) -> str | None:
        """I-EL-BATCH-ID-1: UUID4 for multi-event calls, None for single."""
        return str(uuid.uuid4()) if len(events) > 1 else None

    def check_optimistic_lock(
        self,
        current_max: int | None,
        expected_head: int | None,
    ) -> None:
        """I-OPTLOCK-1: raise StaleStateError if current_max != expected_head.

        Both None → skip check (initial empty log or lock not required).
        expected_head None → skip check unconditionally.
        """
        if expected_head is not None and current_max != expected_head:
            raise StaleStateError(
                f"I-OPTLOCK-1: EventLog head advanced: "
                f"expected={expected_head}, current={current_max}"
            )

    def filter_duplicates(
        self,
        events: list[dict[str, Any]],
        existing_pairs: set[tuple[str, int]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """I-IDEM-SCHEMA-1: split events into (to_insert, skipped) lists.

        existing_pairs: set of (command_id, event_index) already in event_log.
        An event without command_id is never considered a duplicate.
        Returns (to_insert, skipped) — order preserved, identity stable.
        """
        to_insert: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for event in events:
            cmd_id = event.get("command_id")
            if cmd_id is not None and (cmd_id, event.get("event_index", 0)) in existing_pairs:
                skipped.append(event)
            else:
                to_insert.append(event)
        return to_insert, skipped
