"""Tests for infra/metrics.py — I-M-1, I-EL-11, I-DB-1, I-DB-2."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sdd.infra.db import open_sdd_connection
from sdd.infra.metrics import get_phase_metrics, record_metric


def test_record_metric_batch_with_task_completed(tmp_db_path: str) -> None:
    """Mode (a): both TaskCompleted and MetricRecorded written when task_id provided."""
    record_metric(
        "task.lead_time",
        42.0,
        task_id="T-001",
        phase_id=1,
        db_path=tmp_db_path,
    )

    conn = open_sdd_connection(tmp_db_path)
    rows = conn.execute(
        "SELECT event_type, level FROM events ORDER BY seq ASC"
    ).fetchall()
    conn.close()

    event_types = [r[0] for r in rows]
    assert len(event_types) == 2
    assert "TaskCompleted" in event_types
    assert "MetricRecorded" in event_types
    # MetricRecorded is always L2
    metric_row = next(r for r in rows if r[0] == "MetricRecorded")
    assert metric_row[1] == "L2"


def test_i_m_1_enforced(tmp_db_path: str) -> None:
    """I-M-1: if batch commit fails, neither TaskCompleted nor MetricRecorded is written."""
    from sdd.infra.db import open_sdd_connection as real_open

    class _FailingConn:
        """Delegates all DuckDB operations except commit, which raises."""

        def __init__(self, conn: object) -> None:
            self._conn = conn

        def begin(self) -> object:
            return self._conn.begin()  # type: ignore[attr-defined]

        def execute(self, sql: str, params: object = None) -> object:
            if params is not None:
                return self._conn.execute(sql, params)  # type: ignore[attr-defined]
            return self._conn.execute(sql)  # type: ignore[attr-defined]

        def commit(self) -> None:
            raise RuntimeError("injected commit failure after TaskCompleted insert")

        def rollback(self) -> object:
            return self._conn.rollback()  # type: ignore[attr-defined]

        def close(self) -> object:
            return self._conn.close()  # type: ignore[attr-defined]

    def _mock_open(db_path: str) -> _FailingConn:
        return _FailingConn(real_open(db_path))

    with patch("sdd.infra.event_log.open_sdd_connection", side_effect=_mock_open):
        with pytest.raises(Exception, match="injected commit failure"):
            record_metric("latency", 1.0, task_id="T-001", db_path=tmp_db_path)

    # Both events must be absent — the transaction was rolled back
    conn = real_open(tmp_db_path)
    rows = conn.execute("SELECT event_type FROM events").fetchall()
    conn.close()
    assert rows == [], (
        "Neither TaskCompleted nor MetricRecorded should be present after failed batch"
    )


def test_get_phase_metrics_requires_db_path() -> None:
    """I-DB-1, I-DB-2: db_path is required — calling without it raises TypeError."""
    with pytest.raises(TypeError):
        get_phase_metrics(1)  # type: ignore[call-arg]
