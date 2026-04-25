# Spec_v13 — Phase 13: Runtime Stabilization

Status: Draft
Baseline: Spec_v10_KernelHardening.md, Spec_v12_SelfHosted.md

---

## 0. Goal

Eliminate `.sdd/tools/` as a runtime dependency. After Phase 13, `src/sdd/` is the **sole runtime**; `.sdd/` contains only data and archived artifacts. This closes the dual-runtime gap introduced during the Phase 1–9 migration and satisfies the new system invariant I-RUNTIME-1.

---

## 1. Scope

### In-Scope

- **STEP 1**: Fix hook dependency — replace hardcoded `.sdd/tools/log_tool.py` path with `sdd-hook-log` console_scripts entry point; add failsafe fallback to stderr JSON (I-HOOK-FAILSAFE-1)
- **STEP 2**: Wire missing CLI commands (`record-decision`, `validate-config`); verify `validate-invariants` and `show-state` flag/projection parity
- **STEP 3**: Write behavior parity test suite (`tests/integration/test_legacy_parity.py`) — 11 tests (4 structural + 4 behavioral + 3 invariant)
- **STEP 4**: Kill test — block `.sdd/tools/` at filesystem level AND verify `sys.modules` and resolved path (I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1)
- **STEP 5**: Freeze — archive `.sdd/tools/` to `.sdd/_deprecated_tools`, register all new invariants in `project_profile.yaml`, update CLAUDE.md §0.10

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-13: Runtime Migration Overlay

BC-13 is a **migration overlay**, not a new domain BC. No new domain logic is introduced. This phase modifies existing surfaces only:

```
pyproject.toml             # add sdd-hook-log console_scripts entry point
~/.claude/settings.json    # update PreToolUse/PostToolUse hook command
src/sdd/cli.py             # wire record-decision, validate-config commands
src/sdd/hooks/log_tool.py  # add failsafe stderr fallback (I-HOOK-FAILSAFE-1)
tests/integration/
  test_legacy_parity.py    # new — 11 behavior parity tests
.sdd/config/
  project_profile.yaml     # register new invariants + forbidden patterns
.sdd/_deprecated_tools/    # renamed from .sdd/tools/ (archived)
```

### Dependencies

```text
BC-13 → BC-7 (Telemetry/Hooks)    : sdd-hook-log entry point replaces log_tool.py adapter
BC-13 → BC-4 (Commands)           : record-decision, validate-config wired to existing handlers
BC-13 → BC-3 (Guards)             : kill test validates in-process guard parity
BC-13 → BC-6 (Projections)        : projection parity test validates derive_state.py equivalence
```

---

## 3. Domain Events

No new domain events. Phase 13 produces the following existing events via the new execution path:

### Event Catalog

| Event | Emitter | Description |
|-------|---------|-------------|
| `ToolUseStarted` | `sdd-hook-log pre` | Hook fires via console_scripts entry point (not .sdd/tools) |
| `ToolUseCompleted` | `sdd-hook-log post` | Hook fires via console_scripts entry point |
| `TaskImplemented` | `sdd complete T-NNN` | Emitted through in-process guards (not subprocess) |
| `TaskValidated` | `sdd validate T-NNN` | Emitted through in-process guards |

---

## 4. Types & Interfaces

### New Entry Point

```toml
# pyproject.toml — [project.scripts]
sdd-hook-log = "sdd.hooks.log_tool:main"
```

### Hook Failsafe Contract (I-HOOK-FAILSAFE-1)

`src/sdd/hooks/log_tool.py:main()` MUST implement a fallback:

```python
try:
    # normal: append ToolUseStarted to DuckDB
    sdd_append(event_type, payload, db_path, level)
except Exception as exc:
    # fallback: structured JSON to stderr — never swallow silently
    import json, sys
    json.dump({"event_type": event_type, "payload": payload,
               "hook_error": str(exc)}, sys.stderr)
    sys.stderr.write("\n")
    # exit 0 — hook must never block tool execution (NORM-AUDIT-BASH)
```

### New CLI Commands (wire existing handlers)

```python
# src/sdd/cli.py additions

@main.command("record-decision")
@click.option("--decision-id", required=True, help="Format: D-NNN")
@click.option("--title", required=True)
@click.option("--summary", required=True)
@click.option("--phase", type=int)
@click.option("--task")
def record_decision_cmd(decision_id, title, summary, phase, task): ...

@main.command("validate-config")
@click.option("--phase", type=int, required=True)
def validate_config_cmd(phase): ...
```

Handlers already exist: `src/sdd/commands/record_decision.py`, `src/sdd/commands/validate_config.py`.

### Existing Code Reused

| Need | Module | Path |
|------|--------|------|
| Hook logging | `sdd.hooks.log_tool.main` | `src/sdd/hooks/log_tool.py` |
| Record decision | `RecordDecisionHandler` | `src/sdd/commands/record_decision.py` |
| Validate config | `ValidateConfigHandler` | `src/sdd/commands/validate_config.py` |
| Event level | `classify_event_level` | `src/sdd/core/events.py` |
| Projections | `build_projection` | `src/sdd/infra/projections.py` |

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-RUNTIME-1 | All executable logic must reside in `src/sdd/`. `.sdd/` contains only data and archived artifacts. No code in `.sdd/` may be executed at runtime. | 13 |
| I-RUNTIME-LINEAGE-1 | Every executed command MUST originate from the `src/sdd/` entrypoint chain. No execution path may originate from `.sdd/tools/` or legacy adapters. | 13 |
| I-STATE-SYNC-1 | Any command that mutates the EventLog MUST trigger a state rebuild within the same execution boundary (eventually immediate or atomic batch commit). `State_index.yaml` MUST reflect the mutation before the process exits. | 13 |
| I-BEHAVIOR-SEQ-1 | For identical input trace, the sequence of EventLog entries (by event_type and position) MUST be identical across old and new execution paths. Event order is part of the contract. | 13 |
| I-HOOK-FAILSAFE-1 | If `sdd-hook-log` fails to write to DuckDB, it MUST emit structured JSON to stderr and exit 0. Silent failure is forbidden. | 13 |
| I-TOOL-PATH-1 | The resolved filesystem path of any executed module at runtime MUST NOT contain `.sdd/tools`. Dynamic imports, `importlib`, and `pathlib` reconstruction are covered by this invariant. | 13 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-HOOK-WIRE-1 | Hook invocation path must not depend on cwd or PYTHONPATH |
| I-LEGACY-0a | No `sys.path` mutation toward `.sdd/` in `src/sdd/**/*.py` |
| I-LEGACY-0b | No `subprocess` calls to `.sdd/tools/` in `src/sdd/**/*.py` |
| I-ENTRY-1 | No `__main__` blocks in `src/sdd/**/*.py` except `cli.py` and `hooks/*.py` |
| I-EXEC-ISOL-1 | Tests MUST use `tmp_path`-isolated DuckDB; project `sdd_events.duckdb` never touched |
| I-CLI-API-1 | JSON error fields `error_type`, `message`, `exit_code` are frozen |

---

## 6. Pre/Post Conditions

### STEP 1: Hook Migration

**Pre:**
- `pyproject.toml` has `sdd` console_scripts entry point (exists)
- `src/sdd/hooks/log_tool.py:main()` is implemented (exists)

**Post:**
- `sdd-hook-log` resolves via venv PATH regardless of cwd or PYTHONPATH (I-HOOK-WIRE-1)
- `~/.claude/settings.json` uses `sdd-hook-log pre/post` (not `.sdd/tools/log_tool.py`)
- `ToolUseStarted` events continue to appear in EventLog
- Hook failure emits JSON to stderr and exits 0 — never silently drops event (I-HOOK-FAILSAFE-1)

### STEP 2: CLI Wiring

**Pre:**
- `src/sdd/commands/record_decision.py` and `validate_config.py` are implemented
- `sdd validate-invariants --help` exists

**Post:**
- `sdd record-decision --help` works
- `sdd validate-config --help` works
- `sdd validate-invariants` exposes `--phase`, `--task`, `--check` flags (parity with legacy)
- `sdd show-state` output is consistent with `infra/projections.py` projection (not stale cache)

### STEP 3: Parity Tests

**Pre:**
- `tests/conftest.py` provides `tmp_path` isolation fixtures
- Both old and new execution paths are accessible

**Post:**
- `tests/integration/test_legacy_parity.py` contains 11 tests, all PASS
- Tests cover: DB schema, event append, taskset parse, state yaml, event order (SEQ), guard rejection, state sync, sys.modules, projection equivalence, CLI flag parity, projection consistency

### STEP 4: Kill Test

**Pre:**
- STEP 1–3 complete
- `.sdd/tools/` still exists (not yet archived)

**Post:**
- With `.sdd/tools/` blocked (`chmod 000`), full test suite passes (filesystem layer)
- `test_no_runtime_import_of_sdd_tools` passes — no `.sdd.tools` in `sys.modules` (module cache layer)
- `grep -r '\.sdd[/\\]tools' src/ tests/` returns no matches (static layer)
- Hook still fires: `sdd query-events --event ToolUseStarted --limit 1` shows recent event

### STEP 5: Freeze

**Pre:**
- Kill test PASSED (all three layers: filesystem, sys.modules, grep)
- All STEP 1–4 complete

**Post:**
- `.sdd/tools/` renamed to `.sdd/_deprecated_tools/` (or removed via git)
- `project_profile.yaml` registers: I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1 forbidden patterns
- CLAUDE.md §0.10 updated: "deprecated adapters" language removed, archive status noted
- `sdd show-state` and full test suite pass without `.sdd/tools/`

---

## 7. Use Cases

### UC-13-1: Hook Fires Without .sdd/tools

**Actor:** Claude Code hook system  
**Trigger:** Any tool call (PreToolUse/PostToolUse)  
**Pre:** `sdd-hook-log` installed via `pip install -e .`  
**Steps:**
1. Claude Code fires PreToolUse hook
2. Hook command `sdd-hook-log pre` resolves via venv PATH
3. `sdd.hooks.log_tool.main()` executes
4. `ToolUseStarted` event appended to DuckDB
**Post:** Event visible via `sdd query-events --event ToolUseStarted --limit 1`

### UC-13-2: Hook Fails Gracefully (I-HOOK-FAILSAFE-1)

**Actor:** Claude Code hook system  
**Trigger:** DuckDB unavailable or write failure  
**Pre:** `sdd-hook-log` installed; DuckDB file locked or missing  
**Steps:**
1. `sdd.hooks.log_tool.main()` catches exception from `sdd_append()`
2. Structured JSON written to stderr: `{"event_type": ..., "payload": ..., "hook_error": ...}`
3. Exits with code 0 — tool execution is NOT blocked
**Post:** No silent failure; stderr contains loggable record; tool proceeds normally

### UC-13-3: Guard Rejects Already-Done Task (Behavior Parity)

**Actor:** LLM via `sdd complete T-NNN`  
**Trigger:** Task T-NNN already has Status=DONE in TaskSet  
**Pre:** State consistent, task marked DONE  
**Steps:**
1. `sdd complete T-NNN` invoked
2. In-process guard pipeline checks task status
3. Guard rejects: task already DONE
4. CLI exits with code 1, JSON error to stderr
**Post:** No duplicate `TaskImplemented` event; error JSON matches I-CLI-API-1 schema

### UC-13-4: State Always Synced After Command (I-STATE-SYNC-1)

**Actor:** LLM via `sdd complete T-NNN`  
**Trigger:** Task T-NNN has Status=TODO  
**Pre:** State consistent, task TODO  
**Steps:**
1. `sdd complete T-NNN` executes successfully
2. `TaskImplemented` event appended to EventLog
3. State rebuild triggered within same execution boundary
4. `State_index.yaml` updated: `done_ids` includes T-NNN, `tasks.completed` incremented
**Post:** Reading `State_index.yaml` after process exit shows mutation reflected

### UC-13-5: Event Order Determinism (I-BEHAVIOR-SEQ-1)

**Actor:** Test harness  
**Trigger:** `test_event_order_determinism` with controlled input trace  
**Pre:** Isolated DuckDB (tmp_path); known task sequence  
**Steps:**
1. Execute `sdd complete T-001` → capture EventLog sequence
2. Reset to same initial state
3. Execute `sdd complete T-001` again
4. Compare event sequences by (event_type, position)
**Post:** Both runs produce identical event sequences — no reordering

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-7 Telemetry | this → BC-7 | `sdd-hook-log` delegates to `sdd.hooks.log_tool.main` — same EventLog |
| BC-4 Commands | this → BC-4 | `record-decision`, `validate-config` wire to existing handlers |
| BC-3 Guards | this ← BC-3 | Kill test validates in-process guard pipeline behavior |
| BC-6 Projections | this ← BC-6 | `test_projection_equivalence` validates `infra/projections.py` vs `derive_state.py` |

### No Reducer Extensions

Phase 13 introduces no new event handlers in the reducer. All events are existing types processed by existing handlers.

---

## 9. Verification

| # | Test Name | Invariant(s) | File |
|---|-----------|--------------|------|
| 1 | `test_db_schema_parity` | I-RUNTIME-1 | `test_legacy_parity.py` |
| 2 | `test_event_append_parity` | I-RUNTIME-1 | `test_legacy_parity.py` |
| 3 | `test_taskset_parse_equivalence` | I-RUNTIME-1 | `test_legacy_parity.py` |
| 4 | `test_state_yaml_roundtrip` | I-STATE-SYNC-1 | `test_legacy_parity.py` |
| 5 | `test_event_order_determinism` | I-BEHAVIOR-SEQ-1 | `test_legacy_parity.py` |
| 6 | `test_command_event_equivalence` | I-RUNTIME-1, I-STATE-SYNC-1 | `test_legacy_parity.py` |
| 7 | `test_guard_behavior_equivalence` | I-CLI-API-1, I-RUNTIME-1 | `test_legacy_parity.py` |
| 8 | `test_state_always_synced_after_command` | I-STATE-SYNC-1 | `test_legacy_parity.py` |
| 9 | `test_no_runtime_import_of_sdd_tools` | I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1 | `test_legacy_parity.py` |
| 10 | `test_projection_equivalence` | I-RUNTIME-1, I-BEHAVIOR-SEQ-1 | `test_legacy_parity.py` |
| 11 | `test_cli_projection_consistency` | I-RUNTIME-1 | `test_legacy_parity.py` |
| 12 | Kill test: `pytest tests/ --tb=short` with `.sdd/tools/` blocked (`chmod 000`) | I-RUNTIME-1 | manual / CI |
| 13 | `grep -r '\.sdd[/\\]tools' src/ tests/` returns no matches | I-RUNTIME-1 | `validate_invariants.py` |
| 14 | `validate_invariants.py --check I-RUNTIME-1 --scope full-src` | I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1 | `validate_invariants.py` |

### Test Signatures (canonical)

```python
def test_event_order_determinism(tmp_path):
    """I-BEHAVIOR-SEQ-1: same input trace → identical EventLog sequence."""
    # run sdd complete T-001 twice from identical state
    # compare [(event_type, position)] lists — must be equal

def test_no_runtime_import_of_sdd_tools(tmp_path):
    """I-TOOL-PATH-1 + I-RUNTIME-LINEAGE-1: no .sdd.tools in sys.modules after sdd command."""
    import subprocess, sys, json
    result = subprocess.run(
        ["python3", "-c",
         "import sdd.cli; import sys; "
         "bad = [m for m in sys.modules if '.sdd.tools' in m or '\\.sdd\\\\tools' in m]; "
         "print(json.dumps(bad))"],
        capture_output=True, text=True
    )
    assert json.loads(result.stdout) == []

def test_projection_equivalence(tmp_path):
    """infra/projections.py produces same phase/task counts as legacy derive_state.py."""
    # build identical EventLog in tmp_path DuckDB
    # run both projectors, compare: phase_id, task counts, done_ids

def test_cli_projection_consistency(tmp_path):
    """sdd show-state output is consistent with infra/projections.py (not stale cache)."""
    # complete a task, immediately run sdd show-state
    # parse stdout: verify done count matches projections.py output
```

### Full Verification Command

```bash
# Parity suite
pytest tests/integration/test_legacy_parity.py -v

# Existing suites must still pass
pytest tests/unit/test_cli_exec_contract.py tests/integration/test_env_independence.py \
       tests/regression/test_kernel_contract.py tests/integration/test_pipeline_smoke.py \
       tests/integration/test_pipeline_deterministic.py tests/unit/infra/test_metrics_purity.py -v

# Static invariant checks
python3 .sdd/tools/validate_invariants.py --check I-RUNTIME-1 --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-ENTRY-1 --scope full-src

# Kill test (STEP 4)
chmod -R 000 .sdd/tools/
pytest tests/ --tb=short    # must be all GREEN
chmod -R 755 .sdd/tools/    # restore before STEP 5

# CLI smoke
sdd show-state
sdd record-decision --help
sdd validate-config --help
sdd validate-invariants --help
sdd query-events --event ToolUseStarted --limit 1
```

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Migration of `migrate_jsonl_to_duckdb.py` (one-time tool, already run) | None |
| Migration of `norm_catalog.py` (pure library, no runtime callers) | Phase 14+ if needed |
| EventLog replay parity testing (covered by `test_pipeline_deterministic.py`) | Phase 10 |
| Parallel execution groups in TaskSet | Phase 11+ |
| Formal Spec for Phase 11 (Improvements & Integration) | Phase 11 |
| Phase 10 DoD validation (prerequisite, not part of Phase 13) | Phase 10 |
| Concurrency/async state sync (beyond single execution boundary) | Phase 14+ |
| `strace`-based runtime path tracing (covered by sys.modules test) | N/A |
