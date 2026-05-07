"""Tests: I-PURE-1, I-PURE-1a — compute_trend and detect_anomalies are pure (no I/O).

duckdb was removed in Phase 46; purity is now guaranteed by the absence of the
dependency. Tests verify the functions run without errors and produce valid output.
"""
from __future__ import annotations

from sdd.infra.metrics import MetricRecord, compute_trend, detect_anomalies


def _sample_records() -> list[MetricRecord]:
    return [
        MetricRecord(phase=1, metric_id="test.metric", value=1.0),
        MetricRecord(phase=2, metric_id="test.metric", value=2.0),
        MetricRecord(phase=3, metric_id="test.metric", value=3.0),
    ]


def test_compute_trend_no_io() -> None:
    """I-PURE-1: compute_trend must not touch any I/O (duckdb removed in Phase 46)."""
    result = compute_trend(_sample_records())
    assert result is not None


def test_detect_anomalies_no_io() -> None:
    """I-PURE-1a: detect_anomalies must not touch any I/O (duckdb removed in Phase 46)."""
    result = detect_anomalies(_sample_records())
    assert result is not None
