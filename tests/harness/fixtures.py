"""BC-VR-1: VR test fixtures — db_factory, event_factory, state_builder, make_minimal_event.

Invariants: I-VR-HARNESS-4 (PG-schema-isolated DB per test call).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import psycopg
import pytest

from sdd.core.events import DomainEvent, EventLevel
from sdd.domain.state.reducer import SDDState
from sdd.infra.event_log import EventLog
from sdd.infra.projections import get_current_state
from tests.conftest import _apply_sdd_ddl, _require_sdd_database_url  # noqa: F401 — re-export fixture


@dataclass(frozen=True)
class _MinimalTestEvent(DomainEvent):
    """Test-only event; unknown to reducer, skipped gracefully per EV-4."""


def make_minimal_event(
    event_type: str = "_test_minimal",
    event_source: str = "runtime",
) -> DomainEvent:
    """Return a minimal DomainEvent with a unique event_id, suitable for test DB seeding."""
    return _MinimalTestEvent(
        event_type=event_type,
        event_id=str(uuid.uuid4()),
        appended_at=int(time.time() * 1000),
        level=EventLevel.L2,
        event_source=event_source,
        caused_by_meta_seq=None,
    )


@pytest.fixture
def db_factory(_require_sdd_database_url: str):
    """Provide a factory of isolated PostgreSQL schemas (I-VR-HARNESS-4, BC-46-E).

    Usage: db_url = db_factory()  — fresh isolated PG schema per call.
    Skip-safe: skipped when SDD_DATABASE_URL is not set.
    """
    base_url = _require_sdd_database_url
    created: list[str] = []

    def _make() -> str:
        schema = f"harness_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(base_url) as conn:
            conn.execute(f"CREATE SCHEMA {schema}")
            _apply_sdd_ddl(conn, schema)
            conn.commit()
        created.append(schema)
        return f"{base_url}?options=-csearch_path%3D{schema}"

    yield _make

    if created:
        schemas_sql = ", ".join(created)
        with psycopg.connect(base_url) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {schemas_sql} CASCADE")
            conn.commit()


@pytest.fixture
def event_factory():
    """Return a callable that creates minimal DomainEvents with unique IDs."""

    def _make(event_type: str = "_test_event", event_source: str = "runtime") -> DomainEvent:
        return make_minimal_event(event_type=event_type, event_source=event_source)

    return _make


@pytest.fixture
def state_builder(db_factory):
    """Return a builder: seed events into an isolated DB and return SDDState.

    Implements I-VR-HARNESS-3: events are only appended, never modified.
    """

    def _build(events: list[DomainEvent]) -> SDDState:
        db_path = db_factory()
        if events:
            EventLog(db_path).append(events, source="test_seed", allow_outside_kernel="test")
        return get_current_state(db_path)

    return _build
