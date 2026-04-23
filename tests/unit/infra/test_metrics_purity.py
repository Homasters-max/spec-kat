"""Tests: I-PURE-1, I-PURE-1a — compute_trend and detect_anomalies are pure (no I/O)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from sdd.infra.metrics import MetricRecord, compute_trend, detect_anomalies


def _sample_records() -> list[MetricRecord]:
    return [
        MetricRecord(phase=1, metric_id="test.metric", value=1.0),
        MetricRecord(phase=2, metric_id="test.metric", value=2.0),
        MetricRecord(phase=3, metric_id="test.metric", value=3.0),
    ]


def test_compute_trend_no_io() -> None:
    """I-PURE-1: compute_trend must not touch DuckDB or any I/O."""
    mock_duckdb = MagicMock()
    with patch("sdd.infra.metrics.duckdb", mock_duckdb, create=True), \
         patch("duckdb.connect") as mock_connect:
        compute_trend(_sample_records())
    assert mock_duckdb.call_count == 0
    assert mock_connect.call_count == 0


def test_detect_anomalies_no_io() -> None:
    """I-PURE-1a: detect_anomalies must not touch DuckDB or any I/O."""
    mock_duckdb = MagicMock()
    with patch("sdd.infra.metrics.duckdb", mock_duckdb, create=True), \
         patch("duckdb.connect") as mock_connect:
        detect_anomalies(_sample_records())
    assert mock_duckdb.call_count == 0
    assert mock_connect.call_count == 0
