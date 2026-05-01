# Session: CHECK_DOD
<!-- source: §0.5 transitions + §K.15 MPS + §K.4 SDD-6 + §K.5 PI-5 + §K.11 + §0.9 -->

## Preconditions

```bash
# Step 0: graph-guard check — enforce I-GRAPH-PROTOCOL-1 before DoD gate
sdd graph-guard check --session <session_id>
# exit 0: protocol satisfied → proceed
# exit 1: GRAPH_PROTOCOL_VIOLATION in JSON stderr → STOP
```

- All tasks in TaskSet_vN.md have Status: DONE
- `invariants.status = PASS`
- `tests.status = PASS`
- Previous phase MUST be COMPLETE (MPS-2)
- Run `sdd validate-config --phase N` first (config valid before DoD)

---

## DoD Conditions (SDD-6)

Phase CANNOT be marked COMPLETE if any:
- Task not DONE
- Any invariant FAIL
- Any test FAIL

---

## Execution

```bash
sdd validate --check-dod --phase N
```

⚠ `sdd check-dod` как отдельный subcommand НЕ существует. Единственный корректный вызов — флаг `--check-dod` на `sdd validate`.

Events emitted on success: `PhaseCompleted`, `MetricRecorded(phase.completion_time)`

---

## Phase Index Invariant (PI-5)

Exactly one phase has status ACTIVE at any time.
After `validate --check-dod` succeeds: current phase → COMPLETE.
Next phase starts ONLY via human: `sdd activate-phase N+1`.

---

## Multi-Phase Safety (MPS-1..3)

- MPS-1: only one ACTIVE phase allowed
- MPS-2: next phase cannot start if previous not COMPLETE
- MPS-3: parallel phases forbidden unless Spec explicitly allows

---

## Consistency Rule (§K.11)

If mismatch between State_index / Phases_index / Spec / Plan / TaskSet:
```
→ ERROR (Inconsistency)
→ DO NOT AUTO-RESOLVE
→ Human must fix OR run: sdd sync-state --phase N
```

---

## §0.9 Spec Approval Rule

Phase COMPLETE ⇒ `Spec_vN` is operationally approved for downstream phases.
Formal `Artifacts_index.md` update is a human cleanup task.

---

## On Success

→ Run SUMMARIZE Phase N session.

## On Failure

→ classify error from JSON stderr → load `sessions/recovery.md`
