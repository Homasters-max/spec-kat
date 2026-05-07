"""BC-43-E: Projector — apply domain events to p_* projection tables.

Invariants: I-PROJ-1, I-PROJ-NOOP-1, I-TABLE-SEP-1, I-EVENT-PURE-1
"""
from __future__ import annotations

import logging
import os
import types
from dataclasses import dataclass
from typing import Any, Callable

from sdd.core.events import DomainEvent
from sdd.db.connection import open_db_connection

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionRecord:
    """Immutable snapshot of a single non-invalidated session from p_sessions."""

    session_type: str
    phase_id: int | None
    task_id: str | None
    seq: int
    timestamp: str


@dataclass(frozen=True)
class SessionsView:
    """Immutable snapshot of non-invalidated sessions indexed for O(1) access.

    I-SESSIONSVIEW-O1-1: get_last is O(1) via _index keyed by (session_type, phase_id).
    I-GUARD-PURE-1: built before guard pipeline; guards do not receive it.
    """

    _index: dict[tuple[str, int | None], SessionRecord]

    def get_last(
        self,
        session_type: str,
        phase_id: int | None,
    ) -> SessionRecord | None:
        """O(1) lookup. Returns None if no non-invalidated session exists for key."""
        return self._index.get((session_type, phase_id))


# DDL for projection tables (I-PROJ-1: p_* = f(event_log))
_P_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS p_tasks (
    task_id           TEXT    PRIMARY KEY,
    phase_id          INTEGER NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'TODO',
    validation_result TEXT
)
"""

_P_PHASES_DDL = """
CREATE TABLE IF NOT EXISTS p_phases (
    phase_id   INTEGER PRIMARY KEY,
    status     TEXT    NOT NULL DEFAULT 'ACTIVE',
    is_current BOOLEAN NOT NULL DEFAULT FALSE
)
"""

_P_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS p_sessions (
    id           BIGSERIAL PRIMARY KEY,
    session_type TEXT    NOT NULL,
    phase_id     INTEGER,
    task_id      TEXT,
    seq          BIGINT  NOT NULL DEFAULT 0,
    timestamp    TEXT
)
"""

_P_SESSIONS_MIGRATION: list[str] = [
    "ALTER TABLE p_sessions ADD COLUMN IF NOT EXISTS seq BIGINT",
    "UPDATE p_sessions SET seq = 0 WHERE seq IS NULL",
    "ALTER TABLE p_sessions ALTER COLUMN seq SET NOT NULL",
]

_P_DECISIONS_DDL = """
CREATE TABLE IF NOT EXISTS p_decisions (
    decision_id TEXT    PRIMARY KEY,
    title       TEXT    NOT NULL,
    summary     TEXT,
    phase_id    INTEGER NOT NULL,
    timestamp   TEXT
)
"""

_P_INVARIANTS_DDL = """
CREATE TABLE IF NOT EXISTS p_invariants (
    invariant_id TEXT    PRIMARY KEY,
    phase_id     INTEGER NOT NULL,
    statement    TEXT    NOT NULL,
    timestamp    TEXT
)
"""

_P_SPECS_DDL = """
CREATE TABLE IF NOT EXISTS p_specs (
    phase_id  INTEGER NOT NULL,
    spec_hash TEXT    NOT NULL,
    actor     TEXT    NOT NULL DEFAULT 'human',
    spec_path TEXT    NOT NULL,
    PRIMARY KEY (phase_id, spec_hash)
)
"""

_P_DDL_STATEMENTS: list[str] = [
    _P_TASKS_DDL,
    _P_PHASES_DDL,
    _P_SESSIONS_DDL,
    _P_DECISIONS_DDL,
    _P_INVARIANTS_DDL,
    _P_SPECS_DDL,
]


class Projector:
    """Apply domain events to p_* projection tables.

    Idempotent: handlers use ON CONFLICT DO UPDATE or ON CONFLICT DO NOTHING.
    Unknown event types: NO-OP with DEBUG log (I-PROJ-NOOP-1).

    Connection lifecycle: single psycopg connection opened in __init__,
    reused across all apply() calls, closed in close() / __exit__.
    Use as context manager for rebuild (many events); for single events,
    _apply_projector_safe() calls close() after the batch.
    """

    def __init__(self, pg_url: str) -> None:
        if not pg_url:
            raise ValueError("pg_url must be non-empty")
        self._pg_url = pg_url
        self._conn = open_db_connection(pg_url)
        self._commit_deferred: bool = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create p_* projection tables if absent (I-PROJ-1, idempotent DDL)."""
        project = os.environ.get("SDD_PROJECT", "")
        cur = self._conn.cursor()
        if project:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS p_{project}")
            cur.execute("CREATE SCHEMA IF NOT EXISTS shared")
        for ddl in _P_DDL_STATEMENTS:
            cur.execute(ddl)
        for stmt in _P_SESSIONS_MIGRATION:
            cur.execute(stmt)
        self._commit()
        cur.close()

    def _commit(self) -> None:
        """Commit unless inside rebuild() transaction (I-REBUILD-ATOMIC-1)."""
        if not self._commit_deferred:
            self._conn.commit()

    def rebuild(self, pg_conn: Any) -> None:
        """Atomic rebuild: TRUNCATE p_* → replay event_log → apply all → UPDATE p_meta → COMMIT.

        I-REBUILD-ATOMIC-1: all writes execute inside a single transaction on pg_conn.
        I-PROJ-VERSION-1: p_meta.last_applied_sequence_id = MAX(event_log.sequence_id).
        I-REPLAY-1: replays all events from sequence_id=0 (after_seq=None).
        I-PROJ-WRITE-1: p_* tables written only via apply() dispatch.
        """
        from sdd.infra.event_log import PostgresEventLog  # noqa: PLC0415 — avoid circular at module level

        el = PostgresEventLog(self._pg_url)
        rows = el.replay()
        max_seq = el.max_seq() or 0

        saved_conn = self._conn
        self._conn = pg_conn
        self._commit_deferred = True
        try:
            cur = pg_conn.cursor()
            for table in ("p_tasks", "p_phases", "p_sessions", "p_decisions", "p_invariants", "p_specs"):
                cur.execute(f"TRUNCATE TABLE {table}")
            cur.close()

            for row in rows:
                payload = {k: v for k, v in (row.get("payload") or {}).items() if k != "event_type"}
                proxy = types.SimpleNamespace(event_type=row["event_type"], **payload)
                proxy.seq = row.get("sequence_id", 0)  # needed by _handle_session_declared
                self.apply(proxy)  # type: ignore[arg-type]

            cur = pg_conn.cursor()
            cur.execute(
                """
                INSERT INTO p_meta (singleton, last_applied_sequence_id, updated_at)
                VALUES (TRUE, %s, now())
                ON CONFLICT (singleton) DO UPDATE
                    SET last_applied_sequence_id = EXCLUDED.last_applied_sequence_id,
                        updated_at = EXCLUDED.updated_at
                """,
                (max_seq,),
            )
            cur.close()
            pg_conn.commit()
        except Exception:
            try:
                pg_conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._conn = saved_conn
            self._commit_deferred = False

    def apply(self, event: DomainEvent) -> None:
        """Apply one domain event to the appropriate p_* table (I-PROJ-1).

        Unknown event types: NO-OP + DEBUG log (I-PROJ-NOOP-1).
        Business logic in Python only; DB is storage only (I-EVENT-PURE-1).
        p_* and event_log tables never mixed in a single SQL query (I-TABLE-SEP-1).
        """
        handler = _HANDLERS.get(event.event_type)
        if handler is None:
            _log.debug(
                "Projector.apply: no handler for event_type=%r — NO-OP (I-PROJ-NOOP-1)",
                event.event_type,
            )
            return
        handler(self, event)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self) -> "Projector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- event handlers (one per event type, alphabetical) ---

    def _handle_decision_recorded(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_decisions (decision_id, title, summary, phase_id, timestamp)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (decision_id) DO NOTHING",
            (
                getattr(event, "decision_id", None),
                getattr(event, "title", None),
                getattr(event, "summary", None),
                getattr(event, "phase_id", None),
                getattr(event, "timestamp", None),
            ),
        )
        self._commit()
        cur.close()

    def _handle_invariant_registered(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_invariants (invariant_id, phase_id, statement, timestamp)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (invariant_id) DO UPDATE"
            "   SET statement = EXCLUDED.statement, phase_id = EXCLUDED.phase_id",
            (
                getattr(event, "invariant_id", None),
                getattr(event, "phase_id", None),
                getattr(event, "statement", None),
                getattr(event, "timestamp", None),
            ),
        )
        self._commit()
        cur.close()

    def _handle_phase_completed(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE p_phases SET status = 'COMPLETE' WHERE phase_id = %s",
            (getattr(event, "phase_id", None),),
        )
        self._commit()
        cur.close()

    def _handle_phase_context_switched(self, event: DomainEvent) -> None:
        to_phase = getattr(event, "to_phase", None)
        cur = self._conn.cursor()
        # Single-statement two-step: atomically reset all, set target (I-TABLE-SEP-1)
        cur.execute(
            "UPDATE p_phases SET is_current = (phase_id = %s)",
            (to_phase,),
        )
        self._commit()
        cur.close()

    def _handle_phase_initialized(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_phases (phase_id, status, is_current) VALUES (%s, 'ACTIVE', FALSE)"
            " ON CONFLICT (phase_id) DO UPDATE SET status = 'ACTIVE'",
            (getattr(event, "phase_id", None),),
        )
        self._commit()
        cur.close()

    def _handle_session_declared(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_sessions (session_type, phase_id, task_id, seq, timestamp)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                getattr(event, "session_type", None),
                getattr(event, "phase_id", None),
                getattr(event, "task_id", None),
                getattr(event, "seq", 0),
                getattr(event, "timestamp", None),
            ),
        )
        self._commit()
        cur.close()

    def _handle_spec_approved(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_specs (phase_id, spec_hash, actor, spec_path)"
            " VALUES (%s, %s, %s, %s) ON CONFLICT (phase_id, spec_hash) DO NOTHING",
            (
                getattr(event, "phase_id", None),
                getattr(event, "spec_hash", None),
                getattr(event, "actor", None),
                getattr(event, "spec_path", None),
            ),
        )
        self._commit()
        cur.close()

    def _handle_task_implemented(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO p_tasks (task_id, phase_id, status) VALUES (%s, %s, 'DONE')"
            " ON CONFLICT (task_id) DO UPDATE SET status = 'DONE'",
            (
                getattr(event, "task_id", None),
                getattr(event, "phase_id", None),
            ),
        )
        self._commit()
        cur.close()

    def _handle_task_validated(self, event: DomainEvent) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE p_tasks SET validation_result = %s WHERE task_id = %s",
            (
                getattr(event, "result", None),
                getattr(event, "task_id", None),
            ),
        )
        self._commit()
        cur.close()


def _sync_p_sessions(conn: Any) -> None:
    """Apply to p_sessions any SessionDeclared events not yet projected.

    Finds MAX(seq) already in p_sessions, then applies SessionDeclared events
    from event_log with sequence_id > MAX(seq), in sequence_id ASC order.
    I-PROJECTION-FRESH-1: must be called before build_sessions_view().
    """
    import json as _json

    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(seq), 0) FROM p_sessions")
    max_seq: int = cur.fetchone()[0]
    cur.execute(
        "SELECT sequence_id, payload FROM event_log"
        " WHERE event_type = 'SessionDeclared' AND sequence_id > %s"
        " ORDER BY sequence_id ASC",
        (max_seq,),
    )
    rows = cur.fetchall()
    for seq_id, raw_payload in rows:
        p: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else (_json.loads(raw_payload) if raw_payload else {})
        cur.execute(
            "INSERT INTO p_sessions (session_type, phase_id, task_id, seq, timestamp)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                p.get("session_type"),
                p.get("phase_id"),
                p.get("task_id"),
                seq_id,
                p.get("timestamp"),
            ),
        )
    conn.commit()
    cur.close()


def build_sessions_view(conn: Any) -> SessionsView:
    """Query p_sessions (post-sync) and return an immutable O(1)-indexed snapshot.

    Filters out entries whose seq appears in EventInvalidated target_seq values
    (I-INVALIDATION-FINAL-1, I-PROJECTION-SESSIONS-1).
    Processes rows ORDER BY seq ASC; last seq per (session_type, phase_id) wins
    (I-PROJECTION-ORDER-1).
    I-DEDUP-PROJECTION-CONSISTENCY-1: _sync_p_sessions() MUST be called before this.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT session_type, phase_id, task_id, seq, timestamp"
        " FROM p_sessions"
        " WHERE seq NOT IN ("
        "   SELECT DISTINCT (payload->>'target_seq')::BIGINT"
        "   FROM event_log"
        "   WHERE event_type = 'EventInvalidated'"
        " )"
        " ORDER BY seq ASC"
    )
    rows = cur.fetchall()
    cur.close()
    index: dict[tuple[str, int | None], SessionRecord] = {}
    for session_type, phase_id, task_id, seq, timestamp in rows:
        index[(session_type, phase_id)] = SessionRecord(
            session_type=session_type,
            phase_id=phase_id,
            task_id=task_id,
            seq=seq,
            timestamp=timestamp or "",
        )
    return SessionsView(_index=index)


# Module-level dispatch map — defined after class so references are valid (I-PROJ-NOOP-1)
_HANDLERS: dict[str, Callable[..., Any]] = {
    "DecisionRecorded": Projector._handle_decision_recorded,
    "InvariantRegistered": Projector._handle_invariant_registered,
    "PhaseCompleted": Projector._handle_phase_completed,
    "PhaseContextSwitched": Projector._handle_phase_context_switched,
    "PhaseInitialized": Projector._handle_phase_initialized,
    # PhaseStarted → NO-OP (I-PHASE-STARTED-1: informational only)
    "SessionDeclared": Projector._handle_session_declared,
    "SpecApproved": Projector._handle_spec_approved,
    "TaskImplemented": Projector._handle_task_implemented,
    "TaskValidated": Projector._handle_task_validated,
}
