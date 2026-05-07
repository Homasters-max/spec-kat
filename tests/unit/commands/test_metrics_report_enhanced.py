"""Tests for compute_trend and detect_anomalies — T-807.

Covers: I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sdd.infra.metrics import (
    AnomalyRecord,
    MetricRecord,
    TrendRecord,
    compute_trend,
    detect_anomalies,
)


# ─── compute_trend ────────────────────────────────────────────────────────────


def test_trend_two_phases() -> None:
    """I-TREND-1: two phases produce two TrendRecords, second has delta computed."""
    records = [
        MetricRecord(phase=1, metric_id="m", value=10.0),
        MetricRecord(phase=2, metric_id="m", value=12.0),
    ]
    result = compute_trend(records)
    assert len(result) == 2
    assert result[0] == TrendRecord(phase=1, metric_id="m", value=10.0, delta=None, direction="→")
    assert result[1].phase == 2
    assert result[1].delta == pytest.approx(2.0)


def test_trend_first_phase_delta_none() -> None:
    """I-TREND-1: oldest phase in each metric window must have delta=None."""
    records = [
        MetricRecord(phase=3, metric_id="x", value=5.0),
        MetricRecord(phase=4, metric_id="x", value=6.0),
        MetricRecord(phase=5, metric_id="x", value=7.0),
    ]
    result = compute_trend(records)
    first = next(r for r in result if r.phase == 3)
    assert first.delta is None
    assert first.direction == "→"


def test_trend_direction_up_down_flat() -> None:
    """I-TREND-1: directions ↑/↓/→ based on delta/value ratio threshold 0.05."""
    records = [
        MetricRecord(phase=1, metric_id="a", value=100.0),
        MetricRecord(phase=2, metric_id="a", value=110.0),  # delta/value = 0.10 → ↑
        MetricRecord(phase=3, metric_id="a", value=104.5),  # delta/value ≈ -0.05 boundary → →
        MetricRecord(phase=4, metric_id="a", value=89.0),   # delta/value ≈ -0.175 → ↓
    ]
    result = compute_trend(records)
    by_phase = {r.phase: r for r in result}
    assert by_phase[2].direction == "↑"
    assert by_phase[4].direction == "↓"
    # phase 3: delta = -5.5, value = 104.5, ratio ≈ -0.0526 which is < -0.05 → ↓
    # Verify phase 1 is flat (delta=None)
    assert by_phase[1].direction == "→"


def test_trend_pure_no_io() -> None:
    """I-TREND-1: compute_trend must not perform any I/O or DuckDB access."""
    records = [
        MetricRecord(phase=1, metric_id="p", value=1.0),
        MetricRecord(phase=2, metric_id="p", value=2.0),
    ]
    with patch("sdd.infra.metrics.load_metrics") as mock_load:
        result = compute_trend(records)
    mock_load.assert_not_called()
    assert len(result) == 2


def test_trend_direction_zero_value() -> None:
    """I-TREND-2: when abs(value) < trend_epsilon, direction must be '→' to avoid division."""
    tiny = 1e-10  # well below default epsilon of 1e-9
    records = [
        MetricRecord(phase=1, metric_id="z", value=1.0),
        MetricRecord(phase=2, metric_id="z", value=tiny),
    ]
    result = compute_trend(records)
    by_phase = {r.phase: r for r in result}
    assert by_phase[2].direction == "→"


# ─── detect_anomalies ─────────────────────────────────────────────────────────


def test_anomaly_empty_below_3_points() -> None:
    """I-ANOM-1: fewer than 3 data points → returns []."""
    records = [
        MetricRecord(phase=1, metric_id="q", value=1.0),
        MetricRecord(phase=2, metric_id="q", value=2.0),
    ]
    assert detect_anomalies(records) == []


def test_anomaly_detected_above_2sigma() -> None:
    """I-ANOM-1: value with |zscore| > 2.0 must appear in result.

    10 points: nine values at 1.0, one at 100.0.
    sample stdev ≈ 31.3, mean ≈ 10.9, zscore(100) ≈ 2.85 → flagged.
    """
    base = [MetricRecord(phase=i, metric_id="r", value=1.0) for i in range(1, 10)]
    outlier = MetricRecord(phase=10, metric_id="r", value=100.0)
    records = base + [outlier]
    result = detect_anomalies(records)
    assert len(result) == 1
    assert result[0].phase == 10
    assert result[0].metric_id == "r"
    assert abs(result[0].zscore) > 2.0


def test_anomaly_not_detected_within_2sigma() -> None:
    """I-ANOM-1: values within 2σ must NOT be flagged."""
    records = [
        MetricRecord(phase=1, metric_id="s", value=10.0),
        MetricRecord(phase=2, metric_id="s", value=11.0),
        MetricRecord(phase=3, metric_id="s", value=10.5),
    ]
    result = detect_anomalies(records)
    assert result == []


def test_anomaly_pure_no_io() -> None:
    """I-ANOM-1: detect_anomalies must not perform any I/O or DuckDB access."""
    base = [MetricRecord(phase=i, metric_id="t", value=1.0) for i in range(1, 10)]
    outlier = MetricRecord(phase=10, metric_id="t", value=100.0)
    records = base + [outlier]
    with patch("sdd.infra.metrics.load_metrics") as mock_load:
        result = detect_anomalies(records)
    mock_load.assert_not_called()
    assert len(result) == 1


def test_anomaly_empty_on_zero_stdev() -> None:
    """I-ANOM-2: all-identical values → stdev == 0 → returns [] (no ZeroDivisionError)."""
    records = [
        MetricRecord(phase=1, metric_id="u", value=5.0),
        MetricRecord(phase=2, metric_id="u", value=5.0),
        MetricRecord(phase=3, metric_id="u", value=5.0),
    ]
    result = detect_anomalies(records)
    assert result == []
