---
source: CLAUDE.md §0.20 + §0.25
last_synced: 2026-04-24
update_trigger: when new FS-* scenarios added or RP-* protocols change
---

# Ref: Recovery & Resilience (Extended)
<!-- Extended reference from sessions/recovery.md -->

## Recovery Decision Rules (RD-1..5)

Classify from JSON stderr BEFORE selecting RP-*. Primary signal: `stage`. Secondary: `error_type`.

| Rule | Condition | Action |
|------|-----------|--------|
| RD-1 | `error_type=Inconsistency` AND PostgreSQL reachable | RP-1 |
| RD-2 | `error_type=StaleStateError` (error_code=6) | CLI retry (CON-4); terminal → `sdd report-error` |
| RD-3 | `error_type=MissingState` OR `error_type=ProjectionError` | RP-1 |
| RD-4 | `stage=BUILD_CONTEXT` (error_code=5) | RP-3 |
| RD-5 | PostgreSQL inaccessible (connection error at any stage) | RP-2 |

## Recovery Protocols (RP-1..4)

**RP-1** — Projection divergence:
```bash
sdd sync-state --phase N
```
- Idempotent, safe to re-run
- Bypasses PhaseGuard (I-SYNC-NO-PHASE-GUARD-1)
- Available in any phase status (PLANNED/ACTIVE/COMPLETE)
- Full EventLog replay → rebuilds State_index.yaml + TaskSet.md in STRICT mode

**RP-2** — sync-state fails OR PostgreSQL inaccessible:
```bash
sdd report-error --type Inconsistency --message "recovery-failed"
# STOP — human operator required
```

**RP-3** — BUILD_CONTEXT failure:
```bash
sdd report-error --type MissingState
# STOP — error in audit_log.jsonl
```
No execution attempted. Human investigates PostgreSQL event log.

**RP-4** — Complete EventLog loss (break-glass, HUMAN ONLY):
```bash
export SDD_EMERGENCY=1
# human calls rebuild_state(EMERGENCY) directly — NOT via CLI
```
LLM MUST NOT execute this path (I-REBUILD-EMERGENCY-2).

## Full Failure Scenario Matrix (§0.25)

### 1. State / Projection

| FS | Signal | Classification | Action | Command | Guarantees |
|----|--------|----------------|--------|---------|------------|
| FS-1 | `error_type=Inconsistency` AND PostgreSQL OK | Projection divergence | RD-1 → RP-1 | `sdd sync-state --phase N` | Idempotent; no EventLog mutation |
| FS-2 | `sdd sync-state` throws PostgreSQL error | Infra failure | RD-5 → RP-2 | `sdd report-error --type Inconsistency --message "sync-state failed"` | No partial writes |
| FS-3 | `MissingState` OR YAML parse fail | Projection missing | RD-3 → RP-1 | `sdd sync-state --phase N` | YAML fully from EventLog |

### 2. Concurrency

| FS | Signal | Classification | Action | Command | Guarantees |
|----|--------|----------------|--------|---------|------------|
| FS-4 | `stage=COMMIT`, error_code=6 | Concurrency conflict | RD-2 → CLI retry | *(CLI handles)* Terminal: `sdd report-error --type StaleStateError` | No duplicate writes (I-IDEM-1) |
| FS-5 | `stage=GUARD`, error_code=1 | Policy violation | STOP, no retry | `sdd report-error --type GuardViolationError --message "<reason>"` | No EventLog mutation |

### 3. Execution

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-6a | `stage=EXECUTE`, error_code=2 | Invariant check failed | STOP | `sdd report-error --type InvariantViolationError --message "<stderr.reason>"` |
| FS-6b | `stage=EXECUTE`, error_code=3 | Handler exception | STOP | `sdd report-error --type ExecutionError --message "<stderr.reason>"` |
| FS-7 | `stage=COMMIT`, error_code=4 | EventStore.append failed | STOP | `sdd report-error --type CommitError` |

### 4. Context / Input

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-8 | `stage=BUILD_CONTEXT`, error_code=5 | EventLog replay failed | RD-4 → RP-3 | `sdd report-error --type MissingState` |
| FS-9 | `MissingContext` OR `ScopeViolation` | Task contract violation | STOP | `sdd report-error --type MissingContext` |

### 5. EventLog / Data

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-10 | BUILD_CONTEXT fail during replay | Critical corruption | RD-4 → RP-3 | `sdd report-error --type Inconsistency` |
| FS-11 | PostgreSQL connection lost / data unavailable | Total data loss | STOP + human break-glass | *(human only)* `SDD_EMERGENCY=1` |

### 6. Validation / Quality

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-12 | `validate-invariants` FAIL | Spec violation | STOP progression | `sdd validate T-NNN` + `sdd report-error --type InvariantViolationError` |
| FS-13 | `tests.status=FAIL` | Quality failure | STOP | `sdd validate T-NNN` + `sdd report-error --type Inconsistency` |

### 7. SLA

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-14 | Metric exceeds threshold | Performance degradation | Continue (non-blocking) | `sdd metrics-report --phase N --anomalies` |

### 8. Governance

| FS | Signal | Classification | Action | Command |
|----|--------|----------------|--------|---------|
| FS-15 | `ScopeViolation` | Security breach | STOP immediately | `sdd report-error --type ScopeViolation` |
| FS-16 | `InvalidState` | FSM violation | STOP | `sdd report-error --type InvalidState` |

## Meta-Rules (FSM-1..5)

- FSM-1: exactly one FS-* MUST match — deterministic
- FSM-2: MUST NOT combine multiple recovery strategies
- FSM-3: no match → STOP + `sdd report-error --type Inconsistency --message "unclassified"`
- FSM-4: no silent failure, no implicit retry
- FSM-5: all actions MUST map to RP-1..4

## Error Semantics Quick Reference

**error_code table:**

| code | Type | Stage |
|------|------|-------|
| 1 | `GuardViolationError` | GUARD |
| 2 | `InvariantViolationError` | EXECUTE |
| 3 | `ExecutionError` | EXECUTE |
| 4 | `CommitError` | COMMIT |
| 5 | `ProjectionError` | BUILD_CONTEXT / PROJECT |
| 6 | `StaleStateError` | COMMIT |
| 7 | `KernelInvariantError` | GUARD |

**Diagnostic triplet (I-DIAG-1):** every kernel failure answers:
1. **where** — `stage` field
2. **why** — `reason` + `violated_invariant`
3. **what state** — `context_hash` + `trace_id`
