---
source: CLAUDE.md §0.10
last_synced: 2026-04-25
update_trigger: when new sdd CLI commands shipped or existing commands changed
---

# Ref: SDD Tool Reference (§0.10)
<!-- Loaded by §HARD-LOAD Rule 4 when CLI command not in §TOOLS -->

## §CONTRACT HIERARCHY

```
1. .sdd/contracts/cli.schema.yaml  ← MACHINE TRUTH — authoritative source
2. src/sdd/commands/*.py           ← Python implementation (MUST match schema)
3. tool-reference.md               ← DERIVED from schema (human-readable)
4. .sdd/docs/sessions/*.md         ← usage recipes (reference tool-reference)
```

RULE: `tool-reference.md` is NOT an authoritative contract.
      Any discrepancy with `cli.schema.yaml` → `cli.schema.yaml` wins.

## §CLI CONTRACT

| Command | REQUIRED FLAGS | OPTIONAL FLAGS | STATE_SOURCE | FORBIDDEN FLAGS |
|---------|---------------|----------------|--------------|-----------------|
| `sdd path <resource>` | `resource` (positional: state\|taskset\|eventlog\|plan\|config) | `--phase N` (taskset/plan) | FS-direct (§BOOTSTRAP) | — |
| `sdd phase-guard check` | `--command`, `--state` | — | arg | — |
| `sdd task-guard check` | `--task`, `--taskset` | — | arg | — |
| `sdd check-scope read` | `<path>` (positional) | `--inputs file1,file2,...` | — | — |
| `sdd norm-guard check` | `--actor`, `--action` | — | — | — |
| `sdd show-state` | — | `--state` | sdd.path.state | `--json`, `--format` |
| `sdd show-task` | `<T-NNN>` (positional) | `--phase N` | — | — |
| `sdd show-spec` | `--phase N` | — | — | — |
| `sdd show-plan` | — | `--phase N` | sdd.path.state | — |
| `sdd complete` | `<T-NNN>` (positional) | — | REGISTRY | — |
| `sdd validate` | `<T-NNN>` (positional), `--result PASS\|FAIL` | `--check-dod` (DoD mode: omit T-NNN, add `--phase N`) | REGISTRY | — |
| `sdd activate-phase` | `<N>` (positional) | `--tasks <path>` [DEPRECATED], `--executed-by <actor>` | REGISTRY | — |
| `sdd record-session` | `--type T`, `--phase N` | — | REGISTRY | — |
| `sdd sync-state` | `--phase N` | — | REGISTRY | — |
| `sdd record-decision` | `--decision-id`, `--title`, `--summary` | `--phase N` | REGISTRY | — |
| `sdd query-events` | `--phase N` | `--step`, `--event`, `--include-bash`, `--json`, `--save`, `--list-types` | — | — |
| `sdd metrics-report` | `--phase N` | `--trend`, `--anomalies` | — | — |
| `sdd report-error` | `--type`, `--message` | — | — | — |
| `sdd validate-config` | `--phase N` | `--config <path>` | — | — |
| `sdd validate-invariants` | `--phase N` | `--task T-NNN`, `--check I-XXX`, `--scope` | — | — |
| `sdd resolve` | `<QUERY>` (positional) | `--format json\|text`, `--rebuild`, `--debug` | graph | — |
| `sdd explain` | `<NODE_ID>` (positional) | `--edge-types TYPE1,...`, `--format json\|text`, `--rebuild`, `--debug` | graph | — |
| `sdd trace` | `<NODE_ID>` (positional) | `--edge-types TYPE1,...`, `--format json\|text`, `--rebuild`, `--debug` | graph | — |
| `sdd graph-stats` | — | `--edge-type KIND`, `--node-type KIND`, `--format json\|text` | graph | — |

**Notes:**
- ⚠ `resolve --format json`: REQUIRED in STEP 4.5 anchor discovery; text format is human-only
- ⚠ `explain --edge-types`: comma-separated, no spaces (e.g. `implements,guards,emits`); `""` → non-zero exit; omit → default BFS kinds
- ⚠ `trace --edge-types`: comma-separated; omit → all in-edges (backward compat)
- ⚠ `phase-guard check`: `--state` REQUIRED — guard does NOT auto-detect paths (see `cli.schema.yaml`)
- ⚠ `task-guard check`: `--taskset` REQUIRED — guard does NOT auto-detect paths (see `cli.schema.yaml`)
- ⚠ `check-scope read <path> --inputs f1,f2,...`: `--inputs` required for any `src/` path — without it guard assumes no declared inputs and denies access; pass ALL Task Inputs comma-joined
- ⚠ `validate T-NNN`: `--result PASS|FAIL` REQUIRED — omitting it raises `InvalidState` (exit 1 JSON stderr)
- ⚠ `validate --check-dod`: DoD mode — no `task_id`, requires `--phase N`; `sdd check-dod` as standalone does NOT exist
- `show-state`: FORBIDDEN: `--json`, `--format`
- `query-events`: the ONLY command with `--json` output flag
- `activate-phase`: HUMAN-ONLY gate — LLM MUST NOT invoke EXCEPT in DECOMPOSE
  auto-action with `--executed-by llm` (I-SESSION-AUTO-1). In all other contexts,
  LLM invocation is forbidden (NORM-ACTOR-001).
- ⚠ `activate-phase --tasks`: [DEPRECATED] — `--tasks` flag is deprecated; prefer explicit TaskSet placement via `sdd path taskset`
- ⚠ `activate-phase --executed-by`: distinguishes `actor` (who is authorized to run the command, always `human`) from `executed_by` (the concrete identity of the executor: human username (e.g. `katyrev`) or `llm` in DECOMPOSE auto-action); used for audit attribution in SessionDeclared / PhaseInitialized events
- ⚠ `record-session --type T --phase N`: LLM MUST call this at session start to emit `SessionDeclared`; satisfies I-SESSION-DECLARED-1 (session type declared) and I-SESSION-ACTOR-1 (actor logged)

**Canonical usage with path resolution:**
```bash
STATE=$(sdd path state)
TASKSET=$(sdd path taskset)          # auto-detects phase
TASKSET=$(sdd path taskset --phase 17)  # explicit phase

sdd phase-guard check --command "Implement T-NNN" --state "$STATE"
sdd task-guard check --task T-NNN --taskset "$TASKSET"
sdd show-state --state "$STATE"
```

> `sdd` CLI (`pip install -e .`) is the sole runtime interface for all governance operations.
> `.sdd/_deprecated_tools/` — historical reference only; do NOT invoke directly.
>
> **Invocation rule:** ALWAYS use the `sdd` shell command directly (console_script entry point).
> NEVER use `python3 -m sdd` — the package has no `__main__.py`, this will fail with exit 1.
> If `sdd` is not found: run `pip install -e .` from the repo root, then retry.

## Write Commands (REGISTRY — all go through execute_and_project)

| Command | Purpose | Actor |
|---------|---------|-------|
| `sdd complete T-NNN` | Mark task DONE — sole mutation path for TaskSet + State | llm |
| `sdd validate T-NNN --result PASS\|FAIL` | Validate task invariants + record results | llm |
| `sdd validate --check-dod --phase N` | Terminal DoD check; emits PhaseCompleted on success | llm |
| `sdd activate-phase N [--tasks T] [--executed-by <actor>]` | Activate next phase; emits PhaseStarted + TaskSetDefined | **human** |
| `sdd record-session --type T --phase N` | Declare session type + actor; emits SessionDeclared | llm |
| `sdd sync-state --phase N` | Rebuild State_index from EventLog replay (NoOpHandler + project_all) | llm |
| `sdd record-decision …` | Audit record; emits DecisionRecordedEvent | llm |

## Read-Only Commands (bypass REGISTRY — I-READ-ONLY-EXCEPTION-1)

| Command | Purpose |
|---------|---------|
| `sdd show-state` | Print State_index as markdown table |
| `sdd show-task T-NNN [--phase N]` | Task definition: status, inputs, outputs, invariants, acceptance |
| `sdd show-spec --phase N` | Full spec content for phase N |
| `sdd show-plan --phase N` | Full plan content for phase N |
| `sdd validate-config --phase N` | Validate project_profile.yaml + phase_N.yaml |
| `sdd validate-invariants --phase N [--task T-NNN] [--check I-XXX]` | Check I-SDD invariants + record quality metrics |
| `sdd query-events --phase N [--step T-NNN] [--event TYPE] [--include-bash] [--json] [--save]` | Query EventLog (PostgreSQL single source) |
| `sdd metrics-report --phase N [--trend] [--anomalies]` | Generate Metrics_PhaseN.md |
| `sdd report-error --type T --message M` | Structured violation reporter |
| `sdd phase-guard check --command "Implement T-NNN"` | PhaseGuard + SDDEventRejected emitter |
| `sdd task-guard check --task T-NNN` | Verify task Status == TODO |
| `sdd check-scope read <path>` | Validate file access against SENAR norms |
| `sdd norm-guard check --actor llm --action implement_task` | Machine-readable norm enforcement |

## Graph Navigation Commands (IMPLEMENT-allowed)

> NORM-GRAPH-001: LLM MAY invoke these commands during IMPLEMENT and DECOMPOSE sessions.
> Purpose: deterministic file scope discovery (I-IMPLEMENT-GRAPH-1). See `implement.md` STEP 4.5.

### `sdd resolve <QUERY> --format json`

Searches graph nodes by free-text keyword. Returns ranked candidates with `node_id`, `kind`, `score`.

**STEP 4.5 usage — anchor discovery (Sub-step 4.5-A):**
```bash
sdd resolve "TaskNavigationSpec" --format json
# → exit 0 required (I-DECOMPOSE-RESOLVE-1)
# → top-1 candidate.kind ∈ expected_kinds (I-DECOMPOSE-RESOLVE-2)
# Repeat per each resolve_keyword in task.navigation
```

| Flag | Required | Description |
|------|----------|-------------|
| `<QUERY>` | yes | Free-text search term (keyword from task.navigation) |
| `--format json` | **yes in STEP 4.5** | Machine-readable output for anchor extraction; text is human-only |
| `--rebuild` | no | Force graph rebuild (ignore GraphCache) |
| `--debug` | no | Show selection debug info |

### `sdd explain <NODE_ID> [--edge-types TYPE1,TYPE2,...]`

BFS traversal from anchor node following out-edges. Returns FILE nodes reachable via whitelisted edge kinds.

**STEP 4.5 usage — dependency traversal (Sub-step 4.5-B):**
```bash
sdd explain TASK:T-5521 --edge-types implements,guards,emits
# → FILE nodes reachable from anchor via listed edge kinds
# → these files receive graph justification for reading (I-IMPLEMENT-GRAPH-1, case a)
# Repeat per each anchor node found in Sub-step 4.5-A
```

| Flag | Required | Description |
|------|----------|-------------|
| `<NODE_ID>` | yes | Anchor node id (e.g. `TASK:T-5521`, `FILE:src/sdd/cli.py`, `MODULE:sdd.graph`) |
| `--edge-types` | no | Comma-separated edge kinds to filter BFS; omit → default kinds (`implements,guards,emits`); `""` → error |
| `--format` | no | `json` or `text` (default: `text`) |
| `--rebuild` | no | Force graph rebuild |

**graph_budget warning** (non-blocking): `max_graph_calls_warning: 5`, `max_traversal_depth: 2`

### `sdd trace <NODE_ID> [--edge-types TYPE1,TYPE2,...]`

Reverse BFS from target file. Returns all dependents (who imports / uses the target).

**STEP 4.5 usage — before-write trace (Sub-step 4.5-C):**
```bash
sdd trace FILE:src/sdd/tasks/navigation.py --edge-types imports
# → returns all FILE nodes that import the target
# → I-IMPLEMENT-TRACE-1: every dependent MUST get an explicit decision
# Repeat per each file in task.navigation.write_scope
```

| Flag | Required | Description |
|------|----------|-------------|
| `<NODE_ID>` | yes | Target file node id (e.g. `FILE:src/sdd/tasks/navigation.py`) |
| `--edge-types` | no | Comma-separated in-edge kinds to filter; omit → all in-edges (backward compat) |
| `--format` | no | `json` or `text` (default: `text`) |
| `--rebuild` | no | Force graph rebuild |

**I-IMPLEMENT-TRACE-1:** every dependent returned by `sdd trace` MUST receive an explicit decision before writing (keep read-only, escalate, or open a new task for dependent changes).

### `sdd graph-stats [--node-type KIND] [--edge-type KIND] [--format json|text]`

Shows aggregate statistics about the knowledge graph: node counts by kind, edge counts by kind.
Optionally filter to a single node kind or edge kind.

| Flag | Required | Description |
|------|----------|-------------|
| `--node-type` | no | Show only nodes of this kind (e.g. `FILE`, `COMMAND`, `TASK`) |
| `--edge-type` | no | Show only edges of this kind (e.g. `imports`, `emits`, `guards`) |
| `--format` | no | `json` or `text` (default: `text`) |

**Example:**
```bash
sdd graph-stats                          # total nodes + edges
sdd graph-stats --node-type FILE         # FILE node count only
sdd graph-stats --edge-type imports      # imports edge count only
sdd graph-stats --format json            # JSON output
```

---

## Hook Commands (console_scripts)

| Command | Purpose |
|---------|---------|
| `sdd-hook-log pre\|post` | Claude Code PreToolUse/PostToolUse hook → emits ToolUse* to PostgreSQL |

## Querying EventLog

```bash
# All SDD process events for Phase N
sdd query-events --phase N

# Step-level: all events for task T-NNN
sdd query-events --phase N --step T-NNN

# Event-level: all TaskImplemented events
sdd query-events --phase N --event TaskImplemented

# Phase N events + bash commands
sdd query-events --phase N --include-bash

# JSON output for programmatic use + save snapshot
sdd query-events --phase N --json --save

# Show all event types
sdd query-events --list-types
```

## SDD_SEQ_CHECKPOINT (SDD-SEQ-1)

```python
SDD_SEQ_CHECKPOINT = 85   # floor; update when manually resetting sequence
```

Update ONLY when PostgreSQL schema is reset or events manually deleted.
Set to `MAX(seq) + 1` from new DB state.
Update both `sdd_db.py` AND CLAUDE.md §0.12 simultaneously.

## Event Types (phase ordering)

| # | Event | Level | payload.phase_id |
|---|-------|-------|-----------------|
| 1 | `ToolUseStarted` | L2 | — |
| 2 | `ToolUseCompleted` | L2 | — |
| 3 | `TaskImplemented` | L1 | N |
| 4 | `MetricRecorded(task.lead_time)` | L2 | N |
| 5 | `TestRunCompleted` | L1 | N |
| 6 | `MetricRecorded(quality.*)` | L2 | N |
| 7 | `TaskValidated` | L1 | N |
| 8 | `MetricRecorded(task.validation_attempts)` | L2 | N |
| 9 | `PhaseCompleted` | L1 | N |
| 10 | `MetricRecorded(phase.completion_time)` | L2 | N |

**Levels:** L1 = replay/SSOT (retain forever), L2 = observability (~90 days), L3 = debug (7 days).

## Archived Adapters (historical reference — do NOT invoke)

Former `.sdd/tools/` scripts → now in `.sdd/_deprecated_tools/`:
`update_state.py`, `sync_state.py`, `phase_guard.py`, `task_guard.py`, `check_scope.py`,
`norm_guard.py`, `validate_invariants.py`, `report_error.py`, `query_events.py`,
`metrics_report.py`, `show_state.py`, `build_context.py`, `senar_audit.py`,
`norm_catalog.py`, `record_metric.py`, `sdd_run.py` (deleted in Phase 15).
