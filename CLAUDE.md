# CLAUDE — SDD Master Protocol (Unified)

**Status:** ACTIVE — supersedes CLAUDE_v2.md, CLAUDE_v3.md, CLAUDE_v3-PLAN.md  
**Formal model:** .sdd/specs/SDD_Spec_v1.md (events, reducer, guards — BC-9)  
**SENAR norms:** .sdd/norms/norm_catalog.yaml (machine-readable, enforcement layer)  
**Tools:** .sdd/tools/*.py (deterministic Python enforcement scripts)

---

## §0 — META (load always)

### §0.1 Loading Instructions

```
CODER AGENT   (Implement T-NNN, Validate T-NNN):
  Load §0 + §R only. SKIP §K entirely.
  Reason: §K context contaminates execution scope.

PLANNER AGENT (Draft Spec, Plan Phase, Decompose, Summarize Phase):
  Load §0 + §K only. SKIP §R entirely.
  Reason: §R execution rules are irrelevant during planning.

FULL LOAD (when agent type is unknown or both roles apply):
  Load §0 + §R + §K. §R takes precedence during Implement/Validate.
```

### §0.2 Priority Hierarchy

Contradiction resolution order (highest wins):

```
1. .sdd/specs/SDD_Spec_v1.md                ← formal truth, immutable
2. .sdd/norms/norm_catalog.yaml             ← SENAR regulation layer
3. CLAUDE.md §R [Runtime]                   ← execution scope rules
4. CLAUDE.md §K [Kernel]                    ← process workflow rules
5. .sdd/plans/Plan_vN.md                    ← phase plan
6. .sdd/tasks/TaskSet_vN.md                 ← task definitions
7. .sdd/config/project_profile.yaml         ← project-specific config (stack, rules, scope)
8. .sdd/config/phases/phase_N.yaml          ← phase-level overrides
```

### §0.3 Execution Boundary Table

| Layer | Active During | Governs |
|---|---|---|
| Spec invariants | Always | Events, types, guards, I-SDD-1..G9 |
| SENAR norms | Always | Actor permissions, supervision gates, audit |
| §R Runtime rules | Implement T-NNN, Validate T-NNN | I/O scope, single-task, forbidden patterns |
| §K Kernel rules | Draft Spec, Plan Phase, Decompose, Summarize | Workflow, artifacts, versions, DDD |
| State Guard | Every command | State consistency checks |

### §0.4 SDD State Machine

```
DRAFT_SPEC → APPROVED_SPEC → PLAN_DRAFT → PLAN_ACTIVE
  → TASKS_DEFINED → IMPLEMENTATION → VALIDATION → PHASE_COMPLETE
```

Invalid transition → ERROR (InvalidState). LLM MUST REFUSE execution.

### §0.5 Status Transition Table (canonical — no ambiguity)

| Field | Transition | Actor | Mechanism |
|---|---|---|---|
| `phase.status` | PLANNED → ACTIVE | **Human only** | Direct YAML edit in State_index.yaml |
| `phase.status` | ACTIVE → COMPLETE | LLM + DoD | `update_state.py validate --check-dod` (all tasks DONE + invariants PASS + tests PASS) |
| `plan.status` | PLANNED → ACTIVE | **Human only** | Direct YAML edit in State_index.yaml |
| `plan.status` | ACTIVE → COMPLETE | LLM + DoD | `update_state.py validate --check-dod` (same conditions as phase) |
| `tasks.done_ids` | Add T-NNN | LLM only | `update_state.py complete T-NNN` (marks task DONE in TaskSet, syncs counts) |
| `invariants.status` | UNKNOWN → PASS/FAIL | LLM only | `update_state.py validate T-NNN` |
| `tests.status` | UNKNOWN → PASS/FAIL | LLM only | `update_state.py validate T-NNN` |

**Disambiguation:**
- `complete T-NNN` = marks ONE task DONE in TaskSet + syncs State aggregate
- `validate T-NNN` = checks invariants/tests for ONE task post-implementation
- `validate --check-dod` = terminal phase/plan transition (ALL tasks complete + all checks pass)

### §0.6 Roles

**Human:**
- Approves specs (moves draft → .sdd/specs/)
- Sets `phase.status` / `plan.status` PLANNED → ACTIVE
- Resolves ambiguities and conflicts
- Decides phase completion (supervision gate)

**LLM:**
- Writes drafts in .sdd/specs_draft/
- Generates plans, task sets, implementation, validation reports, phase summaries
- Marks tasks DONE via `update_state.py complete T-NNN`
- Sets invariants/tests status via `update_state.py validate T-NNN`

**LLM MUST NOT:**
- Modify .sdd/specs/ (immutable)
- Set phase.status / plan.status → ACTIVE (human-only)
- Execute multiple tasks in one command
- Emit SpecApproved, PlanActivated, PhaseCompleted events (NORM-ACTOR-001..003)
- Use glob patterns in file access (NORM-SCOPE-003)

### §0.7 SENAR Integration

SENAR (Supervised Engineering & Normative AI Regulation) provides:
- **Norm catalog**: machine-readable actor permissions (.sdd/norms/norm_catalog.yaml)
- **Supervision gates**: human approval checkpoints (NORM-GATE-001..003)
- **Audit trail**: every LLM action logged to .sdd/runtime/audit_log.jsonl
- **Enforcement tools**: .sdd/tools/*.py (deterministic, no AI, no randomness)

On any SENAR violation: STOP → call `report_error.py` → DO NOT PROCEED.

### §0.8 Operational Rules

```
SEM-1  No guessing
SEM-2  No implicit assumptions
SEM-3  No missing artifact tolerance
SEM-4  Always validate preconditions before execution
SEM-5  Fail fast on violation — STOP immediately
SEM-6  On any violation: call .sdd/tools/report_error.py
SEM-7  Every guard MUST be called via Python script — LLM does NOT interpret rules directly
SEM-8  Every metric MUST be recorded via record_metric.py — no inferred or estimated values
SEM-9  Context is always built via build_context.py — LLM does not choose what to read
```

### §0.9 Spec Approval Operational Rule

If a Phase is marked COMPLETE in .sdd/plans/Phases_index.md, its associated Spec_vN is treated as
operationally approved for downstream phases. Formal Artifacts_index.md update is a human cleanup task.

---

## §R — RUNTIME (load for Implement T-NNN / Validate T-NNN only)

> **CODER AGENT:** This is your complete operational context. §K does not apply.

### §R-core — What To Do (5 essential commands + implementation protocols)

**5 essential sdd commands (read every session):**

| Command | Purpose |
|---------|---------|
| `sdd complete T-NNN` | Mark task DONE after implementation |
| `sdd validate T-NNN` | Run invariant checks after implementation |
| `sdd show-state` | Read current phase/task state |
| `sdd query-events` | Inspect event log |
| `sdd report-error` | Structured error reporting |

### §R.1 System Model

```
LLM = Pure Function:  Output = f(CLI_Output, Task_Inputs)

Where:
- CLI_Output:   deterministic projection of SDD artifacts via sdd show-* commands
- Task_Inputs:  source files listed in Task Inputs field (exact paths only)

Constraints:
- No hidden state
- No global scanning
- Only explicit inputs allowed
- SDD artifact data MUST come from CLI output, never direct file reads
```

### §R.6 Implement T-NNN Protocol

```
Pre-execution (MUST run in order):
  1. sdd phase-guard check --command "Implement T-NNN"
  2. sdd task-guard check --task T-NNN
  3. sdd check-scope read <each_input_file>
  4. sdd norm-guard check --actor llm --action implement_task

Execution:
  5. Read ONLY files in Task Inputs (exact paths)
  6. Modify ONLY files in Task Outputs (exact paths)
  7. No cross-task reasoning. No future task anticipation.

Post-execution:
  8. sdd complete T-NNN
     (auto-records metric: task.lead_time, task.implementation_count)

Events emitted: TaskImplemented, StateSynced, MetricRecorded(task.lead_time)
```

### §R.7 Validate T-NNN Protocol

```
Pre-execution:
  1. sdd phase-guard check --command "Validate T-NNN"
  2. sdd validate-config --phase N   (config valid before running checks)

Execution:
  3. sdd validate-invariants --phase N --task T-NNN
     (runs checks[] from TaskSet via project_profile build.commands — auto-records quality metrics)
  4. Produce .sdd/reports/ValidationReport_T-NNN.md

Post-execution:
  5. sdd validate T-NNN
     (auto-records metric: task.validation_attempts, task.first_try_pass_rate)

Events emitted: TaskValidated, InvariantsUpdated, TestsUpdated, DoDChecked,
                MetricRecorded(quality.test_coverage, quality.lint_violations, task.validation_attempts)
```

### §R-rules — What Not To Do (scope, guards, forbidden constraints)

### §R.2 Read Scope (CRITICAL — enforced by check_scope.py)

LLM MUST obtain SDD artifact data ONLY via these authorized CLI commands (I-CLI-SSOT-1, I-SCOPE-CLI-2):

| Command | SDD artifact provided |
|---|---|
| `sdd show-state` | current phase/task state |
| `sdd show-task T-NNN` | task definition: inputs, outputs, invariants, acceptance |
| `sdd show-spec --phase N` | current phase spec content |
| `sdd show-plan --phase N` | current phase plan content |

Additionally: files listed in Task Inputs field (exact paths only) — source files only.

**FORBIDDEN — direct `.sdd/` file reads (I-CLI-SSOT-1, I-SCOPE-CLI-2):**
```
resolved via paths.py → state_file()         ← use: sdd show-state
resolved via paths.py → specs_dir()          ← use: sdd show-spec --phase N
resolved via paths.py → plan_file(N)         ← use: sdd show-plan --phase N
resolved via paths.py → taskset_file(N)      ← use: sdd show-task T-NNN
resolved via paths.py → phases_index_file()  ← use: sdd show-state
```

**FORBIDDEN — scan patterns (hard — NORM-SCOPE-001..003):**
```
tests/**            ← any test directory traversal
src/**              ← any source directory scan (unless in Task Inputs)
**/*.py             ← any glob pattern
*                   ← any wildcard
```

Tool enforcement: `sdd check-scope read <path>`  
Violation → ERROR (ScopeViolation) → STOP

### §R.3 Write Scope (enforced by update_state.py)

LLM MUST modify ONLY:
- Files listed in Task Outputs (exact paths)
- `.sdd/tasks/TaskSet_vN.md` — single row: T-NNN Status TODO → DONE
- `.sdd/runtime/State_index.yaml` — via Sync State only (never direct edit)

**FORBIDDEN:**
- `.sdd/specs/**` — immutable (NORM-SCOPE-004, I-SDD-19)
- Any file not in Task Outputs

Mutation path: `sdd complete T-NNN`

### §R.4 PhaseGuard (enforced by phase_guard.py)

Preconditions for Implement T-NNN / Validate T-NNN:

```
PG-1  phase.current == N for TaskSet_vN
PG-2  plan.version == N == tasks.version
PG-3  phase.status == ACTIVE
```

Tool: `sdd phase-guard check --command "Implement T-NNN"`  
Rejection emits `SDDEventRejected` (SDD_Spec_v1.md §3.3).

### §R.5 State Guard (every command)

```
IF State_index.yaml missing                   → ERROR (MissingState)
IF phase.current ≠ plan.version               → ERROR (Inconsistency)
IF plan.version ≠ tasks.version               → ERROR (Inconsistency)
IF tasks.completed > tasks.total              → ERROR (Inconsistency)
IF len(tasks.done_ids) ≠ tasks.completed      → ERROR (Inconsistency)
```

### §R.8 Task Contract

Each task MUST declare:
```
Inputs:   explicit file list (exact paths)
Outputs:  explicit file list (exact paths)
```
If missing → ERROR (MissingContext) → DO NOT PROCEED.

### §R.9 Task Isolation Rule

During T-NNN:
- Operate ONLY within task scope
- No reading unrelated files
- No future task anticipation
- No cross-task reasoning

### §R.10 Command Scope Rule

Each command operates on EXACTLY ONE task.

```
Allowed:   Implement T-309
Forbidden: Implement T-309-314
           Implement multiple tasks
```

### §R.11 Idempotency

```
Implement → same result if re-run (TaskSet already DONE, State already synced)
Validate  → overwrite ValidationReport (idempotent)
Sync      → same result (derived from TaskSet)
```

### §R.12 Global Failure Rule

On ANY violation:
```
STOP
sdd report-error --type <type> --message "<msg>" --task T-NNN
DO NOT PROCEED
```

---

## §K — KERNEL (load for Draft Spec / Plan Phase / Decompose / Summarize only)

> **PLANNER AGENT:** This is your complete operational context. §R does not apply.

### §K.1 Commands

#### Draft Spec_vN

```
Preconditions: Phase N exists in .sdd/plans/Phases_index.md
Output:        .sdd/specs_draft/Spec_vN_*.md  (use .sdd/templates/Spec_template.md)
Do NOT:        write into .sdd/specs/
Idempotent:    overwrite .sdd/specs_draft/Spec_vN_*.md
```

#### Plan Phase N

```
Preconditions: .sdd/specs/Spec_vN exists + Phase N in Phases_index
Output:        .sdd/plans/Plan_vN.md  Status: DRAFT  (use .sdd/templates/Plan_template.md)
Idempotent:    overwrite .sdd/plans/Plan_vN.md
```

#### Decompose Phase N

```
Preconditions: .sdd/plans/Plan_vN.md exists + Status = ACTIVE
Output:        .sdd/tasks/TaskSet_vN.md  all tasks Status: TODO (use .sdd/templates/TaskSet_template.md)
Idempotent:    overwrite .sdd/tasks/TaskSet_vN.md
```

#### Init State N

```
Preconditions: .sdd/runtime/State_index.yaml does NOT exist; Human provides phase N
Output:        .sdd/runtime/State_index.yaml (created from scratch)
Exempt from:   State Guard (only command allowed without State_index.yaml)
Steps:
  - phase.current = N, phase.status = ACTIVE, plan.status = ACTIVE
  - plan.version = N, tasks.version = N
  - Read .sdd/tasks/TaskSet_vN.md → count total/completed → done_ids
  - invariants.status = UNKNOWN, tests.status = UNKNOWN
  - meta.last_updated = ISO8601, schema_version = 1
```

#### Summarize Phase N

```
Output:        .sdd/reports/PhaseN_Summary.md  (use .sdd/templates/PhaseSummary_template.md)
Must include:  task statuses, invariant coverage, spec coverage, tests, decision
Idempotent:    overwrite
```

#### Metrics Report (BEFORE EventLog Snapshot — mandatory)

```
Command:   sdd metrics-report --phase N
Output:    .sdd/reports/Metrics_PhaseN.md
Timing:    AFTER Summarize Phase N, BEFORE EventLog Snapshot
Includes:  process health, code quality, agent behavior, infra metrics,
           inter-phase trend (--trend), anomalies (--anomalies)
Idempotent: overwrite
```

PhaseN_Summary.md MUST reference Metrics_PhaseN.md and include improvement hypotheses
derived from anomalies (e.g. tasks too large, guard rejection spike, coverage drop).

#### EventLog Snapshot (LAST command of every phase — mandatory)

```
Command:   sdd query-events --phase N --include-bash --json --save
Output:    .sdd/reports/EL_PhaseN_events.json
Source:    DuckDB sdd_events.duckdb → table events (partition_key='sdd') — единственный источник
Timing:    AFTER Summarize Phase N, BEFORE human gate (phase ACTIVE → COMPLETE)
Idempotent: overwrite (same command re-run overwrites previous snapshot)
```

This snapshot freezes the full event trace for phase N:
- All SDD process events (TaskImplemented, TaskValidated, PhaseCompleted) filtered by payload.phase_id = N
- All ToolUse* / BashCommand* events from the session (no phase_id — included via --include-bash)
- Provides audit trail for replay, debugging, and post-mortem analysis

#### Show State

```
Preconditions: State Guard passes
Output:        human-readable markdown summary table — NO file writes
```

### §K.2 Versioning Rules

```
VR-1  Spec_vN ↔ Phase N
VR-2  Plan_vN MUST use Spec_vN
VR-3  TaskSet_vN MUST use Plan_vN
VR-4  Mixing versions → ERROR (VersionMismatch)
```

### §K.3 Artifact Model

```
.sdd/runtime/State_index.yaml        SSOT operational state (projection, LLM-managed)
.sdd/specs/Spec_vN_*.md              immutable, approved specs
.sdd/specs_draft/Spec_vN_*.md        editable drafts
.sdd/plans/Plan_vN.md                phase plan
.sdd/tasks/TaskSet_vN.md             task decomposition
.sdd/reports/ValidationReport_T-*.md task validation
.sdd/reports/PhaseN_Summary.md       phase summary (mandatory)
```

Templates: see .sdd/templates/

### §K.4 SDD Invariants

```
SDD-1   Plan must reference Spec sections
SDD-2   Every Task must reference exactly one Spec section + ≥1 invariant
SDD-3   TaskSet must cover all Plan milestones
SDD-4   Tasks must not introduce entities absent in Spec
SDD-5   Validation must reference Spec, invariants, and acceptance criterion
SDD-6   Phase cannot be COMPLETE if any invariant FAIL or any task not DONE
SDD-7   LLM must refuse execution on inconsistency
SDD-8   Task Outputs field defines the allowed modification scope
SDD-9   .sdd/specs/ is immutable
SDD-10  Drafts must stay in .sdd/specs_draft/
SDD-11  LLM MUST obtain SDD artifact data only via sdd show-* CLI or Task Inputs; direct .sdd/ reads forbidden (I-CLI-SSOT-1)
SDD-12  CLI output is an authoritative deterministic projection; LLM MUST treat sdd show-* as single source of truth (I-CLI-SSOT-2)
SDD-13  LLM MUST NOT simulate CLI by reading equivalent files directly — sdd show-task/spec/plan required (I-SCOPE-CLI-2)
SDD-14  No literal .sdd/ path strings in src/sdd/**/*.py except infra/paths.py (I-PATH-1)
SDD-15  paths.py imports ONLY stdlib (os, pathlib) — zero intra-sdd imports (I-PATH-2)
SDD-16  Task Inputs/Outputs paths are relative to repo root, not SDD_HOME (I-PATH-3)
SDD-17  paths.py does NOT create directories; callers are responsible for existence (I-PATH-4)
SDD-18  reset_sdd_root() MUST NOT be called in production code — test isolation only (I-PATH-5)
SDD-19  Config MUST NOT override core SDD paths (state, tasks, specs, plans, db) (I-CONFIG-PATH-1)
```

### §K.5 Phase Guard

```
Phase N valid ONLY IF present in .sdd/plans/Phases_index.md
Phase.spec must exist in .sdd/specs/ for execution commands
Violation → HARD ERROR → DO NOT PROCEED
```

Phase Index Invariants:
```
PI-1  Every phase referenced by any command must exist in Phases_index.md
PI-2  Phase.id is unique and monotonic
PI-3  Phase.spec points to .sdd/specs/ OR is TODO (for future phases)
PI-4  Phase.status ∈ {PLANNED, ACTIVE, COMPLETE}
PI-5  Exactly one phase has status ACTIVE at any time
```

### §K.6 Read Order (strict — for planning commands)

```
0. sdd show-state                    ← always first (State Guard; includes phase index)
1. sdd show-state                    ← Phases_index info is in show-state output
2. sdd show-spec --phase N           ← spec content (I-CLI-SSOT-1; do NOT read .sdd/specs/ directly)
3. sdd show-plan --phase N           ← plan content (I-CLI-SSOT-1; do NOT read .sdd/plans/ directly)
4. sdd show-task T-NNN               ← task definition (I-CLI-SSOT-1; do NOT read .sdd/tasks/ directly)
5. .sdd/reports/  (if summarizing)   ← reports dir only; accessed via paths.py / reports_dir()
```

### §K.7 Phase Isolation Rules

```
PIR-1  When on Phase N: MUST NOT read TaskSet_vM, Plan_vM, Spec_vM where M ≠ N
PIR-2  Allowed per Phase N: State_index.yaml, Phases_index.md, Spec_vN, Plan_vN, .sdd/templates/
PIR-3  Cross-phase reading only if explicitly required by Spec_vN
PIR-4  Glob patterns matching TaskSet_v*.md FORBIDDEN — use exact path only
```

Anti-Pattern Guard:
```
APG-1  Do NOT infer TaskSet structure from previous phases
APG-2  Templates are the ONLY structural source for new artifacts
APG-3  Previous TaskSet_vM are NOT examples for decomposing Phase N
```

### §K.8 SSOT State Model

```
TaskSet_vN.md    = source of truth for individual task statuses
State_index.yaml = projection (aggregate), derived via sync_state.py

Flow:
  Implement T-NNN → update TaskSet → update_state.py complete T-NNN
  Validate T-NNN  → update reports → update_state.py validate T-NNN
```

Future: State_index.yaml = projection(EventLog) when BC-9 is implemented.

### §K.9 Code Editing Protocol (CEP)

```
CEP-1  Prefer diff-style patches over full file rewrites
CEP-2  Modify ONLY files declared in Task Outputs
CEP-3  Never delete existing tests
CEP-4  New behavior requires new tests
CEP-5  Code removal must be justified in ValidationReport
CEP-6  No speculative refactoring
CEP-7  Public interfaces stable unless Spec requires change
CEP-8  Follow SER invariants: determinism, purity, event-sourcing
```

Test Policy:
```
TP-1  Existing tests MUST pass after changes
TP-2  New functionality MUST include tests
TP-3  Determinism MUST be tested where applicable
TP-4  Event-sourced components MUST have replay tests
```

### §K.10 DDD & Clean Architecture

```
DDD-1  Code organized by Bounded Context (BC)
DDD-2  No direct cross-BC imports — only via interfaces/events
DDD-3  Domain logic must not depend on infrastructure
DDD-4  Reducer layer is pure domain logic
DDD-5  Side effects only via event emission
DDD-6  All state changes expressed as events
DDD-7  No hidden state mutations
DDD-8  State must be reconstructable via replay
```

### §K.11 Consistency Rule

```
If mismatch between State_index / Phases_index / Spec / Plan / TaskSet:
  → ERROR (Inconsistency)
  → DO NOT AUTO-RESOLVE
  → Human must fix or run: sdd sync-state --phase N
```

### §K.12 Error Protocol

```
On any violation emit:

ERROR:
  type:            PhaseGuard | MissingSpec | Inconsistency | InvalidState |
                   VersionMismatch | MissingState | ScopeViolation | NormViolation
  message:         <short explanation>
  required_action: <human fix>

Then call: sdd report-error --type <type> --message "<msg>"
```

### §K.13 TaskSet Granularity

```
TG-1  Task must be independently implementable AND independently testable
TG-2  Recommended: 10–30 tasks per phase
TG-3  If exceeded → regroup tasks
Each task MUST declare: Invariants Covered: I-XXX, I-YYY
```

### §K.14 Meta-SDD

```
LLM may propose SDD process improvements:
  Output: .sdd/specs_draft/SDD_Improvements.md
  Never auto-applied — requires human approval
```

### §K.15 Multi-Phase Safety

```
MPS-1  Only one ACTIVE phase allowed (PI-5)
MPS-2  Next phase cannot start if previous not COMPLETE
MPS-3  Parallel phases forbidden unless explicitly allowed
```

---

## §0.10 Tool Reference

> **Phase 13 complete:** `.sdd/tools/` has been archived to `.sdd/_deprecated_tools/`. **`sdd` CLI (`pip install -e .`) is the sole runtime interface for all governance operations.** Former adapter scripts are preserved in `.sdd/_deprecated_tools/` for historical reference only — do not invoke them directly. **`build_command(command_type, **kwargs)`** is the canonical pattern for constructing `Command` envelopes in all handlers — import from `sdd.core.payloads`. Direct instantiation of `Command(...)` or subclassing `Command` is forbidden (I-CMD-ENV-1). See §0.15 for frozen kernel interfaces.

| `sdd` CLI command | Purpose | Archived adapter |
|---|---|---|
| **`sdd complete T-NNN`** | Mark task DONE — sole mutation path for TaskSet + State | `.sdd/_deprecated_tools/update_state.py` |
| **`sdd validate T-NNN`** | Validate task invariants + record results | `.sdd/_deprecated_tools/update_state.py` |
| **`sdd sync-state --phase N [--dry-run]`** | Rebuild State_index from EventLog replay | `.sdd/_deprecated_tools/sync_state.py` |
| **`sdd validate-invariants --phase N [--task T-NNN] [--check I-XXX]`** | Check I-SDD invariants + record quality metrics | `.sdd/_deprecated_tools/validate_invariants.py` |
| **`sdd report-error --type T --message M`** | Structured violation reporter | `.sdd/_deprecated_tools/report_error.py` |
| **`sdd query-events --phase N [--step T-NNN] [--event TYPE] [--include-bash] [--json] [--save]`** | Query EventLog (DuckDB single source) | `.sdd/_deprecated_tools/query_events.py` |
| **`sdd metrics-report --phase N [--trend] [--anomalies]`** | Generate Metrics_PhaseN.md + trends + anomalies | `.sdd/_deprecated_tools/metrics_report.py` |
| **`sdd show-state`** | Print State_index as markdown table | `.sdd/_deprecated_tools/show_state.py` |
| **`sdd show-task T-NNN [--phase N]`** *(Phase 14 complete)* | Print task definition: status, inputs, outputs, invariants, acceptance | *(new — no deprecated adapter)* |
| **`sdd show-spec --phase N`** *(Phase 14 complete)* | Print full spec content for phase N (read-only, no events) | *(new — no deprecated adapter)* |
| **`sdd show-plan --phase N`** *(Phase 14 complete)* | Print full plan content for phase N (read-only, no events) | *(new — no deprecated adapter)* |
| **`sdd-hook-log pre\|post`** *(console_scripts — Phase 13 M1 complete)* | Claude Code PreToolUse/PostToolUse hook | `.sdd/_deprecated_tools/log_tool.py` |
| *(historical record only — replaced by log_tool.py, not wired)* | Former Bash-only hook | `.sdd/_deprecated_tools/log_bash.py` |
| **`sdd phase-guard`** *(Phase 13 M2 complete)* | PhaseGuard + SDDEventRejected emitter | `.sdd/_deprecated_tools/phase_guard.py` |
| **`sdd task-guard`** *(Phase 13 M2 complete)* | Verify task Status == TODO before implementation | `.sdd/_deprecated_tools/task_guard.py` |
| **`sdd check-scope`** *(Phase 13 M2 complete)* | Validate file access against SENAR norms | `.sdd/_deprecated_tools/check_scope.py` |
| **`sdd norm-guard`** *(Phase 13 M2 complete)* | Machine-readable norm enforcement | `.sdd/_deprecated_tools/norm_guard.py` |
| **`sdd validate-config`** *(Phase 13 M2 complete)* | Validate project_profile.yaml + phase_N.yaml | `.sdd/_deprecated_tools/validate_config.py` |
| *(no CLI equivalent — SEM-9 internal)* | Staged context loader | `.sdd/_deprecated_tools/build_context.py` |
| *(no CLI equivalent — internal audit)* | Audit trail logger | `.sdd/_deprecated_tools/senar_audit.py` |
| *(no CLI equivalent — library only)* | Norm catalog reader | `.sdd/_deprecated_tools/norm_catalog.py` |
| *(auto-called by complete + validate-invariants)* | Sole write path for metrics → DuckDB | `.sdd/_deprecated_tools/record_metric.py` |

## §0.11 Repository Structure

```
/src            → SER application code (BC-1..BC-8)
/.sdd           → SDD control plane (all governance artifacts)
  /docs         → Architecture, bounded contexts, glossary (reference docs)
  /_deprecated_tools → Archived adapter scripts (historical reference only — do not invoke)
  /norms        → SENAR norm catalog + config
  /config       → Project configuration (NEW)
    project_profile.yaml  ← стек, code rules, scope, domain, custom norms
    sdd_config.yaml       ← режимы, gates, budgets
    /phases/              ← phase-level overrides (phase_N.yaml)
  /state        → DuckDB event store (partition_key: sdd | metrics | audit)
  /runtime      → State_index.yaml (SSOT), audit_log.jsonl (SENAR audit)
  /specs        → Formal specs (immutable after approval)
  /specs_draft  → Draft specs (editable)
  /plans        → Phases_index.md, Plan_vN.md
  /tasks        → TaskSet_vN.md
  /reports      → ValidationReports, PhaseSummaries, SENARIncidents, Metrics_PhaseN.md
  /templates    → Artifact templates
```

## §0.12 Bash Command Audit (Hook Infrastructure)

Every Bash command executed by Claude Code is automatically intercepted and logged via
Claude Code hooks configured in `~/.claude/settings.json`.

### Hook mechanism

> **Phase 13 M1 complete:** Hook migrated from `python3 .sdd/tools/log_tool.py pre|post` to `sdd-hook-log pre|post` (console_scripts entry point — no PYTHONPATH/cwd dependency). All logic lives in `src/sdd/hooks/log_tool.py`. (I-HOOK-WIRE-1, I-HOOK-FAILSAFE-1)

```
PreToolUse  (.*)  → sdd-hook-log pre  → sdd.hooks.log_tool.main()
                                        → emits ToolUseStarted → sdd_events.duckdb only

PostToolUse (.*)  → sdd-hook-log post → sdd.hooks.log_tool.main()
                                        → emits ToolUseCompleted → sdd_events.duckdb only
```

Legacy (before this session): matcher was `Bash` → `log_bash.py` → emitted `BashCommandStarted`/`BashCommandCompleted` → DuckDB + audit_log.jsonl. These events remain in DuckDB as historical record.

### Event payloads

```
BashCommandStarted:
  command:        full shell command string
  description:    tool description field
  timestamp_ms:   Unix ms

BashCommandCompleted:
  command:        full shell command string
  description:    tool description field
  output_snippet: first 500 chars of stdout/stderr
  interrupted:    bool
  timestamp_ms:   Unix ms
```

### NORM-AUDIT-BASH

```
norm_id:     NORM-AUDIT-BASH
actor:       llm
type:        informational (not enforcement)
result:      always "allowed" — hook NEVER blocks execution (exit 0)
applies_to:  every tool call (matcher: ".*"), regardless of phase
```

### SDD_SEQ_CHECKPOINT rule

DuckDB does not always persist sequence state across connections. `sdd_db.py` compensates
by recreating the sequence on every `open_sdd_connection()` call:

```python
next_seq = max(SDD_SEQ_CHECKPOINT, current_max + 1)
CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}
```

`SDD_SEQ_CHECKPOINT` is a documented floor — its value must be kept ≤ actual `MAX(seq)`:

```
SDD_SEQ_CHECKPOINT = 85   # floor; update when manually resetting sequence
```

**When to update `SDD_SEQ_CHECKPOINT`** (rule `SDD-SEQ-1`):
- Only when the DuckDB file is recreated or events are manually deleted
- Set value to `MAX(seq) + 1` from the new database state
- Update both `sdd_db.py` and this comment in CLAUDE.md simultaneously

The dynamic `MAX(seq)+1` is authoritative. `SDD_SEQ_CHECKPOINT` is a safety floor, not a counter.

---

BashCommand events have **no `phase_id`** in payload. To query them:
```
sdd query-events --event BashCommandStarted
sdd query-events --phase 7 --include-bash
```

### EventLog event taxonomy for a Phase N

When implementing Phase N the following events are recorded in chronological order:

| # | Event type | Level | Source | payload.phase_id | payload.task_id |
|---|---|---|---|---|---|
| 1 | `ToolUseStarted` | L2 Operational | log_tool.py | — | — |
| 2 | `ToolUseCompleted` | L2 Operational | log_tool.py | — | — |
| 3 | `TaskImplemented` | **L1 Domain** | update_state.py complete | N | T-Nxx |
| 4 | `MetricRecorded(task.lead_time)` | L2 Operational | update_state.py complete | N | T-Nxx |
| 5 | `ToolUseStarted` / `ToolUseCompleted` | L2 Operational | log_tool.py | — | — |
| 6 | `TestRunCompleted` | **L1 Domain** | update_state.py validate --run-tests | N | T-Nxx |
| 7 | `MetricRecorded(quality.*)` | L2 Operational | validate_invariants.py | N | T-Nxx |
| 8 | `TaskValidated` | **L1 Domain** | update_state.py validate | N | T-Nxx |
| 9 | `MetricRecorded(task.validation_attempts)` | L2 Operational | update_state.py validate | N | T-Nxx |
| 10 | *(repeat 1–9 for each task)* | | | | |
| 11 | `PhaseCompleted` | **L1 Domain** | update_state.py validate --check-dod | N | last task |
| 12 | `MetricRecorded(phase.completion_time)` | L2 Operational | update_state.py --check-dod | N | — |

**Event levels** (L1 = replay/SSOT, L2 = observability, L3 = debug — see §0.14):

**ToolUseStarted payload fields by tool:**

| tool_name | extra fields |
|---|---|
| `Bash` | `command` (≤300 chars), `description` |
| `Read` | `file_path`, `offset`?, `limit`? |
| `Edit` | `file_path`, `old_len`, `new_len` |
| `Write` | `file_path`, `content_len` |
| `Glob` | `pattern`, `path` |
| `Grep` | `pattern`, `glob`, `path`, `output_mode` |
| `Agent` | `description` (≤120 chars), `subagent_type` |
| others | `keys` (list of input key names) |

**ToolUseCompleted** always adds: `output_len` (bytes), `interrupted` (bool), `error_snippet` (if error).

For **Phase 7 specifically**, Spec_v7 also defines these domain-level events emitted by the
application itself (not SDD tooling) — they will be in the application EventLog, not `.sdd`:
- `ExecutionEnvironmentSnapshot`
- `CostModelFrozen`

### Querying EventLog context

```bash
# All SDD process events for Phase 7
sdd query-events --phase 7

# Step-level: all events for task T-701
sdd query-events --phase 7 --step T-701

# Event-level: all TaskImplemented events for Phase 7
sdd query-events --phase 7 --event TaskImplemented

# Phase 7 events + bash commands executed during implementation
sdd query-events --phase 7 --include-bash

# All bash commands ever logged (any phase)
sdd query-events --event BashCommandStarted

# Show all event types in the log
sdd query-events --list-types

# JSON output for programmatic use
sdd query-events --phase 7 --json
```

## §0.13 Project Configuration

Project-specific settings live in `.sdd/config/` — loaded by Python scripts, never interpreted by LLM directly.

```
.sdd/config/project_profile.yaml   ← стек, code rules, scope, domain, custom norms
.sdd/config/sdd_config.yaml        ← режимы, gates, budgets
.sdd/config/phases/phase_N.yaml    ← phase-level overrides
```

**3-уровневый override (lowest → highest priority):**
```
base defaults (SDD built-in) ← project_profile.yaml ← phases/phase_N.yaml
```

**Ключевые блоки `project_profile.yaml`:**

| Блок | Читает скрипт | Что настраивает |
|---|---|---|
| `stack` | `build_context.py` | Языки, версии, linter/formatter/typecheck |
| `build.commands` | `validate_invariants.py` | Команды lint, test, typecheck, build |
| `testing.coverage_threshold` | `validate_invariants.py` | exit 1 если coverage ниже порога |
| `code_rules.forbidden_patterns` | `validate_invariants.py` | grep по outputs задачи (hard/soft) |
| `scope.forbidden_dirs` | `check_scope.py` | Расширяет базовый deny-list |
| `domain.glossary` | `build_context.py` | Layer 0 контекста агента |
| `norms.custom` | `norm_guard.py` | Проектные нормы поверх базовых |

**Правила:**
- `sdd_config_loader.py` — единственная точка входа для чтения конфигов (SEM-9)
- `validate_config.py --phase N` запускается ПЕРЕД каждой Validate T-NNN командой
- Добавление нового блока = YAML + чтение в sdd_config_loader.py + использование в скрипте + validate_config.py check

Полная схема: см. `sdd_arch_v2.md §13`.

---

## §0.14 Metrics Layer

Все метрики → DuckDB (`partition_key='metrics'`). Единственный путь записи: `record_metric.py`.

**4 категории:**

| Категория | Примеры метрик | Источник |
|---|---|---|
| Process | `task.lead_time`, `task.first_try_pass_rate`, `guard.rejection_rate` | `update_state.py`, `phase_guard.py` |
| Quality | `quality.test_coverage`, `quality.lint_violations`, `quality.type_errors` | `validate_invariants.py` |
| Agent | `agent.tokens_used`, `agent.scope_violations_attempted`, `agent.context_layers_loaded` | `build_context.py`, `check_scope.py`, hooks |
| Infra | `infra.eventlog_size`, `infra.event_level_distribution`, `infra.guard_latency_ms` | `metrics_snapshot.py`, hooks |

**Автосбор:** каждый скрипт пишет метрики автоматически — LLM не пишет метрики вручную (SEM-8).

**Обязательный шаг фазы (ПОСЛЕ Summarize, ПЕРЕД EventLog Snapshot):**
```
sdd metrics-report --phase N --trend --anomalies
→ .sdd/reports/Metrics_PhaseN.md
```

**Петля улучшения:**
```
Metrics_PhaseN.md → Human review → изменения в project_profile.yaml / sdd_config.yaml
→ Phase N+1 стартует с улучшенной конфигурацией
```

**Event levels (для EventLog):**
```
Level 1 — Domain Events   → replay, SSOT, forever retention
Level 2 — Operational     → MetricRecorded, ToolUse*, 90 days, compactable
Level 3 — Debug           → ephemeral details, 7 days, можно отключить
```

Replay строится ТОЛЬКО по Level 1. Метрики — Level 2.

Полная схема: см. `sdd_arch_v2.md §14`.

---

## §0.15 Kernel Contract Freeze

**Phase 8** freezes the following public interfaces (invariant I-KERNEL-EXT-1). These surfaces MAY be extended only with: (a) optional parameters with default values, or (b) new backward-compatible return fields. Any change to positional arguments, parameter order, or required parameters is a **breaking change** and requires a new spec and human approval.

| Module | Frozen surface |
|--------|----------------|
| `core/types.py` | `Command` dataclass fields; `CommandHandler` Protocol |
| `core/events.py` | `DomainEvent` base fields; `EventLevel`; `classify_event_level()` |
| `infra/event_log.py` | `sdd_append()`, `sdd_append_batch()`, `sdd_replay()` signatures |
| `infra/event_store.py` | `EventStore.append()` interface |
| `domain/state/reducer.py` | `reduce()` signature; I-REDUCER-1 filter contract |
| `domain/guards/context.py` | `GuardContext`, `GuardResult`, `GuardOutcome` |
| `infra/paths.py` | `get_sdd_root()`, `reset_sdd_root()`, `event_store_file()`, `state_file()`, `audit_log_file()`, `norm_catalog_file()`, `config_file()`, `phases_index_file()`, `specs_dir()`, `specs_draft_dir()`, `plans_dir()`, `tasks_dir()`, `reports_dir()`, `templates_dir()`, `taskset_file(phase)`, `plan_file(phase)` — stdlib-only imports (I-PATH-2) |

**Not frozen** (may evolve per phase spec): DuckDB schema internals, reducer handler logic, guard pipeline composition, command handler implementations, projections, CLI layer.

**Enforcement:** I-KERNEL-EXT-1 is a governance invariant enforced at the human review gate (PR merge) — no automated test. Before proposing any change to a frozen interface, consult this table: if the change is breaking, open a new spec draft first.

---

## §0.16 Kernel Hardening Catalog (Phase 10)

All 18 Phase 10 invariants with machine-verifiable check method. All MUST be PASS before Phase 10 can be COMPLETE.

| Invariant | Statement (short) | Verification file | Command |
|-----------|-------------------|-------------------|---------|
| I-FAIL-1 | SDDError → exit 1 + JSON stderr; Exception → exit 2 + JSON stderr | `tests/unit/test_cli_exec_contract.py` | `pytest tests/unit/test_cli_exec_contract.py -v` |
| I-USAGE-1 | `click.ClickException` → JSON stderr with `exit_code: 1` (not 2) | `tests/unit/test_cli_exec_contract.py` | `pytest tests/unit/test_cli_exec_contract.py::test_click_exception_exit_1_not_2 -v` |
| I-EXEC-SUCCESS-1 | CLI success path calls `sys.exit(result or 0)` — never implicit exit | `tests/unit/test_cli_exec_contract.py` | `pytest tests/unit/test_cli_exec_contract.py::test_success_path_exit_zero -v` |
| I-CLI-API-1 | JSON error fields `error_type`, `message`, `exit_code` are frozen | `tests/unit/test_cli_exec_contract.py` | `pytest tests/unit/test_cli_exec_contract.py::test_cli_json_schema_fields -v` |
| I-ERR-CLI-1 | `click.ClickException` MUST NOT produce ErrorEvent | `tests/unit/test_cli_exec_contract.py` | `pytest tests/unit/test_cli_exec_contract.py::test_click_exception_no_error_event -v` |
| I-EXEC-NO-CATCH-1 | No intermediate layer may catch without re-raising; only `cli.main()` terminates exception flow | code review (S-EXEC-1) | `grep -n "except" src/sdd/cli.py` |
| I-ENV-1 | `sdd --help` succeeds with minimal env dict (no PYTHONPATH) | `tests/integration/test_env_independence.py` | `pytest tests/integration/test_env_independence.py::test_sdd_help_minimal_env -v` |
| I-ENV-2 | Adapter ImportError MUST output "run pip install -e ." to stderr | `tests/integration/test_env_independence.py` | `pytest tests/integration/test_env_independence.py::test_adapter_import_error_message -v` |
| I-ENV-BOOT-1 | Adapter ImportError output MUST be structured JSON matching I-CLI-API-1 schema | `tests/integration/test_env_independence.py` | `pytest tests/integration/test_env_independence.py::test_adapter_import_error_message -v` |
| I-LEGACY-0a | No `sys.path` mutation toward `.sdd/` in `src/sdd/**/*.py` | grep via validate_invariants.py | `sdd validate-invariants --check I-LEGACY-0a --scope full-src` |
| I-LEGACY-0b | No `subprocess` calls to `.sdd/tools/` in `src/sdd/**/*.py` | grep via validate_invariants.py | `sdd validate-invariants --check I-LEGACY-0b --scope full-src` |
| I-ENTRY-1 | No `__main__` blocks in `src/sdd/**/*.py` except `cli.py` and `hooks/*.py` | grep via validate_invariants.py | `sdd validate-invariants --check I-ENTRY-1 --scope full-src` |
| I-KERNEL-REG | Six frozen modules pass `mypy --strict` + import-time smoke | `tests/regression/test_kernel_contract.py` | `pytest tests/regression/test_kernel_contract.py -v` |
| I-KERNEL-SIG-1 | Public function signatures of frozen modules MUST NOT change | `tests/regression/test_kernel_contract.py` | `pytest tests/regression/test_kernel_contract.py::test_frozen_modules_signatures -v` |
| I-REG-ENV-1 | Regression suite runs against pinned dev toolchain (`mypy>=1.8`) | `tests/regression/test_kernel_contract.py` | `pytest tests/regression/test_kernel_contract.py -v` |
| I-PURE-1 | `compute_trend()` and `detect_anomalies()` make zero I/O calls | `tests/unit/infra/test_metrics_purity.py` | `pytest tests/unit/infra/test_metrics_purity.py -v` |
| I-PURE-1a | No `import duckdb` inside function bodies in `sdd/infra/metrics.py` | `tests/unit/infra/test_metrics_purity.py` | `pytest tests/unit/infra/test_metrics_purity.py -v` |
| I-EXEC-ISOL-1 | Tests MUST use `tmp_path`-isolated DuckDB; project `sdd_events.duckdb` never touched by tests | `tests/integration/test_pipeline_deterministic.py` | `pytest tests/integration/test_pipeline_deterministic.py -v` |

**Full Phase 10 suite:**
```bash
pytest tests/unit/test_cli_exec_contract.py tests/integration/test_env_independence.py \
       tests/regression/test_kernel_contract.py tests/integration/test_pipeline_smoke.py \
       tests/integration/test_pipeline_deterministic.py tests/unit/infra/test_metrics_purity.py -v
sdd validate-invariants --check I-LEGACY-0a --scope full-src
sdd validate-invariants --check I-LEGACY-0b --scope full-src
sdd validate-invariants --check I-ENTRY-1 --scope full-src
```

---

*Archived reference:*  
*CLAUDE_v2.md → Kernel v2 archive | CLAUDE_v3.md → Runtime v3 archive | CLAUDE_v3-PLAN.md → Plan archive*
