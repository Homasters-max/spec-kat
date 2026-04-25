# Session: PLAN Phase N
<!-- source: §K.1 Plan Phase + §K.2-§K.5 + §K.6 Read Order + §K.7 + §K.15 MPS -->

## Preconditions

- `Spec_vN` exists in `.sdd/specs/` (approved)
- Phase N present in `.sdd/plans/Phases_index.md`
- State Guard passes

---

## Read Order (strict)

```
0. sdd show-state                    ← always first; includes phase index info
1. sdd show-spec --phase N           ← spec content (I-CLI-SSOT-1)
2. sdd show-plan --phase N           ← prior plan content if exists (I-CLI-SSOT-1)
   .sdd/templates/Plan_template.md   ← structural template
```

FORBIDDEN: direct reads of `.sdd/specs/`, `.sdd/plans/`, `.sdd/tasks/`.

---

## Output

```
.sdd/plans/Plan_vN.md   Status: DRAFT
```

- Use `.sdd/templates/Plan_template.md` as structural template
- Plan MUST reference Spec_vN sections (SDD-1)
- Idempotent: overwrite existing `Plan_vN.md`

---

## Versioning Rules (VR-1..4)

- VR-1: Spec_vN ↔ Phase N (versions must match)
- VR-2: Plan_vN MUST use Spec_vN
- VR-3: TaskSet_vN MUST use Plan_vN
- VR-4: mixing versions → ERROR (VersionMismatch)

---

## Phase Index Invariants (PI-1..5)

- PI-1: every phase referenced by any command MUST exist in Phases_index.md
- PI-2: Phase.id is unique and monotonic
- PI-3: Phase.spec points to `.sdd/specs/` OR is TODO (future phases)
- PI-4: Phase.status ∈ {PLANNED, ACTIVE, COMPLETE}
- PI-5: exactly one phase has status ACTIVE at any time

---

## Phase Isolation (PIR-1..4)

- PIR-1: MUST NOT read TaskSet_vM, Plan_vM, Spec_vM where M ≠ N
- PIR-2: allowed: State_index.yaml, Phases_index, Spec_vN, Plan_vN, templates
- PIR-3: cross-phase reading only if explicitly required by Spec_vN
- PIR-4: glob patterns matching TaskSet_v*.md FORBIDDEN

Anti-patterns (APG-1..3):
- APG-1: do NOT infer Plan structure from previous phases
- APG-2: templates are the ONLY structural source
- APG-3: previous Plan_vM are NOT examples for planning Phase N

---

## Multi-Phase Safety (MPS-1..3)

- MPS-1: only one ACTIVE phase allowed (PI-5)
- MPS-2: next phase cannot start if previous not COMPLETE
- MPS-3: parallel phases forbidden unless explicitly allowed by Spec

---

## SDD Plan Invariants (SDD-1..5 relevant)

- SDD-1: Plan MUST reference Spec sections
- SDD-2: every Task MUST reference exactly one Spec section + ≥1 invariant
- SDD-3: TaskSet MUST cover all Plan milestones
- SDD-4: Tasks MUST NOT introduce entities absent in Spec
- SDD-5: Validation MUST reference Spec, invariants, acceptance criterion

---

## After Plan is Written

Human reviews Plan_vN.md → activates phase:
```
sdd activate-phase N [--tasks T]   ← human-only action
```
LLM waits. On activation: `sdd show-state` to confirm new state.
