from __future__ import annotations

from dataclasses import dataclass

from sdd.infra.db import open_sdd_connection


@dataclass(frozen=True)
class EventRecord:
    seq: int
    event_type: str
    payload: str
    event_source: str
    level: str | None
    expired: bool
    caused_by_meta_seq: int | None


@dataclass(frozen=True)
class QueryFilters:
    phase_id: int | None = None
    event_type: str | None = None
    event_source: str | None = None
    include_expired: bool = False
    limit: int | None = None
    order: str = "ASC"
    batch_id: str | None = None
    is_batched: bool | None = None
    task_id: str | None = None


class EventLogQuerier:
    """Read-only query path. Never calls sdd_append or modifies DB.

    I-PROJ-CONST-1: same db_path + same filters → same result (deterministic).
    I-PROJ-CONST-2: no shared state between calls; no hidden caching.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def query(self, filters: QueryFilters) -> tuple[EventRecord, ...]:
        """
        I-QE-1: ordered by seq ASC/DESC per filters.order
        I-QE-2: event_source filter is exact — no partial matches
        I-QE-3: expired=true rows excluded when include_expired=False (default)
        I-QE-4: phase_id filter matches JSON_EXTRACT(payload, '$.phase_id')
        """
        conditions: list[str] = []
        params: list[object] = []

        if not filters.include_expired:
            conditions.append("expired = FALSE")

        if filters.event_source is not None:
            conditions.append("event_source = ?")
            params.append(filters.event_source)

        if filters.event_type is not None:
            conditions.append("event_type = ?")
            params.append(filters.event_type)

        if filters.phase_id is not None:
            conditions.append(
                "CAST(json_extract_string(payload, '$.phase_id') AS INTEGER) = ?"
            )
            params.append(filters.phase_id)

        if filters.task_id is not None:
            conditions.append(
                "json_extract_string(payload, '$.task_id') = ?"
            )
            params.append(filters.task_id)

        if filters.batch_id is not None:
            conditions.append("batch_id = ?")
            params.append(filters.batch_id)
        elif filters.is_batched is True:
            conditions.append("batch_id IS NOT NULL")
        elif filters.is_batched is False:
            conditions.append("batch_id IS NULL")

        order = "ASC" if filters.order == "ASC" else "DESC"
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f"LIMIT {filters.limit}" if filters.limit is not None else ""

        sql = (
            f"SELECT seq, event_type, payload, event_source, level, expired,"
            f" caused_by_meta_seq"
            f" FROM events {where} ORDER BY seq {order} {limit_clause}"
        )

        conn = open_sdd_connection(self._db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return tuple(
            EventRecord(
                seq=row[0],
                event_type=row[1],
                payload=row[2],
                event_source=row[3],
                level=row[4],
                expired=row[5],
                caused_by_meta_seq=row[6],
            )
            for row in rows
        )
