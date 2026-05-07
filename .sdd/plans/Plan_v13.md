# Plan_v13 — Phase 13: Runtime Stabilization

Status: DRAFT
Spec: specs/Spec_v13_RuntimeStabilization.md

---

## Milestones

### M1: Hook Migration — Replace .sdd/tools/log_tool.py with sdd-hook-log entry point

```text
Spec:       §1 STEP 1, §4 (New Entry Point, Hook Failsafe Contract), §6 (STEP 1 Pre/Post)
BCs:        BC-13 → BC-7 (Telemetry/Hooks)
Invariants: I-HOOK-FAILSAFE-1, I-HOOK-WIRE-1
Depends:    — (no prior milestone)
Risks:      If sdd-hook-log is not on PATH after pip install -e ., hooks go silent.
            Failsafe must be in place before settings.json is updated.
```

**Deliverables:**
- `pyproject.toml` — add `sdd-hook-log = "sdd.hooks.log_tool:main"` to `[project.scripts]`
- `src/sdd/hooks/log_tool.py` — add try/except failsafe block (I-HOOK-FAILSAFE-1): emit JSON to stderr on DuckDB failure, exit 0
- `~/.claude/settings.json` — update PreToolUse/PostToolUse hook command from `python3 .sdd/tools/log_tool.py pre|post` to `sdd-hook-log pre|post`

---

### M2: CLI Wiring — Wire record-decision and validate-config; verify parity flags

```text
Spec:       §1 STEP 2, §4 (New CLI Commands), §6 (STEP 2 Pre/Post)
BCs:        BC-13 → BC-4 (Commands)
Invariants: I-RUNTIME-1 (partial — execution path now in src/sdd)
Depends:    — (independent of M1; can proceed in parallel)
Risks:      Handlers exist but may not be wired; flag mismatch in validate-invariants
            or stale projection in show-state would fail parity tests in M3.
```

**Deliverables:**
- `src/sdd/cli.py` — add `record-decision` command with options `--decision-id`, `--title`, `--summary`, `--phase`, `--task`; wire to `RecordDecisionHandler`
- `src/sdd/cli.py` — add `validate-config` command with `--phase` option; wire to `ValidateConfigHandler`
- Verify `sdd validate-invariants` exposes `--phase`, `--task`, `--check` flags (parity with legacy `.sdd/tools/validate_invariants.py`)
- Verify `sdd show-state` output derives from `infra/projections.py` (not stale cache)

---

### M3: Parity Test Suite — 11-test behavior parity battery

```text
Spec:       §1 STEP 3, §6 (STEP 3 Pre/Post), §9 (Verification tests 1–11 + canonical signatures)
BCs:        BC-13 ← BC-3 (Guards), BC-13 ← BC-6 (Projections)
Invariants: I-RUNTIME-1, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1, I-TOOL-PATH-1,
            I-RUNTIME-LINEAGE-1, I-CLI-API-1
Depends:    M1 (hook fires via sdd-hook-log), M2 (CLI commands wired)
Risks:      test_projection_equivalence requires legacy derive_state.py accessible;
            if already removed, comparison baseline is lost.
            test_no_runtime_import_of_sdd_tools may have false positives if conftest
            imports anything from .sdd.tools transitively.
```

**Deliverables:**
- `tests/integration/test_legacy_parity.py` — 11 tests (all must PASS):
  1. `test_db_schema_parity`
  2. `test_event_append_parity`
  3. `test_taskset_parse_equivalence`
  4. `test_state_yaml_roundtrip`
  5. `test_event_order_determinism`
  6. `test_command_event_equivalence`
  7. `test_guard_behavior_equivalence`
  8. `test_state_always_synced_after_command`
  9. `test_no_runtime_import_of_sdd_tools`
  10. `test_projection_equivalence`
  11. `test_cli_projection_consistency`
- All tests use `tmp_path`-isolated DuckDB (I-EXEC-ISOL-1 compliance)

---

### M4: Kill Test — Verify zero runtime dependency on .sdd/tools/

```text
Spec:       §1 STEP 4, §6 (STEP 4 Pre/Post), §9 (Verification tests 12–14)
BCs:        BC-13 (all layers: filesystem, sys.modules, static grep)
Invariants: I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1
Depends:    M1, M2, M3 (all parity tests GREEN before kill test runs)
Risks:      chmod 000 on .sdd/tools/ is reversible but must not be committed.
            Any failing test here means a hidden runtime path to .sdd/tools/ exists —
            must be traced and cut before proceeding to M5.
```

**Deliverables:**
- Filesystem layer: `chmod -R 000 .sdd/tools/` → `pytest tests/ --tb=short` all GREEN → `chmod -R 755 .sdd/tools/` (restore)
- Module cache layer: `test_no_runtime_import_of_sdd_tools` PASS — no `.sdd.tools` in `sys.modules`
- Static layer: `grep -r '\.sdd[/\\]tools' src/ tests/` returns no matches
- Hook smoke: `sdd query-events --event ToolUseStarted --limit 1` shows recent event (hook still fires)
- ValidationReport: `.sdd/reports/ValidationReport_T-13XX.md` for this milestone documents kill test results

---

### M5: Freeze — Archive .sdd/tools/, register invariants, update CLAUDE.md

```text
Spec:       §1 STEP 5, §6 (STEP 5 Pre/Post)
BCs:        BC-13 (governance/config layer)
Invariants: I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1
Depends:    M4 (kill test PASSED — all three layers verified)
Risks:      Renaming .sdd/tools/ breaks any remaining references in docs or CLAUDE.md;
            all references must be updated atomically in this milestone.
            project_profile.yaml forbidden_patterns must match actual grep patterns
            used by validate_invariants.py.
```

**Deliverables:**
- `.sdd/_deprecated_tools/` — rename from `.sdd/tools/` (git mv or filesystem rename)
- `.sdd/config/project_profile.yaml` — register forbidden patterns for I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1 (e.g. pattern `\.sdd[/\\]tools` in `code_rules.forbidden_patterns`)
- `CLAUDE.md §0.10` — update Tool Reference table: mark all `.sdd/tools/*.py` scripts as archived (point to `.sdd/_deprecated_tools/`); remove "deprecated adapters for backward compatibility" language; note archive status
- Final smoke: `sdd show-state` and full test suite pass without `.sdd/tools/`

---

## Risk Notes

- R-1: **Hook silence window** — between updating `settings.json` (M1) and `pip install -e .` completing, hooks may fail silently. Mitigation: install entry point first, verify `sdd-hook-log --help` resolves, then update `settings.json`.
- R-2: **derive_state.py baseline** — `test_projection_equivalence` (M3) compares new projections.py against legacy derive_state.py. If derive_state.py has already been removed, the test has no baseline. Mitigation: confirm `derive_state.py` exists before writing M3 tests; if absent, document equivalence via EventLog replay instead.
- R-3: **Transitive .sdd/tools imports** — conftest.py or fixtures may indirectly import from `.sdd/tools/`. Static grep in M4 catches this, but runtime sys.modules check is the authoritative gate. Mitigation: run `test_no_runtime_import_of_sdd_tools` in M3 as an early signal before the full kill test.
- R-4: **settings.json cwd-sensitivity** — if `~/.claude/settings.json` stores a relative path, the hook may fail when Claude Code starts from a different directory. Mitigation: I-HOOK-WIRE-1 requires cwd-independence; use the bare command `sdd-hook-log` (resolved via PATH) not a path fragment.
- R-5: **project_profile.yaml forbidden pattern alignment** — patterns registered in M5 must exactly match the grep expressions used by `validate_invariants.py`. Misalignment means the invariant check passes vacuously. Mitigation: test the pattern manually (`grep -r '<pattern>' src/ tests/`) before registering.
