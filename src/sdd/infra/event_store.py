"""EventStore — single atomic write path for all domain events (I-ES-1).

Spec: Spec_v4 §4.12, §2.0 Canonical Data Flow
Invariant: I-ES-1
"""
from __future__ import annotations

from dataclasses import asdict

from sdd.core.errors import SDDError
from sdd.core.events import DomainEvent
from sdd.infra.event_log import EventInput, sdd_append_batch

# DomainEvent base fields stored as dedicated DB columns — excluded from payload dict.
_BASE_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "event_id",
    "appended_at",
    "level",
    "event_source",
    "caused_by_meta_seq",
})


class EventStoreError(SDDError):
    """Raised when EventStore.append() cannot write to the EventLog."""


class EventStore:
    """Single write path for all domain events (I-ES-1).

    append() is atomic: delegates to sdd_append_batch so the entire list lands in
    one DB transaction.  A failure raises EventStoreError — callers MUST NOT fall
    back to direct file mutation (I-ES-1 write-order invariant).

    Callers in production:
      - CommandRunner.run()  — success path after handler returns events
      - CommandRunner.run()  — audit_events on guard DENY path
      - error_event_boundary — ErrorEvent on exception path (sole handler-side exception)
    Nothing else calls append() directly.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def append(self, events: list[DomainEvent], source: str) -> None:
        """Atomically append *events* to the EventLog.

        source: module name of the emitter, stored in each event payload under
                "_source" for audit trail purposes.
        Raises EventStoreError on any DB write failure.
        """
        if not events:
            return

        inputs: list[EventInput] = []
        for event in events:
            all_fields = asdict(event)
            payload = {k: v for k, v in all_fields.items() if k not in _BASE_FIELDS}
            payload["_source"] = source

            inputs.append(EventInput(
                event_type=event.event_type,
                payload=payload,
                event_source=event.event_source,
                level=event.level,
                caused_by_meta_seq=event.caused_by_meta_seq,
            ))

        try:
            sdd_append_batch(inputs, db_path=self._db_path)
        except Exception as exc:
            raise EventStoreError(f"EventStore.append() failed: {exc}") from exc
