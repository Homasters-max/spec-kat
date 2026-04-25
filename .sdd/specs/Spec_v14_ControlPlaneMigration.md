# Spec_v14 — Phase 14: Control Plane Migration

Status: Draft
Baseline: Spec_v13_RuntimeStabilization.md; plan at /root/.claude/plans/glowing-zooming-quokka.md

---

## 0. Goal

Eliminate the three-source-of-truth problem for SDD filesystem paths by introducing
`src/sdd/infra/paths.py` as the single, frozen path resolver. All 23 hardcoded `.sdd/`
strings scattered across 12 source files are replaced with calls to `paths.py` functions
driven by the `SDD_HOME` env var. Simultaneously, three new read-only CLI commands
(`sdd show-task`, `sdd show-spec`, `sdd show-plan`) replace direct filesystem access by
the LLM, closing the §R.2 dual-model gap where LLM reasoning used hardcoded paths that
differed from runtime behavior. After this phase, the LLM MUST NOT read `.sdd/` files
directly; it uses only CLI output.

---

## 1. Scope

### In-Scope

- **BC-14-PATHS**: new `src/sdd/infra/paths.py` — frozen single source of truth for all SDD paths
- **BC-1 Infra** (existing): `db.py`, `audit.py`, `event_log.py` — remove `__file__`-relative paths and `SDD_EVENTS_DB` constant
- **BC-3 Guards** (existing): `scope.py`, `task.py`, `phase.py`, `norm.py` — replace hardcoded paths
- **BC-4 Commands** (existing): 7 command files — replace `SDD_DB_PATH` / `SDD_STATE_PATH` env overrides
- **BC-5 Context** (existing): `build_context.py` — close config-override backdoor (I-CONFIG-PATH-1)
- **BC-8 CLI** (existing): `cli.py` and new commands `show_task.py`, `show_spec.py`, `show_plan.py`
- **BC-Hooks** (existing): `hooks/log_tool.py` — replace `SDD_DB_PATH`, use `paths.py`
- **Test infrastructure**: new `tests/integration/test_sdd_home_isolation.py`; update `tests/regression/test_kernel_contract.py` for new `None` defaults
- **Config**: add I-PATH-1 forbidden pattern to `.sdd/config/project_profile.yaml`
- **Governance docs**: CLAUDE.md §R.2, §0.15, §0.10, §K.4

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-14-PATHS: `infra/paths.py`

```
src/sdd/infra/
  paths.py    # single source of truth for all SDD filesystem paths
```

**Frozen interface** (I-PATH-2): imports ONLY `os`, `pathlib` — zero intra-sdd imports.
**No directory creation** (I-PATH-4): returns `Path` objects, never calls `mkdir`.
**Lazy cached root** (I-PATH-3-IMPL): `_sdd_root` global, set once, cleared only by `reset_sdd_root()` for test isolation.

```
get_sdd_root() → Path          # SDD_HOME env → .sdd/ default → .resolve()
reset_sdd_root() → None        # test isolation ONLY (I-PATH-5)
event_store_file() → Path
state_file() → Path
audit_log_file() → Path
norm_catalog_file() → Path
config_file() → Path
phases_index_file() → Path
specs_dir() → Path             # immutable approved specs
specs_draft_dir() → Path       # editable drafts
plans_dir() → Path
tasks_dir() → Path
reports_dir() → Path           # base dir; callers construct filenames (e.g. reports_dir() / f"ValidationReport_T-{task_id}.md")
templates_dir() → Path
taskset_file(phase: int) → Path
plan_file(phase: int) → Path
```

Non-critical report files (ValidationReport_T-NNN.md, PhaseN_Summary.md, etc.) are
constructed by callers as `reports_dir() / filename`. `paths.py` exposes the base dir,
not per-report functions, to avoid combinatorial explosion of named functions.

### BC-8 CLI additions: `show-task`, `show-spec`, `show-plan`

```
src/sdd/commands/
  show_task.py    # sdd show-task T-NNN [--phase N]
  show_spec.py    # sdd show-spec --phase N
  show_plan.py    # sdd show-plan --phase N
```

Read-only commands. No events emitted, no state mutation. Output is deterministic
structured markdown to stdout (I-CLI-READ-1, I-CLI-SCHEMA-1). Errors go to stderr as
structured JSON (I-CLI-API-1 schema). Schema version is implicitly 1 (I-CLI-VERSION-1).

### `build_context.py` — separation of concerns (SEM-9 preserved)

`build_context.py` remains the SEM-9 mechanism for loading project config context
(project_profile.yaml, domain glossary, stack config). It is **not replaced** by CLI
commands — it serves a different concern.

The two mechanisms are **orthogonal**:

| Mechanism | Purpose | Path source |
|-----------|---------|-------------|
| `build_context.py` | project config / profile context | `paths.py` (backdoor closed per I-CONFIG-PATH-1) |
| `sdd show-*` CLI | SDD artifact content for LLM reads | `paths.py` |

`build_context.py` MUST NOT call `sdd show-*` commands internally — shell calls from
Python are a scope violation and create circular dependency. If build_context needs SDD
artifact content in future, it reads via `paths.py` functions directly (it is internal
infrastructure, not LLM-facing scope).

### Dependencies

```text
paths.py          → stdlib only (I-PATH-2)
infra/db.py       → paths.py
infra/audit.py    → paths.py
infra/event_log.py → paths.py
guards/*          → paths.py
commands/*        → paths.py
context/build_context.py → paths.py
hooks/log_tool.py → paths.py
cli.py            → paths.py; show_task, show_spec, show_plan
show_task.py      → paths.py (taskset_file)
show_spec.py      → paths.py (specs_dir)
show_plan.py      → paths.py (plan_file)
```

---

## 3. Domain Events

The `show-*` commands are **read-only**: they emit no domain events and do not mutate
`State_index.yaml` or the EventLog. The `paths.py` refactor itself produces no new
domain events — it is a structural change that alters how existing events are produced
(via corrected path resolution).

No new events are introduced in this phase.

### Preserved Events

All existing domain events (TaskImplemented, TaskValidated, PhaseCompleted, MetricRecorded,
ToolUseStarted, ToolUseCompleted) remain structurally unchanged. `sdd-hook-log` continues
emitting ToolUseStarted/Completed but now resolves the DB path via `paths.py`
(`str(event_store_file())`) instead of the `SDD_DB_PATH` env var.

---

## 4. Types & Interfaces

### `paths.py` — frozen public interface (added to §0.15 table)

```python
def get_sdd_root() -> Path: ...
def reset_sdd_root() -> None: ...          # I-PATH-5: test isolation ONLY
def event_store_file() -> Path: ...
def state_file() -> Path: ...
def audit_log_file() -> Path: ...
def norm_catalog_file() -> Path: ...
def config_file() -> Path: ...
def phases_index_file() -> Path: ...
def specs_dir() -> Path: ...
def specs_draft_dir() -> Path: ...
def plans_dir() -> Path: ...
def tasks_dir() -> Path: ...
def reports_dir() -> Path: ...
def templates_dir() -> Path: ...
def taskset_file(phase: int) -> Path: ...
def plan_file(phase: int) -> Path: ...
```

Sentinel pattern (Decision 1): `str | None = None` with `if x is None:` guard.
`""` as sentinel is **forbidden** — it is a valid (if unusual) string value.

### `infra/event_log.py` — frozen interface extension (§0.15 backward-compat)

```python
# BEFORE
def sdd_append(..., db_path: str = SDD_EVENTS_DB) -> None: ...
def sdd_append_batch(..., db_path: str = SDD_EVENTS_DB) -> None: ...
def sdd_replay(..., db_path: str = SDD_EVENTS_DB) -> list[dict]: ...
def exists_command(..., db_path: str = SDD_EVENTS_DB) -> bool: ...
def exists_semantic(..., db_path: str = SDD_EVENTS_DB) -> bool: ...
def get_error_count(..., db_path: str = SDD_EVENTS_DB) -> int: ...

# AFTER — None sentinel; body resolves via paths.event_store_file()
def sdd_append(..., db_path: str | None = None) -> None: ...
def sdd_append_batch(..., db_path: str | None = None) -> None: ...
def sdd_replay(..., db_path: str | None = None) -> list[dict]: ...
def exists_command(..., db_path: str | None = None) -> bool: ...
def exists_semantic(..., db_path: str | None = None) -> bool: ...
def get_error_count(..., db_path: str | None = None) -> int: ...
```

Broadening `str` → `str | None` is backward-compatible per §0.15(a): all callers passing
a `str` continue working. `test_kernel_contract.py::test_frozen_modules_signatures` must
be updated to expect `None` as the new default.

### `infra/audit.py` — sentinel extension

```python
# BEFORE
def log_action(..., audit_log_path: str = _AUDIT_LOG_DEFAULT) -> AuditEntry: ...

# AFTER — _AUDIT_LOG_DEFAULT constant removed; resolved lazily in body
def log_action(..., audit_log_path: str | None = None) -> AuditEntry: ...
```

### `guards/scope.py` — Path.resolve() comparison

```python
# BEFORE (string comparison — fragile)
if path.startswith(".sdd/specs/") or path == ".sdd/specs":

# AFTER (Decision 3)
def _is_specs_path(path: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(specs_dir().resolve())
    except (ValueError, TypeError):
        return False
```

For Python < 3.9: `str(Path(path).resolve()).startswith(str(specs_dir().resolve()))`.

### CLI output schema — `sdd show-task` (I-CLI-SCHEMA-1, frozen)

```
## Task: T-NNN
Status: <TODO|DONE>

### Inputs
- <path>

### Outputs
- <path>

### Invariants Covered
- <I-XXX>

### Acceptance Criteria
<verbatim text from TaskSet>
```

Section names, order, and heading levels are frozen (I-CLI-SCHEMA-2). Callers parsing
this output MAY rely on `## Task:`, `### Inputs`, `### Outputs`, `### Invariants Covered`,
`### Acceptance Criteria` as stable anchors. No additional sections without a version bump.

`sdd show-spec` and `sdd show-plan` output the raw file content verbatim — no schema
wrapping. Their determinism guarantee is at the file level (same file → same bytes).

### `show-spec` — AmbiguousSpec guard + resolution SSOT (Decisions 3–4)

If `specs_dir()` contains more than one `Spec_vN_*.md` for the requested phase:
`ERROR (AmbiguousSpec)`, exit 1 with structured JSON. `sorted()[0]` is **forbidden**
(filesystem ordering is non-deterministic across OSes).

The authoritative spec filename for phase N is the `spec` field in `Phases_index.md`
(I-SPEC-RESOLVE-2). `show-spec` SHOULD validate that the file listed in Phases_index.md
exists and is the only match — Phases_index.md is the SSOT for spec-to-phase mapping,
not filesystem enumeration.

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-PATH-1 | No literal `.sdd/` strings in `src/sdd/**/*.py` except `infra/paths.py` | 14 |
| I-PATH-2 | `paths.py` imports ONLY stdlib (`os`, `pathlib`) — zero intra-sdd imports | 14 |
| I-PATH-3 | Task Inputs/Outputs in TaskSet/Plan/Spec are relative to repo root, not `SDD_HOME` | 14 |
| I-PATH-4 | `paths.py` does NOT create directories; callers are responsible for existence | 14 |
| I-PATH-5 | `reset_sdd_root()` MUST NOT be called in production/runtime code — test isolation only | 14 |
| I-CONFIG-PATH-1 | Config MUST NOT override core SDD paths (state, tasks, specs, plans, db) | 14 |
| I-EVENT-PATH-1 | EventLog MUST NOT be used as source of filesystem paths; legacy `.sdd/` entries in DuckDB are opaque historical data | 14 |
| I-CLI-SSOT-1 | All data consumed by LLM MUST originate from `sdd show-*` CLI commands or Task Inputs field (direct filesystem reads of `.sdd/` are forbidden) | 14 |
| I-CLI-SSOT-2 | CLI output is a trusted deterministic projection of underlying SDD artifacts; LLM MUST treat it as authoritative | 14 |
| I-CLI-READ-1 | All `show-*` outputs are deterministic — no timestamps in content, no ANSI colors, fixed field ordering | 14 |
| I-CLI-READ-2 | `show-*` output is structured markdown with fixed section headers (machine-parseable) | 14 |
| I-CLI-SCHEMA-1 | `sdd show-task` output MUST follow the frozen schema: `## Task:`, `### Inputs`, `### Outputs`, `### Invariants Covered`, `### Acceptance Criteria` — in that order | 14 |
| I-CLI-SCHEMA-2 | Section names, order, and heading levels in `show-task` output MUST NOT change without a schema version bump | 14 |
| I-CLI-FAILSAFE-1 | All `show-*` commands exit 0 on success or structured JSON error on stderr (I-CLI-API-1 schema) — no raw tracebacks | 14 |
| I-CLI-VERSION-1 | All CLI `show-*` outputs carry implicit schema_version = 1; future structural changes require version increment and spec update | 14 |
| I-SCOPE-CLI-1 | CLI commands (`show-task`, `show-spec`, `show-plan`) are authorized to read SDD data paths regardless of LLM read scope — this is intentional and governed | 14 |
| I-SCOPE-CLI-2 | LLM MUST NOT simulate CLI by manually reading equivalent files — running `sdd show-task` is required; reading TaskSet directly is forbidden even when CLI output is available | 14 |
| I-SPEC-RESOLVE-1 | Spec resolution MUST NOT depend on filesystem ordering; no `sorted()[0]` or similar | 14 |
| I-SPEC-RESOLVE-2 | The authoritative spec filename for phase N is the `spec` field in `Phases_index.md` — filesystem enumeration alone is insufficient | 14 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-SDD-9 | `.sdd/specs/` is immutable |
| I-SDD-19 | Specs dir may not be written by LLM |
| I-KERNEL-EXT-1 | Frozen interfaces extended only via backward-compatible additions |
| I-FAIL-1 | SDDError → exit 1 + JSON stderr; Exception → exit 2 + JSON stderr |
| I-CLI-API-1 | JSON error fields `error_type`, `message`, `exit_code` are frozen |
| I-EXEC-ISOL-1 | Tests use `tmp_path`-isolated DuckDB; project `sdd_events.duckdb` never touched by tests |

---

## 6. Pre/Post Conditions

### `paths.get_sdd_root()`

**Pre:**
- May be called at any time (no state precondition)
- `SDD_HOME` env var may or may not be set

**Post:**
- Returns absolute resolved `Path` (never relative)
- If `SDD_HOME` is set: `result == Path(SDD_HOME).resolve()`
- If `SDD_HOME` is unset: `result == Path(".sdd").resolve()`
- Result is cached: subsequent calls return same object unless `reset_sdd_root()` called
- Directory does NOT need to exist (I-PATH-4)

### `sdd show-task T-NNN [--phase N]`

**Pre:**
- `State_index.yaml` is readable (for auto-detecting phase when `--phase` omitted)
- `taskset_file(phase)` exists and is readable
- T-NNN exists in the TaskSet

**Post:**
- Exit 0; structured markdown to stdout with sections: ID, Status, Inputs, Outputs, Invariants Covered, Acceptance Criterion
- If T-NNN not found: exit 1, JSON error `{error_type: "TaskNotFound", message: "...", exit_code: 1}`
- Output is deterministic (I-CLI-READ-1): same input → byte-identical output

### `sdd show-spec --phase N`

**Pre:**
- `specs_dir()` is accessible
- Exactly one `Spec_vN_*.md` file exists for phase N

**Post:**
- Exit 0; full spec content to stdout
- If zero files: exit 1, JSON error `{error_type: "SpecNotFound", ...}`
- If >1 file: exit 1, JSON error `{error_type: "AmbiguousSpec", ...}` (I-FAIL-SPEC-1)

### `sdd show-plan --phase N`

**Pre:**
- `plan_file(N)` exists and is readable

**Post:**
- Exit 0; full plan content to stdout
- If file missing: exit 1, JSON error `{error_type: "PlanNotFound", ...}`

### `infra/db.py` — `open_sdd_connection(db_path: str | None = None)`

**Pre:** None (lazy path resolution)

**Post:**
- If `db_path is None`: uses `str(event_store_file())` — respects `SDD_HOME`
- If `db_path` is a string: uses that path (test isolation path)
- `SDD_EVENTS_DB` module constant no longer exported

### `context/build_context.py` — config backdoor closed

**Pre:** `project_profile.yaml` may contain `state_path` or `phases_index_path` keys

**Post:**
- Those keys are ignored; `state_file()` and `phases_index_file()` from `paths.py` are always used (I-CONFIG-PATH-1)
- No regression in existing context-building behavior

---

## 7. Use Cases

### UC-14-1: LLM reads task definition via CLI

**Actor:** LLM (Coder Agent)
**Trigger:** Implement T-NNN pre-execution step
**Pre:** Phase 14 ACTIVE; T-1401 status TODO
**Steps:**
1. LLM runs `sdd show-task T-1401`
2. `show_task.py` reads `State_index.yaml` → determines `tasks.version = 14`
3. Reads `taskset_file(14)` → parses T-1401 row
4. Emits structured markdown: ID, Status, Inputs, Outputs, Invariants, Criterion
5. LLM uses output to determine read/write scope — never reads TaskSet file directly
**Post:** LLM knows exact inputs/outputs/invariants for T-1401; §R.2 satisfied

### UC-14-2: Tests run in full isolation via SDD_HOME

**Actor:** CI system / developer
**Trigger:** `SDD_HOME=/tmp/test_root pytest tests/ -q`
**Pre:** `SDD_HOME` env var set to a temp directory
**Steps:**
1. `paths.get_sdd_root()` resolves to `/tmp/test_root`
2. All `event_store_file()`, `state_file()`, etc. derive from that root
3. Tests using `tmp_path` call `paths.reset_sdd_root()` + `monkeypatch.setenv("SDD_HOME", ...)`
4. No file access touches `/root/project/.sdd/`
**Post:** Test suite passes without side-effecting project DuckDB or State_index (I-EXEC-ISOL-1)

### UC-14-3: LLM reads spec without direct filesystem access

**Actor:** LLM (Planner Agent)
**Trigger:** Draft Spec / Plan Phase / Decompose Phase command
**Pre:** Phase N spec exists in `specs_dir()` with exactly one file
**Steps:**
1. LLM runs `sdd show-spec --phase N`
2. `show_spec.py` calls `specs_dir()` → lists `Spec_vN_*.md` files
3. If exactly one found: reads and emits to stdout
4. LLM uses stdout content — never calls `Read` on `.sdd/specs/` directly
**Post:** §R.2 enforced; spec content available to LLM without direct file access

### UC-14-4: Non-editable install resolves DB path correctly

**Actor:** Production deployment / CI in installed-package mode
**Trigger:** Any `sdd` command in non-editable install
**Pre:** Package installed via `pip install sdd` (not `pip install -e .`)
**Steps:**
1. `sdd complete T-NNN` → `update_state.py` → `sdd_append()` with `db_path=None`
2. Body calls `event_store_file()` → `get_sdd_root()` → resolves from `SDD_HOME` or CWD
3. Path is CWD-relative, not `__file__`-relative → identical in editable and non-editable installs
**Post:** No path divergence between dev and production (Bug 1 fixed)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-1 Infra (db, audit, event_log) | this → BC-14-PATHS | path resolution |
| BC-3 Guards (scope, task, phase, norm) | this → BC-14-PATHS | path resolution |
| BC-4 Commands (7 files) | this → BC-14-PATHS | path resolution, remove SDD_DB_PATH/SDD_STATE_PATH |
| BC-5 Context (build_context) | this → BC-14-PATHS | close config backdoor |
| BC-8 CLI (cli.py + 3 new commands) | this → BC-14-PATHS | show-task, show-spec, show-plan |
| BC-Hooks (log_tool) | this → BC-14-PATHS | remove SDD_DB_PATH override |
| BC-14-PATHS | → stdlib only | I-PATH-2 |

### Frozen Interface Extensions (§0.15)

The following are **backward-compatible extensions** per §0.15(a):

| Module | Change | Compatibility |
|--------|--------|---------------|
| `infra/paths.py` | new frozen module — all functions new | N/A (new) |
| `infra/event_log.py` | `db_path: str = SDD_EVENTS_DB` → `db_path: str | None = None` | all callers passing `str` unaffected |
| `infra/audit.py` | `audit_log_path: str = _AUDIT_LOG_DEFAULT` → `str | None = None` | all callers passing `str` unaffected |

### `project_profile.yaml` — I-PATH-1 enforcement

```yaml
code_rules:
  forbidden_patterns:
    - pattern: '\.sdd[/\\]'
      applies_to: "src/sdd/**/*.py"
      exclude:
        - "src/sdd/infra/paths.py"
      severity: hard
      message: "I-PATH-1: hardcoded .sdd/ paths forbidden in src/sdd/ — use sdd.infra.paths"
```

`validate_invariants.py` already reads `code_rules.forbidden_patterns` — no script changes needed.

### CLAUDE.md changes (atomic with code — §K.9 CEP-1)

- **§R.1**: Update formal model: `LLM = f(CLI_Output, Task_Inputs)` where `CLI_Output` is
  a deterministic projection of State/Spec/TaskSet via `show-*` commands and `Task_Inputs`
  are source files listed in Task Inputs field. Old form `LLM = f(State, Spec, Task)` is
  superseded — the LLM never reads state/spec/task files directly after this phase.
- **§R.2**: Replace "LLM MUST read ONLY..." with CLI-only read model; enumerate
  `sdd show-state`, `sdd show-task T-NNN`, `sdd show-spec --phase N`, `sdd show-plan --phase N`
  as the ONLY authorized data sources for SDD artifacts; mark direct `.sdd/` reads FORBIDDEN.
  Remove all literal `.sdd/` path examples — replace with "resolved via paths.py".
- **§0.15**: Add `infra/paths.py` row to frozen interface table
- **§0.10**: Add `sdd show-task T-NNN`, `sdd show-spec --phase N`, `sdd show-plan --phase N` rows
- **§K.4**: Add SDD-11..SDD-19 invariants
- **§K.6 Read Order**: Update step 2 (Spec) to say `sdd show-spec --phase N` instead of
  direct file path; step 4 (TaskSet) to `sdd show-task T-NNN`
- Remove all mentions of `SDD_DB_PATH`, `SDD_STATE_PATH` as env vars (removed without
  fallback shim; users must migrate to `SDD_HOME`)

---

## 9. Verification

| # | Test / Check | Invariant(s) | Command |
|---|-------------|--------------|---------|
| 1 | `test_sdd_home_redirects_all_paths` | I-PATH-1, I-PATH-3 | `pytest tests/integration/test_sdd_home_isolation.py::test_sdd_home_redirects_all_paths -v` |
| 2 | `test_no_hardcoded_sdd_paths_in_src` | I-PATH-1 | `pytest tests/integration/test_sdd_home_isolation.py::test_no_hardcoded_sdd_paths_in_src -v` |
| 3 | `test_paths_module_no_sdd_imports` | I-PATH-2 | `pytest tests/integration/test_sdd_home_isolation.py::test_paths_module_no_sdd_imports -v` |
| 4 | Full runtime isolation | I-EXEC-ISOL-1 | `SDD_HOME=/tmp/sdd_test_root pytest tests/ -q` |
| 5 | Frozen interface signatures | I-KERNEL-EXT-1 | `pytest tests/regression/test_kernel_contract.py -v` |
| 6 | `sdd show-task T-NNN` determinism | I-CLI-READ-1, I-CLI-READ-2 | `sdd show-task T-1401 \| diff - <(sdd show-task T-1401)` |
| 7 | `sdd show-spec --phase 14` | I-FAIL-SPEC-1, I-CLI-FAILSAFE-1 | `sdd show-spec --phase 14` |
| 8 | `sdd show-plan --phase 14` | I-CLI-READ-1, I-CLI-FAILSAFE-1 | `sdd show-plan --phase 14` |
| 9 | AmbiguousSpec guard | I-SPEC-RESOLVE-1, I-SPEC-RESOLVE-2 | manually create two Spec_v14_*.md files → `sdd show-spec --phase 14` must exit 1 with JSON |
| 10 | `sdd check-scope read /abs/path/.sdd/specs/Spec_v14.md` | I-SDD-9, scope.py Path.resolve() | must be REJECTED (absolute path, resolve comparison) |
| 11 | I-PATH-1 structural check | I-PATH-1 | `sdd validate-invariants --check I-PATH-1 --scope full-src` |
| 12 | `show-task` schema conformance | I-CLI-SCHEMA-1, I-CLI-SCHEMA-2 | assert output contains `## Task:`, `### Inputs`, `### Outputs`, `### Invariants Covered`, `### Acceptance Criteria` in order |
| 13 | `reset_sdd_root` not imported outside tests | I-PATH-5 | `grep -r "reset_sdd_root" src/` must return empty |
| 14 | `SDD_DB_PATH` / `SDD_STATE_PATH` not referenced in src/ | I-PATH-1 (env variant) | `grep -r "SDD_DB_PATH\|SDD_STATE_PATH" src/` must return empty |
| 15 | Full test suite regression | all preserved invariants | `pytest tests/ -q` |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Migrating historical `.sdd/` entries in DuckDB event payloads | No action needed — I-EVENT-PATH-1 treats them as opaque |
| `sdd show-taskset --phase N` (full TaskSet view) | Phase 15+ if needed |
| `sdd show-phases` command | Phase 15+ |
| `specs_draft_dir()` write-access control (LLM can write drafts directly today) | Phase 15+ — out of scope until I-CLI-SSOT-1 is extended to write paths |
| Multi-repo / remote `SDD_HOME` (e.g. S3, NFS) | Out of SDD scope entirely |
| Removing `SDD_HOME` from hooks if Claude Code stops inheriting env | Phase 15+ if empirically needed |
| Auto-migration of `SDD_DB_PATH` / `SDD_STATE_PATH` env vars in user shell profiles | User responsibility |
