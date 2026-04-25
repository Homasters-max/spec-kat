# Session: DRAFT_SPEC vN
<!-- source: §K.1 Draft Spec + §K.2-§K.5 + §K.6 + §K.7 -->

## Preconditions

- Phase N present in `.sdd/plans/Phases_index.md`
- State Guard passes

---

## Read Order (strict)

```
0. sdd show-state                    ← always first
   .sdd/templates/Spec_template.md   ← structural template (mandatory)
```

FORBIDDEN: direct reads of `.sdd/specs/`, `.sdd/plans/`.

---

## Output

```
.sdd/specs_draft/Spec_vN_<name>.md
```

- Use `.sdd/templates/Spec_template.md` — template is the ONLY structural source
- NEVER write into `.sdd/specs/` (immutable, human-controlled)
- Idempotent: overwrite existing draft

---

## Versioning Rules (VR-1..4)

- VR-1: Spec_vN ↔ Phase N (version must match)
- VR-2: Plan_vN MUST use Spec_vN
- VR-4: mixing versions → ERROR (VersionMismatch)

---

## SDD Invariants for Spec Structure (SDD-1..10)

- SDD-1: Plan MUST reference Spec sections (Spec must be structured to allow this)
- SDD-2: every Task MUST reference exactly one Spec section + ≥1 invariant
- SDD-3: TaskSet MUST cover all Plan milestones (Spec must define milestones)
- SDD-4: Tasks MUST NOT introduce entities absent in Spec → Spec must declare all entities
- SDD-5: Validation MUST reference Spec, invariants, acceptance criterion
- SDD-6: Phase cannot be COMPLETE if any invariant FAIL or any task not DONE
- SDD-7: LLM must refuse execution on inconsistency
- SDD-9: `.sdd/specs/` is immutable — draft goes to `.sdd/specs_draft/`
- SDD-10: drafts MUST stay in `.sdd/specs_draft/`

---

## Phase Isolation (PIR-1..4)

- PIR-1: MUST NOT read Spec_vM where M ≠ N
- PIR-2: allowed: State_index.yaml, Phases_index, templates
- PIR-3: cross-phase reference only if explicitly required

---

## After Draft is Written

Human reviews `.sdd/specs_draft/Spec_vN_*.md` → approves → moves to `.sdd/specs/`.

LLM MUST NOT move spec to `.sdd/specs/` (SDD-9, NORM-ACTOR-001).
