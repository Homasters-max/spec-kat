# Session: IMPLEMENT T-NNN
<!-- source: §R.1-§R.12 + §K.4 SDD-8..19 + §K.7 PIR+APG + §K.8 + §K.9 CEP+TP + §K.10 DDD -->

## System Model

LLM = Pure Function: `Output = f(CLI_Output, Task_Inputs)`

- `CLI_Output`: deterministic projection via `sdd show-*` commands
- `Task_Inputs`: files listed in Task Inputs field (exact paths only)
- No hidden state. No global scanning. Only explicit inputs allowed.

**CLI invocation rule:** ALWAYS `sdd <command>` — NEVER `python3 -m sdd`.
The package has no `__main__.py`; `python3 -m sdd` fails with exit 1 (SEM-1: no guessing).

---

## Preconditions (EXECUTION ORDER CONTRACT — run as strict linear chain, SEM-13)

```bash
# Step 0: resolve paths (FS-direct, no state dependency — §BOOTSTRAP STATE RULE)
STATE=$(sdd path state)
TASKSET=$(sdd path taskset)

# Step 1: phase guard — must pass before step 2
sdd phase-guard check --command "Implement T-NNN" --state "$STATE"

# Step 2: task guard — depends on step 1 passing
sdd task-guard check --task T-NNN --taskset "$TASKSET"

# Step 3: scope check — for every file in Task Inputs (one call per file)
# --inputs must list ALL Task Inputs (comma-separated) so src/ access is validated
INPUTS=$(echo "<file1>,<file2>,..." )   # all Task Inputs joined with comma
sdd check-scope read <each_input_file> --inputs "$INPUTS"

# Step 4: norm guard
sdd norm-guard check --actor llm --action implement_task
```

ONE tool call per step. Stop on first non-zero exit (SEM-13).
execution_order defined in .sdd/contracts/cli.schema.yaml.

---

## Read Scope — CRITICAL

SDD artifact data MUST come ONLY from CLI (I-CLI-SSOT-1, SDD-11..13):

| Need | Command |
|------|---------|
| Phase/task state | `sdd show-state` |
| Task definition | `sdd show-task T-NNN` |
| Spec content | `sdd show-spec --phase N` |
| Plan content | `sdd show-plan --phase N` |
| Source files | only exact paths listed in Task Inputs |

**FORBIDDEN — direct .sdd/ reads (SDD-11..13):**
- `.sdd/runtime/State_index.yaml` → use `sdd show-state`
- `.sdd/specs/**` → use `sdd show-spec --phase N`
- `.sdd/plans/**` → use `sdd show-plan --phase N`
- `.sdd/tasks/**` → use `sdd show-task T-NNN`

**FORBIDDEN — glob/scan patterns (NORM-SCOPE-001..003):**
```
tests/**   src/**   **/*.py   *   (any wildcard)
```

---

## Write Scope

Modify ONLY files listed in Task Outputs (exact paths). Nothing else.

FORBIDDEN write targets:
- `.sdd/specs/**` — immutable (NORM-SCOPE-004, SDD-9)
- Any file not in Task Outputs

---

## Execution

```
5. Read ONLY files in Task Inputs (exact paths)
6. Modify ONLY files in Task Outputs (exact paths)
7. No cross-task reasoning. No future task anticipation.
```

If Task Inputs or Outputs field is missing → ERROR (MissingContext) → STOP.

---

## Code Architecture Constraints (CEP-1..8 + DDD-1..8)

**Code Editing Protocol:**
- CEP-1: prefer diff-style patches over full file rewrites
- CEP-2: modify ONLY files in Task Outputs
- CEP-3: never delete existing tests
- CEP-4: new behavior requires new tests
- CEP-5: code removal must be justified in ValidationReport
- CEP-6: no speculative refactoring
- CEP-7: public interfaces stable unless Spec requires change
- CEP-8: follow SER invariants (determinism, purity, event-sourcing)

**Domain-Driven Design:**
- DDD-1: code organized by Bounded Context
- DDD-2: no direct cross-BC imports — only via interfaces/events
- DDD-3: domain logic must not depend on infrastructure
- DDD-4: reducer layer is pure domain logic
- DDD-5: side effects only via event emission
- DDD-6: all state changes expressed as events
- DDD-7: no hidden state mutations
- DDD-8: state must be reconstructable via replay

**Test Policy:**
- TP-1: existing tests MUST pass after changes
- TP-2: new functionality MUST include tests
- TP-3: determinism MUST be tested where applicable
- TP-4: event-sourced components MUST have replay tests

---

## Path Rules (SDD-14..19)

- SDD-14: no literal `.sdd/` path strings in `src/sdd/**/*.py` except `infra/paths.py`
- SDD-15: `paths.py` imports ONLY stdlib (os, pathlib) — zero intra-sdd imports
- SDD-16: Task Inputs/Outputs paths relative to repo root, not SDD_HOME
- SDD-17: `paths.py` does NOT create directories; callers responsible for existence
- SDD-18: `reset_sdd_root()` MUST NOT be called in production code
- SDD-19: Config MUST NOT override core SDD paths (state, tasks, specs, plans, db)

---

## Phase Isolation (PIR-1..4 + APG-1..3)

- PIR-1: MUST NOT read TaskSet_vM, Plan_vM, Spec_vM where M ≠ current phase N
- PIR-2: allowed per Phase N: State_index.yaml, Phases_index, Spec_vN, Plan_vN, templates
- PIR-3: cross-phase reading only if explicitly required by Spec_vN
- PIR-4: glob patterns matching TaskSet_v*.md FORBIDDEN
- APG-1: do NOT infer TaskSet structure from previous phases
- APG-2: templates are the ONLY structural source for new artifacts
- APG-3: previous TaskSet_vM are NOT examples

**PIR-1 Exception — patch/backfill phases (I-AGENT-IMPL-1):**

If `sdd show-state` shows `phase.logical_type == "patch"` or `"backfill"`, LLM MUST load
anchor-phase context via CLI before implementation:

```bash
[Auto-action] sdd show-state          ← check phase.logical_type and phase.context
[Auto-action] sdd show-plan --phase <anchor_phase_id>
[Auto-action] sdd show-spec --phase <anchor_phase_id>
```

Purpose: understand what is being fixed (patch) or filled (backfill) without blind implementation.
Direct reads of `.sdd/plans/` and `.sdd/specs/` remain FORBIDDEN (NORM-SCOPE-004).

**I-AGENT-IMPL-1:** In IMPLEMENT-session for a phase with `logical_type != None`, LLM MUST load
anchor-phase plan and spec via `sdd show-*` CLI before any implementation begins.

---

## Post-Execution

```
8. sdd complete T-NNN
```

Events emitted: `TaskImplemented`, `StateSynced`, `MetricRecorded(task.lead_time)`

---

## Phase State Interpretation (I-AGENT-STATE-1)

`sdd show-state` exposes two distinct fields after BC-41-C:

| Field | Meaning |
|-------|---------|
| `phase.context` | Navigation context — the phase LLM/human switched to |
| `phase.latest_completed` | Max phase_id with status COMPLETE |

**I-AGENT-STATE-1:** If `phase.context ≠ phase.latest_completed`, LLM MUST explicitly name both values. Never represent `phase.context` alone as "the current active phase". Output: "Контекст = фаза N (навигация), последняя завершённая = фаза M."

---

## On Failure

→ `RECOVERY` session (load `sessions/recovery.md`, classify via JSON stderr, follow RP-*)
