"""BC-INFRA event log — sdd_append, sdd_append_batch, sdd_replay, meta_context.

Invariants: I-PK-2, I-PK-3, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12,
            I-EL-NON-KERNEL-1
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from sdd.core import classify_event_level
from sdd.core.errors import SDDError, StaleStateError
from sdd.core.events import DomainEvent
from sdd.core.execution_context import KernelContextError, assert_in_kernel, current_execution_context
from sdd.infra.db import open_sdd_connection
from sdd.infra.paths import is_production_event_store

_log = logging.getLogger(__name__)

class EventLogError(SDDError):
    """Raised when EventLog.append() cannot write to the EventLog."""


_VALID_SOURCES = frozenset({"meta", "runtime"})

# ContextVar for causal chain propagation (I-EL-8a)
_meta_seq_var: ContextVar[int | None] = ContextVar("_meta_seq_var", default=None)


@dataclass(frozen=True)
class EventInput:
    """Typed input for sdd_append_batch. All fields explicit — no silent defaults."""

    event_type: str
    payload: Mapping[str, Any]
    event_source: str = "runtime"
    level: str | None = None
    caused_by_meta_seq: int | None = None


def _make_event_id(event_type: str, payload: dict[str, Any], timestamp_ms: int) -> str:
    canonical_payload = json.dumps(payload, sort_keys=True)
    raw = (event_type + canonical_payload + str(timestamp_ms)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_source(event_source: str) -> None:
    if event_source not in _VALID_SOURCES:
        raise ValueError(
            f"event_source must be 'meta' or 'runtime', got {event_source!r}"
        )


def _resolve_caused_by(
    event_source: str,
    explicit: int | None,
) -> int | None:
    if explicit is not None:
        return explicit
    if event_source == "runtime":
        return _meta_seq_var.get()
    return None


def sdd_append(  # legacy: raw event write
    event_type: str,
    payload: dict[str, Any],
    db_path: str | None = None,
    level: str | None = None,
    event_source: str = "runtime",
    caused_by_meta_seq: int | None = None,
) -> None:
    _validate_source(event_source)
    # I-DB-WRITE-3, I-KERNEL-WRITE-1: production DB writes must go through execute_command
    if db_path is not None and is_production_event_store(db_path):
        if current_execution_context() != "execute_command":
            raise KernelContextError(
                f"sdd_append called outside execute_command (ctx={current_execution_context()!r})"
            )

    timestamp_ms = int(time.time() * 1000)
    resolved_level = level if level is not None else classify_event_level(event_type)
    event_id = _make_event_id(event_type, payload, timestamp_ms)
    resolved_caused_by = _resolve_caused_by(event_source, caused_by_meta_seq)
    payload_str = json.dumps(payload, sort_keys=True)

    assert db_path is not None, "I-DB-2: caller must resolve db_path before sdd_append"
    conn = open_sdd_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO events
                (seq, event_id, event_type, payload, schema_version,
                 appended_at, level, event_source, caused_by_meta_seq, expired, batch_id)
            VALUES
                (nextval('sdd_event_seq'), ?, ?, ?, 1,
                 ?, ?, ?, ?, FALSE, NULL)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [
                event_id, event_type, payload_str, timestamp_ms,
                resolved_level, event_source, resolved_caused_by,
            ],
        )
    finally:
        conn.close()


def sdd_append_batch(
    events: list[EventInput],
    db_path: str | None = None,
) -> None:
    """Write all events atomically in a single transaction (I-EL-11).

    I-EL-NON-KERNEL-1: MUST NOT be called inside execute_command.
    """
    # I-EL-NON-KERNEL-1: sdd_append_batch is the non-kernel write path (metrics, hooks,
    # bootstrap). Kernel code must use EventLog.append() instead.
    if current_execution_context() == "execute_command":
        raise KernelContextError(
            "sdd_append_batch MUST NOT be called inside execute_command (I-EL-NON-KERNEL-1)"
        )

    for ev in events:
        _validate_source(ev.event_source)

    assert db_path is not None, "I-DB-2: caller must resolve db_path before sdd_append_batch"
    batch_id = str(uuid.uuid4())
    conn = open_sdd_connection(db_path)
    try:
        conn.begin()
        timestamp_ms = int(time.time() * 1000)
        for ev in events:
            resolved_level = (
                ev.level if ev.level is not None
                else classify_event_level(ev.event_type)
            )
            payload_dict = dict(ev.payload)
            event_id = _make_event_id(ev.event_type, payload_dict, timestamp_ms)
            resolved_caused_by = _resolve_caused_by(ev.event_source, ev.caused_by_meta_seq)
            payload_str = json.dumps(payload_dict, sort_keys=True)

            conn.execute(
                """
                INSERT INTO events
                    (seq, event_id, event_type, payload, schema_version,
                     appended_at, level, event_source, caused_by_meta_seq, expired, batch_id)
                VALUES
                    (nextval('sdd_event_seq'), ?, ?, ?, 1,
                     ?, ?, ?, ?, FALSE, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [
                    event_id, ev.event_type, payload_str, timestamp_ms,
                    resolved_level, ev.event_source, resolved_caused_by, batch_id,
                ],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sdd_replay(
    after_seq: int | None = None,
    db_path: str | None = None,
    level: str = "L1",
    source: str = "runtime",
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    """Return events ordered by seq ASC (I-PK-3, I-EL-10)."""
    assert db_path is not None, "I-DB-2: caller must resolve db_path before sdd_replay"
    conn = open_sdd_connection(db_path, read_only=True)
    try:
        conditions = ["level = ?", "event_source = ?"]
        params: list[Any] = [level, source]

        if after_seq is not None:
            conditions.append("seq > ?")
            params.append(after_seq)

        if not include_expired:
            conditions.append("expired = FALSE")

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT seq, event_id, event_type, payload, schema_version, "
            f"appended_at, level, event_source, caused_by_meta_seq, expired "
            f"FROM events WHERE {where} ORDER BY seq ASC",
            params,
        ).fetchall()

        columns = [
            "seq", "event_id", "event_type", "payload", "schema_version",
            "appended_at", "level", "event_source", "caused_by_meta_seq", "expired",
        ]
        result = []
        for row in rows:
            record = dict(zip(columns, row, strict=False))
            try:
                record["payload"] = json.loads(record["payload"])
            except (TypeError, ValueError):
                pass
            result.append(record)
        return result
    finally:
        conn.close()


def archive_expired_l3(
    cutoff_ms: int,
    db_path: str | None = None,
) -> int:
    """Mark L3 events older than cutoff_ms as expired=TRUE. No DELETE ever issued (I-EL-7)."""
    assert db_path is not None, "I-DB-2: caller must resolve db_path before archive_expired_l3"
    conn = open_sdd_connection(db_path)
    try:
        conn.execute(
            "UPDATE events SET expired = TRUE "
            "WHERE level = 'L3' AND appended_at < ? AND expired = FALSE",
            [cutoff_ms],
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE level = 'L3' AND expired = TRUE "
            "AND appended_at < ?",
            [cutoff_ms],
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


@contextmanager
def meta_context(meta_seq: int) -> Generator[None, None, None]:
    """Propagate meta_seq as caused_by_meta_seq for all sdd_append calls within (I-EL-8a)."""
    token = _meta_seq_var.set(meta_seq)
    try:
        yield
    finally:
        _meta_seq_var.reset(token)


# DomainEvent base fields stored as dedicated DB columns — excluded from payload dict.
_BASE_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "event_id",
    "appended_at",
    "level",
    "event_source",
    "caused_by_meta_seq",
})

_VALID_OUTSIDE_KERNEL: frozenset[str] = frozenset({"bootstrap", "test", "metrics"})


@runtime_checkable
class EventLogKernelProtocol(Protocol):
    """Structural interface for EventLog used by the Write Kernel (I-ELK-PROTO-1).

    Any object implementing max_seq() and append() satisfies this protocol.
    """

    def max_seq(self) -> int | None: ...

    def append(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: Literal["bootstrap", "test", "metrics"] | None = None,
        batch_id: str | None = None,
    ) -> None: ...


class EventLog:
    """Single write path for all domain events (I-EL-UNIFIED-2, I-ES-1).

    append() is atomic: all events land in one DuckDB transaction.
    Locked and unlocked paths share the same transaction-capable implementation
    (I-EL-UNIFIED-2) — no separate _append_locked() method exists.
    """

    def __init__(self, db_path: str) -> None:
        if not db_path:
            raise ValueError("I-DB-1: db_path must be explicit non-empty str")
        self._db_path = db_path
        self._invalidated_cache: frozenset[int] | None = None

    def _get_invalidated_seqs(self) -> frozenset[int]:
        """Pre-scan EventInvalidated events with per-instance cache (I-INVALID-CACHE-1)."""
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

    def append(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: Literal["bootstrap", "test", "metrics"] | None = None,
        batch_id: str | None = None,
    ) -> None:
        """Atomically append *events* to the EventLog.

        Locked and unlocked paths share this single transaction-capable implementation
        (I-EL-UNIFIED-2). When command_id or expected_head are provided, the optimistic
        lock check and idempotency deduplication run inside the same transaction.

        batch_id: if None and len(events) > 1 → auto-generate UUID4 (I-EL-BATCH-ID-1).
                  if None and single event → write NULL.

        allow_outside_kernel: "bootstrap", "test", or "metrics" bypass the kernel guard.
            None (default) enforces I-KERNEL-WRITE-1 for production DB.

        Raises EventLogError on DB failure.
        Raises StaleStateError when expected_head != MAX(seq).
        Raises KernelContextError outside execute_command for production DB.
        Raises ValueError for unrecognized allow_outside_kernel value.
        """
        # I-INVALID-CACHE-1: reset per-instance cache on every append
        self._invalidated_cache = None

        if allow_outside_kernel is not None and allow_outside_kernel not in _VALID_OUTSIDE_KERNEL:
            raise ValueError(
                f"Invalid allow_outside_kernel={allow_outside_kernel!r}; "
                "allowed: 'bootstrap', 'test', 'metrics', None"
            )
        # I-KERNEL-WRITE-1: guard production DB writes
        if allow_outside_kernel is None:
            if is_production_event_store(self._db_path):
                assert_in_kernel("EventLog.append")

        if not events:
            return

        # I-EL-BATCH-ID-1: auto-generate batch_id for multi-event calls; single → NULL
        if batch_id is not None:
            effective_batch_id: str | None = batch_id
        elif len(events) > 1:
            effective_batch_id = str(uuid.uuid4())
        else:
            effective_batch_id = None

        conn = open_sdd_connection(self._db_path)
        try:
            conn.begin()
            timestamp_ms = int(time.time() * 1000)
            rows_inserted = 0

            # I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1: verify head inside transaction
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
                        continue

                resolved_level = event.level or classify_event_level(event.event_type)
                payload_str = json.dumps(payload, sort_keys=True)
                event_id = hashlib.sha256(
                    (event.event_type + payload_str + str(timestamp_ms)).encode()
                ).hexdigest()
                resolved_caused_by = _resolve_caused_by(event.event_source, event.caused_by_meta_seq)

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
                        effective_batch_id,
                    ],
                )
                rows_inserted += 1

            conn.commit()

            # I-IDEM-LOG-1: log INFO when all events were duplicates
            if rows_inserted == 0 and command_id is not None:
                _log.info(
                    "EventLog.append: all events already present for command_id=%s "
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
            raise EventLogError(f"EventLog.append() failed: {exc}") from exc
        finally:
            conn.close()

    def replay(
        self,
        after_seq: int | None = None,
        level: str = "L1",
        source: str = "runtime",
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """Return events ordered by seq ASC, excluding invalidated seqs (I-INVALID-2)."""
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
                _log.debug("EventLog.replay: skipping invalidated seq=%d", e["seq"])
                continue
            filtered.append(e)
        return filtered

    def max_seq(self) -> int | None:
        """Return MAX(seq) from the EventLog, or None if empty."""
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
            if row and row[0] is not None:
                return int(row[0])
            return None
        finally:
            conn.close()

    def exists_command(self, command_id: str) -> bool:
        """Return True if any non-expired event with payload.command_id exists (I-EL-DEEP-1)."""
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) > 0 FROM events "
                "WHERE json_extract_string(payload, '$.command_id') = ? AND expired = FALSE",
                [command_id],
            ).fetchone()
            return bool(row[0]) if row else False
        finally:
            conn.close()

    def exists_semantic(
        self,
        command_type: str,
        task_id: str | None,
        phase_id: int | None,
        payload_hash: str,
    ) -> bool:
        """Return True if matching (command_type, task_id, phase_id, payload_hash) exists (I-EL-DEEP-1)."""
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            parts = [
                "event_type = ?",
                "json_extract_string(payload, '$.payload_hash') = ?",
                "expired = FALSE",
            ]
            params: list[Any] = [command_type, payload_hash]

            if task_id is None:
                parts.append("json_extract_string(payload, '$.task_id') IS NULL")
            else:
                parts.append("json_extract_string(payload, '$.task_id') = ?")
                params.append(task_id)

            if phase_id is None:
                parts.append("json_extract(payload, '$.phase_id') IS NULL")
            else:
                parts.append("CAST(json_extract(payload, '$.phase_id') AS INTEGER) = ?")
                params.append(phase_id)

            sql = "SELECT COUNT(*) > 0 FROM events WHERE " + " AND ".join(parts)
            row = conn.execute(sql, params).fetchone()
            return bool(row[0]) if row else False
        finally:
            conn.close()

    def get_error_count(self, command_id: str) -> int:
        """Return count of ErrorEvent records for command_id (I-EL-DEEP-1)."""
        conn = open_sdd_connection(self._db_path, read_only=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM events "
                "WHERE event_type = 'ErrorEvent' "
                "AND json_extract_string(payload, '$.command_id') = ? "
                "AND expired = FALSE",
                [command_id],
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


# DDL statements for PostgresEventLog (I-PG-DDL-1)
_PG_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS event_log (
        event_id           UUID        PRIMARY KEY,
        event_type         TEXT        NOT NULL,
        payload            JSONB       NOT NULL,
        metadata           JSONB       DEFAULT '{}',
        created_at         TIMESTAMPTZ DEFAULT now(),
        sequence_id        BIGSERIAL   UNIQUE,
        level              TEXT        DEFAULT NULL,
        event_source       TEXT        NOT NULL DEFAULT 'runtime',
        caused_by_meta_seq BIGINT      DEFAULT NULL,
        expired            BOOLEAN     NOT NULL DEFAULT FALSE,
        batch_id           UUID        DEFAULT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_el_event_type ON event_log (event_type)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_el_cmd_idx
        ON event_log ((payload->>'command_id'), (payload->>'event_index'))
        WHERE payload->>'command_id' IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS p_meta (
        singleton                 BOOLEAN     PRIMARY KEY DEFAULT TRUE,
        last_applied_sequence_id  BIGINT      NOT NULL DEFAULT 0,
        updated_at                TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT p_meta_singleton CHECK (singleton = TRUE)
    )
    """,
    "INSERT INTO p_meta DEFAULT VALUES ON CONFLICT DO NOTHING",
]


class PostgresEventLog:
    """PostgreSQL EventLog implementation (BC-43-D, I-PG-DDL-1).

    Satisfies EventLogKernelProtocol structurally (I-ELK-PROTO-1).
    Table: event_log (UUID PK, JSONB payload, BIGSERIAL sequence_id UNIQUE).
    Idempotency via idx_el_cmd_idx partial UNIQUE index (I-IDEM-SCHEMA-1).
    Optimistic lock via MAX(sequence_id) check inside transaction (I-OPTLOCK-1).
    """

    def __init__(self, db_url: str) -> None:
        if not db_url:
            raise ValueError("I-DB-1: db_url must be explicit non-empty str")
        self._db_url = db_url
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create event_log, p_meta tables and indexes (idempotent, I-PG-DDL-1)."""
        conn = open_sdd_connection(self._db_url)
        try:
            for stmt in _PG_DDL:
                conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    def max_seq(self) -> int | None:
        """Return MAX(sequence_id) from event_log, or None if empty."""
        conn = open_sdd_connection(self._db_url)
        try:
            row = conn.execute(
                "SELECT MAX(sequence_id) FROM event_log"
            ).fetchone()
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
        allow_outside_kernel: Literal["bootstrap", "test", "metrics"] | None = None,
        batch_id: str | None = None,
    ) -> None:
        """Atomically append *events* to the PostgreSQL event_log.

        Optimistic lock (I-OPTLOCK-1): MAX(sequence_id) == expected_head checked inside TX.
        Idempotency (I-IDEM-SCHEMA-1): duplicate (command_id, event_index) pairs skipped.
        Raises StaleStateError when expected_head != MAX(sequence_id).
        Raises KernelContextError outside execute_command for production DB.
        Raises EventLogError on DB failure.
        """
        if allow_outside_kernel is not None and allow_outside_kernel not in _VALID_OUTSIDE_KERNEL:
            raise ValueError(
                f"Invalid allow_outside_kernel={allow_outside_kernel!r}; "
                "allowed: 'bootstrap', 'test', 'metrics', None"
            )
        if allow_outside_kernel is None and is_production_event_store(self._db_url):
            assert_in_kernel("PostgresEventLog.append")

        if not events:
            return

        if batch_id is not None:
            effective_batch_id: str | None = batch_id
        elif len(events) > 1:
            effective_batch_id = str(uuid.uuid4())
        else:
            effective_batch_id = None

        conn = open_sdd_connection(self._db_url)
        try:
            # I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1: verify head inside transaction
            if expected_head is not None:
                row = conn.execute(
                    "SELECT MAX(sequence_id) FROM event_log"
                ).fetchone()
                current_max: int | None = (
                    int(row[0]) if (row and row[0] is not None) else None
                )
                if current_max != expected_head:
                    conn.rollback()
                    raise StaleStateError(
                        f"I-OPTLOCK-1: EventLog head advanced: "
                        f"expected={expected_head}, current={current_max}"
                    )

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
                        "SELECT count(*) FROM event_log "
                        "WHERE payload->>'command_id' = %s "
                        "AND payload->>'event_index' = %s",
                        [command_id, str(event_index)],
                    ).fetchone()
                    if dup_row and dup_row[0] > 0:
                        continue

                resolved_level = event.level or classify_event_level(event.event_type)
                resolved_caused_by = _resolve_caused_by(
                    event.event_source, event.caused_by_meta_seq
                )
                event_id_pg = uuid.uuid4()
                batch_id_pg = uuid.UUID(effective_batch_id) if effective_batch_id else None

                conn.execute(
                    """
                    INSERT INTO event_log
                        (event_id, event_type, payload, level,
                         event_source, caused_by_meta_seq, expired, batch_id)
                    VALUES
                        (%s, %s, %s::jsonb, %s,
                         %s, %s, FALSE, %s)
                    """,
                    [
                        event_id_pg,
                        event.event_type,
                        json.dumps(payload, sort_keys=True),
                        resolved_level,
                        event.event_source,
                        resolved_caused_by,
                        batch_id_pg,
                    ],
                )
                rows_inserted += 1

            conn.commit()

            # I-IDEM-LOG-1: log INFO when all events were duplicates
            if rows_inserted == 0 and command_id is not None:
                _log.info(
                    "PostgresEventLog.append: all events already present for command_id=%s "
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
            raise EventLogError(f"PostgresEventLog.append() failed: {exc}") from exc
        finally:
            conn.close()

    def replay(
        self,
        after_seq: int | None = None,
        level: str = "L1",
        source: str = "runtime",
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """Return events ordered by sequence_id ASC (I-ORDER-1).

        payload is returned as dict (psycopg3 auto-deserializes JSONB; R-3 type guard applied).
        """
        conn = open_sdd_connection(self._db_url)
        try:
            conditions = ["level = %s", "event_source = %s"]
            params: list[Any] = [level, source]

            if after_seq is not None:
                conditions.append("sequence_id > %s")
                params.append(after_seq)

            if not include_expired:
                conditions.append("expired = FALSE")

            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT sequence_id, event_id, event_type, payload, "
                f"level, event_source, caused_by_meta_seq, expired, created_at "
                f"FROM event_log WHERE {where} ORDER BY sequence_id ASC",
                params,
            ).fetchall()

            columns = [
                "sequence_id", "event_id", "event_type", "payload",
                "level", "event_source", "caused_by_meta_seq", "expired", "created_at",
            ]
            result = []
            for row in rows:
                record = dict(zip(columns, row, strict=False))
                # JSONB type guard: psycopg3 returns dict; fallback for other drivers (R-3)
                raw = record["payload"]
                record["payload"] = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                result.append(record)
            return result
        finally:
            conn.close()

    def exists_command(self, command_id: str) -> bool:
        """Return True if any non-expired event with payload.command_id exists (I-EL-DEEP-1)."""
        conn = open_sdd_connection(self._db_url)
        try:
            row = conn.execute(
                "SELECT COUNT(*) > 0 FROM event_log "
                "WHERE payload->>'command_id' = %s AND expired = FALSE",
                [command_id],
            ).fetchone()
            return bool(row[0]) if row else False
        finally:
            conn.close()

    def exists_semantic(
        self,
        command_type: str,
        task_id: str | None,
        phase_id: int | None,
        payload_hash: str,
    ) -> bool:
        """Return True if matching (command_type, task_id, phase_id, payload_hash) exists."""
        conn = open_sdd_connection(self._db_url)
        try:
            parts = [
                "event_type = %s",
                "payload->>'payload_hash' = %s",
                "expired = FALSE",
            ]
            params: list[Any] = [command_type, payload_hash]

            if task_id is None:
                parts.append("payload->>'task_id' IS NULL")
            else:
                parts.append("payload->>'task_id' = %s")
                params.append(task_id)

            if phase_id is None:
                parts.append("(payload->'phase_id') IS NULL")
            else:
                parts.append("(payload->>'phase_id')::integer = %s")
                params.append(phase_id)

            sql = "SELECT COUNT(*) > 0 FROM event_log WHERE " + " AND ".join(parts)
            row = conn.execute(sql, params).fetchone()
            return bool(row[0]) if row else False
        finally:
            conn.close()

    def get_error_count(self, command_id: str) -> int:
        """Return count of ErrorEvent records for command_id."""
        conn = open_sdd_connection(self._db_url)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM event_log "
                "WHERE event_type = 'ErrorEvent' "
                "AND payload->>'command_id' = %s "
                "AND expired = FALSE",
                [command_id],
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
