# TaskSet_v16 — Phase 16: Legacy Architecture Closure

Spec: specs_draft/Spec_v16_LegacyArchitectureClosure.md
Plan: plans/Plan_v16.md

---

T-1601: Fix cli.py I-PATH-1 — 4 hardcoded .sdd/ paths

Status:               DONE
Spec ref:             Spec_v16 §2 BC-1 Infra; §8 Integration
Invariants:           I-PATH-1
spec_refs:            [Spec_v16 §2 BC-1, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/cli.py, src/sdd/infra/paths.py
Outputs:              src/sdd/cli.py
Acceptance:           `grep -n '\.sdd/' src/sdd/cli.py` → 0 lines; `pytest tests/ -q` → green
Depends on:           —

---

T-1602: Rewrite test_adapters.py as test_cli_contracts.py

Status:               DONE
Spec ref:             Spec_v16 §2 BC-TEST; §7 UC-16-1
Invariants:           I-SHIM-CONTRACT-1, I-DEPRECATED-RM-2
spec_refs:            [Spec_v16 §2 BC-TEST, I-SHIM-CONTRACT-1, I-DEPRECATED-RM-2]
produces_invariants:  [I-SHIM-CONTRACT-1]
requires_invariants:  [I-FAIL-1, I-CLI-API-1, I-HOOK-FAILSAFE-1]
Inputs:               tests/unit/test_adapters.py, src/sdd/cli.py
Outputs:              tests/unit/test_cli_contracts.py, tests/unit/test_adapters.py
Acceptance:           `pytest tests/unit/test_cli_contracts.py -v` → all pass;
                      tests/unit/test_adapters.py deleted or contains zero deprecated-tool references
Depends on:           T-1601

---

T-1603: Fix test_log_tool_parity.py — remove deprecated AST checks

Status:               DONE
Spec ref:             Spec_v16 §2 BC-TEST
Invariants:           I-DEPRECATED-RM-2
spec_refs:            [Spec_v16 §2 BC-TEST, I-DEPRECATED-RM-2]
produces_invariants:  [I-DEPRECATED-RM-2]
requires_invariants:  []
Inputs:               tests/unit/hooks/test_log_tool_parity.py
Outputs:              tests/unit/hooks/test_log_tool_parity.py
Acceptance:           no AST checks reference _deprecated_tools/log_tool.py;
                      `pytest tests/unit/hooks/test_log_tool_parity.py -v` → green
Depends on:           T-1601

---

T-1604: Fix remaining deprecated-dependent integration tests

Status:               DONE
Spec ref:             Spec_v16 §2 BC-TEST
Invariants:           I-DEPRECATED-RM-2
spec_refs:            [Spec_v16 §2 BC-TEST, I-DEPRECATED-RM-2]
produces_invariants:  [I-DEPRECATED-RM-2]
requires_invariants:  []
Inputs:               tests/integration/test_env_independence.py,
                      tests/integration/test_task_output_invariant.py,
                      tests/integration/test_legacy_parity.py
Outputs:              tests/integration/test_env_independence.py,
                      tests/integration/test_task_output_invariant.py,
                      tests/integration/test_legacy_parity.py
Acceptance:           `grep -rn "_deprecated_tools" tests/` → 0; `pytest tests/ -q` → green
Depends on:           T-1601

---

T-1605: Verify + fix taskset_parser.py behavioural coverage

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LOGIC-VERIFY
Invariants:           I-LOGIC-COVER-1
spec_refs:            [Spec_v16 §2 BC-LOGIC-VERIFY, I-LOGIC-COVER-1]
produces_invariants:  [I-LOGIC-COVER-1]
requires_invariants:  []
Inputs:               src/sdd/domain/tasks/parser.py
Outputs:              tests/unit/domain/test_taskset_parser.py
Acceptance:           `pytest tests/unit/domain/test_taskset_parser.py -v` → both format branches
                      (free-form + table) pass; `phase_from_task` covered
Depends on:           T-1601

---

T-1606: Verify + fix state_yaml.py coverage including atomic_write crash test

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LOGIC-VERIFY
Invariants:           I-LOGIC-COVER-2
spec_refs:            [Spec_v16 §2 BC-LOGIC-VERIFY, I-LOGIC-COVER-2]
produces_invariants:  [I-LOGIC-COVER-2]
requires_invariants:  []
Inputs:               src/sdd/domain/state/yaml_state.py
Outputs:              tests/unit/domain/test_state_yaml.py
Acceptance:           `pytest tests/unit/domain/test_state_yaml.py::test_atomic_write_crash -v` → pass;
                      crash test uses monkeypatch of Path.rename raising OSError; asserts .tmp
                      left behind and original file intact; parse_field and update_status_field covered
Depends on:           T-1601

---

T-1607: Verify + fix norm_catalog.py coverage including stdlib YAML fallback

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LOGIC-VERIFY
Invariants:           I-LOGIC-COVER-3
spec_refs:            [Spec_v16 §2 BC-LOGIC-VERIFY, I-LOGIC-COVER-3]
produces_invariants:  [I-LOGIC-COVER-3]
requires_invariants:  []
Inputs:               src/sdd/domain/norms/catalog.py
Outputs:              tests/unit/domain/test_norm_catalog.py
Acceptance:           `pytest tests/unit/domain/test_norm_catalog.py::test_stdlib_yaml_fallback -v` → pass;
                      `get_norms_for_actor` covered; all Norm dataclass fields verified
Depends on:           T-1601

---

T-1608: Verify + add sdd_latest_seq() coverage in sdd.infra.db

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LOGIC-VERIFY; §4 Types (sdd_event_log.sdd_latest_seq)
Invariants:           I-DEP-AUDIT-1
spec_refs:            [Spec_v16 §2 BC-LOGIC-VERIFY, §4, I-DEP-AUDIT-1]
produces_invariants:  [I-DEP-AUDIT-1]
requires_invariants:  []
Inputs:               src/sdd/infra/db.py
Outputs:              tests/unit/infra/test_db.py
Acceptance:           `grep -rn "sdd_latest_seq\|latest_seq" tests/` → ≥ 1 match;
                      corresponding test passes; if function missing from sdd.infra.db,
                      add it (output: src/sdd/infra/db.py added to Outputs)
Depends on:           T-1601

---

T-1609: Document dep-audit gate results

Status:               DONE
Spec ref:             Spec_v16 §2 BC-DEP-AUDIT; §11 M4
Invariants:           I-DEP-AUDIT-1
spec_refs:            [Spec_v16 §2 BC-DEP-AUDIT, I-DEP-AUDIT-1]
produces_invariants:  [I-DEP-AUDIT-1]
requires_invariants:  [I-DEPRECATED-RM-2, I-SHIM-CONTRACT-1, I-LOGIC-COVER-1, I-LOGIC-COVER-2, I-LOGIC-COVER-3]
Inputs:               src/, tests/ (read-only grep audit)
Outputs:              .sdd/reports/DepAudit_Phase16.md
Acceptance:           all three greps return 0 and results are recorded in DepAudit_Phase16.md:
                      (1) `grep -rEn "sdd_db|sdd_event_log" src/ tests/ --include="*.py" --exclude-dir=_deprecated_tools` → 0
                      (2) `grep -rn "compute_spec_hash" src/ tests/` → 0
                      (3) `grep -rEn "(import|subprocess).*\.(report_error|sync_state)\.py" src/ tests/ --include="*.py" --exclude-dir=_deprecated_tools` → 0
Depends on:           T-1602, T-1603, T-1604, T-1605, T-1606, T-1607, T-1608

---

T-1610: Delete 15 shim files from _deprecated_tools/

Status:               DONE
Spec ref:             Spec_v16 §2 BC-SHIM-RM; §11 M5
Invariants:           I-DEPRECATED-RM-1, I-DEPRECATED-RM-2
spec_refs:            [Spec_v16 §2 BC-SHIM-RM, I-DEPRECATED-RM-1, I-DEPRECATED-RM-2]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  [I-DEPRECATED-RM-2, I-SHIM-CONTRACT-1, I-DEP-AUDIT-1]
Inputs:               .sdd/_deprecated_tools/ (read before delete)
Outputs:              .sdd/_deprecated_tools/build_context.py (deleted),
                      .sdd/_deprecated_tools/check_scope.py (deleted),
                      .sdd/_deprecated_tools/norm_guard.py (deleted),
                      .sdd/_deprecated_tools/phase_guard.py (deleted),
                      .sdd/_deprecated_tools/task_guard.py (deleted),
                      .sdd/_deprecated_tools/log_tool.py (deleted),
                      .sdd/_deprecated_tools/log_bash.py (deleted),
                      .sdd/_deprecated_tools/record_metric.py (deleted),
                      .sdd/_deprecated_tools/senar_audit.py (deleted),
                      .sdd/_deprecated_tools/query_events.py (deleted),
                      .sdd/_deprecated_tools/metrics_report.py (deleted),
                      .sdd/_deprecated_tools/report_error.py (deleted),
                      .sdd/_deprecated_tools/sync_state.py (deleted),
                      .sdd/_deprecated_tools/update_state.py (deleted),
                      .sdd/_deprecated_tools/validate_invariants.py (deleted)
Acceptance:           `pytest tests/ -q` → green; 15 listed files no longer exist
Depends on:           T-1609

---

T-1611: Delete 5 uncategorised files (BC-CLEANUP-RM)

Status:               DONE
Spec ref:             Spec_v16 §1 In-Scope BC-CLEANUP-RM; §11 M5b
Invariants:           I-DEPRECATED-RM-1
spec_refs:            [Spec_v16 §1 BC-CLEANUP-RM, I-DEPRECATED-RM-1]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  [I-LOGIC-COVER-1, I-LOGIC-COVER-2, I-LOGIC-COVER-3, I-DEP-AUDIT-1]
Inputs:               .sdd/_deprecated_tools/ (read before delete)
Outputs:              .sdd/_deprecated_tools/show_state.py (deleted),
                      .sdd/_deprecated_tools/init_state.py (deleted),
                      .sdd/_deprecated_tools/norm_catalog.py (deleted),
                      .sdd/_deprecated_tools/state_yaml.py (deleted),
                      .sdd/_deprecated_tools/taskset_parser.py (deleted)
Acceptance:           `pytest tests/ -q` → green; 5 listed files no longer exist;
                      `ls .sdd/_deprecated_tools/*.py | wc -l` = 7 (only legacy infra remain)
Depends on:           T-1605, T-1606, T-1607, T-1610

---

T-1612: Decision 1 — delete _deprecated_tools/sdd_run.py and guard_runner.py

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LEGACY-RESOLVE Decision 1; §4 Types
Invariants:           I-DEPRECATED-RM-1
spec_refs:            [Spec_v16 §2 BC-LEGACY-RESOLVE Decision 1, §4, I-DEPRECATED-RM-1]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  []
Inputs:               .sdd/_deprecated_tools/sdd_run.py,
                      .sdd/_deprecated_tools/guard_runner.py,
                      CLAUDE.md
Outputs:              .sdd/_deprecated_tools/sdd_run.py (deleted),
                      .sdd/_deprecated_tools/guard_runner.py (deleted),
                      CLAUDE.md
Acceptance:           both files deleted; CLAUDE.md §0.10 updated with note:
                      "`sdd run` — unregistered; CommandRunner removal deferred to Phase 15
                      Step 4; use `sdd complete` / `sdd validate`"; `pytest tests/ -q` → green
Depends on:           T-1610, T-1611

---

T-1613: Decision 2 — verify derive_state → sdd sync-state --dry-run coverage

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LEGACY-RESOLVE Decision 2
Invariants:           I-DEPRECATED-RM-1
spec_refs:            [Spec_v16 §2 BC-LEGACY-RESOLVE Decision 2, I-DEPRECATED-RM-1]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  []
Inputs:               .sdd/_deprecated_tools/derive_state.py,
                      src/sdd/commands/sync_state.py (or equivalent)
Outputs:              .sdd/_deprecated_tools/derive_state.py (deleted),
                      CLAUDE.md
Acceptance:           `sdd sync-state --dry-run` prints diff output (coverage confirmed);
                      if --dry-run does not print diff, `sync_state.py` updated first;
                      derive_state.py deleted; loss documented in CLAUDE.md §0.10;
                      `pytest tests/ -q` → green
Depends on:           T-1610, T-1611

---

T-1614: Decision 3 — add deprecation warning to src/sdd/domain/state/init_state.py

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LEGACY-RESOLVE Decision 3; §10 Out-of-Scope
Invariants:           I-1
spec_refs:            [Spec_v16 §2 BC-LEGACY-RESOLVE Decision 3, §10, I-1]
produces_invariants:  [I-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/init_state.py
Outputs:              src/sdd/domain/state/init_state.py
Acceptance:           calling init_state direct YAML-write path emits DeprecationWarning;
                      module NOT deleted (full removal deferred to Phase 17+);
                      `pytest tests/ -q` → green
Depends on:           T-1610, T-1611

---

T-1615: Delete 7 legacy infra files

Status:               DONE
Spec ref:             Spec_v16 §2 BC-LEGACY-RM; §11 M7
Invariants:           I-DEPRECATED-RM-1
spec_refs:            [Spec_v16 §2 BC-LEGACY-RM, I-DEPRECATED-RM-1]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  [I-DEP-AUDIT-1]
Inputs:               .sdd/_deprecated_tools/ (read before delete)
Outputs:              .sdd/_deprecated_tools/sdd_db.py (deleted),
                      .sdd/_deprecated_tools/sdd_event_log.py (deleted),
                      .sdd/_deprecated_tools/record_decision.py (deleted),
                      .sdd/_deprecated_tools/migrate_jsonl_to_duckdb.py (deleted)
Acceptance:           4 files deleted (sdd_run.py and guard_runner.py deleted in T-1612,
                      derive_state.py deleted in T-1613 — total 7 complete);
                      `ls .sdd/_deprecated_tools/*.py | wc -l` → 0; `pytest tests/ -q` → green;
                      re-run dep-audit grep as sanity check before deletion
Depends on:           T-1612, T-1613, T-1614

---

T-1616: Delete _deprecated_tools/ directory

Status:               DONE
Spec ref:             Spec_v16 §2 BC-DIR-RM; §11 M8
Invariants:           I-DEPRECATED-RM-1
spec_refs:            [Spec_v16 §2 BC-DIR-RM, I-DEPRECATED-RM-1]
produces_invariants:  [I-DEPRECATED-RM-1]
requires_invariants:  [I-DEPRECATED-RM-1]
Inputs:               .sdd/_deprecated_tools/ (verify empty with ls -la)
Outputs:              .sdd/_deprecated_tools/ (directory deleted)
Acceptance:           `test ! -d .sdd/_deprecated_tools && echo PASS` → PASS;
                      no hidden files (.gitkeep etc.) left behind
Depends on:           T-1615

---

T-1617: Fix CLAUDE.md, norm_catalog.yaml, document activate_plan.py as internal-only

Status:               DONE
Spec ref:             Spec_v16 §2 BC-DOCS; §9 checks #15, #16; §5 I-CLI-REG-1
Invariants:           I-CLI-REG-1
spec_refs:            [Spec_v16 §2 BC-DOCS, §9, I-CLI-REG-1]
produces_invariants:  [I-CLI-REG-1]
requires_invariants:  []
Inputs:               CLAUDE.md, .sdd/norms/norm_catalog.yaml
Outputs:              CLAUDE.md, .sdd/norms/norm_catalog.yaml
Acceptance:           4 CLAUDE.md stale lines patched per spec §2 BC-DOCS table;
                      activate_plan.py documented as internal-only in CLAUDE.md §0.10;
                      all scope_exempt entries referencing _deprecated_tools/ removed from
                      norm_catalog.yaml;
                      `grep -c '\.sdd/tools' CLAUDE.md` → 0;
                      `grep -c '_deprecated_tools' .sdd/norms/norm_catalog.yaml` → 0
Depends on:           T-1616

---

T-1618: CLI registration audit — satisfy I-CLI-REG-1

Status:               DONE
Spec ref:             Spec_v16 §2 BC-CLI-REG; §9 check #11; §5 I-CLI-REG-1
Invariants:           I-CLI-REG-1
spec_refs:            [Spec_v16 §2 BC-CLI-REG, §9 check #11, I-CLI-REG-1]
produces_invariants:  [I-CLI-REG-1]
requires_invariants:  [I-CLI-REG-1]
Inputs:               src/sdd/commands/, src/sdd/cli.py, CLAUDE.md
Outputs:              .sdd/reports/CLIAudit_Phase16.md
Acceptance:           every src/sdd/commands/*.py with user-facing main() is either
                      registered in cli.py OR listed as internal-only in CLAUDE.md §0.10;
                      `sdd validate-invariants --check I-CLI-REG-1 --scope full-src` → PASS
                      (if command not yet implemented: manual audit documented in
                      CLIAudit_Phase16.md with explicit list of registered vs internal-only);
                      activate_plan.py confirmed internal-only (done in T-1617)
Depends on:           T-1617

---

T-1619: Fix pre-existing test failures — exists_command signature, hook ToolUseStarted, context hash

Status:               DONE
Spec ref:             Spec_v16 §9 (test-suite green gate)
Invariants:           I-EXEC-ISOL-1
spec_refs:            [Spec_v16 §9]
produces_invariants:  [I-EXEC-ISOL-1]
requires_invariants:  []
Inputs:               src/sdd/infra/event_log.py, src/sdd/hooks/log_tool.py, src/sdd/context/build_context.py
Outputs:              src/sdd/infra/event_log.py, src/sdd/hooks/log_tool.py, src/sdd/context/build_context.py
Acceptance:           `pytest tests/unit/infra/test_event_log_commands.py tests/unit/hooks/test_log_tool.py tests/unit/context/test_build_context.py -q` → 0 failed
Depends on:           T-1601

---

<!-- Granularity: 19 tasks (TG-2: 10–30 range ✓). Each independently implementable and testable (TG-1). -->
<!-- Deletion sequence enforced by Depends on chain: M4 gate before M5, M5 before M6, M7 before M8. -->
