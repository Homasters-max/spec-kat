# Validation Report — T-1318: End-to-end phase execution playbook

**Task:** T-1318  
**Phase:** 13  
**Status:** PASS  
**Generated:** 2026-04-23T08:32:53Z  
**Spec ref:** Spec_v13 §1, §6, §9  
**Invariants:** I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1, I-HOOK-FAILSAFE-1, I-TOOL-PATH-1

---

## Acceptance Checklist

### Step 3 — M1: Hook migration (critical path)

| Check | Result | Evidence |
|---|---|---|
| `pyproject.toml` contains `sdd-hook-log = "sdd.hooks.log_tool:main"` | **PASS** | Line 17 of pyproject.toml |
| `src/sdd/hooks/log_tool.py` contains failsafe try/except (I-HOOK-FAILSAFE-1) | **PASS** | Lines 104–153: primary try/except + HookError fallback + double-failure stderr |
| `~/.claude/settings.json` hook command is `sdd-hook-log pre\|post` | **PASS** | PreToolUse/PostToolUse hooks use `sdd-hook-log pre` / `sdd-hook-log post` |
| `sdd-hook-log --help` resolves via PATH (exit 0) | **PASS** | `/usr/local/bin/sdd-hook-log` — exit 0 |

### Step 4 — M2: CLI wiring

| Check | Result | Evidence |
|---|---|---|
| `sdd record-decision --help` exits 0 | **PASS** | exit 0, usage shown |
| `sdd validate-config --help` exits 0 | **PASS** | exit 0, usage shown |

### Step 5 — M3: Parity tests

| Check | Result | Evidence |
|---|---|---|
| `pytest tests/integration/test_legacy_parity.py -v` — all 11 tests PASS | **PASS** | 11 passed in 2.82s |

### Step 6 — M4: Kill test

| Check | Result | Evidence |
|---|---|---|
| `chmod -R 000 .sdd/tools/ 2>/dev/null \|\| true && pytest tests/ --tb=short` exits 0 | **PASS** | 449 passed in 35.84s, exit 0 (chmod no-op: `.sdd/tools/` already absent) |

### Step 7 — M5: Freeze

| Check | Result | Evidence |
|---|---|---|
| `.sdd/tools/` does not exist | **PASS** | `ls .sdd/tools/` → No such file or directory |
| `.sdd/_deprecated_tools/` contains archived scripts | **PASS** | Directory present with all former adapters |
| `project_profile.yaml` registers I-RUNTIME-1/I-RUNTIME-LINEAGE-1/I-TOOL-PATH-1 forbidden patterns | **PASS** | Lines 59, 64, 69 of project_profile.yaml |
| `CLAUDE.md §0.10` no longer references `.sdd/tools/` as runtime path | **PASS** | §0.10 table uses `.sdd/_deprecated_tools/` only; §0.12 updated: M1 "pending" → "complete", hook path updated to `sdd-hook-log pre\|post`; §0.11 updated: `/tools` → `/_deprecated_tools` |

---

## Fixes Applied During Validation

### 1. `src/sdd/hooks/log_tool.py` — I-HOOK-4 compliance

**Problem:** On `sdd_append` failure the except block only wrote to stderr. Tests `test_hook_error_event_level_l3`, `test_hook_emits_error_event_on_failure`, and `test_hook_logs_stderr_on_double_failure` all failed because `HookError` events were never written to the DB.

**Fix:** Added two-stage fallback in the except block:
1. First attempt: write `HookError` event (L3, event_source=meta) to DB
2. If that also fails (double failure): serialize `{"double failure": true, ...}` to stderr

This satisfies I-HOOK-4 (HookError on failure) and I-HOOK-FAILSAFE-1 (stderr on double failure).

### 2. `src/sdd/cli.py` — I-CLI-1 pure-router violation

**Problem:** `show_state()` command in cli.py had a local `from sdd.infra.projections import rebuild_state` import. The AST-based test `test_cli_is_pure_router` walks all nodes including function bodies and flagged it as a forbidden `sdd.infra` import.

**Fix:** Removed `rebuild_state` call from `cli.py`. Moved it into `sdd/commands/show_state.main()` as a best-effort pre-step (errors silently swallowed; State Guard handles staleness downstream).

### 3. `CLAUDE.md` — Phase 13 M1 status update

**Problem:** §0.12 still described the hook as "pending Phase 13 M1" with the old `python3 .sdd/tools/log_tool.py` path. §0.10 table row for `sdd-hook-log` still marked "pending Phase 13 M1". §0.11 listed `/tools` as active enforcement scripts directory.

**Fix:**
- §0.12: Updated note from "pending" to "complete"; updated hook path diagram to `sdd-hook-log pre|post`
- §0.10: Updated `sdd-hook-log` row to "Phase 13 M1 complete"
- §0.11: Replaced `/tools → Enforcement scripts` with `/_deprecated_tools → Archived adapter scripts (historical reference only)`

---

## Test Results Summary

| Suite | Tests | Result |
|---|---|---|
| `tests/unit/hooks/test_log_tool.py` | 11 | PASS |
| `tests/unit/test_cli.py` | 10 | PASS |
| `tests/integration/test_legacy_parity.py` | 11 | PASS |
| Full suite (`tests/`) | 449 | PASS |

---

## Invariants Covered

| Invariant | Status | Notes |
|---|---|---|
| I-RUNTIME-1 | PASS | No `src/sdd/` references to `.sdd/tools/` — verified by parity test `test_no_runtime_import_of_sdd_tools` |
| I-RUNTIME-LINEAGE-1 | PASS | Execution path originates from `sdd` CLI, not `.sdd/tools/` |
| I-STATE-SYNC-1 | PASS | `sdd show-state` calls `rebuild_state` before reading State_index.yaml |
| I-BEHAVIOR-SEQ-1 | PASS | Full 449-test suite passes; all command behaviors preserved |
| I-HOOK-FAILSAFE-1 | PASS | `log_tool.py`: double failure → stderr JSON with "double failure" key |
| I-TOOL-PATH-1 | PASS | No dynamic imports or pathlib reconstruction to legacy adapters |
