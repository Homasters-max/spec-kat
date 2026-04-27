# Session: DECOMPOSE Phase N
<!-- source: §K.1 Decompose + §K.2-§K.5 + §K.6 + §K.7 + §K.13 TG -->

## Preconditions

- `Plan_vN.md` exists in `.sdd/plans/`
- State Guard passes

---

## Read Order (strict)

```
0. sdd show-state                    ← always first; note phase.context vs phase.latest_completed (I-AGENT-STATE-1)
1. sdd show-plan --phase N           ← plan content (I-CLI-SSOT-1); extract logical_context section (I-AGENT-DECOMPOSE-1)
   .sdd/templates/TaskSet_template.md ← structural template
```

FORBIDDEN: direct reads of `.sdd/plans/`, `.sdd/tasks/`.

---

## Content Check (I-SESSION-PI-6)

Before proceeding to Output, verify `Plan_vN.md` contains:

- `## Milestones` section (non-empty)
- `## Risk Notes` section (non-empty)

If either section is absent or empty → ERROR (MissingContext) → STOP → `sdd report-error --type MissingContext --message "Plan_vN.md missing required section"`.

---

## Output

```
.sdd/tasks/TaskSet_vN.md   all tasks Status: TODO
```

- Use `.sdd/templates/TaskSet_template.md` as structural template
- Idempotent: overwrite existing `TaskSet_vN.md`

---

## TaskSet Granularity (TG-1..3)

- TG-1: task MUST be independently implementable AND independently testable
- TG-2: recommended 10–30 tasks per phase; if exceeded → regroup
- TG-3: each task MUST declare `Invariants Covered: I-XXX, I-YYY`

Each task MUST have:
```
Inputs:   explicit file list (exact paths)
Outputs:  explicit file list (exact paths)
Invariants Covered: I-XXX
```

If any field missing → ERROR (MissingContext) → DO NOT PROCEED (§R.8).

---

## Phase Isolation (PIR-1..4 + APG-1..3)

- PIR-1: MUST NOT read TaskSet_vM or Plan_vM where M ≠ N
- PIR-2: allowed: State_index.yaml, Phases_index, Spec_vN, Plan_vN, templates
- PIR-4: glob patterns matching TaskSet_v*.md FORBIDDEN

Anti-patterns — CRITICAL:
- APG-1: do NOT infer TaskSet structure from previous phases
- APG-2: templates are the ONLY structural source for new TaskSet
- APG-3: previous TaskSet_vM are NOT examples — structure from template only

---

## Versioning Rules

- VR-3: TaskSet_vN MUST use Plan_vN (versions must match)
- VR-4: mixing versions → ERROR (VersionMismatch)

---

## SDD Invariants (SDD-2..3)

- SDD-2: every Task MUST reference exactly one Spec section + ≥1 invariant
- SDD-3: TaskSet MUST cover all Plan milestones (no gaps)
- SDD-4: Tasks MUST NOT introduce entities absent in Spec

---

## Auto-actions (I-SESSION-AUTO-1)

After `TaskSet_vN.md` is written, LLM MUST execute in order:

```bash
# 1. Record session event
sdd record-session --type DECOMPOSE --phase N

# 2. Read logical_context from Plan_vN.md (already loaded via sdd show-plan in Read Order)
#    Extract: logical_context.type and logical_context.anchor_phase

# 3. Activate phase — pass logical metadata if present (I-AGENT-DECOMPOSE-1)
# If Plan_vN.md logical_context.type != "none" AND logical_context is present:
sdd activate-phase N --executed-by llm --logical-type <type> --anchor <anchor_phase>
# If logical_context absent OR type == "none":
sdd activate-phase N --executed-by llm
```

**I-AGENT-DECOMPOSE-1:** `sdd activate-phase` in DECOMPOSE MUST pass `--logical-type` and `--anchor`
if and only if `Plan_vN.md` contains `logical_context.type` that is not `"none"`. Both flags are
required together (I-LOGICAL-ANCHOR-2); passing one without the other is a protocol violation.

Then confirm:
```bash
sdd show-state   ← task count must match TaskSet
```

### On Failure (SEM-12)

MUST NOT invoke recovery blindly. Read JSON stderr first: check `error_type` and `error_code`.

If `activate-phase N --executed-by llm` fails:

| `error_type` | `error_code` | Action |
|---|---|---|
| `StaleStateError` | 6 | RD-2: retry CLI once; if still fails → `sdd report-error --type StaleStateError` |
| other | any | Load `sessions/recovery.md` → classify → apply matching RP-* |

---

## Phase State Interpretation (I-AGENT-STATE-1)

`sdd show-state` exposes two distinct fields after BC-41-C:

| Field | Meaning |
|-------|---------|
| `phase.context` | Navigation context — the phase LLM/human switched to |
| `phase.latest_completed` | Max phase_id with status COMPLETE |

**I-AGENT-STATE-1:** If `phase.context ≠ phase.latest_completed`, LLM MUST explicitly name both values. Never represent `phase.context` alone as "the current active phase". Output: "Контекст = фаза N (навигация), последняя завершённая = фаза M."

