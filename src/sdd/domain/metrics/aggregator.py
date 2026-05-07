from __future__ import annotations

import json
from dataclasses import dataclass

from sdd.infra.event_query import EventRecord


@dataclass(frozen=True)
class MetricRecord:
    seq: int
    metric_id: str
    value: float
    task_id: str | None
    phase_id: int | None
    context: tuple[tuple[str, str], ...]
    recorded_at: str


@dataclass(frozen=True)
class MetricsSummary:
    phase_id: int
    task_count: int
    metric_count: int
    metrics: tuple[MetricRecord, ...]
    im1_violations: tuple[str, ...]
    has_im1_violation: bool


class MetricsAggregator:
    """
    Pure aggregation over queried events. No I/O — accepts pre-fetched event tuples.
    I-MR-2: same inputs → same MetricsSummary (pure function).
    I-PROJ-CONST-1: deterministic; no randomness, no I/O.
    I-PROJ-CONST-2: no instance state between calls.
    """

    def aggregate(
        self,
        task_completed_events: tuple[EventRecord, ...],
        metric_recorded_events: tuple[EventRecord, ...],
        phase_id: int,
    ) -> MetricsSummary:
        """
        I-MR-1: for each TaskCompleted event with payload.task_id == T,
        check for a MetricRecorded event with payload.task_id == T and
        payload.metric_id == "task.lead_time". Correlation by task_id only.
        """
        metrics: list[MetricRecord] = []
        for er in metric_recorded_events:
            try:
                p = json.loads(er.payload)
            except (ValueError, TypeError):
                continue
            context_raw = p.get("context", {})
            if isinstance(context_raw, dict):
                context: tuple[tuple[str, str], ...] = tuple(
                    (str(k), str(v)) for k, v in context_raw.items()
                )
            else:
                context = ()
            metrics.append(
                MetricRecord(
                    seq=er.seq,
                    metric_id=str(p.get("metric_id", "")),
                    value=float(p.get("value", 0.0)),
                    task_id=p.get("task_id") or None,
                    phase_id=int(p["phase_id"]) if p.get("phase_id") is not None else None,
                    context=context,
                    recorded_at=str(p.get("recorded_at", "")),
                )
            )

        # Build set of task_ids that have a task.lead_time metric
        lead_time_task_ids: set[str] = {
            m.task_id
            for m in metrics
            if m.metric_id == "task.lead_time" and m.task_id is not None
        }

        # I-MR-1: find TaskCompleted task_ids with no matching MetricRecorded
        violations: list[str] = []
        for er in task_completed_events:
            try:
                p = json.loads(er.payload)
            except (ValueError, TypeError):
                continue
            task_id = p.get("task_id")
            if task_id and task_id not in lead_time_task_ids:
                violations.append(task_id)

        im1_violations = tuple(violations)
        return MetricsSummary(
            phase_id=phase_id,
            task_count=len(task_completed_events),
            metric_count=len(metrics),
            metrics=tuple(metrics),
            im1_violations=im1_violations,
            has_im1_violation=bool(im1_violations),
        )
