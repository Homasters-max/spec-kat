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

## Logical Context Evaluation (I-AGENT-PLAN-1)

Before writing `Plan_vN.md`, LLM MUST evaluate the logical type of the new phase:

| Question | `logical_type` | anchor |
|----------|----------------|--------|
| This phase fixes a bug/error in existing phase M | `patch` | `anchor_phase: M` |
| This phase fills a gap missed before phase M | `backfill` | `anchor_phase: M` |
| Standard new phase | `none` | (omit anchor_phase) |

Write `## Logical Context` in `Plan_vN.md`:

```markdown
## Logical Context
type: patch
anchor_phase: 32
rationale: "Fixes BC-32-2 error found in phase 34."
```

If `type: none` — write section with `rationale: "standard phase"` (no `anchor_phase`).

**I-AGENT-PLAN-1:** Every `Plan_vN.md` MUST include `## Logical Context` section (even if type=none). Missing section = protocol violation.

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

## Phase Index Invariants (PI-1..6)

- PI-1: every phase referenced by any command MUST exist in Phases_index.md
- PI-2: Phase.id is unique and monotonic
- PI-3: Phase.spec points to `.sdd/specs/` OR is TODO (future phases)
- PI-4: Phase.status ∈ {PLANNED, ACTIVE, COMPLETE}
- PI-5: exactly one phase has status ACTIVE at any time
- PI-6: after Plan_vN.md is written, Phases_index.md MUST contain an entry for Phase N with `spec = Spec_vN.md` and `plan = Plan_vN.md`; LLM MUST update Phases_index.md before completing the session

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

## Auto-actions (after Plan_vN.md written)

Execute in order before ending the session:

1. **Update Phases_index.md** — ensure Phase N entry exists with:
   - `spec: Spec_vN.md` (points to approved spec in `.sdd/specs/`)
   - `plan: Plan_vN.md` (points to the just-written plan)
   - `status: PLANNED` (if new phase entry; do NOT change existing status)
2. **Validate I-PHASES-INDEX-1**:
   ```
   sdd validate-invariants --check I-PHASES-INDEX-1
   ```
   Must return `passed: true`. On failure → STOP → `sdd report-error`.

> I-PHASES-INDEX-1: `Phases_index.md` MUST contain an entry for every Phase N that has a `Plan_vN.md`; each entry MUST have non-empty `spec` and `plan` fields.

---

## After Plan is Written

Human reviews Plan_vN.md. On approval, session ends.
LLM suggests: `DECOMPOSE Phase N`

> Phase activation (`sdd activate-phase N --executed-by llm`) is performed automatically by LLM
> at the end of the DECOMPOSE session (I-SESSION-AUTO-1), not here.

---

## Phase State Interpretation (I-AGENT-STATE-1)

`sdd show-state` exposes two distinct fields after BC-41-C:

| Field | Meaning |
|-------|---------|
| `phase.context` | Navigation context — the phase LLM/human switched to |
| `phase.latest_completed` | Max phase_id with status COMPLETE |

**I-AGENT-STATE-1:** If `phase.context ≠ phase.latest_completed`, LLM MUST explicitly name both values. Never represent `phase.context` alone as "the current active phase". Output: "Контекст = фаза N (навигация), последняя завершённая = фаза M."
