"""BC-VR-1: VR test fixtures — db_factory, event_factory, state_builder, make_minimal_event.

Invariants: I-VR-HARNESS-4 (tmp_path-isolated DuckDB per test call).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import pytest

from sdd.core.events import DomainEvent, EventLevel
from sdd.domain.state.reducer import SDDState
from sdd.infra.event_store import EventStore
from sdd.infra.projections import get_current_state


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
def db_factory(tmp_path):
    """Provide a factory of tmp_path-isolated DuckDB paths (I-VR-HARNESS-4).

    Usage: db = db_factory()  — fresh isolated path per call.
    """
    _n = [0]

    def _make() -> str:
        _n[0] += 1
        return str(tmp_path / f"vr_{_n[0]}.duckdb")

    return _make


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
            EventStore(db_path).append(events, source="test_seed", allow_outside_kernel="test")
        return get_current_state(db_path)

    return _build
