"""Tests for MetricsReportHandler — T-608.

Covers: I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdd.commands.metrics_report import MetricsReportCommand, MetricsReportHandler
from sdd.infra.event_query import EventRecord


_QUERIER_PATH = "sdd.commands.metrics_report.EventLogQuerier"


def _cmd(phase_id: int, output_path: str | None = None) -> MetricsReportCommand:
    return MetricsReportCommand(
        command_id="test-cmd-id",
        command_type="metrics_report",
        payload={},
        phase_id=phase_id,
        output_path=output_path,
    )


def _tc_record(seq: int, task_id: str, phase_id: int = 6) -> EventRecord:
    return EventRecord(
        seq=seq,
        event_type="TaskCompleted",
        payload=json.dumps({"task_id": task_id, "phase_id": phase_id}),
        event_source="update_state.py",
        level="L1",
        expired=False,
        caused_by_meta_seq=None,
    )


def _mr_record(
    seq: int,
    metric_id: str,
    value: float,
    task_id: str | None,
    phase_id: int = 6,
) -> EventRecord:
    return EventRecord(
        seq=seq,
        event_type="MetricRecorded",
        payload=json.dumps(
            {
                "metric_id": metric_id,
                "value": value,
                "task_id": task_id,
                "phase_id": phase_id,
                "recorded_at": "2026-04-22T00:00:00Z",
            }
        ),
        event_source="update_state.py",
        level="L2",
        expired=False,
        caused_by_meta_seq=None,
    )


def test_report_returns_empty_events() -> None:
    """handle() always returns [] — no domain events emitted (I-ES-6)."""
    with patch(_QUERIER_PATH) as mock_cls:
        mock_cls.return_value.query.return_value = ()
        handler = MetricsReportHandler(db_path="/fake/db")
        result = handler.handle(_cmd(phase_id=6))

    assert result == []


def test_report_renders_markdown(tmp_path: Path) -> None:
    """handle() writes valid markdown with all expected sections when output_path is set."""
    tc = (_tc_record(1, "T-601"),)
    mr = (_mr_record(2, "task.lead_time", 30.0, "T-601"),)
    out = str(tmp_path / "report.md")

    with patch(_QUERIER_PATH) as mock_cls:
        mock_cls.return_value.query.side_effect = [tc, mr]
        handler = MetricsReportHandler(db_path="/fake/db")
        handler.handle(_cmd(phase_id=6, output_path=out))

    content = Path(out).read_text()
    assert "# Metrics Report — Phase 6" in content
    assert "## Summary" in content
    assert "## I-MR-1 Violations" in content
    assert "## Recorded Metrics" in content
    assert "task.lead_time" in content


def test_report_deterministic(tmp_path: Path) -> None:
    """Same db_path + same phase_id → same Markdown output on repeated calls (I-MR-2)."""
    tc = (_tc_record(1, "T-601"), _tc_record(3, "T-602"))
    mr = (
        _mr_record(2, "task.lead_time", 10.0, "T-601"),
        _mr_record(4, "task.lead_time", 20.0, "T-602"),
    )
    out1 = str(tmp_path / "r1.md")
    out2 = str(tmp_path / "r2.md")

    with patch(_QUERIER_PATH) as mock_cls:
        mock_cls.return_value.query.side_effect = [tc, mr, tc, mr]
        handler = MetricsReportHandler(db_path="/fake/db")
        handler.handle(_cmd(phase_id=6, output_path=out1))
        handler.handle(_cmd(phase_id=6, output_path=out2))

    assert Path(out1).read_text() == Path(out2).read_text()


def test_report_writes_file_when_output_path_set(tmp_path: Path) -> None:
    """handle() creates parent dirs and writes the markdown file to output_path."""
    out = str(tmp_path / "subdir" / "nested" / "report.md")

    with patch(_QUERIER_PATH) as mock_cls:
        mock_cls.return_value.query.return_value = ()
        handler = MetricsReportHandler(db_path="/fake/db")
        handler.handle(_cmd(phase_id=6, output_path=out))

    assert Path(out).exists()
    content = Path(out).read_text()
    assert "# Metrics Report — Phase 6" in content


def test_no_query_handler_in_report() -> None:
    """MetricsReportHandler.handle() uses EventLogQuerier directly — no other CommandHandler (I-CHAIN-1)."""
    import sdd.commands.metrics_report as mod

    other_handlers = [
        name
        for name in dir(mod)
        if name.endswith("Handler") and name != "MetricsReportHandler"
    ]
    assert other_handlers == [], f"Unexpected handler imports in metrics_report: {other_handlers}"


def test_report_no_handler_cache() -> None:
    """Each handle() call instantiates a fresh EventLogQuerier — no caching (I-PROJ-CONST-3)."""
    with patch(_QUERIER_PATH) as mock_cls:
        mock_cls.return_value.query.return_value = ()
        handler = MetricsReportHandler(db_path="/fake/db")
        handler.handle(_cmd(phase_id=6))
        handler.handle(_cmd(phase_id=6))

    assert mock_cls.call_count == 2, (
        f"EventLogQuerier instantiated {mock_cls.call_count} times; "
        "expected 2 (once per handle() call, no caching)"
    )
