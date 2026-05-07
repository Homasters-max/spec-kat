# TaskSet_v13 — Phase 13: Runtime Stabilization

Spec: specs/Spec_v13_RuntimeStabilization.md
Plan: plans/Plan_v13.md

---

T-1301: Add sdd-hook-log console_scripts entry point to pyproject.toml

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 1, §4 (New Entry Point)
Invariants:           I-HOOK-WIRE-1
spec_refs:            [Spec_v13 §1, Spec_v13 §4, I-HOOK-WIRE-1]
produces_invariants:  [I-HOOK-WIRE-1]
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              pyproject.toml
Acceptance:           `pip install -e .` succeeds; `sdd-hook-log --help` resolves via venv PATH regardless of cwd
Depends on:           —

---

T-1302: Add failsafe try/except to src/sdd/hooks/log_tool.py

Status:               DONE
Spec ref:             Spec_v13 §4 (Hook Failsafe Contract), §6 STEP 1 Post
Invariants:           I-HOOK-FAILSAFE-1
spec_refs:            [Spec_v13 §4, Spec_v13 §6, I-HOOK-FAILSAFE-1]
produces_invariants:  [I-HOOK-FAILSAFE-1]
requires_invariants:  []
Inputs:               src/sdd/hooks/log_tool.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/hooks/log_tool.py
Acceptance:           When DuckDB write raises, stderr contains JSON with keys `event_type`, `payload`, `hook_error`; process exits 0
Depends on:           —

---

T-1303: Update ~/.claude/settings.json hook command to sdd-hook-log

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 1, §6 STEP 1 Post
Invariants:           I-HOOK-WIRE-1, I-HOOK-FAILSAFE-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, I-HOOK-WIRE-1]
produces_invariants:  []
requires_invariants:  [I-HOOK-WIRE-1]
Inputs:               ~/.claude/settings.json, T-1301 (sdd-hook-log installed)
Outputs:              ~/.claude/settings.json
Acceptance:           `ToolUseStarted` event appears in EventLog after next tool call; hook command is `sdd-hook-log pre` (not `python3 .sdd/tools/log_tool.py pre`)
Depends on:           T-1301, T-1302

---

T-1304: Wire record-decision CLI command in src/sdd/cli.py

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 2, §4 (New CLI Commands)
Invariants:           I-RUNTIME-1
spec_refs:            [Spec_v13 §1, Spec_v13 §4, I-RUNTIME-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/cli.py, src/sdd/commands/record_decision.py
Outputs:              src/sdd/cli.py
Acceptance:           `sdd record-decision --help` exits 0; `sdd record-decision --decision-id D-001 --title T --summary S` invokes RecordDecisionHandler without error
Depends on:           —

---

T-1305: Wire validate-config CLI command in src/sdd/cli.py

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 2, §4 (New CLI Commands)
Invariants:           I-RUNTIME-1
spec_refs:            [Spec_v13 §1, Spec_v13 §4, I-RUNTIME-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/cli.py, src/sdd/commands/validate_config.py
Outputs:              src/sdd/cli.py
Acceptance:           `sdd validate-config --help` exits 0; `sdd validate-config --phase 13` runs ValidateConfigHandler without error
Depends on:           —

---

T-1306: Verify validate-invariants flag parity and show-state projection freshness

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 2, §6 STEP 2 Post
Invariants:           I-RUNTIME-1, I-STATE-SYNC-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, I-RUNTIME-1, I-STATE-SYNC-1]
produces_invariants:  [I-STATE-SYNC-1]
requires_invariants:  []
Inputs:               src/sdd/cli.py, src/sdd/infra/projections.py
Outputs:              src/sdd/cli.py
Acceptance:           `sdd validate-invariants --help` shows `--phase`, `--task`, `--check` flags; `sdd show-state` output is derived from `infra/projections.py` (not stale cache)
Depends on:           T-1304, T-1305

---

T-1307: Write structural parity tests (tests 1–3)

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 3, §9 (tests 1–3)
Invariants:           I-RUNTIME-1, I-EXEC-ISOL-1
spec_refs:            [Spec_v13 §1, Spec_v13 §9, I-RUNTIME-1, I-EXEC-ISOL-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               tests/conftest.py, src/sdd/infra/sdd_db.py, src/sdd/infra/event_log.py, src/sdd/domain/taskset_parser.py (or equivalent)
Outputs:              tests/integration/test_legacy_parity.py
Acceptance:           `pytest tests/integration/test_legacy_parity.py::test_db_schema_parity tests/integration/test_legacy_parity.py::test_event_append_parity tests/integration/test_legacy_parity.py::test_taskset_parse_equivalence -v` all PASS
Depends on:           T-1303, T-1306

---

T-1308: Write state and sequencing tests (tests 4–5)

Status:               DONE
Spec ref:             Spec_v13 §9 (tests 4–5), §7 UC-13-5
Invariants:           I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1
spec_refs:            [Spec_v13 §9, Spec_v13 §7, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1]
produces_invariants:  [I-BEHAVIOR-SEQ-1]
requires_invariants:  [I-STATE-SYNC-1]
Inputs:               tests/integration/test_legacy_parity.py (from T-1307), src/sdd/infra/event_log.py, src/sdd/runtime/State_index.yaml schema
Outputs:              tests/integration/test_legacy_parity.py
Acceptance:           `pytest tests/integration/test_legacy_parity.py::test_state_yaml_roundtrip tests/integration/test_legacy_parity.py::test_event_order_determinism -v` both PASS; canonical signatures from Spec §9 are used verbatim
Depends on:           T-1307

---

T-1309: Write command and guard parity tests (tests 6–7)

Status:               DONE
Spec ref:             Spec_v13 §9 (tests 6–7), §7 UC-13-3
Invariants:           I-RUNTIME-1, I-STATE-SYNC-1, I-CLI-API-1
spec_refs:            [Spec_v13 §9, Spec_v13 §7, I-RUNTIME-1, I-CLI-API-1]
produces_invariants:  []
requires_invariants:  [I-STATE-SYNC-1, I-CLI-API-1]
Inputs:               tests/integration/test_legacy_parity.py (from T-1308), src/sdd/cli.py, src/sdd/domain/guards/
Outputs:              tests/integration/test_legacy_parity.py
Acceptance:           `pytest tests/integration/test_legacy_parity.py::test_command_event_equivalence tests/integration/test_legacy_parity.py::test_guard_behavior_equivalence -v` both PASS; guard rejection JSON matches I-CLI-API-1 schema fields
Depends on:           T-1308

---

T-1310: Write state sync and sys.modules tests (tests 8–9)

Status:               DONE
Spec ref:             Spec_v13 §9 (tests 8–9), §7 UC-13-4, §9 canonical signatures
Invariants:           I-STATE-SYNC-1, I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1
spec_refs:            [Spec_v13 §9, Spec_v13 §7, I-STATE-SYNC-1, I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1]
produces_invariants:  [I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1]
requires_invariants:  [I-STATE-SYNC-1]
Inputs:               tests/integration/test_legacy_parity.py (from T-1309), src/sdd/cli.py
Outputs:              tests/integration/test_legacy_parity.py
Acceptance:           `pytest tests/integration/test_legacy_parity.py::test_state_always_synced_after_command tests/integration/test_legacy_parity.py::test_no_runtime_import_of_sdd_tools -v` both PASS; canonical signature from Spec §9 used verbatim for test_no_runtime_import_of_sdd_tools
Depends on:           T-1309

---

T-1311: Write projection tests (tests 10–11)

Status:               DONE
Spec ref:             Spec_v13 §9 (tests 10–11), §9 canonical signatures
Invariants:           I-RUNTIME-1, I-BEHAVIOR-SEQ-1
spec_refs:            [Spec_v13 §9, I-RUNTIME-1, I-BEHAVIOR-SEQ-1]
produces_invariants:  []
requires_invariants:  [I-BEHAVIOR-SEQ-1, I-STATE-SYNC-1]
Inputs:               tests/integration/test_legacy_parity.py (from T-1310), src/sdd/infra/projections.py
Outputs:              tests/integration/test_legacy_parity.py
Acceptance:           `pytest tests/integration/test_legacy_parity.py -v` all 11 tests PASS; canonical signatures from Spec §9 used for test_projection_equivalence and test_cli_projection_consistency
Depends on:           T-1310

---

T-1312: Run filesystem kill test (chmod 000 → pytest → restore)

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 4, §6 STEP 4 Post, §9 (test 12)
Invariants:           I-RUNTIME-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, Spec_v13 §9, I-RUNTIME-1]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1, I-HOOK-WIRE-1, I-HOOK-FAILSAFE-1]
Inputs:               .sdd/tools/ (directory to block), tests/ (full suite), T-1311 result (all 11 parity tests PASS)
Outputs:              .sdd/reports/ValidationReport_T-1312.md
Acceptance:           `chmod -R 000 .sdd/tools/ && pytest tests/ --tb=short` exits 0 (all GREEN); `chmod -R 755 .sdd/tools/` restores; `sdd query-events --event ToolUseStarted --limit 1` shows recent event
Depends on:           T-1311

---

T-1313: Static grep and hook smoke verification

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 4, §6 STEP 4 Post, §9 (tests 13–14)
Invariants:           I-RUNTIME-1, I-LEGACY-0a, I-LEGACY-0b
spec_refs:            [Spec_v13 §1, Spec_v13 §6, Spec_v13 §9, I-RUNTIME-1, I-LEGACY-0a, I-LEGACY-0b]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1]
Inputs:               src/ (grep target), tests/ (grep target), .sdd/tools/validate_invariants.py
Outputs:              .sdd/reports/ValidationReport_T-1313.md
Acceptance:           `grep -r '\.sdd[/\\]tools' src/ tests/` returns no matches; `python3 .sdd/tools/validate_invariants.py --check I-RUNTIME-1 --scope full-src` exits 0; `python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src` exits 0; `python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src` exits 0
Depends on:           T-1312

---

T-1314: Archive .sdd/tools/ to .sdd/_deprecated_tools/

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 5, §6 STEP 5 Post
Invariants:           I-RUNTIME-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, I-RUNTIME-1]
produces_invariants:  [I-RUNTIME-1]
requires_invariants:  []
Inputs:               .sdd/tools/ (directory), T-1313 result (kill test PASSED — all three layers verified)
Outputs:              .sdd/_deprecated_tools/ (renamed from .sdd/tools/)
Acceptance:           `.sdd/tools/` no longer exists; `.sdd/_deprecated_tools/` contains all former scripts; `sdd show-state` exits 0 without `.sdd/tools/`
Depends on:           T-1313

---

T-1315: Register new invariants in .sdd/config/project_profile.yaml

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 5, §5 (New Invariants), §6 STEP 5 Post
Invariants:           I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1
spec_refs:            [Spec_v13 §1, Spec_v13 §5, Spec_v13 §6, I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1]
Inputs:               .sdd/config/project_profile.yaml, Spec_v13 §5 (invariant statements)
Outputs:              .sdd/config/project_profile.yaml
Acceptance:           `project_profile.yaml` `code_rules.forbidden_patterns` contains entries for `\.sdd[/\\]tools` (hard) covering I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-TOOL-PATH-1; pattern tested manually via grep before registration
Depends on:           T-1314

---

T-1316: Update CLAUDE.md §0.10 Tool Reference table

Status:               DONE
Spec ref:             Spec_v13 §1 STEP 5, §6 STEP 5 Post
Invariants:           I-RUNTIME-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, I-RUNTIME-1]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1]
Inputs:               CLAUDE.md (§0.10 section), .sdd/_deprecated_tools/ (archive location)
Outputs:              CLAUDE.md
Acceptance:           §0.10 Tool Reference table no longer refers to `.sdd/tools/` as runtime path; scripts are noted as archived in `.sdd/_deprecated_tools/`; "deprecated adapters for backward compatibility" language removed; `sdd` CLI is the sole documented interface
Depends on:           T-1315

---

T-1317: Final smoke validation — full suite + sdd show-state without .sdd/tools/

Status:               DONE
Spec ref:             Spec_v13 §6 STEP 5 Post, §9 (Full Verification Command)
Invariants:           I-RUNTIME-1, I-STATE-SYNC-1, I-HOOK-FAILSAFE-1
spec_refs:            [Spec_v13 §6, Spec_v13 §9, I-RUNTIME-1, I-STATE-SYNC-1]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1, I-HOOK-WIRE-1, I-HOOK-FAILSAFE-1, I-BEHAVIOR-SEQ-1, I-TOOL-PATH-1]
Inputs:               tests/ (full suite), src/sdd/ (installed package), .sdd/_deprecated_tools/ (archived, no .sdd/tools/)
Outputs:              .sdd/reports/ValidationReport_T-1317.md
Acceptance:           `pytest tests/integration/test_legacy_parity.py tests/unit/test_cli_exec_contract.py tests/integration/test_env_independence.py tests/regression/test_kernel_contract.py tests/integration/test_pipeline_smoke.py tests/integration/test_pipeline_deterministic.py tests/unit/infra/test_metrics_purity.py -v` all PASS; `sdd show-state` exits 0; `sdd record-decision --help` exits 0; `sdd validate-config --help` exits 0; `sdd query-events --event ToolUseStarted --limit 1` shows recent event
Depends on:           T-1316

---

T-1318: End-to-end phase execution playbook

Status:               DONE
Spec ref:             Spec_v13 §1 (all STEPs), §6 (all Pre/Post), §9 (Full Verification Command)
Invariants:           I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1, I-HOOK-FAILSAFE-1, I-TOOL-PATH-1
spec_refs:            [Spec_v13 §1, Spec_v13 §6, Spec_v13 §9, I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1, I-HOOK-FAILSAFE-1, I-TOOL-PATH-1]
produces_invariants:  []
requires_invariants:  [I-RUNTIME-1, I-RUNTIME-LINEAGE-1, I-STATE-SYNC-1, I-BEHAVIOR-SEQ-1, I-HOOK-FAILSAFE-1, I-TOOL-PATH-1]
Inputs:               T-1317 result (all prior tasks DONE and PASS), pyproject.toml, src/sdd/hooks/log_tool.py, ~/.claude/settings.json, src/sdd/cli.py, tests/integration/test_legacy_parity.py, .sdd/_deprecated_tools/, .sdd/config/project_profile.yaml, CLAUDE.md
Outputs:              .sdd/reports/ValidationReport_T-1318.md
Acceptance:           All checklist items below produce exit 0 / expected output with no .sdd/tools/ present:

  Step 3 — M1: Hook migration (critical path)
    [ ] pyproject.toml contains sdd-hook-log = "sdd.hooks.log_tool:main"
    [ ] src/sdd/hooks/log_tool.py contains failsafe try/except (I-HOOK-FAILSAFE-1)
    [ ] ~/.claude/settings.json hook command is `sdd-hook-log pre|post` (not python3 .sdd/tools/...)
    [ ] `pip install -e .` exits 0; `sdd-hook-log --help` resolves via PATH

  Step 4 — M2: CLI wiring (independent of M1)
    [ ] `sdd record-decision --help` exits 0
    [ ] `sdd validate-config --help` exits 0

  Step 5 — M3: Parity tests
    [ ] `pytest tests/integration/test_legacy_parity.py -v` — all 11 tests PASS

  Step 6 — M4: Kill test
    [ ] `chmod -R 000 .sdd/tools/ 2>/dev/null || true && pytest tests/ --tb=short` exits 0
    [ ] (Note: .sdd/tools/ is already archived as .sdd/_deprecated_tools/ at this point — chmod is a no-op; test confirms suite passes without it)

  Step 7 — M5: Freeze
    [ ] `.sdd/tools/` does not exist; `.sdd/_deprecated_tools/` contains archived scripts
    [ ] `project_profile.yaml` registers I-RUNTIME-1/I-RUNTIME-LINEAGE-1/I-TOOL-PATH-1 forbidden patterns
    [ ] CLAUDE.md §0.10 no longer references `.sdd/tools/` as runtime path
Depends on:           T-1317

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->
