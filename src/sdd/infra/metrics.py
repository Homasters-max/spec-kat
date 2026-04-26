"""BC-INFRA metrics — record_metric, MetricEvent, load_metrics, get_phase_metrics, compute_trend, detect_anomalies."""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import Any

from sdd.infra.event_log import EventInput, sdd_append, sdd_append_batch

_TREND_EPSILON: float = 1e-9


@dataclass(frozen=True)
class MetricRecord:
    """A single metric value recorded for a phase (§4.0)."""

    phase: int
    metric_id: str
    value: float


@dataclass(frozen=True)
class TrendRecord:
    """Inter-phase delta for one metric/phase pair (§4.1)."""

    phase: int
    metric_id: str
    value: float
    delta: float | None  # None for the first phase in the window
    direction: str       # "↑" | "↓" | "→"


@dataclass(frozen=True)
class AnomalyRecord:
    """Statistical outlier for one metric/phase pair (§4.2)."""

    phase: int
    metric_id: str
    value: float
    zscore: float


@dataclass(frozen=True)
class MetricEvent:
    """Typed representation of a metric to be recorded."""

    metric_id: str
    value: float | int
    task_id: str | None = None
    phase_id: int | None = None
    context: dict[str, Any] | None = None


def record_metric(
    metric_id: str,
    value: float | int,
    task_id: str | None = None,
    phase_id: int | None = None,
    context: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> None:
    """Write a MetricRecorded event, optionally batched with TaskCompleted (I-M-1).

    Mode (a) — task_id provided: writes TaskCompleted + MetricRecorded atomically.
    Mode (b) — task_id absent:   writes only MetricRecorded.
    MetricRecorded is always level=L2 in both modes.
    """
    metric_payload: dict[str, Any] = {
        "metric_id": metric_id,
        "value": value,
    }
    if task_id is not None:
        metric_payload["task_id"] = task_id
    if phase_id is not None:
        metric_payload["phase_id"] = phase_id
    if context:
        metric_payload["context"] = context

    if task_id is not None:
        task_payload: dict[str, Any] = {"task_id": task_id}
        if phase_id is not None:
            task_payload["phase_id"] = phase_id
        sdd_append_batch(
            [
                EventInput(event_type="TaskCompleted", payload=task_payload, level="L2"),
                EventInput(
                    event_type="MetricRecorded",
                    payload=metric_payload,
                    level="L2",
                ),
            ],
            db_path=db_path,
        )
    else:
        sdd_append(
            "MetricRecorded",
            metric_payload,
            db_path=db_path,
            level="L2",
        )


# ─── Trend + Anomaly Analysis (BC-METRICS-EXT, §2.2, §4.0b–§4.4) ─────────────


def load_metrics(metric_ids: list[str], db_path: str, window: int = 10) -> list[MetricRecord]:
    """All DuckDB I/O isolated here — NOT in compute_trend or detect_anomalies (§4.0b).

    Queries the metrics partition ordered by seq ASC; returns the last `window`
    phases per metric_id, sorted by (metric_id, phase) ASC.
    Returns [] for unknown metric_ids.
    db_path MUST be explicit (I-DB-1).
    """
    from sdd.infra.db import open_sdd_connection  # local import keeps module top-level clean

    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT payload FROM events "
            "WHERE partition_key = 'metrics' "
            "ORDER BY seq ASC"
        ).fetchall()
    finally:
        conn.close()

    metric_id_set = set(metric_ids)

    # (metric_id, phase) → value; later seq overwrites earlier for the same pair
    by_phase: dict[tuple[str, int], float] = {}
    for (payload_str,) in rows:
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except (json.JSONDecodeError, TypeError):
            continue
        mid = payload.get("metric_id") or payload.get("metric")
        phase_raw = payload.get("phase_id") or payload.get("phase")
        value_raw = payload.get("value")
        if mid not in metric_id_set or phase_raw is None or value_raw is None:
            continue
        try:
            by_phase[(str(mid), int(phase_raw))] = float(value_raw)
        except (TypeError, ValueError):
            continue

    # Group by metric_id, take last `window` phases, return sorted ASC
    grouped: dict[str, list[tuple[int, float]]] = {}
    for (mid, ph), val in by_phase.items():
        grouped.setdefault(mid, []).append((ph, val))

    result: list[MetricRecord] = []
    for mid in sorted(grouped):
        entries = sorted(grouped[mid])  # sort by phase ASC
        for ph, val in entries[-window:]:
            result.append(MetricRecord(phase=ph, metric_id=mid, value=val))
    return result


def get_phase_metrics(phase_n: int, db_path: str) -> list[MetricRecord]:
    """Return all MetricRecorded events for phase_n (I-DB-1: db_path required).

    Queries the metrics partition and filters by phase_id == phase_n.
    Returns [] if no metrics recorded for the phase.
    """
    from sdd.infra.db import open_sdd_connection

    conn = open_sdd_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT payload FROM events "
            "WHERE partition_key = 'metrics' "
            "ORDER BY seq ASC"
        ).fetchall()
    finally:
        conn.close()

    result: list[MetricRecord] = []
    for (payload_str,) in rows:
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except (json.JSONDecodeError, TypeError):
            continue
        mid = payload.get("metric_id") or payload.get("metric")
        phase_raw = payload.get("phase_id") or payload.get("phase")
        value_raw = payload.get("value")
        if mid is None or phase_raw is None or value_raw is None:
            continue
        try:
            if int(phase_raw) != phase_n:
                continue
            result.append(MetricRecord(phase=phase_n, metric_id=str(mid), value=float(value_raw)))
        except (TypeError, ValueError):
            continue
    return result


def compute_trend(
    records: list[MetricRecord],
    trend_epsilon: float = _TREND_EPSILON,
) -> list[TrendRecord]:
    """I-TREND-1: truly pure function — no I/O, no DuckDB, no randomness (§4.3).

    Returns TrendRecord list ordered by (metric_id, phase) ASC.
    delta=None for the oldest phase in each metric's window.
    Direction: "→" when delta is None or abs(value) < trend_epsilon (I-TREND-2);
               "↑" when delta/value > 0.05; "↓" when delta/value < -0.05; "→" otherwise.
    """
    if not records:
        return []

    grouped: dict[str, list[MetricRecord]] = {}
    for r in records:
        grouped.setdefault(r.metric_id, []).append(r)

    result: list[TrendRecord] = []
    for mid in sorted(grouped):
        entries = sorted(grouped[mid], key=lambda r: r.phase)
        prev_value: float | None = None
        for r in entries:
            if prev_value is None:
                delta: float | None = None
                direction = "→"
            else:
                delta = r.value - prev_value
                if abs(r.value) < trend_epsilon:
                    direction = "→"
                elif delta / r.value > 0.05:
                    direction = "↑"
                elif delta / r.value < -0.05:
                    direction = "↓"
                else:
                    direction = "→"
            result.append(
                TrendRecord(
                    phase=r.phase,
                    metric_id=r.metric_id,
                    value=r.value,
                    delta=delta,
                    direction=direction,
                )
            )
            prev_value = r.value
    return result


def detect_anomalies(
    records: list[MetricRecord],
    threshold: float = 2.0,
) -> list[AnomalyRecord]:
    """I-ANOM-1: truly pure function — no I/O, no DuckDB, no randomness (§4.4).

    Returns [] if fewer than 3 data points per metric_id (I-ANOM-1).
    Returns [] if stdev == 0 (I-ANOM-2).
    zscore = (value − mean) / stdev using statistics.mean / statistics.stdev (sample, ddof=1).
    """
    if not records:
        return []

    grouped: dict[str, list[MetricRecord]] = {}
    for r in records:
        grouped.setdefault(r.metric_id, []).append(r)

    result: list[AnomalyRecord] = []
    for mid in sorted(grouped):
        entries = sorted(grouped[mid], key=lambda r: r.phase)
        values = [r.value for r in entries]

        if len(values) < 3:
            continue

        mean = statistics.mean(values)
        stdev = statistics.stdev(values)

        if stdev == 0:
            continue

        for r in entries:
            zscore = (r.value - mean) / stdev
            if abs(zscore) > threshold:
                result.append(
                    AnomalyRecord(
                        phase=r.phase,
                        metric_id=r.metric_id,
                        value=r.value,
                        zscore=zscore,
                    )
                )
    return result


# ─── CLI entry point (Pattern B target) ──────────────────────────────────────

def record_metric_cli(argv: list[str] | None = None) -> int:
    """CLI: record_metric.py --metric <id> --value <v> [--task T-NNN] [--phase N] [--context {...}]"""
    import argparse
    import sys

    args_list = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="record_metric.py",
        description="Record a metric to the SDD event store.",
    )
    parser.add_argument("--metric", required=True, help="Metric ID")
    parser.add_argument("--value", required=True, type=float, help="Numeric value")
    parser.add_argument("--task", default=None, help="Task ID (e.g. T-801)")
    parser.add_argument("--phase", type=int, default=None, help="Phase number")
    parser.add_argument("--context", default=None, help="JSON context dict")
    ns = parser.parse_args(args_list)

    ctx: dict[str, Any] | None = None
    if ns.context:
        import json
        try:
            ctx = json.loads(ns.context)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --context JSON: {e}", file=sys.stderr)
            return 1

    try:
        record_metric(ns.metric, ns.value, ns.task, ns.phase, ctx)
        return 0
    except Exception as e:
        print(f"Error recording metric: {e}", file=sys.stderr)
        return 1
