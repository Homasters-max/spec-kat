"""Tests for RecordMetricHandler — Spec_v56 §2 BC-56-A2.

Covers:
- I-HANDLER-PURE-1: handle() returns events only, no side effects
- I-2: event emitted via REGISTRY (CommandSpec registered)
- I-EREG-SCOPE-1: MetricRecorded in V1_L1_EVENT_TYPES; test_i_st_10 passes
- BC-56-A2: correct fields metric_key/value/phase_id/task_id/context
"""
from __future__ import annotations

import pytest

from sdd.commands.record_metric import RecordMetricCommand, RecordMetricHandler
from sdd.commands.registry import REGISTRY
from sdd.core.events import MetricRecorded, V1_L1_EVENT_TYPES, classify_event_level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cmd(
    metric_key: str = "graph_calls_count",
    value: float = 3.0,
    phase_id: int = 56,
    task_id: str = "T-5601",
    context: str = "",
) -> RecordMetricCommand:
    return RecordMetricCommand(
        command_id="test-cmd-id",
        command_type="RecordMetric",
        payload={"metric_key": metric_key, "phase_id": phase_id, "task_id": task_id},
        metric_key=metric_key,
        value=value,
        phase_id=phase_id,
        task_id=task_id,
        context=context,
    )


# ---------------------------------------------------------------------------
# Handler correctness
# ---------------------------------------------------------------------------

def test_handle_returns_metric_recorded_event(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    events = handler.handle(_make_cmd())
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, MetricRecorded)
    assert ev.event_type == "MetricRecorded"


def test_handle_correct_fields(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    events = handler.handle(_make_cmd(
        metric_key="graph_calls_count",
        value=5.0,
        phase_id=56,
        task_id="T-5601",
        context="test context",
    ))
    ev = events[0]
    assert ev.metric_key == "graph_calls_count"
    assert ev.value == 5.0
    assert ev.phase_id == 56
    assert ev.task_id == "T-5601"
    assert ev.context == "test context"


def test_handle_context_truncated_to_140_chars(pg_test_db: str):
    long_ctx = "x" * 200
    handler = RecordMetricHandler(db_path=pg_test_db)
    events = handler.handle(_make_cmd(context=long_ctx))
    assert len(events[0].context) == 140


def test_handle_empty_context_allowed(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    events = handler.handle(_make_cmd(context=""))
    assert events[0].context == ""


def test_handle_value_coerced_to_float(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    events = handler.handle(_make_cmd(value=3))
    assert isinstance(events[0].value, float)


def test_handle_rejects_empty_metric_key(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    with pytest.raises(Exception):
        handler.handle(_make_cmd(metric_key=""))


def test_handle_rejects_whitespace_metric_key(pg_test_db: str):
    handler = RecordMetricHandler(db_path=pg_test_db)
    with pytest.raises(Exception):
        handler.handle(_make_cmd(metric_key="   "))


# ---------------------------------------------------------------------------
# Event level (I-EREG-SCOPE-1, BC-56-A2)
# ---------------------------------------------------------------------------

def test_metric_recorded_is_l1():
    assert classify_event_level("MetricRecorded") == "L1"


def test_metric_recorded_in_v1_l1_event_types():
    assert "MetricRecorded" in V1_L1_EVENT_TYPES


def test_i_st_10_all_event_types_classified():
    """I-ST-10: MetricRecorded in V1_L1_EVENT_TYPES must be classified by EventReducer."""
    from sdd.domain.state.reducer import EventReducer
    classified = EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys())
    missing = V1_L1_EVENT_TYPES - classified
    assert not missing, f"Events in V1_L1_EVENT_TYPES but not classified: {missing}"


# ---------------------------------------------------------------------------
# REGISTRY entry (I-2, I-EREG-SCOPE-1)
# ---------------------------------------------------------------------------

def test_record_metric_in_registry():
    assert "record-metric" in REGISTRY


def test_registry_entry_actor_is_llm():
    spec = REGISTRY["record-metric"]
    assert spec.actor == "llm"


def test_registry_entry_event_schema_contains_metric_recorded():
    spec = REGISTRY["record-metric"]
    assert MetricRecorded in spec.event_schema
