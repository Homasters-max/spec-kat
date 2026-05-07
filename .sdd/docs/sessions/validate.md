# Session: VALIDATE T-NNN
<!-- source: §R.1, §R.7 + §K.4 SDD-8..13 + §K.9 TP + §R.5 State Guard -->

## Preconditions (EXECUTION ORDER CONTRACT — run as strict linear chain, SEM-13)

```bash
# Step 0: resolve paths (FS-direct, no state dependency — §BOOTSTRAP STATE RULE)
STATE=$(sdd path state)

# Step 1: phase guard — must pass before step 2
sdd phase-guard check --command "Validate T-NNN" --state "$STATE"

# Step 2: config valid before running checks
sdd validate-config --phase N
```

ONE tool call per step. Stop on first non-zero exit (SEM-13).
execution_order defined in .sdd/contracts/cli.schema.yaml.

---

## Read Scope — CLI SSOT (SDD-11..13)

SDD artifact data MUST come ONLY from CLI:

| Need | Command |
|------|---------|
| Phase/task state | `sdd show-state` |
| Task definition | `sdd show-task T-NNN` |

FORBIDDEN: direct reads of `.sdd/runtime/`, `.sdd/tasks/`, `.sdd/specs/`.
FORBIDDEN: glob patterns (`tests/**`, `src/**`, `**/*.py`).

---

## Execution

```
3. sdd validate-invariants --phase N --task T-NNN
   (runs checks[] from TaskSet via project_profile build.commands;
    auto-records quality metrics)

4. Produce .sdd/reports/ValidationReport_T-NNN.md
```

ValidationReport MUST reference:
- Spec section covered
- Invariants checked (I-XXX)
- Acceptance criterion result
- Test results

---

## Tech Stack (loaded via §HARD-LOAD Rule 3)

Build commands, coverage thresholds, linter config — from `.sdd/docs/ref/tech-stack.md`.
MUST be loaded before running validate-invariants.

---

## Test Policy (TP-1..4)

- TP-1: existing tests MUST pass
- TP-2: new functionality MUST have tests
- TP-3: determinism MUST be tested where applicable
- TP-4: event-sourced components MUST have replay tests

---

## State Guard

```
IF State_index.yaml missing                   → ERROR (MissingState)
IF phase.current ≠ plan.version               → ERROR (Inconsistency)
IF plan.version ≠ tasks.version               → ERROR (Inconsistency)
IF tasks.completed > tasks.total              → ERROR (Inconsistency)
IF len(tasks.done_ids) ≠ tasks.completed      → ERROR (Inconsistency)
```

---

## Post-Execution

```
5. sdd validate T-NNN --result PASS|FAIL
   (auto-records: task.validation_attempts, task.first_try_pass_rate)
```

⚠ `--result PASS|FAIL` ОБЯЗАТЕЛЕН — без него команда завершается exit 1 с `InvalidState`.

Events emitted: `TaskValidated`, `InvariantsUpdated`, `TestsUpdated`, `DoDChecked`,
`MetricRecorded(quality.test_coverage, quality.lint_violations, task.validation_attempts)`

---

## On Failure

- Invariant FAIL → `sdd report-error --type InvariantViolationError` → fix → re-validate
- State Guard fail → load `sessions/recovery.md`, apply RP-1
- Any other error → `RECOVERY` session
