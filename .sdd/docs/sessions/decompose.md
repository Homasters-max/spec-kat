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

## Navigation Section (STEP 4.5 readiness — I-DECOMPOSE-RESOLVE-1)

Every task whose `Outputs` include ≥1 `src/` file SHOULD declare a `Navigation:` block.
Tasks with no `src/` outputs MAY still declare `Navigation:` to guide anchor discovery.
Absence of `Navigation:` triggers STEP 4.5 fallback (Task Inputs only) in IMPLEMENT — valid but suboptimal.

### Format

```
Navigation:
    resolve_keywords: <KeySymbol1>, <KeySymbol2>
    write_scope:      <path/to/output1.py>, <path/to/output2.py>
```

Indented by 4 spaces. Parsed by `TaskNavigationSpec.parse()` (navigation.py).

### Rules for `resolve_keywords`

- List 1–3 domain symbols the task primarily implements or modifies
- Use class names, invariant IDs, or guard names — whatever is indexed in the graph
- Keywords MUST be validated via `sdd resolve "<keyword>" --format json` after TaskSet is written (I-DECOMPOSE-RESOLVE-1)
- If `sdd resolve` returns NOT_FOUND → replace keyword before committing TaskSet
- Prefer specific symbols (`GraphSessionState`, `scope_policy`) over generic words (`handler`, `utils`)

### Rules for `write_scope`

- Copy `Outputs` paths that are `src/` files (exact same paths, comma-separated)
- Exclude `.sdd/` artifacts, test files, config files — only implementation targets
- If `Outputs` has no `src/` files → leave `write_scope:` empty (valid: STEP 4.5-C skipped)

### v56+ anchor mode (anchor_nodes)

When exact graph node IDs are known (e.g. after a previous `sdd resolve` in a related task):

```
Navigation:
    anchor_nodes:      GUARD:scope_policy, FILE:src/sdd/graph_navigation/session_state.py
    allowed_traversal: implements, guards
    write_scope:       src/sdd/guards/scope_policy.py
```

Use `anchor_nodes` instead of `resolve_keywords` when `is_anchor_mode()` should return True.
Do NOT mix both fields in the same task — choose one mode.

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

## Keyword Validation (I-DECOMPOSE-RESOLVE-1 / I-DECOMPOSE-RESOLVE-2)

After writing `TaskSet_vN.md`, validate every `resolve_keywords` entry across all tasks.
If no task contains a `navigation` section → skip this step entirely.

For each `resolve_keyword` entry (strict sequential chain, SEM-13 — one tool call per keyword):

```bash
sdd resolve "<keyword>" --format json
# → exit 0 required (I-DECOMPOSE-RESOLVE-1)
# → candidates[0].kind ∈ expected_kinds for this entry (I-DECOMPOSE-RESOLVE-2)
```

On failure:
- exit non-zero → ERROR (KeywordResolveError) → STOP → `sdd report-error --type KeywordResolveError --message "Keyword '<keyword>' failed to resolve"`
- `candidates[0].kind` ∉ `expected_kinds` → ERROR (KeywordKindMismatch) → STOP → `sdd report-error --type KeywordKindMismatch --message "Keyword '<keyword>' resolved to unexpected kind '<actual_kind>'"`

Invalid or unresolvable keyword MUST NOT be committed to TaskSet — fix the keyword before proceeding.

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

