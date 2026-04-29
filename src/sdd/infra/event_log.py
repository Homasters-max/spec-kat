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
from sdd.infra.el_kernel import EventLogKernel
from sdd.infra.paths import is_production_event_store

_kernel = EventLogKernel()

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
    h = hashlib.sha256(raw).hexdigest()
    # Format first 128 bits of SHA256 as UUID for PostgreSQL UUID column compatibility.
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


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


def sdd_append(  # non-kernel raw event write (hooks, metrics)
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

    assert db_path is not None, "I-DB-2: caller must resolve db_path before sdd_append"
    conn = open_sdd_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO event_log
                (event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired, batch_id)
            VALUES
                (%s, %s, %s::jsonb, %s, %s, %s, FALSE, NULL)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [
                event_id, event_type, json.dumps(payload, sort_keys=True),
                resolved_level, event_source, resolved_caused_by,
            ],
        )
        conn.commit()
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
        timestamp_ms = int(time.time() * 1000)
        for ev in events:
            resolved_level = (
                ev.level if ev.level is not None
                else classify_event_level(ev.event_type)
            )
            payload_dict = dict(ev.payload)
            event_id = _make_event_id(ev.event_type, payload_dict, timestamp_ms)
            resolved_caused_by = _resolve_caused_by(ev.event_source, ev.caused_by_meta_seq)

            conn.execute(
                """
                INSERT INTO event_log
                    (event_id, event_type, payload, level, event_source, caused_by_meta_seq, expired, batch_id)
                VALUES
                    (%s, %s, %s::jsonb, %s, %s, %s, FALSE, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [
                    event_id, ev.event_type, json.dumps(payload_dict, sort_keys=True),
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
            f"created_at, level, event_source, caused_by_meta_seq, expired "
            f"FROM event_log WHERE {where} ORDER BY sequence_id ASC",
            params,
        ).fetchall()

        result = []
        for seq_id, event_id, event_type, row_payload, created_at, lv, ev_src, caused_by, expired in rows:
            payload_dict: dict = (
                row_payload if isinstance(row_payload, dict)
                else (json.loads(row_payload) if row_payload else {})
            )
            record = {
                "seq": seq_id,  # backward-compat alias for sequence_id
                "event_id": event_id,
                "event_type": event_type,
                "payload": payload_dict,
                "appended_at": int(created_at.timestamp() * 1000) if created_at else None,
                "level": lv,
                "event_source": ev_src,
                "caused_by_meta_seq": caused_by,
                "expired": expired,
            }
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
            "UPDATE event_log SET expired = TRUE "
            "WHERE level = 'L3' AND created_at < to_timestamp(%s / 1000.0) AND expired = FALSE",
            [cutoff_ms],
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM event_log WHERE level = 'L3' AND expired = TRUE "
            "AND created_at < to_timestamp(%s / 1000.0)",
            [cutoff_ms],
        ).fetchone()
        conn.commit()
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
    """PostgreSQL-backed event log. SQL adapter only (BC-47-A, I-EL-KERNEL-1).

    Business logic (batch_id, optimistic lock, idempotency) delegated to EventLogKernel.
    This class: SQL specifics, psycopg3 connection, schema mapping.
    Satisfies EventLogKernelProtocol structurally (I-ELK-PROTO-1).
    Table: event_log (UUID PK, JSONB payload, BIGSERIAL sequence_id UNIQUE).
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

        # I-EL-BATCH-ID-1: delegate batch_id resolution to kernel
        effective_batch_id: str | None = (
            batch_id if batch_id is not None else _kernel.resolve_batch_id(events)
        )

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
                try:
                    _kernel.check_optimistic_lock(current_max, expected_head)
                except StaleStateError:
                    conn.rollback()
                    raise

            # Build payload dicts for all events (required for filter_duplicates)
            timestamp_ms = int(time.time() * 1000)
            event_payloads: list[tuple[DomainEvent, dict[str, Any]]] = []
            for event_index, event in enumerate(events):
                all_fields = asdict(event)
                payload: dict[str, Any] = {
                    k: v for k, v in all_fields.items() if k not in _BASE_FIELDS
                }
                payload["_source"] = source
                if command_id is not None:
                    payload["command_id"] = command_id
                    payload["event_index"] = event_index
                event_payloads.append((event, payload))

            # I-IDEM-SCHEMA-1: fetch existing (command_id, event_index) pairs once
            if command_id is not None:
                dup_rows = conn.execute(
                    "SELECT payload->>'command_id', (payload->>'event_index')::integer "
                    "FROM event_log "
                    "WHERE payload->>'command_id' = %s AND expired = FALSE",
                    [command_id],
                ).fetchall()
                existing_pairs: set[tuple[str, int]] = {
                    (r[0], int(r[1])) for r in dup_rows if r[0] is not None
                }
            else:
                existing_pairs = set()

            # Delegate duplicate filtering to kernel
            payload_dicts = [p for _, p in event_payloads]
            to_insert_payloads, _ = _kernel.filter_duplicates(payload_dicts, existing_pairs)
            to_insert_ids = {id(p) for p in to_insert_payloads}

            rows_inserted = 0
            for event, payload in event_payloads:
                if id(payload) not in to_insert_ids:
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


# EventLog alias (DuckDB implementation removed in T-4609; PostgresEventLog is the sole impl)
EventLog = PostgresEventLog


def open_event_log(db_path: str) -> PostgresEventLog:
    """Factory: returns PostgresEventLog for the given PG URL."""
    return PostgresEventLog(db_path)
