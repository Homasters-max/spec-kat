"""BC-VR-5: Schema Evolution — v1 upcast, forward-unknown safety, stability.

Invariants: I-VR-STABLE-8, I-EVENT-UPCAST-1, I-EVOLUTION-FORWARD-1
"""
from __future__ import annotations

import json
import pathlib

from sdd.domain.state.reducer import (
    SDDState,
    reduce,
    reduce_with_diagnostics,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURES_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "compatibility" / "fixtures" / "v1_events.json"
)


def _load_v1_events() -> list[dict]:
    with _FIXTURES_PATH.open() as f:
        return json.load(f)


def _upcast_v1_event(v1_event: dict) -> dict:
    """Convert a v1 event (payload-nested format) to the flat dict the reducer expects.

    V1 format stores level/event_source inside the nested `payload` object.
    Current format (from DB replay) has them at the top level, with remaining
    payload fields merged in — matching what get_current_state() produces.
    """
    payload = dict(v1_event.get("payload", {}))
    result: dict = {
        "event_type": v1_event["event_type"],
        "schema_version": v1_event.get("schema_version", 1),
        "level": payload.pop("level", "L1"),
        "event_source": payload.pop("event_source", "runtime"),
        "caused_by_meta_seq": payload.pop("caused_by_meta_seq", None),
    }
    result.update(payload)
    return result


def _upcast_all(v1_events: list[dict]) -> list[dict]:
    return [_upcast_v1_event(e) for e in v1_events]


# ---------------------------------------------------------------------------
# Test 1 — I-EVENT-UPCAST-1: upcast correctness
# ---------------------------------------------------------------------------


def test_event_schema_upcast_correctness() -> None:
    """Upcast v1 events are processed correctly by the reducer.

    Runtime L1 events in the fixture: TaskImplemented (T-0101) and
    TaskValidated (PASS).  Meta-source events are filtered by I-REDUCER-1.
    """
    events = _upcast_all(_load_v1_events())

    state = reduce(events)

    assert "T-0101" in state.tasks_done_ids, "TaskImplemented must be folded"
    assert state.tasks_completed == 1
    assert state.tests_status == "PASS", "TaskValidated PASS must propagate"
    assert state.invariants_status == "PASS"


# ---------------------------------------------------------------------------
# Test 2 — I-EVOLUTION-FORWARD-1: forward-unknown event is safe
# ---------------------------------------------------------------------------


def test_forward_unknown_event_safe() -> None:
    """Unknown future event types are silently skipped — no crash (I-EVOLUTION-FORWARD-1)."""
    events = _upcast_all(_load_v1_events())

    synthetic_v2: dict = {
        "event_type": "FutureEventV2Synthetic",
        "level": "L1",
        "event_source": "runtime",
        "caused_by_meta_seq": None,
        "future_field": "synthetic_value",
    }
    events_with_future = events + [synthetic_v2]

    state = reduce(events_with_future)
    assert isinstance(state, SDDState)

    _, diag = reduce_with_diagnostics(events_with_future)
    assert diag.events_unknown_type == 1, "Exactly one unknown event must be counted"


# ---------------------------------------------------------------------------
# Test 3 — I-EVENT-UPCAST-1: no data loss during upcast
# ---------------------------------------------------------------------------


def test_no_data_loss() -> None:
    """All payload fields survive upcast — no field is dropped or corrupted."""
    v1_events = _load_v1_events()
    task_impl_v1 = next(e for e in v1_events if e["event_type"] == "TaskImplemented")
    orig_payload = task_impl_v1["payload"]

    upcast = _upcast_v1_event(task_impl_v1)

    assert upcast["level"] == orig_payload["level"]
    assert upcast["event_source"] == orig_payload["event_source"]
    assert upcast["task_id"] == orig_payload["task_id"]
    assert upcast["phase_id"] == orig_payload["phase_id"]
    assert upcast["timestamp"] == orig_payload["timestamp"]
    assert upcast["event_id"] == orig_payload["event_id"]
    assert upcast["appended_at"] == orig_payload["appended_at"]


# ---------------------------------------------------------------------------
# Test 4 — I-VR-STABLE-8: unknown fields are silently ignored
# ---------------------------------------------------------------------------


def test_unknown_fields_ignored() -> None:
    """Extra/unknown fields in upcast events are silently ignored by the reducer."""
    events = _upcast_all(_load_v1_events())

    events_with_extras = [
        {**event, "unknown_future_field": "value", "_internal_hint": 42}
        for event in events
    ]

    state = reduce(events_with_extras)

    assert isinstance(state, SDDState)
    assert "T-0101" in state.tasks_done_ids, "Extra fields must not break reducer dispatch"


# ---------------------------------------------------------------------------
# Test 5 — I-VR-STABLE-8: backward-compat state_hash is stable
# ---------------------------------------------------------------------------


def test_backward_compat_state_hash() -> None:
    """state_hash derived from v1 upcast is deterministic across multiple reduce() calls."""
    events = _upcast_all(_load_v1_events())

    state1 = reduce(events)
    state2 = reduce(events)

    assert state1.state_hash == state2.state_hash
    assert len(state1.state_hash) == 64, "SHA-256 hex digest must be 64 chars"
    assert state1.state_hash != "", "state_hash must be non-empty"


# ---------------------------------------------------------------------------
# Test 6 — I-VR-STABLE-8: evolution is idempotent
# ---------------------------------------------------------------------------


def test_evolution_idempotent() -> None:
    """reduce(v1_events) is deterministic: identical input → identical SDDState."""
    events = _upcast_all(_load_v1_events())

    state_a = reduce(events)
    state_b = reduce(events)

    assert state_a == state_b
    assert state_a.state_hash == state_b.state_hash
    assert state_a.tasks_done_ids == state_b.tasks_done_ids
    assert state_a.tests_status == state_b.tests_status
    assert state_a.invariants_status == state_b.invariants_status
