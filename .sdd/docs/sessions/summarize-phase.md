# Session: SUMMARIZE Phase N
<!-- source: §K.1 (Summarize+Metrics+EventLog) + §K.8 + §0.9 Spec Approval Rule -->

## When to run

After all tasks are DONE and `sdd check-dod` passes. Before human gate.

---

## Read Scope

```
sdd show-state                     ← phase/task counts
.sdd/reports/ValidationReport_T-*.md  ← all validation reports for Phase N
.sdd/templates/PhaseSummary_template.md ← structural template
```

---

## Preconditions

```bash
# Step 0: graph-guard check — enforce I-GRAPH-PROTOCOL-1 before summarize (I-GRAPH-PROTOCOL-1)
sdd graph-guard check --session <session_id>
# exit 0: protocol satisfied → proceed
# exit 1: GRAPH_PROTOCOL_VIOLATION in JSON stderr → STOP
```

---

## Mandatory Steps (IN ORDER)

### Step 1 — PhaseN_Summary.md

```
Output: .sdd/reports/PhaseN_Summary.md
```

Use `.sdd/templates/PhaseSummary_template.md`. Must include:
- Task statuses (all tasks with DONE/FAIL)
- Invariant coverage
- Spec section coverage
- Tests status
- Key decisions
- Reference to Metrics_PhaseN.md (mandatory)
- Improvement hypotheses from anomalies

### Step 2 — Metrics Report (BEFORE EventLog Snapshot)

```
sdd metrics-report --phase N --trend --anomalies
Output: .sdd/reports/Metrics_PhaseN.md
```

PhaseN_Summary.md MUST reference Metrics_PhaseN.md and include improvement hypotheses
derived from anomalies (e.g. tasks too large, guard rejection spike, coverage drop).

### Step 3 — EventLog Snapshot (LAST command)

```
sdd query-events --phase N --include-bash --json --save
Output: .sdd/reports/EL_PhaseN_events.json
```

Source: DuckDB `sdd_events.duckdb` — единственный источник.
Idempotent: re-run overwrites previous snapshot.

---

## Order Constraint (CRITICAL)

```
Summarize → Metrics Report → EventLog Snapshot → human gate
```

EventLog Snapshot MUST be the last LLM action before human review.

---

## §0.9 Spec Approval Rule

If Phase N is marked COMPLETE in `.sdd/plans/Phases_index.md`, its associated Spec_vN
is treated as operationally approved for downstream phases.
Formal Artifacts_index.md update is a human cleanup task.

---

## SSOT State Model (§K.8)

- `TaskSet_vN.md` = source of truth for individual task statuses
- `State_index.yaml` = projection (aggregate), derived via sync_state / replay
- Never edit State_index.yaml directly
