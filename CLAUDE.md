# CLAUDE — SDD Master Protocol (Hardened Context Architecture v5)

**Status:** ACTIVE — supersedes all prior CLAUDE_v*.md versions  
**Formal model:** .sdd/specs/SDD_Spec_v1.md (events, reducer, guards — BC-9)  
**SENAR norms:** .sdd/norms/norm_catalog.yaml (machine-readable, enforcement layer)  
**Tools:** `sdd` CLI (src/sdd/ — pip install -e .)  
**Docs:** .sdd/docs/sessions/ (session files) · .sdd/docs/ref/ (reference files)

> **Язык ответов:** все ответы LLM в чате — **только на русском языке**. Код, команды, пути, идентификаторы — на языке оригинала (английский).

---

## §WORKFLOW — SDD Lifecycle

```
Artifact FSM:
  DRAFT_SPEC → [human: approve] → APPROVED_SPEC → PLAN_DRAFT →
  [human: activate] → PLAN_ACTIVE → TASKS_DEFINED →
  IMPLEMENTATION → VALIDATION → PHASE_COMPLETE

Phase Status FSM:
  PLANNED → [human: sdd activate-phase N] → ACTIVE →
  [llm: sdd check-dod] → COMPLETE
```

Human gates: spec approval, plan/phase activation, phase completion review.  
LLM gates: implementation, validation, DoD verification.  
If unsure of position: `sdd show-state`

---

## §SESSION — Session Contract & Routing

**On session start:** declare session type. Load session file. Follow preconditions exactly.  
**Ambiguity rule:** type ambiguous OR multi-type match → STOP → ask user.  
**On any error:** STOP → load `sessions/recovery.md` → classify → follow RP-*.

### Routing Table

| Session type | Load |
|---|---|
| `IMPLEMENT T-NNN` | `.sdd/docs/sessions/implement.md` |
| `VALIDATE T-NNN` | `.sdd/docs/sessions/validate.md` |
| `PLAN Phase N` | `.sdd/docs/sessions/plan-phase.md` |
| `DECOMPOSE Phase N` | `.sdd/docs/sessions/decompose.md` |
| `DRAFT_SPEC vN` | `.sdd/docs/sessions/draft-spec.md` |
| `SUMMARIZE Phase N` | `.sdd/docs/sessions/summarize-phase.md` |
| `CHECK_DOD` | `.sdd/docs/sessions/check-dod.md` |
| `RECOVERY` | `.sdd/docs/sessions/recovery.md` |
| `INIT_STATE` | `.sdd/docs/sessions/init-state.md` |
| `FULL_LOAD` | `sessions/implement.md` + `sessions/plan-phase.md` + `ref/kernel-contracts.md` |

### Session FSM (complete)

```
Planner sequence:

  DRAFT_SPEC vN
    → LLM AUTO: sdd record-session --type DRAFT_SPEC --phase N   (I-SESSION-DECLARED-1)
    → LLM: creates .sdd/specs_draft/Spec_vN.md
    → [human: approves — moves file to .sdd/specs/]              ← HUMAN GATE

  PLAN Phase N
    → LLM AUTO: sdd record-session --type PLAN --phase N         (I-SESSION-DECLARED-1)
    → LLM: writes Plan_vN.md
    → LLM AUTO: updates Phases_index.md; validates I-PHASES-INDEX-1  (I-SESSION-PI-6)
    → [Auto-action] display: "Phases_index updated. Phase N = PLANNED"
    → suggests: "DECOMPOSE Phase N"

  DECOMPOSE Phase N
    → Preconditions: Plan_vN.md EXISTS + content check (Milestones + Risk Notes) +
                     Spec_vN.md in .sdd/specs/
    → LLM AUTO: sdd record-session --type DECOMPOSE --phase N    (I-SESSION-DECLARED-1)
    → LLM: writes TaskSet_vN.md
    → LLM AUTO: sdd activate-phase N --executed-by llm           (I-SESSION-AUTO-1)
    → LLM AUTO: sdd show-state
    → suggests: "IMPLEMENT T-N01"

IMPLEMENT/VALIDATE cycle:

  IMPLEMENT T-NNN
    → LLM AUTO: sdd record-session --type IMPLEMENT --phase N    (I-SESSION-DECLARED-1)
    → LLM: implements code
    → LLM AUTO: sdd complete T-NNN
    → suggests next TODO task or VALIDATE

  VALIDATE T-NNN
    → LLM AUTO: sdd record-session --type VALIDATE --phase N     (I-SESSION-DECLARED-1)
    → LLM: runs checks
    → LLM AUTO: sdd validate T-NNN --result PASS|FAIL

  VALIDATE T-NNN [last task] → SUMMARIZE Phase N
  SUMMARIZE → CHECK_DOD

Error transitions (from ANY session):
  any → RECOVERY   (on any error)
  RECOVERY → any   (on resolution: re-declare session type)

Auto-action display rule (I-SESSION-VISIBLE-1):
  [Auto-action] sdd <command>
  [Result] <outcome summary>
  [State] <key state fields>
```

---

## §HARD-LOAD — Mandatory Context Rules

These are explicit agent actions. "Confirmed" without loading = protocol breach.

**Rule 1:** Before any LLM write command (`complete` | `validate` | `check-dod` | `sync-state` | `record-decision`):
→ confirm `kernel-contracts.md` loaded; if not: LOAD `.sdd/docs/ref/kernel-contracts.md`

**Rule 2:** Before any failure recovery action:
→ confirm `sessions/recovery.md` loaded; if not: LOAD `.sdd/docs/sessions/recovery.md`

**Rule 3:** Before `VALIDATE` or `CHECK_DOD` session:
→ MUST LOAD `.sdd/docs/ref/tech-stack.md` (build commands, coverage threshold)

**Rule 4:** Before executing any CLI command NOT listed in §TOOLS:
→ MUST LOAD `.sdd/docs/ref/tool-reference.md`

---

## §META — Priority & State

### Priority Hierarchy (highest wins)

```
1. .sdd/specs/SDD_Spec_v1.md              ← formal truth, immutable
2. .sdd/norms/norm_catalog.yaml           ← SENAR regulation
3. CLAUDE.md §HARD-LOAD / §INV            ← execution scope rules
4. .sdd/docs/sessions/<type>.md           ← session-specific rules
5. .sdd/docs/ref/*.md                     ← reference detail
6. .sdd/plans/Plan_vN.md                  ← phase plan
7. .sdd/tasks/TaskSet_vN.md               ← task definitions
8. .sdd/config/project_profile.yaml       ← project config
```

### Execution Boundary Table

| Layer | Active During | Governs |
|---|---|---|
| Spec invariants | Always | Events, types, guards |
| SENAR norms | Always | Actor permissions, supervision gates |
| Session rules | Declared session only | I/O scope, preconditions, protocol |
| Kernel contracts | Any write command | Interface stability, Write Kernel |

### Ref File Maintenance

Each ref file carries `update_trigger` header. Update when source section changes.  
`SDD_SEQ_CHECKPOINT` rule: see `.sdd/docs/ref/audit-hooks.md`.

---

## §INV — Baseline Invariants

| ID | Statement |
|----|-----------|
| I-1 | All SDD state = reduce(events); State_index.yaml is a readonly snapshot, never truth source |
| I-2 | All write commands execute via REGISTRY[name] → execute_and_project(spec, ...) |
| I-3 | All side-effects (EventStore.append, projection rebuilds) occur in Write Kernel only |
| I-SPEC-EXEC-1 | CLI contains only: REGISTRY lookup + execute_and_project; no direct kernel calls outside registry.py |
| I-HANDLER-PURE-1 | `handle()` methods return events only — no EventStore, no rebuild_state, no sync_projections |
| I-ERROR-1 | Write Kernel MUST emit ErrorEvent before raising at every failure stage |
| I-RRL-1 | Scope override = вызов scope_policy.py::resolve_scope. Inline exceptions в scope.py запрещены. |
| I-RRL-2 | Rule resolution MUST be deterministic: одинаковые inputs → идентичное решение + идентичный override metadata. |
| I-RRL-3 | Silent override запрещён. Любой override MUST emit override metadata в JSON output. |
| I-DB-1 | `open_sdd_connection(db_path)` — `db_path` MUST be explicit non-empty str |
| I-DB-2 | CLI is the single point that resolves `event_store_file()` for default DB path |
| I-DB-TEST-1 | Tests MUST NOT open production DB; path equality via `Path.resolve()` |
| I-DB-TEST-2 | In test context (`PYTEST_CURRENT_TEST`): `timeout_secs = 0.0` (fail-fast) |
| I-TASK-MODE-1 | В task mode из build_commands исключаются все команды, ключ которых начинается с `"test"` (`k.startswith("test")`) |
| I-PHASE-SEQ-1 | `activate-phase` MUST satisfy `phase_id == current + 1`; no skipping, no regression |
| I-PHASE-AUTH-1 | ONLY `PhaseInitialized` and `PhaseContextSwitched` MAY mutate `phase_current`. `PhaseStarted` MUST NOT mutate any state field. |
| I-PHASE-STARTED-1 | `PhaseStarted` MUST NOT be used by any reducer logic or guard logic. It is informational only. Code: `# DO NOT ADD LOGIC HERE`. |
| I-PHASE-CONTEXT-1 | `switch-phase` MUST emit `PhaseContextSwitched`; MUST NOT emit `PhaseStarted` or `PhaseInitialized` |
| I-PHASE-CONTEXT-2 | `switch-phase` MUST target a phase in `phases_known` |
| I-PHASE-CONTEXT-3 | `switch-phase` MUST fail if `phases_known` is empty |
| I-PHASE-CONTEXT-4 | `switch-phase N` where `N == phase_current` MUST be rejected (no-op guard) |
| I-PHASE-LIFECYCLE-1 | `PhaseContextSwitched` MUST NOT override `phase_status`; MUST restore stored snapshot value (preserves COMPLETE) |
| I-PHASE-LIFECYCLE-2 | `PhaseCompleted` is terminal: `phase_status = "COMPLETE"` in snapshot MUST NOT be overwritten by any event except a new `PhaseInitialized` for the same phase |
| I-PHASE-REDUCER-1 | `PhaseStarted` during replay: DEBUG log only; no state change in any branch |
| I-PHASES-KNOWN-1 | `SDDState.phases_known` MUST be `frozenset[int]`; updated ONLY on `PhaseInitialized` replay; `PhaseContextSwitched` MUST NOT modify it |
| I-PHASES-KNOWN-2 | `phases_known == {s.phase_id for s in phases_snapshots}` at all times |
| I-PHASE-SNAPSHOT-1 | `phases_snapshots` MUST contain exactly one entry per `phase_id ∈ phases_known`; updated by all phase-scoped events matching that `phase_id` |
| I-PHASE-SNAPSHOT-2 | Flat state MUST be a projection of `phases_snapshots[phase_current]` after any `_fold` |
| I-PHASE-SNAPSHOT-3 | `PhaseInitialized` MUST overwrite (not append) snapshot for `phase_id`; unconditional |
| I-PHASE-SNAPSHOT-4 | `PhaseContextSwitched` MUST have a corresponding snapshot; absence MUST raise `Inconsistency` (guard failure or corrupted EventLog) |
| I-CMD-IDEM-1 | Navigation commands (`switch-phase`) MUST NOT be idempotent. `CommandSpec.idempotent=False` → `execute_command` MUST pass `command_id=uuid4()` (NOT `None`) to `EventStore.append`. Each invocation MUST produce a unique event in EventLog. |
| I-CMD-IDEM-2 | Handler-level idempotency (`_check_idempotent`) MAY exist as an additional guard, but MUST NOT contradict `CommandSpec.idempotent`. If `spec.idempotent=False`, handler MUST NOT silently suppress event emission via noop. |
| I-CMD-NAV-1 | Navigation events (`PhaseContextSwitched`) are order-sensitive (temporal semantics). Final state is defined by the last event in sequence. Navigation events MUST NOT be deduplicated at any layer. `SwitchPhaseHandler` SHOULD NOT emit event if `phase_id == phase_current` (guard already enforces this — this invariant documents the design intent). |
| I-SESSION-AUTO-1 | LLM MUST run `sdd activate-phase N --executed-by llm` automatically at end of DECOMPOSE. No human CLI step required. |
| I-SESSION-DECLARED-1 | LLM MUST emit `SessionDeclared` event at start of every session (PLAN/DECOMPOSE/IMPLEMENT/VALIDATE) before any auto-action, via `sdd record-session`. |
| I-SESSION-VISIBLE-1 | Every auto-invoked CLI MUST be shown in LLM output as `[Auto-action] ... / [Result] ...`. Silent state mutations are forbidden. |
| I-SESSION-ACTOR-1 | `activate-phase` MUST always pass `actor="human"`. `executed_by="llm"` goes into payload field only, not actor field. VALID_ACTORS remains `{"human"}`. |
| I-SESSION-PI-6 | LLM MUST update Phases_index.md at end of PLAN session. Must validate I-PHASES-INDEX-1 after update. |
| I-PHASES-INDEX-1 | `phases_known ⊆ Phases_index.ids`. Violation → LLM MUST update Phases_index before proceeding. Phases_index is a derived view, never a truth source (I-1). |
| I-PLAN-IMMUTABLE-AFTER-ACTIVATE | `Plan_vN.md` MUST NOT be modified after `activate-phase N` has been executed. Any change to the plan file after phase activation constitutes a protocol violation. If a plan update is required, a new phase (N+1) with a revised spec must be initiated. Declared (not enforced) |
| I-SESSION-PHASE-NULL-1 | `SessionDeclared` events with `session_type = "DRAFT_SPEC"` MUST use `phase_id = 0` as a sentinel value. `phase_id = 0` is reserved exclusively for pre-phase sessions and MUST NOT correspond to any real phase in `phases_known`. Reducer MUST treat `phase_id = 0` in `SessionDeclared` as a no-op (no state mutation). All other session types MUST use a real `phase_id ∈ phases_known`. Declared (not enforced) |

Violation of any invariant → ERROR → STOP → `sdd report-error`.

---

## §RECOVERY — Quick Protocol

On any error: STOP → read JSON stderr (`error_type`, `stage`, `error_code`) →  
load `sessions/recovery.md` → apply exactly the matching RP-*.  
LLM MUST NOT invoke recovery as a blind first action (SEM-12).

---

## §ROLES — Human / LLM Responsibilities

**Human:**
- Approves specs (moves draft → .sdd/specs/)
- Activates phases/plans via `sdd activate-phase N` (human-only gate)
- Resolves ambiguities and conflicts
- Reviews phase completion (supervision gate)

**LLM:**
- Writes drafts in .sdd/specs_draft/
- Generates plans, task sets, implementation, validation reports, summaries
- Marks tasks DONE via `sdd complete T-NNN`
- Sets invariants/tests status via `sdd validate T-NNN`
- Emits `SessionDeclared` event at start of every session via `sdd record-session` (I-SESSION-DECLARED-1)
- Auto-runs `sdd activate-phase N --executed-by llm` at end of DECOMPOSE (I-SESSION-AUTO-1)
- Updates Phases_index.md at end of PLAN session; validates I-PHASES-INDEX-1 (I-SESSION-PI-6)
- Displays every auto-action as `[Auto-action] ... / [Result] ...` (I-SESSION-VISIBLE-1)

**LLM MUST NOT:**
- Modify .sdd/specs/ (immutable, SDD-9)
- Run `sdd activate-phase` without `--executed-by llm` outside DECOMPOSE session (NORM-ACTOR-001);
  exception: DECOMPOSE auto-action with `--executed-by llm` is explicitly allowed (I-SESSION-AUTO-1)
- Execute multiple tasks in one command (§R.10)
- Emit SpecApproved, PlanActivated, PhaseCompleted events directly
- Use glob patterns in file access (NORM-SCOPE-003)
- Read .sdd/ files directly (use `sdd show-*` CLI instead, SDD-11..13)

**Meta-SDD:** LLM may propose SDD process improvements → `.sdd/specs_draft/SDD_Improvements.md`; never auto-applied.

---

## §SEM — Operational Rules

```
SEM-1   No guessing
SEM-2   No implicit assumptions
SEM-3   No missing artifact tolerance
SEM-4   Always validate preconditions before execution
SEM-5   Fail fast on violation — STOP immediately
SEM-6   On any violation: run sdd report-error --type T --message M
SEM-7   Every guard MUST be called via Python script — LLM does NOT interpret rules directly
SEM-8   Every metric MUST be recorded via record_metric.py — no inferred/estimated values
SEM-9   Context always built via build_context.py — LLM does not choose what to read
SEM-10  LLM MUST use reason + violated_invariant from JSON stderr when command fails
SEM-11  Read-only CLI commands that bypass REGISTRY MUST satisfy I-READ-ONLY-EXCEPTION-1
SEM-12  LLM MUST NOT invoke recovery as blind first action; classify from JSON stderr first
SEM-13  ALL session preconditions MUST execute as a strict linear dependency chain —
        one tool call per step, stop on first non-zero exit code. The execution order
        is defined in .sdd/contracts/cli.schema.yaml (execution_order field).
        Parallel tool calls are NOT isolated: a failure in one cancels all sibling calls.
        Guards (phase-guard, task-guard, check-scope, norm-guard) MUST run sequentially
        in declaration order. Violation = undefined state.
SEM-14  pytest MUST always run synchronously (`run_in_background` MUST be `false` or absent).
        Never launch a second pytest while one is already running — hook enforces this via pgrep.
```

---

## §TOOLS — 5 Essential Commands

| Command | Purpose |
|---------|---------|
| `sdd complete T-NNN` | Mark task DONE after implementation |
| `sdd validate T-NNN --result PASS\|FAIL` | Run invariant checks after implementation |
| `sdd show-state` | Read current phase/task state |
| `sdd query-events` | Inspect event log |
| `sdd report-error` | Structured error reporting |

For all other commands → load `.sdd/docs/ref/tool-reference.md` (§HARD-LOAD Rule 4).

---

## §REPO — Repository Structure

```
/src/sdd/          → SDD CLI package (BC-1..BC-8)
/.sdd/
  /docs/
    /sessions/     → 10 session files (IMPLEMENT, VALIDATE, PLAN, etc.)
    /ref/          → 8 reference files (kernel-contracts, recovery, etc.)
  /norms/          → SENAR norm catalog
  /config/         → project_profile.yaml, sdd_config.yaml, phases/
  /state/          → DuckDB event store (sdd_events.duckdb)
  /runtime/        → State_index.yaml (SSOT projection), audit_log.jsonl
  /specs/          → Formal specs (immutable after approval)
  /specs_draft/    → Draft specs (editable)
  /plans/          → Phases_index.md, Plan_vN.md
  /tasks/          → TaskSet_vN.md
  /reports/        → ValidationReports, PhaseSummaries, Metrics_PhaseN.md
  /templates/      → Artifact templates
```
