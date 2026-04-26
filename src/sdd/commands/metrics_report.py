"""MetricsReportCommand + MetricsReportHandler — Spec_v6 §2.3, §4.7; BC-METRICS-EXT §2.2.

Invariants: I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3, I-TREND-1, I-ANOM-1
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sdd.core.events import DomainEvent
from sdd.domain.metrics.aggregator import MetricsAggregator, MetricsSummary
from sdd.infra.event_query import EventLogQuerier, QueryFilters
from sdd.infra.metrics import (
    AnomalyRecord,
    TrendRecord,
    compute_trend,
    detect_anomalies,
    load_metrics,
)
from sdd.infra.paths import event_store_file, reports_dir, state_file

_DEFAULT_METRIC_IDS: list[str] = [
    "task.lead_time",
    "quality.test_coverage",
    "quality.lint_violations",
    "quality.type_errors",
]


@dataclass(frozen=True)
class MetricsReportCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    phase_id:     int
    output_path:  str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class MetricsReportHandler:
    """
    Orchestrates Layer A → Layer B pipeline. No other CommandHandlers called (I-CHAIN-1).
    I-PROJ-CONST-3: no handler-level caching; each handle() call reads from EventLog fresh.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def handle(self, command: MetricsReportCommand) -> list[DomainEvent]:
        """
        Steps:
          1. Query TaskCompleted events via EventLogQuerier directly (I-CHAIN-1)
          2. Query MetricRecorded events via EventLogQuerier directly (I-CHAIN-1)
          3. MetricsAggregator().aggregate() → MetricsSummary
          4. Render Markdown; write to output_path if set
          5. Return []  — no events emitted (I-ES-6)

        I-MR-2: same db_path + same phase_id → same Markdown output
        I-PROJ-CONST-3: fresh EventLog read per call, no caching
        """
        querier = EventLogQuerier(self._db_path)

        tc_events = querier.query(
            QueryFilters(phase_id=command.phase_id, event_type="TaskCompleted")
        )
        mr_events = querier.query(
            QueryFilters(phase_id=command.phase_id, event_type="MetricRecorded")
        )

        summary = MetricsAggregator().aggregate(tc_events, mr_events, command.phase_id)
        markdown = _render_markdown(summary)

        if command.output_path is not None:
            Path(command.output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(command.output_path).write_text(markdown, encoding="utf-8")

        return []


def _render_markdown(summary: MetricsSummary) -> str:
    lines: list[str] = [
        f"# Metrics Report — Phase {summary.phase_id}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Tasks completed | {summary.task_count} |",
        f"| Metrics recorded | {summary.metric_count} |",
        f"| I-MR-1 violations | {len(summary.im1_violations)} |",
        "",
    ]

    lines.append("## I-MR-1 Violations (task.lead_time not recorded)")
    lines.append("")
    if summary.im1_violations:
        for task_id in sorted(summary.im1_violations):
            lines.append(f"- {task_id}")
    else:
        lines.append("_None — all completed tasks have a task.lead\\_time metric._")
    lines.append("")

    lines.append("## Recorded Metrics")
    lines.append("")
    if summary.metrics:
        lines.append("| seq | metric_id | value | task_id | phase_id |")
        lines.append("|---|---|---|---|---|")
        for m in summary.metrics:
            lines.append(
                f"| {m.seq} | {m.metric_id} | {m.value} "
                f"| {m.task_id or ''} | {m.phase_id or ''} |"
            )
    else:
        lines.append("_No metrics recorded for this phase._")
    lines.append("")

    return "\n".join(lines)


def _render_trend(trends: list[TrendRecord]) -> str:
    lines: list[str] = [
        "## Trend Analysis",
        "",
        "| Phase | Metric | Value | Delta | Dir |",
        "|---|---|---|---|---|",
    ]
    for t in trends:
        delta_str = "—" if t.delta is None else f"{t.delta:+.4g}"
        lines.append(f"| {t.phase} | {t.metric_id} | {t.value:.4g} | {delta_str} | {t.direction} |")
    lines.append("")
    return "\n".join(lines)


def _render_anomalies(anomalies: list[AnomalyRecord], threshold: float) -> str:
    lines: list[str] = [
        f"### Anomalies (threshold: {threshold}σ)",
        "",
    ]
    if not anomalies:
        lines.append("_No anomalies detected._")
        lines.append("")
        return "\n".join(lines)
    lines += [
        "| Phase | Metric | Value | z-score |",
        "|---|---|---|---|",
    ]
    for a in anomalies:
        sign = "+" if a.zscore >= 0 else ""
        lines.append(f"| {a.phase} | {a.metric_id} | {a.value:.4g} | {sign}{a.zscore:.2f} |")
    lines.append("")
    return "\n".join(lines)


def _read_phase(state_path: str) -> int:
    import yaml  # local import — optional dep
    with open(state_path, encoding="utf-8") as fh:
        state = yaml.safe_load(fh)
    return int(state["phase"]["current"])


def main(args: list[str] | None = None) -> int:
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="metrics-report")
    parser.add_argument("--phase", type=int, default=None)
    parser.add_argument("--trend", action="store_true")
    parser.add_argument("--anomalies", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--metrics", nargs="+", default=None)
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--db", default=None)
    parser.add_argument("--state", default=None)
    parsed = parser.parse_args(args)

    db = parsed.db or str(event_store_file())
    state = parsed.state or str(state_file())

    try:
        phase_id = parsed.phase if parsed.phase is not None else _read_phase(state)
    except Exception as exc:
        print(f"ERROR: cannot determine phase: {exc}", file=sys.stderr)
        return 1

    sections: list[str] = []

    if parsed.trend or parsed.anomalies:
        metric_ids = parsed.metrics or _DEFAULT_METRIC_IDS
        records = load_metrics(metric_ids, db_path=db)  # I-DB-2: explicit db_path
        if parsed.trend:
            trends = compute_trend(records)
            sections.append(_render_trend(trends))
        if parsed.anomalies:
            anomalies = detect_anomalies(records, threshold=parsed.threshold)
            sections.append(_render_anomalies(anomalies, parsed.threshold))
    else:
        querier = EventLogQuerier(db)
        tc_events = querier.query(QueryFilters(phase_id=phase_id, event_type="TaskCompleted"))
        mr_events = querier.query(QueryFilters(phase_id=phase_id, event_type="MetricRecorded"))
        summary = MetricsAggregator().aggregate(tc_events, mr_events, phase_id)
        sections.append(_render_markdown(summary))

    output = "\n".join(sections)
    out_path = Path(parsed.output) if parsed.output else reports_dir() / f"Metrics_Phase{phase_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"Written: {out_path}", file=sys.stderr)

    return 0
