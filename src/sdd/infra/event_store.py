"""EventStore — single atomic write path for all domain events (I-ES-1).

Spec: Spec_v4 §4.12, §2.0 Canonical Data Flow; Spec_v15 §2 BC-15-REGISTRY A-17
Invariants: I-ES-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1, I-IDEM-SCHEMA-1, I-IDEM-LOG-1
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from sdd.core.errors import SDDError, StaleStateError
from sdd.core.events import DomainEvent
from sdd.core.execution_context import assert_in_kernel
from sdd.infra.db import open_sdd_connection
from sdd.infra.event_log import EventInput, sdd_append_batch

_log = logging.getLogger(__name__)

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

    When command_id and expected_head are provided, append() performs an optimistic
    lock check and command-level idempotency enforcement inside a single DuckDB
    transaction (A-17, I-OPTLOCK-ATOMIC-1, I-IDEM-SCHEMA-1).

    Callers in production:
      - execute_command()  — success path after handler returns events
      - execute_command()  — audit_events on guard DENY path
      - execute_command()  — error path (ErrorEvent)
    Nothing else calls append() directly.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._invalidated_cache: frozenset[int] | None = None

    def _get_invalidated_seqs(self) -> frozenset[int]:
        """Pre-scan EventInvalidated events with per-instance cache (I-INVALID-CACHE-1).

        Cache is reset to None on every append() call.
        Uses idx_event_type index for O(log N) scan.
        """
        if self._invalidated_cache is not None:
            return self._invalidated_cache
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            rows = conn.execute(
                "SELECT payload->>'target_seq' FROM events "
                "WHERE event_type = 'EventInvalidated'"
            ).fetchall()
        finally:
            conn.close()
        result = frozenset(int(r[0]) for r in rows if r[0] is not None)
        self._invalidated_cache = result
        return result

    def replay(
        self,
        after_seq: int | None = None,
        level: str = "L1",
        source: str = "runtime",
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """Replay events with pre-filter for invalidated seqs (I-INVALID-2).

        Invalidated events are excluded before returning to caller; reducer
        never receives them. Each filtered event is logged at DEBUG level.
        """
        from sdd.infra.event_log import sdd_replay
        invalidated = self._get_invalidated_seqs()
        raw_events = sdd_replay(
            after_seq=after_seq,
            db_path=self._db_path,
            level=level,
            source=source,
            include_expired=include_expired,
        )
        filtered = []
        for e in raw_events:
            if e["seq"] in invalidated:
                _log.debug("EventStore.replay: skipping invalidated seq=%d", e["seq"])
                continue
            filtered.append(e)
        return filtered

    def max_seq(self) -> int | None:
        """Return the current MAX(seq) from the EventLog, or None if empty."""
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
            if row and row[0] is not None:
                return int(row[0])
            return None
        finally:
            conn.close()

    def append(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: Literal["bootstrap", "test"] | None = None,
    ) -> None:
        """Atomically append *events* to the EventLog.

        source: module name of the emitter, stored in each event payload under
                "_source" for audit trail purposes.

        command_id: stable idempotency key (A-7). When provided, stored in each event
                    payload alongside event_index. Duplicate (command_id, event_index)
                    pairs within the EventLog are silently skipped; logs INFO when
                    rows_inserted == 0 (I-IDEM-LOG-1).

        expected_head: optimistic lock head (A-17, I-OPTLOCK-ATOMIC-1). When provided,
                       MAX(seq) is verified == expected_head inside the DuckDB transaction
                       before INSERT. Raises StaleStateError if head has advanced.

        allow_outside_kernel: bypass for authorized callers outside execute_command.
                              'bootstrap' — maintenance path (reconcile_bootstrap).
                              'test'      — test harness (fixtures.py, test seeding).
                              None        — default: kernel guard enforced for production DB.

        Raises EventStoreError on any DB write failure.
        Raises StaleStateError when expected_head does not match current MAX(seq).
        Raises KernelContextError when called on production DB outside execute_command.
        Raises ValueError when allow_outside_kernel has an unrecognized value.
        """
        # I-INVALID-CACHE-1: reset per-instance cache on every append
        self._invalidated_cache = None

        # I-KERNEL-WRITE-1, I-DB-WRITE-2: guard — production DB writes must be inside execute_command
        _VALID_BYPASS: frozenset[str] = frozenset({"bootstrap", "test"})
        if allow_outside_kernel is not None and allow_outside_kernel not in _VALID_BYPASS:
            raise ValueError(
                f"Invalid allow_outside_kernel={allow_outside_kernel!r}; "
                "allowed: 'bootstrap', 'test', None"
            )
        if allow_outside_kernel is None:
            from sdd.infra.paths import event_store_file
            if Path(self._db_path).resolve() == Path(str(event_store_file())).resolve():
                assert_in_kernel("EventStore.append")

        if not events:
            return

        if command_id is not None or expected_head is not None:
            self._append_locked(events, source, command_id, expected_head)
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

    def _append_locked(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None,
        expected_head: int | None,
    ) -> None:
        """Atomic check+INSERT path for optimistic locking and command idempotency.

        Implements I-OPTLOCK-ATOMIC-1: the MAX(seq) check and INSERTs run inside
        a single DuckDB transaction, eliminating TOCTOU gaps (A-17).

        Implements I-IDEM-SCHEMA-1: per-event uniqueness enforced via
        (command_id, event_index) check within the transaction before each INSERT.
        """
        batch_id = str(uuid.uuid4())
        conn = open_sdd_connection(self._db_path)
        try:
            conn.begin()

            # Optimistic lock: verify head has not advanced (I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1)
            if expected_head is not None:
                row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
                current_max: int | None = (
                    int(row[0]) if (row and row[0] is not None) else None
                )
                if current_max != expected_head:
                    conn.rollback()
                    raise StaleStateError(
                        f"I-OPTLOCK-1: EventLog head advanced: "
                        f"expected={expected_head}, current={current_max}"
                    )

            timestamp_ms = int(time.time() * 1000)
            rows_inserted = 0

            for event_index, event in enumerate(events):
                all_fields = asdict(event)
                payload: dict[str, Any] = {
                    k: v for k, v in all_fields.items() if k not in _BASE_FIELDS
                }
                payload["_source"] = source
                if command_id is not None:
                    payload["command_id"] = command_id
                    payload["event_index"] = event_index

                # I-IDEM-SCHEMA-1: skip duplicate (command_id, event_index) pairs
                if command_id is not None:
                    dup_row = conn.execute(
                        "SELECT count(*) FROM events "
                        "WHERE json_extract_string(payload, '$.command_id') = ? "
                        "AND json_extract_string(payload, '$.event_index') = ?",
                        [command_id, str(event_index)],
                    ).fetchone()
                    if dup_row and dup_row[0] > 0:
                        continue  # idempotent skip (ON CONFLICT DO NOTHING semantics)

                from sdd.core import classify_event_level
                resolved_level = event.level or classify_event_level(event.event_type)
                payload_str = json.dumps(payload, sort_keys=True)
                event_id = hashlib.sha256(
                    (event.event_type + payload_str + str(timestamp_ms)).encode()
                ).hexdigest()

                from sdd.infra.event_log import _resolve_caused_by
                resolved_caused_by = _resolve_caused_by(
                    event.event_source, event.caused_by_meta_seq
                )

                conn.execute(
                    """
                    INSERT INTO events
                        (seq, event_id, event_type, payload, schema_version,
                         appended_at, level, event_source, caused_by_meta_seq,
                         expired, batch_id)
                    VALUES
                        (nextval('sdd_event_seq'), ?, ?, ?, 1,
                         ?, ?, ?, ?, FALSE, ?)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    [
                        event_id, event.event_type, payload_str, timestamp_ms,
                        resolved_level, event.event_source, resolved_caused_by,
                        batch_id,
                    ],
                )
                rows_inserted += 1

            conn.commit()

            # I-IDEM-LOG-1: log INFO when all events were duplicates (rows_inserted == 0)
            if rows_inserted == 0 and command_id is not None:
                _log.info(
                    "EventStore.append: all events already present for command_id=%s "
                    "(idempotent no-op, I-IDEM-LOG-1)",
                    command_id,
                )

        except StaleStateError:
            raise
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise EventStoreError(f"EventStore._append_locked() failed: {exc}") from exc
        finally:
            conn.close()
