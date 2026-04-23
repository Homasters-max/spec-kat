from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from sdd.domain.metrics.aggregator import MetricsAggregator, MetricRecord, MetricsSummary
from sdd.infra.event_query import EventRecord


# ─── helpers ──────────────────────────────────────────────────────────────────

def _tc_event(seq: int, task_id: str) -> EventRecord:
    """Build a minimal TaskCompleted EventRecord."""
    return EventRecord(
        seq=seq,
        event_type="TaskCompleted",
        payload=json.dumps({"task_id": task_id, "phase_id": 6}),
        event_source="meta",
        level="L1",
        expired=False,
        caused_by_meta_seq=None,
    )


def _mr_event(seq: int, task_id: str, metric_id: str = "task.lead_time", value: float = 1.0) -> EventRecord:
    """Build a minimal MetricRecorded EventRecord."""
    return EventRecord(
        seq=seq,
        event_type="MetricRecorded",
        payload=json.dumps({
            "task_id": task_id,
            "metric_id": metric_id,
            "value": value,
            "phase_id": 6,
            "recorded_at": "2026-01-01T00:00:00Z",
            "context": {"source": "test"},
        }),
        event_source="meta",
        level="L2",
        expired=False,
        caused_by_meta_seq=None,
    )


# ─── tests ────────────────────────────────────────────────────────────────────

def test_aggregator_deterministic() -> None:
    """I-MR-2 + I-PROJ-CONST-1: same inputs → identical MetricsSummary."""
    tc = (_tc_event(1, "T-601"),)
    mr = (_mr_event(2, "T-601"),)
    agg = MetricsAggregator()
    result_a = agg.aggregate(tc, mr, phase_id=6)
    result_b = agg.aggregate(tc, mr, phase_id=6)
    assert result_a == result_b


def test_im1_violation_detected() -> None:
    """I-MR-1: TaskCompleted without matching MetricRecorded → im1_violations contains task_id."""
    tc = (_tc_event(1, "T-601"),)
    mr: tuple[EventRecord, ...] = ()  # no metrics at all
    agg = MetricsAggregator()
    result = agg.aggregate(tc, mr, phase_id=6)
    assert "T-601" in result.im1_violations
    assert result.has_im1_violation is True


def test_no_im1_violation_when_metric_present() -> None:
    """I-MR-1: TaskCompleted paired with task.lead_time MetricRecorded → no violation."""
    tc = (_tc_event(1, "T-601"),)
    mr = (_mr_event(2, "T-601", metric_id="task.lead_time"),)
    agg = MetricsAggregator()
    result = agg.aggregate(tc, mr, phase_id=6)
    assert result.im1_violations == ()
    assert result.has_im1_violation is False


def test_im1_correlation_by_task_id_only() -> None:
    """I-MR-1: correlation is by task_id only, NOT by seq proximity."""
    # T-601 completed at seq=10, metric for T-601 at seq=1 (earlier seq)
    tc = (_tc_event(10, "T-601"),)
    mr = (_mr_event(1, "T-601", metric_id="task.lead_time"),)
    agg = MetricsAggregator()
    result = agg.aggregate(tc, mr, phase_id=6)
    # Must match despite metric appearing before the task event in seq order
    assert result.im1_violations == ()
    assert result.has_im1_violation is False


def test_summary_counts_correct() -> None:
    """MetricsSummary.task_count and metric_count reflect input sizes."""
    tc = (
        _tc_event(1, "T-601"),
        _tc_event(2, "T-602"),
    )
    mr = (
        _mr_event(3, "T-601", metric_id="task.lead_time"),
        _mr_event(4, "T-601", metric_id="task.validation_attempts"),
        _mr_event(5, "T-602", metric_id="task.lead_time"),
    )
    agg = MetricsAggregator()
    result = agg.aggregate(tc, mr, phase_id=6)
    assert result.task_count == 2
    assert result.metric_count == 3
    assert result.phase_id == 6
    assert result.im1_violations == ()


def test_aggregator_pure_no_io(tmp_path, monkeypatch) -> None:
    """I-PROJ-CONST-1 + I-PROJ-CONST-2: aggregate() performs no I/O and holds no state."""
    import builtins

    original_open = builtins.open

    calls: list[str] = []

    def patched_open(file, *args, **kwargs):
        calls.append(str(file))
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", patched_open)

    tc = (_tc_event(1, "T-601"),)
    mr = (_mr_event(2, "T-601"),)

    agg = MetricsAggregator()
    agg.aggregate(tc, mr, phase_id=6)

    assert calls == [], f"aggregate() opened file(s): {calls}"

    # I-PROJ-CONST-2: two calls on fresh instance, no shared state bleed
    agg2 = MetricsAggregator()
    result1 = agg2.aggregate(tc, mr, phase_id=6)
    result2 = agg2.aggregate(tc, mr, phase_id=6)
    assert result1 == result2
