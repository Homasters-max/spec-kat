"""BC-INFRA event log — sdd_append, sdd_append_batch, sdd_replay, meta_context.

Invariants: I-PK-2, I-PK-3, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12
"""
from __future__ import annotations

import datetime
import hashlib
import json
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sdd.core import classify_event_level
from sdd.infra.db import open_sdd_connection

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


def sdd_append(
    event_type: str,
    payload: dict[str, Any],
    db_path: str | None = None,
    level: str | None = None,
    event_source: str = "runtime",
    caused_by_meta_seq: int | None = None,
) -> None:
    _validate_source(event_source)

    timestamp_ms = int(time.time() * 1000)
    resolved_level = level if level is not None else classify_event_level(event_type)
    event_id = _make_event_id(event_type, payload, timestamp_ms)
    resolved_caused_by = _resolve_caused_by(event_source, caused_by_meta_seq)
    payload_str = json.dumps(payload, sort_keys=True)

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
    """Write all events atomically in a single transaction (I-EL-11)."""
    for ev in events:
        _validate_source(ev.event_source)

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
    conn = open_sdd_connection(db_path)
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


def canonical_json(data: dict[str, Any]) -> str:
    """Stable JSON for payload_hash (I-CMD-2b): sorted keys, no whitespace, ISO8601 UTC, no sci notation."""

    def _default(obj: Any) -> Any:
        if isinstance(obj, datetime.datetime):
            if obj.tzinfo is None:
                return obj.strftime("%Y-%m-%dT%H:%M:%SZ")
            return obj.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        raise TypeError(f"Not serializable: {type(obj)!r}")

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)


def exists_command(db_path: str | None = None, *, command_id: str) -> bool:
    """Return True if any event with payload.command_id == command_id exists (I-CMD-10, I-EL-9)."""
    conn = open_sdd_connection(db_path)
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
    db_path: str | None = None,
    *,
    command_type: str,
    task_id: str | None,
    phase_id: int | None,
    payload_hash: str,
) -> bool:
    """Return True if an event matching (command_type, task_id, phase_id, payload_hash) exists (I-CMD-2b, I-CMD-10, I-EL-9)."""
    conn = open_sdd_connection(db_path)
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


def get_error_count(db_path: str | None = None, *, command_id: str) -> int:
    """Return count of ErrorEvent records with payload.command_id == command_id (I-CMD-10, I-EL-9)."""
    conn = open_sdd_connection(db_path)
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
