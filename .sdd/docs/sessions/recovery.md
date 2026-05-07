# Session: RECOVERY
<!-- source: §0.20 RP-1..4 + §0.25 FS-1..16 + §K.12 Error Protocol — self-contained -->

## STOP rule

On ANY violation or error: STOP → classify from JSON stderr → apply exactly the matching RP-*.
LLM MUST NOT invoke recovery as a blind first action (SEM-12).

---

## Step 1 — Classify from JSON stderr

Read `error_type`, `stage`, `error_code` from JSON stderr output.

| Rule | Condition | → Action |
|------|-----------|----------|
| RD-1 | `error_type=Inconsistency` AND PostgreSQL reachable | RP-1 |
| RD-2 | `error_type=StaleStateError` (error_code=6) | CLI retry (CON-4); on terminal → `sdd report-error --type StaleStateError` |
| RD-3 | `error_type=MissingState` OR `error_type=ProjectionError` | RP-1 |
| RD-4 | `stage=BUILD_CONTEXT` (error_code=5) | RP-3 |
| RD-5 | PostgreSQL inaccessible (connection error) | RP-2 |

If no RD-* matches → FSM-3: STOP + `sdd report-error --type Inconsistency --message "unclassified"`.

---

## Step 2 — Apply Recovery Protocol

**RP-1** — Projection divergence (Inconsistency / MissingState / ProjectionError):
```
sdd sync-state --phase N
```
Idempotent. No EventLog mutation. Bypasses PhaseGuard (I-SYNC-NO-PHASE-GUARD-1).
Rebuilds State_index.yaml and TaskSet.md from full EventLog replay.

**RP-2** — sync-state fails OR PostgreSQL inaccessible:
```
sdd report-error --type Inconsistency --message "recovery-failed"
STOP → human operator required
```

**RP-3** — BUILD_CONTEXT failure (error_code=5):
```
sdd report-error --type MissingState
STOP → error written to audit_log.jsonl
```
LLM MUST NOT proceed; human investigates PostgreSQL event log.

**RP-4** — Complete EventLog loss (break-glass — HUMAN ONLY):
```
export SDD_EMERGENCY=1
rebuild_state(EMERGENCY)   ← human operator only, NOT via CLI
```
LLM MUST NOT execute RP-4. I-REBUILD-EMERGENCY-2.

---

## Failure Scenarios Quick Reference

| Scenario | Signal | Action |
|----------|--------|--------|
| FS-1: Projection drift | `error_type=Inconsistency`, PostgreSQL OK | RD-1 → RP-1 |
| FS-2: sync-state fails | PostgreSQL error during sync | RD-5 → RP-2 |
| FS-3: Missing/corrupt YAML | `MissingState` OR YAML parse fail | RD-3 → RP-1 |
| FS-4: StaleStateError | `stage=COMMIT`, error_code=6 | RD-2 → CLI retry |
| FS-5: Guard rejection | `stage=GUARD`, error_code=1 | STOP; do NOT retry; `sdd report-error --type GuardViolationError --message "<reason>"` |
| FS-6a: Invariant violation | `stage=EXECUTE`, error_code=2 | STOP; `sdd report-error --type InvariantViolationError` |
| FS-6b: Handler exception | `stage=EXECUTE`, error_code=3 | STOP; `sdd report-error --type ExecutionError` |
| FS-7: Commit failure | `stage=COMMIT`, error_code=4 | STOP; `sdd report-error --type CommitError` |
| FS-8: BUILD_CONTEXT fail | `stage=BUILD_CONTEXT`, error_code=5 | RD-4 → RP-3 |
| FS-9: Missing task I/O | `MissingContext` OR `ScopeViolation` | STOP; `sdd report-error --type MissingContext` |
| FS-10: EventLog replay crash | BUILD_CONTEXT fail during replay | RD-4 → RP-3 |
| FS-11: EventLog missing | PostgreSQL connection lost / data unavailable | RD-5 → RP-2; human break-glass |
| FS-12: Invariant FAIL | `validate-invariants` returns FAIL | STOP; `sdd validate T-NNN` + `sdd report-error --type InvariantViolationError` |
| FS-13: Test failure | `tests.status=FAIL` | STOP; `sdd validate T-NNN` + `sdd report-error --type Inconsistency` |
| FS-14: SLA violation | Metric exceeds threshold | Continue (non-blocking); `sdd metrics-report --phase N --anomalies` |
| FS-15: Scope violation | `ScopeViolation` | STOP immediately; `sdd report-error --type ScopeViolation` |
| FS-16: Illegal transition | `InvalidState` | STOP; `sdd report-error --type InvalidState` |

---

## Error Protocol Format (§K.12)

```
ERROR:
  type:            PhaseGuard | MissingSpec | Inconsistency | InvalidState |
                   VersionMismatch | MissingState | ScopeViolation | NormViolation
  message:         <short explanation>
  required_action: <human fix>
```

Then call: `sdd report-error --type <type> --message "<msg>"`

---

## Meta-Rules (FSM-1..5)

- FSM-1: exactly one FS-* scenario MUST match — classification is deterministic
- FSM-2: MUST NOT combine multiple recovery strategies or invent hybrid paths
- FSM-3: if no FS-* matches → STOP + `sdd report-error --type Inconsistency --message "unclassified"`
- FSM-4: no scenario allows silent failure or implicit retry
- FSM-5: all recovery actions MUST map to RP-1..4; anything else requires human authorization

---

## Consistency Rule (§K.11)

```
If mismatch between State_index / Phases_index / Spec / Plan / TaskSet:
  → ERROR (Inconsistency)
  → DO NOT AUTO-RESOLVE
  → Human must fix OR run: sdd sync-state --phase N
```

---

## After Recovery

Re-declare session type and continue from preconditions.
NEVER skip preconditions after recovery.

Extended reference: `.sdd/docs/ref/recovery.md` (full RP detail) + `.sdd/docs/ref/error-semantics.md`.
