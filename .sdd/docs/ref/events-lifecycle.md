---
source: CLAUDE.md §0.21 + §0.24
last_synced: 2026-04-24
update_trigger: when EventLog lifecycle rules change, new event types added, or schema evolution rules updated
---

# Ref: EventLog Lifecycle & Schema Evolution
<!-- Loaded from sessions/summarize-phase.md when EventLog rules needed -->

## EventLog Lifecycle Rules (§0.21)

| Rule | Statement |
|------|-----------|
| EL-1 | L1 Domain Events retained forever — NEVER `expired=TRUE`, never deleted; SSOT for replay (I-1) |
| EL-2 | L2 Operational Events (MetricRecorded, ToolUse*, ErrorOccurred) soft TTL ~90 days |
| EL-3 | L3 Debug Events (BashCommandStarted/Completed) soft-expired after 7 days via `archive_expired_l3(cutoff_ms)` — sets `expired=TRUE`, no DELETE |
| EL-4 | No compaction CLI exists; LLM MUST NOT issue `UPDATE events SET expired=TRUE` or `DELETE FROM events` |
| EL-5 | `sdd_replay()` with `include_expired=False` (default) excludes expired events |
| EL-6 | `get_current_state()` calls `sdd_replay(include_expired=False)` — only replay path for state derivation |
| EL-7 | Phase-end snapshots (`sdd query-events --phase N --json --save`) archive full trace before TTL expiry |
| EL-8 | `infra.replay_latency_ms` MUST be monitored; degradation > 2× baseline → SLA-3 anomaly |

**Schema:** `expired BOOLEAN NOT NULL DEFAULT FALSE` column (DB migration 2, additive-only).

**Naming note:** `I-EL-7` (invariant in `infra/event_log.py`) = "no DELETE"; `EL-7` (this section) = snapshotting rule.

## Event Level Taxonomy

| Level | Events | Retention | Purpose |
|-------|--------|-----------|---------|
| L1 Domain | `TaskImplemented`, `TaskValidated`, `PhaseCompleted`, `PhaseStarted`, `TaskSetDefined`, `DecisionRecorded`, `TestRunCompleted` | Forever | SSOT replay |
| L2 Operational | `MetricRecorded`, `ToolUseStarted`, `ToolUseCompleted`, `ErrorOccurred` | ~90 days | Observability |
| L3 Debug | `BashCommandStarted`, `BashCommandCompleted` | 7 days | Debugging |

Replay built ONLY from L1. Metrics are L2.

## Schema Evolution Rules (§0.24)

| Rule | Statement |
|------|-----------|
| EV-1 | DuckDB migrations additive-only: only `ADD COLUMN IF NOT EXISTS` in `SDD_MIGRATION_REGISTRY` |
| EV-2 | Event payload fields additive-only; removing/renaming V1_L1_EVENT_TYPES fields = breaking |
| EV-3 | `schema_version` always 1; upcast mechanism requires new spec |
| EV-4 | Reducer MUST replay ALL historical events without error (production guarantee) |

**C-1 consistency check (enforced at import time in `core/events.py`):**
```python
_KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
```
Mode: `SDD_C1_MODE=strict` (AssertionError) in CI; `warn` in production.

**Adding a new event type (correct procedure):**
1. Add to `V1_L1_EVENT_TYPES` frozenset
2. `register_l1_event_type(event_type, handler=None)` at import time (I-REG-STATIC-1)
3. Add DomainEvent subclass with optional fields only (EV-2)
4. Add `ADD COLUMN IF NOT EXISTS` migration if DB column needed (EV-1)
5. C-1 passes at next import automatically

**EV-4 enforcement:** Reducer uses soft ordering guards — unknown events trigger warnings, not exceptions. Converting warnings to exceptions = breaking change.

## Metrics Layer (§0.14)

All metrics → DuckDB (`partition_key='metrics'`). Only path: `record_metric.py` (auto-called).

| Category | Examples |
|----------|----------|
| Process | `task.lead_time`, `task.first_try_pass_rate`, `guard.rejection_rate` |
| Quality | `quality.test_coverage`, `quality.lint_violations`, `quality.type_errors` |
| Agent | `agent.tokens_used`, `agent.scope_violations_attempted` |
| Infra | `infra.eventlog_size`, `infra.guard_latency_ms`, `infra.replay_latency_ms` |

LLM MUST NOT write metrics manually (SEM-8) — scripts auto-record.

**Mandatory phase-end command (AFTER Summarize, BEFORE EventLog Snapshot):**
```bash
sdd metrics-report --phase N --trend --anomalies
→ .sdd/reports/Metrics_PhaseN.md
```
