# Session: DECOMPOSE Phase N
<!-- source: §K.1 Decompose + §K.2-§K.5 + §K.6 + §K.7 + §K.13 TG -->

## Preconditions

- `Plan_vN.md` exists in `.sdd/plans/`
- `Plan_vN.md` Status = ACTIVE
- State Guard passes

---

## Read Order (strict)

```
0. sdd show-state                    ← always first
1. sdd show-plan --phase N           ← plan content (I-CLI-SSOT-1)
   .sdd/templates/TaskSet_template.md ← structural template
```

FORBIDDEN: direct reads of `.sdd/plans/`, `.sdd/tasks/`.

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

## After TaskSet is Written

Human reviews TaskSet_vN.md → activates:
```
sdd activate-phase N --tasks T   ← human-only (if not already activated)
```
LLM: `sdd show-state` to confirm task count matches.
