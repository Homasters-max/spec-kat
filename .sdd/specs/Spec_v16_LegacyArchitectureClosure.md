# Spec_v16 — Phase 16: Legacy Architecture Closure

Status: ACTIVE
Baseline: Spec_v14_ControlPlaneMigration.md, Spec_v15_KernelUnification.md

---

## 0. Goal

Complete the removal of `.sdd/_deprecated_tools/` and close all remaining architectural
gaps that prevent `src/sdd` from being the sole runtime. Three categories of work:

1. **I-PATH-1 violations**: 4 hardcoded `.sdd/` strings remain in `src/sdd/cli.py` —
   replace with `paths.py` calls.
2. **Test infrastructure debt**: `tests/unit/test_adapters.py` and
   `tests/unit/hooks/test_log_tool_parity.py` test deprecated shim files, not `src/sdd`
   behaviour — rewrite as CLI contract tests before any file is deleted.
3. **Legacy removal**: verify no live dependencies, then delete 15 shims and 7 legacy
   files; resolve 3 critical components (`sdd_run`, `derive_state`, `init_state`) with
   explicit binary decisions; remove dead norms and docs references.

After this phase `.sdd/_deprecated_tools/` does not exist, `grep -r '\.sdd/' src/sdd/`
returns only `infra/paths.py`, and the full test suite passes without referencing any
deleted file.

---

## 1. Scope

### In-Scope

- **BC-1 Infra** (`cli.py`): fix 4 hardcoded `.sdd/` paths (I-PATH-1)
- **BC-TEST**: rewrite `test_adapters.py` and `test_log_tool_parity.py` as `src/sdd`
  contract tests; update `test_env_independence.py`, `test_task_output_invariant.py`,
  `test_legacy_parity.py` to remove deprecated-tool references
- **BC-DEP-AUDIT**: grep-gate — verify zero live usage of `sdd_db`, `sdd_event_log`
  outside `_deprecated_tools/` before any deletion
- **BC-SHIM-RM**: delete 15 shim files from `_deprecated_tools/`
- **BC-LEGACY-RESOLVE**: binary decision + implementation for 3 critical components:
  - `sdd_run.py` / `guard_runner.py` → restore `sdd run` CLI or delete with justification
  - `derive_state.py` → confirm `sdd sync-state --dry-run` covers it or keep as debug tool
  - `init_state.py` → fix event-sourcing violation or isolate as bootstrap carve-out
- **BC-LEGACY-RM**: delete 7 legacy files (`sdd_db.py`, `sdd_event_log.py`,
  `derive_state.py`, `guard_runner.py`, `sdd_run.py`, `record_decision.py`,
  `migrate_jsonl_to_duckdb.py`) after BC-LEGACY-RESOLVE
- **BC-LOGIC-VERIFY**: verify behavioural coverage (not just API) for 3 modules:
  `norm_catalog.py` → `domain/norms/catalog.py`, `taskset_parser.py` →
  `domain/tasks/parser.py`, `state_yaml.py` → `domain/state/yaml_state.py`;
  **delete all three after verification passes**
- **BC-CLEANUP-RM**: delete 5 files not covered by BC-SHIM-RM / BC-LEGACY-RM:
  `show_state.py` (not mentioned elsewhere), `init_state.py` (deprecated, Decision 3),
  `norm_catalog.py`, `state_yaml.py`, `taskset_parser.py` (after BC-LOGIC-VERIFY);
  these are required for M8 gate (`ls .sdd/_deprecated_tools/*.py | wc -l` → 0)
- **BC-DIR-RM**: delete `_deprecated_tools/` directory entirely
- **BC-DOCS**: fix 4 stale CLAUDE.md references; remove 5 dead norm exemptions from
  `norm_catalog.yaml`
- **BC-CLI-REG**: register missing commands in `cli.py` as decided in BC-LEGACY-RESOLVE

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### Dependency and Deletion Order (critical)

Deletion is safe only after this sequence holds:

```
M2: Tests rewritten       → no test imports from _deprecated_tools/
M3: Logic verified        → src/sdd behaviour matches deprecated behaviour
M4: Dep-audit grep = 0   → no live caller of sdd_db / sdd_event_log outside deprecated/
M5: Shims deleted         → 15 files gone
M5b: Cleanup deleted      → 5 uncategorised files deleted (BC-CLEANUP-RM)
M6: Legacy resolved       → sdd_run / derive_state / init_state decisions implemented
M7: Legacy infra deleted  → sdd_db, sdd_event_log, remaining legacy files gone
M8: Dir deleted           → _deprecated_tools/ removed (all 27 files gone)
```

No step may begin before the previous step's gate condition is met.

### BC-1: Fix `cli.py` I-PATH-1 violations

Four locations in `src/sdd/cli.py` use hardcoded `.sdd/` strings:

```python
# Line ~112 — validate_config handler default
# BEFORE
default=".sdd/config/project_profile.yaml"
# AFTER
default=str(config_file())

# Line ~123 — validate_config handler db_path
# BEFORE
db_path = Path(".sdd/state/sdd_events.duckdb")
# AFTER
db_path = event_store_file()

# Line ~221 — record_decision handler state read
# BEFORE
state = yaml.safe_load(Path(".sdd/runtime/State_index.yaml").read_text())
# AFTER
state = yaml.safe_load(state_file().read_text())

# Line ~224 — record_decision handler db_path
# BEFORE
db_path = Path(".sdd/state/sdd_events.duckdb")
# AFTER
db_path = event_store_file()
```

All four resolved via `from sdd.infra.paths import config_file, event_store_file, state_file`.

### BC-TEST: Rewrite deprecated-dependent tests

#### `tests/unit/test_adapters.py` → `tests/unit/test_cli_contracts.py`

Current: tests 15 deprecated shim files for pattern compliance.
Replacement: tests that `sdd` CLI commands exit with correct codes, emit correct
JSON stderr on error, and produce deterministic stdout. Covers the same behavioural
contracts without depending on deprecated files.

Key contracts to preserve:
- All write commands exit 0 on success
- All commands exit 1 on `SDDError` with JSON stderr matching I-CLI-API-1 schema
- `sdd-hook-log pre|post` exits 0 always (I-HOOK-FAILSAFE-1)

#### `tests/unit/hooks/test_log_tool_parity.py`

Remove AST checks that reference `_deprecated_tools/log_tool.py`. Retain any tests
that verify `src/sdd/hooks/log_tool.py` behaviour directly.

#### `tests/integration/test_env_independence.py:57`

```python
# BEFORE
["python3", ".sdd/_deprecated_tools/check_scope.py", "--help"]
# AFTER
["sdd", "check-scope", "--help"]
```

#### `tests/integration/test_task_output_invariant.py`

Remove `DEPRECATED_PREFIX` exclusion logic — no longer needed after directory deleted.

#### `tests/integration/test_legacy_parity.py`

Remove `# Test 9: no .sdd/_deprecated_tools in sys.modules` — trivially true after deletion;
simplify or remove that assertion.

### BC-DEP-AUDIT: Dependency gate

Before any file deletion, this grep MUST return zero results:

```bash
grep -rn --include="*.py" "sdd_db\|sdd_event_log" src/ tests/ \
    --exclude-dir=_deprecated_tools \
    | grep -v "__pycache__"
```

If result ≠ 0: those callers are live dependencies, not legacy — must be migrated first.

Also check for compute_spec_hash usage:

```bash
grep -rn "compute_spec_hash" src/ tests/
```

Must return 0 before `sdd_event_log.py` deletion.

Similarly for shim subprocess contracts (note: exclude test data strings — match only import/subprocess context):

```bash
grep -rEn "(import|subprocess).*\.(query_events|metrics_report|report_error|sync_state|update_state|validate_invariants)\.py" \
    src/ tests/ --include="*.py" --exclude-dir=_deprecated_tools
```

Must return 0 before shim deletion.

### BC-SHIM-RM: 15 shims to delete

**Pattern B (import shims):**
`build_context.py`, `check_scope.py`, `norm_guard.py`, `phase_guard.py`, `task_guard.py`,
`log_tool.py`, `log_bash.py`, `record_metric.py`, `senar_audit.py`

**Pattern A (subprocess shims):**
`query_events.py`, `metrics_report.py`, `report_error.py`, `sync_state.py`,
`update_state.py`, `validate_invariants.py`

### BC-LEGACY-RESOLVE: Binary decisions

#### Decision 1: `sdd_run.py` + `guard_runner.py`

**Two layers — different timelines:**

**Layer A — deprecated adapters** (deleted in M7 this phase):
- `.sdd/_deprecated_tools/sdd_run.py` — subprocess adapter; deleted in M7 ✓
- `.sdd/_deprecated_tools/guard_runner.py` — logic superseded by `domain/guards/pipeline.py`; deleted in M7 ✓

**Layer B — `src/sdd/commands/sdd_run.py`** (deferred to Phase 15 Step 4):
- `CommandRunner` class is the current Write Kernel; removing it requires `execute_command`
  from Phase 15 `registry.py` to be in place first
- `sdd run` is not registered in `cli.py` and has no callers — `main()` is dead code but
  safe to leave until Phase 15 wires all commands through `execute_and_project`
- `run_guard_pipeline` function stays in `sdd_run.py`; Phase 15 `registry.py` imports it

**Spec decision**: Delete deprecated adapters (Layer A) in M7. Defer `CommandRunner` class
removal from `src/sdd/commands/sdd_run.py` to **Phase 15 Step 4** — after `execute_command`
absorbs all callers. `guard_runner.py` deleted (its logic is in `domain/guards/pipeline.py`).

Document in CLAUDE.md §0.10: "`sdd run` — unregistered; `CommandRunner` removal deferred
to Phase 15 Step 4; use `sdd complete` / `sdd validate`".

#### Decision 2: `derive_state.py` — `--verify-only` mode

`sdd sync-state --dry-run` exists. Verify it covers `derive_state --verify-only`:
- `--dry-run`: rebuilds state in memory, prints diff, writes nothing
- `--verify-only`: same behaviour

If coverage confirmed by test: delete `derive_state.py`.
If `--dry-run` does not print diff: add `--verify-only` alias to `sdd sync-state` first,
then delete `derive_state.py`.

Either way the file is deleted by end of Phase 16. The decision is resolved in M6 task.

#### Decision 3: `init_state.py` — event-sourcing violation

`init_state.py` generates `State_index.yaml` by reading `TaskSet_vN.md` directly,
bypassing EventLog. This violates I-1 (`state = reduce(events)`).

**Resolution**: After Phase 15, `sdd activate-phase N --tasks T` emits
`PhaseStartedEvent + TaskSetDefinedEvent` and immediately calls `project_all(STATE_ONLY,
STRICT)` which writes `State_index.yaml` from EventLog. This is the correct event-sourced
bootstrap path.

`init_state.py` (and `src/sdd/domain/state/init_state.py`) are deprecated as bootstrap
mechanisms. The only permitted bootstrap after Phase 16 is:

```bash
sdd activate-phase N --tasks T   # emits events → projects YAML
```

`src/sdd/domain/state/init_state.py` is retained as a module (it may still be called by
tests or edge cases) but its direct YAML-write path is wrapped with a deprecation warning.
`_deprecated_tools/init_state.py` is deleted.

### BC-LOGIC-VERIFY: Behavioural coverage check

Three modules require behavioural verification before deprecated originals are deleted:

#### `norm_catalog.py` → `domain/norms/catalog.py`

Check:
- `gate_type`, `triggers_on`, `required_before`, `senar_category`, `exception` fields
  present in `Norm` dataclass
- stdlib YAML fallback path (when `yaml` not installed) tested
- `get_norms_for_actor(actor)` returns correct subset

#### `taskset_parser.py` → `domain/tasks/parser.py`

Check **both format branches**:
- Free-form format: `T-NNN: <title>\nStatus: TODO\nInputs: ...`
- Table format: `| T-NNN | ... |`

Check `phase_from_task(task_id)` → `int` is implemented and tested.

#### `state_yaml.py` → `domain/state/yaml_state.py`

Check:
- `atomic_write(path, content)` — writes to `.tmp` then `rename()`, never partial
- `parse_field(text, key)` — returns `None` on missing key (not raises)
- `update_status_field(text, key, value)` — replaces in-place without corrupting YAML

#### `sdd_event_log.sdd_latest_seq()` → `sdd.infra.db`

Explicit check required before deleting `sdd_event_log.py`:
- Verify `sdd.infra.db` exposes a `sdd_latest_seq()` equivalent (or inline equivalent in callers)
- Verify it is tested: `grep -rn "sdd_latest_seq\|latest_seq" tests/` → ≥ 1 match

If coverage missing: add function and test before deletion.

If any check fails: add the missing behaviour to `src/sdd` before deletion.

### BC-DOCS: CLAUDE.md and norm_catalog.yaml cleanup

#### CLAUDE.md — 4 stale lines

| Location | Current | Fix |
|---|---|---|
| Header line 4 | `**Tools:** .sdd/tools/*.py` | `**Tools:** \`sdd\` CLI (src/sdd/ — pip install -e .)` |
| §0.7 line ~105 | `Enforcement tools: .sdd/tools/*.py` | `Enforcement tools: \`sdd\` CLI commands (see §0.10)` |
| §0.7 line ~107 | `call \`report_error.py\`` | `run \`sdd report-error\`` |
| §0.8 SEM-6 | `call .sdd/tools/report_error.py` | `run \`sdd report-error --type T --message M\`` |

#### `norm_catalog.yaml` — 5 dead exemptions

Remove all `scope_exempt` entries that reference `.sdd/_deprecated_tools/`. These
exemptions become dead after directory deletion and silently mislead future readers.

### BC-CLI-REG: CLI registration audit

After BC-LEGACY-RESOLVE Decision 1 (Option B):
- `activate_plan.py` — `sdd activate-plan` not in `cli.py`; document as internal-only
  in CLAUDE.md §0.10 (required to satisfy I-CLI-REG-1 before Phase 16 COMPLETE)
- `sdd run` — deleted; add removal note to CLAUDE.md §0.10

---

## 3. Domain Events

No new domain events. This phase is structural — all changes are file deletion,
path correction, and test rewriting. The EventLog schema is unchanged.

---

## 4. Types & Interfaces

No new types. The following are **removed** (not in `src/sdd`, deprecated only):

| Removed | Replacement in src/sdd |
|---|---|
| `sdd_db.open_sdd_connection()` | `sdd.infra.db.open_sdd_connection()` |
| `sdd_event_log.sdd_append()` | `sdd.infra.event_log.sdd_append()` |
| `sdd_event_log.sdd_replay()` | `sdd.infra.event_log.sdd_replay()` |
| `sdd_event_log.classify_event_level()` | `sdd.core.events.classify_event_level()` |
| `sdd_event_log.compute_spec_hash()` | not needed; delete |
| `sdd_event_log.sdd_latest_seq()` | `sdd.infra.db` — verify coverage |
| `CommandRunner` class in `sdd_run.py` | `registry.execute_command()` (Phase 15) |
| `guard_runner.run_guards()` | `sdd.domain.guards.pipeline` |

`sdd_run.run_guard_pipeline` (function, not class) is **retained** as it is imported by
`registry.py`. CommandRunner class removal is deferred to Phase 15 Step 4; this phase
only removes the deprecated adapter `_deprecated_tools/sdd_run.py`.

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-DEPRECATED-RM-1 | `.sdd/_deprecated_tools/` directory MUST NOT exist after Phase 16 | 16 |
| I-DEPRECATED-RM-2 | No test file may import from or subprocess-call `_deprecated_tools/` | 16 |
| I-DEP-AUDIT-1 | `grep -rn "sdd_db\|sdd_event_log" src/ tests/` MUST return 0 before legacy infra deletion | 16 |
| I-SHIM-CONTRACT-1 | All behavioural contracts covered by deleted shims MUST have equivalent tests against `sdd` CLI before shim deletion | 16 |
| I-LOGIC-COVER-1 | Both taskset format branches (free-form + table) MUST have passing tests in `domain/tasks/parser.py` | 16 |
| I-LOGIC-COVER-2 | `atomic_write` MUST be tested with a simulated mid-write crash via monkeypatch of `Path.rename` raising `OSError`; test asserts `.tmp` file is left behind and original file is intact | 16 |
| I-LOGIC-COVER-3 | `norm_catalog` stdlib YAML fallback MUST be tested | 16 |
| I-CLI-REG-1 | Every `src/sdd/commands/*.py` module that defines a user-facing `main()` MUST be registered in `cli.py` or explicitly documented as internal-only in CLAUDE.md §0.10; `activate_plan.py` is pre-declared internal-only in BC-DOCS | 16 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-PATH-1 | No literal `.sdd/` strings in `src/sdd/**/*.py` except `infra/paths.py` |
| I-PATH-2 | `paths.py` imports ONLY stdlib |
| I-EXEC-ISOL-1 | Tests use `tmp_path`-isolated DuckDB |
| I-FAIL-1 | SDDError → exit 1 + JSON stderr |
| I-CLI-API-1 | JSON error fields frozen |
| I-1 | All state = reduce(events) |
| I-HANDLER-PURE-1 | `handle()` returns events only |

---

## 6. Pre/Post Conditions

### Deletion gate (pre-condition for M5, M7, M8)

**Pre (M5 — shim deletion):**
- `pytest tests/ -q` green with rewritten tests (M2 done)
- BC-LOGIC-VERIFY all checks pass (M3 done)
- `grep -rn "sdd_db\|sdd_event_log" src/ tests/` → 0 (M4 done)
- `grep -rn "query_events\.py\|report_error\.py" src/ tests/` → 0 (M4 done)

**Pre (M7 — legacy infra deletion):**
- All M5 conditions hold
- BC-LEGACY-RESOLVE decisions implemented (M6 done)
- `sdd sync-state --dry-run` verified to cover `derive_state --verify-only` (M6 done)

**Pre (M8 — directory deletion):**
- `ls .sdd/_deprecated_tools/*.py | wc -l` → 0

**Post (Phase 16 complete):**
- `grep -r '\.sdd/' src/sdd/ | grep -v 'infra/paths.py'` → 0
- `ls .sdd/_deprecated_tools/` → directory does not exist
- `pytest tests/ -q` → all pass
- `sdd validate-invariants --check I-PATH-1 --scope full-src` → PASS

---

## 7. Use Cases

### UC-16-1: Full test suite passes after shim deletion

**Actor:** CI system
**Trigger:** `pytest tests/ -q` after M5
**Pre:** M2 (tests rewritten), M3 (logic verified), M4 (dep audit clean)
**Steps:**
1. `test_cli_contracts.py` tests `sdd complete`, `sdd validate`, etc. via subprocess — no deprecated file paths
2. `test_log_tool_parity.py` tests `src/sdd/hooks/log_tool.py` directly
3. No test imports `_deprecated_tools/`
**Post:** Green suite; I-DEPRECATED-RM-2 satisfied

### UC-16-2: SDD_HOME isolation still works after deletion

**Actor:** Developer running isolated test suite
**Trigger:** `SDD_HOME=/tmp/sdd_test pytest tests/ -q`
**Pre:** All deprecated files deleted; `src/sdd/infra/paths.py` is sole path resolver
**Steps:**
1. `paths.get_sdd_root()` resolves to `/tmp/sdd_test`
2. All `event_store_file()`, `state_file()` etc. derive from that root
3. No test touches `/root/project/.sdd/`
**Post:** I-EXEC-ISOL-1 satisfied; no side-effects on project DuckDB

### UC-16-3: I-PATH-1 grep check passes in CI

**Actor:** CI system
**Trigger:** `sdd validate-invariants --check I-PATH-1 --scope full-src`
**Pre:** M1 complete (cli.py paths fixed)
**Steps:**
1. `validate_invariants.py` greps `src/sdd/**/*.py` for `\.sdd[/\\]`
2. Only match: `infra/paths.py` (excluded by config)
3. Exit 0
**Post:** I-PATH-1 PASS

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-1 Infra (`cli.py`) | this → BC-14-PATHS | fix 4 hardcodes |
| BC-TEST | this → CLI commands | rewritten tests call `sdd` CLI via subprocess |
| BC-LEGACY-RESOLVE | this → Phase 15 registry | deprecated adapters deleted in M7; `CommandRunner` class removal deferred to Phase 15 Step 4 |
| BC-DOCS | this → CLAUDE.md, norm_catalog.yaml | cleanup |

### Execution order: Phase 16 runs before Phase 15

Phase 16 is a pure cleanup phase (zero behavioural changes). Phase 15 (Kernel Unification)
executes after Phase 16 on the cleaned codebase.

**What Phase 16 does NOT touch in `src/sdd/`**: `CommandRunner` class in
`src/sdd/commands/sdd_run.py` remains intact. It is still the active Write Kernel until
Phase 15 `execute_command` absorbs its logic (Step 2 SWITCH).

**Phase 15 dependency**: `CommandRunner` class removal (`I-SDDRUN-DEAD-1`) requires
Phase 15 `registry.py` and full SWITCH wiring to be complete first. This is why it is
assigned to Phase 15 Step 4 — not Phase 16. See §10 Out of Scope.

All other milestones (M1–M5, M7–M10) have no dependency on Phase 15 and are fully
independent.

### `project_profile.yaml` — forbidden pattern already in place

```yaml
code_rules:
  forbidden_patterns:
    - pattern: '\.sdd[/\\]'
      applies_to: "src/sdd/**/*.py"
      exclude:
        - "src/sdd/infra/paths.py"
      severity: hard
      message: "I-PATH-1: hardcoded .sdd/ paths forbidden — use sdd.infra.paths"
```

This pattern was added in Phase 14. M1 fixes the 4 violations so the check passes.

---

## 9. Verification

| # | Test / Check | Invariant(s) | Command |
|---|---|---|---|
| 1 | I-PATH-1 grep passes | I-PATH-1 | `sdd validate-invariants --check I-PATH-1 --scope full-src` |
| 2 | No .sdd/ hardcodes in cli.py | I-PATH-1 | `grep -n '\.sdd/' src/sdd/cli.py` → 0 lines |
| 3 | `test_cli_contracts.py` all pass | I-SHIM-CONTRACT-1 | `pytest tests/unit/test_cli_contracts.py -v` |
| 4 | dep-audit grep = 0 | I-DEP-AUDIT-1 | `grep -rn "sdd_db\|sdd_event_log" src/ tests/` |
| 5 | taskset parser — both format branches | I-LOGIC-COVER-1 | `pytest tests/unit/domain/test_taskset_parser.py -v` |
| 6 | atomic_write crash simulation | I-LOGIC-COVER-2 | `pytest tests/unit/domain/test_state_yaml.py::test_atomic_write_crash -v` |
| 7 | norm_catalog stdlib YAML fallback | I-LOGIC-COVER-3 | `pytest tests/unit/domain/test_norm_catalog.py::test_stdlib_yaml_fallback -v` |
| 8 | `_deprecated_tools/` does not exist | I-DEPRECATED-RM-1 | `test ! -d .sdd/_deprecated_tools && echo PASS` |
| 9 | No test references deprecated dir | I-DEPRECATED-RM-2 | `grep -rn "_deprecated_tools" tests/` → 0 |
| 10 | CommandRunner absent from src/ | I-SDDRUN-DEAD-1 | `grep -rn "CommandRunner" src/sdd/` → 0 (after Phase 15) |
| 11 | CLI registration audit | I-CLI-REG-1 | `sdd validate-invariants --check I-CLI-REG-1 --scope full-src`; internal-only exceptions (`activate_plan.py`) MUST be listed in CLAUDE.md §0.10 before check runs |
| 12 | SDD_HOME isolation | I-EXEC-ISOL-1 | `SDD_HOME=/tmp/sdd_test_16 pytest tests/ -q` |
| 13 | sync-state covers derive_state --verify-only | I-INIT-STATE-1 | `sdd sync-state --dry-run` produces diff output |
| 14 | Full test suite regression | all preserved | `pytest tests/ -q` |
| 15 | CLAUDE.md — no .sdd/tools references | SDD-11 | `grep -c '\.sdd/tools' CLAUDE.md` → 0 |
| 16 | norm_catalog — no _deprecated_tools exemptions | — | `grep -c '_deprecated_tools' .sdd/norms/norm_catalog.yaml` → 0 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `src/sdd/domain/state/init_state.py` full removal | Phase 17+ (retained with deprecation warning) |
| `EMERGENCY` RebuildMode removal | Phase 17+ |
| `CommandRunner` class removal from `src/sdd/commands/sdd_run.py` | **Phase 15 Step 4** — requires `execute_command` in `registry.py` + full SWITCH wiring; I-SDDRUN-DEAD-1 assigned there |
| Removing `run_guard_pipeline` from `sdd_run.py` | Phase 17 (after Phase 15 inlines it into `execute_command`) |
| I-INIT-STATE-1 (`sdd activate-phase N --tasks T` as sole bootstrap) | **Phase 15** — `--tasks` flag added in Phase 15 BC-4; UC-16-3 (bootstrap use case) deferred to Phase 15 |
| `sdd show-taskset --phase N` command | Phase 17+ |
| `sdd show-phases` command | Phase 17+ |
| Phase 11 / Phase 12 (PLANNED, skipped) | Separate decision by human |
| `activate_plan.py` CLI wiring | Phase 17 if needed; must be documented as internal-only in CLAUDE.md §0.10 in Phase 16 (BC-DOCS) to satisfy I-CLI-REG-1 |
| Auto-generating CLAUDE.md command table from REGISTRY | Phase 17+ |

---

## 11. Implementation Order

Gate conditions enforce safe deletion sequence:

```
M1  Fix cli.py I-PATH-1 (4 lines)              → pytest green; I-PATH-1 check passes
    Gate: grep -n '\.sdd/' src/sdd/cli.py → 0

M2  Rewrite tests                               → no test depends on _deprecated_tools/
    Gate: grep -rn "_deprecated_tools" tests/ → 0
          pytest tests/ -q → green

M3  Verify logic coverage                       → both parsers, atomic_write, norm fallback
    Gate: tests #5, #6, #7 pass

M4  Dep-audit grep gate                         → live usage check
    Gate: grep -rEn "sdd_db|sdd_event_log" src/ tests/ --include="*.py" \
                --exclude-dir=_deprecated_tools → 0
          grep -rn "compute_spec_hash" src/ tests/ → 0
          grep -rEn "(import|subprocess).*\.(report_error|sync_state)\.py" \
                src/ tests/ --include="*.py" --exclude-dir=_deprecated_tools → 0

M5  Delete 15 shims                             → _deprecated_tools/ shrinks to ~12 files
    Gate: M2 + M3 + M4 complete

M5b Delete 5 uncategorised files (BC-CLEANUP-RM) → show_state.py, init_state.py (deprecated),
      norm_catalog.py, state_yaml.py, taskset_parser.py
    Gate: BC-LOGIC-VERIFY checks pass (M3); pytest tests/ -q → green

M6  Resolve critical legacy                     → decisions implemented
      sdd_run (Layer A): _deprecated_tools/sdd_run.py deleted in M7 (no action here)
      sdd_run (Layer B): CommandRunner stays in src/sdd/ — deferred to Phase 15 Step 4
      derive_state: sdd sync-state rewrites YAML from EventLog; --verify-only is debug-only
                    and not a production contract → file deleted without replacement;
                    loss documented in CLAUDE.md §0.10
      init_state: _deprecated_tools/init_state.py deleted; src/sdd/domain/state/init_state.py
                  retained with deprecation warning (full removal Phase 17+)
    Gate: pytest tests/ -q → green after each deletion

M7  Delete legacy infra                         → sdd_db, sdd_event_log, remaining legacy gone
    Gate: M6 complete; dep-audit grep still 0

M8  Delete _deprecated_tools/ directory         → directory removed
    Gate: ls .sdd/_deprecated_tools/*.py → no files

M9  CLAUDE.md + norm_catalog.yaml cleanup       → docs consistent with reality
    Gate: checks #15, #16 pass

M10 CLI registration audit                      → all commands documented or registered
    Gate: check #11 passes
```

Each milestone is one or more tasks in TaskSet_v16. Gate condition is the
acceptance criterion for that task.
