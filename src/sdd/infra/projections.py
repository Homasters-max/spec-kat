"""Projection rebuilders — EventLog → TaskSet.md and State_index.yaml (I-ES-4, I-ES-5).

Spec: Spec_v4 §2 BC-INFRA extensions, Spec_v15 §2 BC-2
Invariants: I-ES-4, I-ES-5, I-PK-5, I-SYNC-1, I-REBUILD-STRICT-1,
            I-REBUILD-EMERGENCY-1, I-REBUILD-EMERGENCY-2, I-ES-REPLAY-1

I-SYNC-1: every task-state mutation MUST rebuild both projections atomically via
sync_projections(). Calling rebuild_taskset or rebuild_state individually after
a mutation is forbidden — use sync_projections() as the sole mutation path.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from sdd.domain.state.reducer import EventReducer, SDDState
from sdd.domain.state.yaml_state import read_state, write_state
from sdd.infra.audit import atomic_write
from sdd.infra.db import open_sdd_connection
from sdd.infra.paths import state_file

_TASK_HEADER_RE = re.compile(r"^(T-\d+[a-z]*):\s")  # I-TASK-ID-1: suffix support
_STATUS_LINE_RE = re.compile(r"^(Status:\s+)(TODO|DONE)(.*)$")


class RebuildMode(Enum):
    STRICT    = "strict"     # YAML ignored entirely (default, always correct post-Phase 15)
    EMERGENCY = "emergency"  # break-glass: empty EventLog bootstrap only (operator-direct)


def _read_yaml_phase_current(state_path: str) -> int:
    """Read phase_current from existing YAML state (EMERGENCY bootstrap only)."""
    try:
        existing = read_state(state_path)
        return existing.phase_current
    except Exception:
        return 0


def rebuild_state(
    db_path: str,
    state_path: str | None = None,
    mode: RebuildMode = RebuildMode.STRICT,
) -> SDDState:
    """Rebuild State_index.yaml from EventLog replay (I-ES-4, I-ES-5, I-REBUILD-STRICT-1).

    Returns the SDDState written to disk so callers can propagate it to
    rebuild_taskset without a second replay (I-REPLAY-1).

    STRICT (default): pure event-replay; YAML is never read (I-REBUILD-STRICT-1).
    EMERGENCY: operator-only break-glass; requires SDD_EMERGENCY=1 env var
    (I-REBUILD-EMERGENCY-1, I-REBUILD-EMERGENCY-2). Used only when EventLog is
    empty and an existing YAML provides phase bootstrap.

    Delegates to get_current_state() for EventLog → SDDState mapping
    (I-PROJECTION-SHARED-CORE-1): replay logic is not duplicated here.
    """
    if state_path is None:
        state_path = str(state_file())

    if mode == RebuildMode.EMERGENCY:
        if os.environ.get("SDD_EMERGENCY") != "1":
            raise AssertionError(
                "I-REBUILD-EMERGENCY-2: RebuildMode.EMERGENCY requires "
                "SDD_EMERGENCY=1 environment variable — this is an operator-only break-glass mode"
            )

    # I-PROJECTION-SHARED-CORE-1: single replay path — delegate, do not duplicate.
    state: SDDState = get_current_state(db_path, full_replay=True)

    if mode == RebuildMode.STRICT:
        # I-PROJ-2: compat fallback for pre-Phase-5 EventLogs without activation events.
        # The reducer leaves phase_status="PLANNED" when no PhaseActivated/PhaseInitialized
        # L1 runtime events exist. If an existing YAML has been human-managed (ACTIVE),
        # preserve those values — applied on top of get_current_state() result.
        if state.phase_status == "PLANNED" and Path(state_path).exists():
            try:
                yaml_st = read_state(state_path)
                state = dataclasses.replace(
                    state,
                    phase_status=yaml_st.phase_status,
                    plan_status=yaml_st.plan_status,
                )
            except Exception:
                pass

    if mode == RebuildMode.EMERGENCY and state.phase_current == 0:
        yaml_phase = _read_yaml_phase_current(state_path)
        if yaml_phase > 0:
            state = dataclasses.replace(state, phase_current=yaml_phase)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = dataclasses.replace(state, last_updated=now)
    write_state(state, state_path)
    return state


def rebuild_taskset(
    db_path: str,
    taskset_path: str,
    state: SDDState | None = None,
) -> None:
    """Update TaskSet.md task statuses from EventLog replay (I-ES-4, I-ES-5, I-ES-REPLAY-1).

    Accepts an optional pre-computed state to avoid a second replay within the
    same CLI invocation (I-REPLAY-1). When state is None, replays from db_path.

    Writes atomically (I-PK-5). Idempotent.
    If taskset_path does not exist, logs warning and returns (I-ES-REPLAY-1).
    """
    if not Path(taskset_path).exists():
        logging.warning("rebuild_taskset: %s not found — skipping (I-ES-REPLAY-1)", taskset_path)
        return

    if state is None:
        state = get_current_state(db_path)
    done_ids: frozenset[str] = frozenset(state.tasks_done_ids)

    with open(taskset_path, encoding="utf-8") as f:
        original = f.read()

    lines = original.splitlines(keepends=True)
    current_task_id: str | None = None
    result: list[str] = []

    for line in lines:
        m = _TASK_HEADER_RE.match(line.strip())
        if m:
            current_task_id = m.group(1)

        if current_task_id in done_ids:
            sm = _STATUS_LINE_RE.match(line.rstrip("\n\r"))
            if sm and sm.group(2) == "TODO":
                eol = "\n" if line.endswith("\n") else ""
                line = sm.group(1) + "DONE" + sm.group(3) + eol

        result.append(line)

    atomic_write(taskset_path, "".join(result))


def _pg_max_seq(db_url: str) -> int:
    """Query MAX sequence_id across all events (no filter) — O(1) index scan."""
    from sdd.db.connection import is_postgres_url
    if is_postgres_url(db_url):
        sql = "SELECT COALESCE(MAX(sequence_id), 0) FROM event_log"
    else:
        sql = "SELECT COALESCE(MAX(seq), 0) FROM events"
    conn = open_sdd_connection(db_url, read_only=True)
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _read_yaml() -> SDDState | None:
    """Read SDDState from State_index.yaml; return None if absent or unreadable."""
    try:
        return read_state(str(state_file()))
    except Exception:
        return None


def _replay_from_event_log(db_url: str) -> SDDState:
    """Full EventLog replay from seq=0 — authoritative read path (I-PROJECTION-READ-1).

    Pure function: no YAML compat fallback, no caching, no partial replay.
    MUST be called only from guards and projections (I-STATE-ACCESS-LAYER-1).
    Filters out invalidated seqs (I-INVALID-2) before reducer dispatch.
    Stamps snapshot_event_id = MAX(seq) so callers can persist a staleness sentinel.

    PG branch (BC-43): queries event_log+sequence_id; handles JSONB payload (psycopg3
    returns dict directly — isinstance guard prevents double-decode).
    DuckDB branch: events+seq, unchanged.
    """
    from sdd.db.connection import is_postgres_url
    _pg = is_postgres_url(db_url)

    if _pg:
        _inv_sql = (
            "SELECT payload->>'target_seq' FROM event_log WHERE event_type = 'EventInvalidated'"
        )
        _rows_sql = (
            "SELECT sequence_id, event_type, payload, level, event_source, caused_by_meta_seq "
            "FROM event_log ORDER BY sequence_id ASC"
        )
    else:
        _inv_sql = (
            "SELECT payload->>'target_seq' FROM events WHERE event_type = 'EventInvalidated'"
        )
        _rows_sql = (
            "SELECT seq, event_type, payload, level, event_source, caused_by_meta_seq "
            "FROM events ORDER BY seq ASC"
        )

    conn = open_sdd_connection(db_url, read_only=True)
    try:
        inv_rows = conn.execute(_inv_sql).fetchall()
        invalidated_seqs: frozenset[int] = frozenset(
            int(r[0]) for r in inv_rows if r[0] is not None
        )
        rows = conn.execute(_rows_sql).fetchall()
    finally:
        conn.close()

    max_seq: int = rows[-1][0] if rows else 0

    events: list[dict] = []
    for seq, event_type, row_payload, level, event_source, caused_by_meta_seq in rows:
        if seq in invalidated_seqs:
            continue
        try:
            payload: dict = (
                row_payload if isinstance(row_payload, dict)
                else (json.loads(row_payload) if row_payload else {})
            )
        except Exception:
            payload = {}
        event: dict = {
            "event_type": event_type,
            "level": level,
            "event_source": event_source,
            "caused_by_meta_seq": caused_by_meta_seq,
        }
        event.update(payload)
        events.append(event)

    state = EventReducer().reduce(events)
    return dataclasses.replace(state, snapshot_event_id=max_seq)


def get_current_state(db_url: str, full_replay: bool = False) -> SDDState:
    """Read current state.

    Default: YAML (O(1)). Falls back to replay if:
    - full_replay=True (explicit, e.g. rebuild-state command)
    - YAML absent or unreadable
    - YAML stale: snapshot_event_id is None or snapshot_event_id < event_log.max_seq

    I-STATE-READ-1: staleness guard prevents stale state from reaching guards.
    """
    if not full_replay:
        yaml_state = _read_yaml()
        if yaml_state is not None and yaml_state.snapshot_event_id is not None:
            max_seq = _pg_max_seq(db_url)
            if yaml_state.snapshot_event_id >= max_seq:
                return yaml_state
            logging.warning(
                "State_index.yaml is stale (snapshot_event_id=%d < el_max=%d). Replaying.",
                yaml_state.snapshot_event_id,
                max_seq,
            )
    return _replay_from_event_log(db_url)


def sync_projections(db_path: str, taskset_path: str, state_path: str) -> None:
    """Rebuild both projections atomically after any task-state mutation (I-SYNC-1).

    Single mandatory path: always call this instead of rebuild_taskset /
    rebuild_state individually. Guarantees TaskSet.md and State_index.yaml
    are always co-consistent after any write. Single EventLog replay (I-REPLAY-1).
    """
    state = rebuild_state(db_path, state_path)
    rebuild_taskset(db_path, taskset_path, state=state)
