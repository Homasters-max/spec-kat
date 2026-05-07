"""Compatibility tests — I-EL-6 (partial): v1 L1 event schema field requirements."""
from __future__ import annotations

import json
import pathlib

from sdd.core.events import DomainEvent, V1_L1_EVENT_TYPES

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
V1_EVENTS_FIXTURE = FIXTURES_DIR / "v1_events.json"

_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "event_id",
    "appended_at",
    "level",
    "event_source",
    "caused_by_meta_seq",
})


def test_v1_l1_events_have_required_fields() -> None:
    """Each entry in V1_L1_EVENT_TYPES can be instantiated with all required fields."""
    for event_type in sorted(V1_L1_EVENT_TYPES):
        event = DomainEvent(
            event_type=event_type,
            event_id="a" * 64,
            appended_at=1735689600000,
            level="L1",
            event_source="runtime",
            caused_by_meta_seq=None,
        )
        assert event.event_type == event_type
        assert event.event_id == "a" * 64
        assert event.appended_at == 1735689600000
        assert event.level == "L1"
        assert event.event_source == "runtime"
        assert event.caused_by_meta_seq is None


def test_v1_events_fixture_has_required_fields() -> None:
    """v1_events.json contains ≥1 sample L1 event per required field (I-EL-6)."""
    events: list[dict] = json.loads(V1_EVENTS_FIXTURE.read_text())
    assert len(events) >= 1

    fields_covered: set[str] = set()
    for entry in events:
        for field in _REQUIRED_FIELDS:
            if field in entry:
                fields_covered.add(field)

    missing = _REQUIRED_FIELDS - fields_covered
    assert not missing, f"Fixture missing coverage for fields: {missing}"
