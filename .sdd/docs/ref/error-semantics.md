---
source: CLAUDE.md §0.19 + §0.22 + §0.18
last_synced: 2026-04-24
update_trigger: when error_code table changes, new error types added, or concurrency model updated
---

# Ref: Error Semantics & Concurrency
<!-- Loaded from sessions/recovery.md when deep error investigation needed -->

## Error Semantics (§0.19)

**Pipeline stages:**
```
BUILD_CONTEXT → GUARD → EXECUTE → COMMIT → (execute_and_project) → PROJECT
```

**error_code table:**

| code | Type | Raised by |
|------|------|-----------|
| 1 | `GuardViolationError` | GUARD stage DENY |
| 2 | `InvariantViolationError` | EXECUTE stage (handler invariant check) |
| 3 | `ExecutionError` (any other handler exception) | EXECUTE stage |
| 4 | `CommitError` (EventStore.append failure, not optimistic lock) | COMMIT stage |
| 5 | BUILD_CONTEXT replay failure + `ProjectionError` | BUILD_CONTEXT and PROJECT stages |
| 6 | `StaleStateError` | COMMIT stage (optimistic lock — I-OPTLOCK-1) |
| 7 | `KernelInvariantError` | GUARD stage (DENY without reason/violated_invariant) |

**trace_id:** `sha256(command_type + str(head_seq))[:16]` — 16-hex chars.
Fallback when `head_seq is None`: `sha256(command_type + str(payload))[:16]` (I-TRACE-FALLBACK-1).

**context_hash:**
- GUARD/EXECUTE/COMMIT: `sha256(reducer_state_repr)[:32]` — 32-hex chars
- BUILD_CONTEXT failure: `f"FAIL:{exc_type}"` sentinel (e.g. `"FAIL:psycopg2.OperationalError"`)
- PROJECT failure: `"FAIL:PROJECTION"` (I-CONTEXT-HASH-SENTINEL-1)

**ErrorEvent emission rules:**
- GUARD/EXECUTE/COMMIT errors → append to EventLog (PostgreSQL)
- BUILD_CONTEXT errors → write to `audit_log.jsonl` (EventLog unavailable)
- PROJECT errors → write to `audit_log.jsonl` (wrapped by execute_and_project)
- `ErrorEvent.phase_id` is always `None` (I-ERROR-PHASE-NULL-1)
- `ErrorEvent` is L2 (observability); NOT in `V1_L1_EVENT_TYPES`; replay ignores it

**Diagnostic triplet (I-DIAG-1):** every kernel failure MUST answer:
1. **where** — `stage` field (BUILD_CONTEXT/GUARD/EXECUTE/COMMIT/PROJECT)
2. **why** — `reason` + `violated_invariant`
3. **what state** — `context_hash` + `trace_id`

## Responsibility Matrix (§0.18)

| Command | CLI | Actor | Notes |
|---------|-----|-------|-------|
| `activate-phase N` | `sdd activate-phase N [--tasks T]` | **human** | Emits PhaseStarted + TaskSetDefined |
| `complete T-NNN` | `sdd complete T-NNN` | llm | Emits TaskImplemented |
| `validate T-NNN` | `sdd validate T-NNN` | llm | Emits TaskValidated |
| `check-dod` | `sdd check-dod --phase N` | llm | Emits PhaseCompleted on success |
| `sync-state` | `sdd sync-state --phase N` | llm | Triggers project_all; no domain events |
| `record-decision` | `sdd record-decision …` | llm | Emits DecisionRecordedEvent (audit only) |

**NormGuard enforcement:** human-only commands (`activate-phase`) rejected if `actor=llm`.

## Concurrency Model (§0.22)

| Rule | Statement |
|------|-----------|
| CON-1 | Single-writer assumption per PostgreSQL connection |
| CON-2 | Optimistic locking: `head_seq` captured at BUILD_CONTEXT; verified before INSERT |
| CON-3 | `StaleStateError` (error_code=6) raised when `MAX(seq) != head_seq` |
| CON-4 | Retry policy: up to 3 attempts, exponential backoff 100ms→200ms→400ms; safe via I-IDEM-1 |
| CON-5 | Guard functions are stateless pure functions (I-GUARD-STATELESS-1) |
| CON-6 | Retry owned exclusively by CLI layer — not LLM, not handler |
| CON-7 | LLM treats `StaleStateError` as terminal → `sdd report-error --type StaleStateError`; CLI handles retry per CON-4 |

**Idempotency layers:**
- I-IDEM-1: `command_id = sha256(asdict(payload))[:32]` — duplicate INSERT silently skipped
- I-IDEM-SCHEMA-1: per-event `(command_id, event_index)` in `EventStore._append_locked`

## Performance SLAs (§0.23)

| Rule | Target |
|------|--------|
| SLA-1: guard pipeline | ≤ 500ms per command (p95) |
| SLA-2: validate_invariants | ≤ 30s (`timeout_secs=30`); hard limit 300s |
| SLA-3: eventlog_size | ≤ 5000 events normal; > 10000 = anomaly |
| SLA-4: SLA violation | MUST emit `MetricRecorded(infra.sla_violation=1)` |
| SLA-5: repeated violations | > 3 per phase → anomaly flag in `sdd metrics-report` |
