# TaskSet_v10 — Phase 10: Kernel Hardening

Spec: specs/Spec_v10_KernelHardening.md
Plan: plans/Plan_v10.md

---

T-1000: Task ID Parsing Refactor — guards (human-authorized kernel bugfix)

Status:               DONE
Spec ref:             Spec_v10 §2 BC-STATIC — guard correctness
Invariants Covered:   I-TASK-ID-1, I-GUARD-REG-1, I-GUARD-REG-2
spec_refs:            [I-TASK-ID-1, I-GUARD-REG-1, I-GUARD-REG-2]
produces_invariants:  [I-TASK-ID-1, I-GUARD-REG-1, I-GUARD-REG-2]
requires_invariants:  []
Inputs:               src/sdd/guards/task.py
                      src/sdd/guards/phase.py
                      .sdd/norms/norm_catalog.yaml
Outputs:              src/sdd/guards/task.py
                      src/sdd/guards/phase.py
                      .sdd/norms/norm_catalog.yaml
Acceptance:           parse_task_id("T-1007b") == (10, 7, "b").
                      parse_task_id("T-1001") == (10, 1, "").
                      parse_task_id("T-101") == (1, 1, "").
                      python3 .sdd/tools/task_guard.py check --task T-1007b → allowed: true.
                      python3 .sdd/tools/phase_guard.py check --command "Implement T-1007b" → allowed: true.
                      python3 .sdd/tools/norm_guard.py check --actor llm --action implement_task → allowed: true.
                      python3 .sdd/tools/norm_guard.py check --actor llm --action validate_task → allowed: true.
Depends on:           — (human-authorized outside-scope fix; added before T-1001 per session decision)

---

T-1001: CLI Execution Contract — cli.py five-path main()

Status:               DONE
Spec ref:             Spec_v10 §2 BC-EXEC — CLI Execution Contract
Invariants Covered:   I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1, I-EXEC-NO-CATCH-1
spec_refs:            [Spec_v10 §2 BC-EXEC, I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1, I-EXEC-NO-CATCH-1]
produces_invariants:  [I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1, I-EXEC-NO-CATCH-1]
requires_invariants:  [I-CLI-1, I-ERR-1]
Inputs:               src/sdd/cli.py
                      src/sdd/core/errors.py
Outputs:              src/sdd/cli.py
Acceptance:           All five execution paths present in cli.main():
                        SUCCESS → sys.exit(result or 0);
                        SDDError → _emit_json_error(..., 1) + sys.exit(1);
                        click.ClickException → _emit_json_error("UsageError", ..., 1) + sys.exit(1);
                        Exception → _emit_json_error("UnexpectedException", ..., 2) + sys.exit(2).
                      _emit_json_error is a private helper (not exported).
                      Existing @cli commands and I-CLI-1 (pure router) are unchanged.
                      All Pattern B adapters (.sdd/tools/*.py) gain ImportError guard
                      emitting {"error_type": "InstallError", ...} to stderr + sys.exit(1).
Depends on:           —

---

T-1002: CLI Execution Contract Tests — test_cli_exec_contract.py

Status:               DONE
Spec ref:             Spec_v10 §9 — Verification table tests 1–6
Invariants Covered:   I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1
spec_refs:            [Spec_v10 §9, I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1]
produces_invariants:  []
requires_invariants:  [I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1]
Inputs:               src/sdd/cli.py
                      src/sdd/core/errors.py
Outputs:              tests/unit/test_cli_exec_contract.py
Acceptance:           pytest tests/unit/test_cli_exec_contract.py -v passes all 6 tests:
                        test_success_path_exit_zero,
                        test_sdd_error_json_stderr_exit_1,
                        test_unexpected_exception_json_stderr_exit_2,
                        test_click_exception_exit_1_not_2,
                        test_click_exception_no_error_event,
                        test_cli_json_schema_fields.
Depends on:           T-1001

---

T-1003: Static Enforcement — forbidden patterns in project_profile.yaml

Status:               DONE
Spec ref:             Spec_v10 §2 BC-STATIC — I-LEGACY-0a/b, I-ENTRY-1
Invariants Covered:   I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1
spec_refs:            [Spec_v10 §2 BC-STATIC, I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1]
produces_invariants:  [I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1]
requires_invariants:  []
Inputs:               .sdd/config/project_profile.yaml
Outputs:              .sdd/config/project_profile.yaml
Acceptance:           Three new entries present under code_rules.forbidden_patterns:
                        I-LEGACY-0a pattern (sys\.path\s*(\.append|\.insert|\[).*\.sdd, severity hard),
                        I-LEGACY-0b pattern (subprocess.*\.sdd[/\\]tools, severity hard),
                        I-ENTRY-1 pattern (if __name__ == ...__main__..., exclude cli.py + hooks, severity hard).
                      Current src/sdd/ produces zero violations when patterns are applied manually.
Depends on:           —

---

T-1004: validate_invariants.py — --scope full-src dual-mode

Status:               DONE
Spec ref:             Spec_v10 §2 BC-STATIC — dual-mode contract
Invariants Covered:   I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1
spec_refs:            [Spec_v10 §2 BC-STATIC, I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1]
produces_invariants:  []
requires_invariants:  [I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1]
Inputs:               src/sdd/commands/validate_invariants.py
                      .sdd/config/project_profile.yaml
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src exits 0.
                      python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src exits 0.
                      python3 .sdd/tools/validate_invariants.py --check I-ENTRY-1 --scope full-src exits 0.
                      Default mode (no --scope flag) is behaviorally identical to Phase 9 (additive only).
Depends on:           T-1003

---

T-1005: Kernel Contract Regression Suite — test_kernel_contract.py + pyproject.toml

Status:               DONE
Spec ref:             Spec_v10 §2 BC-REGRESS — three checks per frozen module
Invariants Covered:   I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1
spec_refs:            [Spec_v10 §2 BC-REGRESS, I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1]
produces_invariants:  [I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1]
requires_invariants:  [I-KERNEL-EXT-1]
Inputs:               src/sdd/core/types.py
                      src/sdd/core/events.py
                      src/sdd/infra/event_log.py
                      src/sdd/infra/event_store.py
                      src/sdd/domain/state/reducer.py
                      src/sdd/domain/guards/context.py
                      pyproject.toml
Outputs:              tests/regression/test_kernel_contract.py
                      pyproject.toml
Acceptance:           pytest tests/regression/test_kernel_contract.py -v passes all 3 tests:
                        test_frozen_modules_mypy_strict (skip if mypy absent — I-REG-ENV-1),
                        test_frozen_modules_import_smoke,
                        test_frozen_modules_signatures.
                      pyproject.toml contains mypy>=1.8 in [project.optional-dependencies.dev].
                      FROZEN_SIGNATURES dict populated from live inspect.signature() at write time.
Depends on:           —

---

T-1006: Environment Independence Tests — test_env_independence.py

Status:               DONE
Spec ref:             Spec_v10 §2 BC-ENV — minimal env dict + adapter ImportError
Invariants Covered:   I-ENV-1, I-ENV-2, I-ENV-BOOT-1
spec_refs:            [Spec_v10 §2 BC-ENV, I-ENV-1, I-ENV-2, I-ENV-BOOT-1]
produces_invariants:  [I-ENV-1, I-ENV-2, I-ENV-BOOT-1]
requires_invariants:  [I-ENV-2, I-ENV-BOOT-1]
Inputs:               src/sdd/cli.py
                      .sdd/tools/update_state.py
Outputs:              tests/integration/test_env_independence.py
Acceptance:           pytest tests/integration/test_env_independence.py -v passes both tests:
                        test_sdd_help_minimal_env (exit 0 with PATH/HOME/VIRTUAL_ENV/LANG/LC_ALL only),
                        test_adapter_import_error_message (broken PYTHONPATH → JSON InstallError on stderr,
                          returncode 1, error_type=="InstallError", "pip install -e ." in message).
Depends on:           T-1001

---

T-1007a: Integration Tests Level A — CLI Smoke — test_pipeline_smoke.py

Status:               DONE
Spec ref:             Spec_v10 §2 BC-INTEG Level A — CLI smoke (3 tests)
Invariants Covered:   I-EXEC-SUCCESS-1, I-USAGE-1, I-CLI-API-1
spec_refs:            [Spec_v10 §2 BC-INTEG Level A, I-EXEC-SUCCESS-1, I-USAGE-1, I-CLI-API-1]
produces_invariants:  []
requires_invariants:  [I-EXEC-SUCCESS-1, I-USAGE-1, I-CLI-API-1]
Inputs:               src/sdd/cli.py
                      .sdd/runtime/State_index.yaml
Outputs:              tests/integration/test_pipeline_smoke.py
Acceptance:           pytest tests/integration/test_pipeline_smoke.py -v passes all 3 tests:
                        test_smoke_show_state (returncode 0, "phase" in stdout),
                        test_smoke_report_error_exit_code (returncode 1, stderr non-empty JSON),
                        test_smoke_unknown_command (returncode 1, JSON error_type=="UsageError", exit_code==1).
Depends on:           T-1001

---

T-1007b: Integration Tests Level B — Domain Determinism — test_pipeline_deterministic.py

Status:               DONE
Spec ref:             Spec_v10 §2 BC-INTEG Level B — isolated DB, determinism (1 test)
Invariants Covered:   I-EXEC-ISOL-1
spec_refs:            [Spec_v10 §2 BC-INTEG Level B, I-EXEC-ISOL-1]
produces_invariants:  [I-EXEC-ISOL-1]
requires_invariants:  []
Inputs:               src/sdd/commands/sdd_run.py
                      src/sdd/commands/activate_phase.py
                      src/sdd/domain/state/reducer.py
                      src/sdd/infra/event_log.py
Outputs:              tests/integration/test_pipeline_deterministic.py
Acceptance:           pytest tests/integration/test_pipeline_deterministic.py -v passes 1 test:
                        test_activate_phase_deterministic: uses tmp_path DuckDB (never sdd_events.duckdb),
                          two sdd_replay() calls on the same DB produce identical reduce() output.
Depends on:           —

---

T-1008: Metrics Purity Tests — test_metrics_purity.py

Status:               DONE
Spec ref:             Spec_v10 §9 — tests 16–17; §2 BC-INTEG; I-PURE-1, I-PURE-1a
Invariants Covered:   I-PURE-1, I-PURE-1a
spec_refs:            [Spec_v10 §9, I-PURE-1, I-PURE-1a]
produces_invariants:  [I-PURE-1, I-PURE-1a]
requires_invariants:  []
Inputs:               src/sdd/infra/metrics.py
Outputs:              tests/unit/infra/test_metrics_purity.py
Acceptance:           pytest tests/unit/infra/test_metrics_purity.py -v passes both tests:
                        test_compute_trend_no_io: dual-patch on sdd.infra.metrics.duckdb and
                          duckdb.connect — both show zero calls after compute_trend() invocation.
                        test_detect_anomalies_no_io: same dual-patch, zero calls after
                          detect_anomalies() invocation.
Depends on:           —

---

T-1009: CLAUDE.md — §R split (§R-core + §R-rules) + §0.16 Kernel Hardening Catalog

Status:               DONE
Spec ref:             Spec_v10 §2 BC-DOC — §R split, §0.16 Kernel Hardening Catalog
Invariants Covered:   —
spec_refs:            [Spec_v10 §2 BC-DOC]
produces_invariants:  []
requires_invariants:  []
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           §R contains two subsections: §R-core (5 sdd CLI commands) and §R-rules
                      (scope/guard/forbidden constraints; content preserved, zero strictness lost).
                      §0.16 Kernel Hardening Catalog table present listing all 18 Phase 10
                      invariants with verification method (test file + command).
Depends on:           T-1001, T-1002, T-1003, T-1004, T-1005, T-1006, T-1007a, T-1007b, T-1008

---

T-1010: sdd_plan.md Phase Overview Table Update (HUMAN TASK)

Status:               DONE
Spec ref:             Spec_v10 §2 BC-DOC — sdd_plan.md Phase Overview table
Invariants Covered:   —
spec_refs:            [Spec_v10 §2 BC-DOC]
produces_invariants:  []
requires_invariants:  []
Inputs:               sdd_plan.md
Outputs:              sdd_plan.md
Acceptance:           Phase Overview table in sdd_plan.md shows:
                        Phases 0–9 COMPLETE, Phase 10 Kernel Hardening ACTIVE,
                        Phase 11 Improvements & Integration (was 10),
                        Phase 12 Self-hosted Governance (was 11).
                      HUMAN TASK — LLM marks DONE only after human confirms edit is applied.
Depends on:           T-1009

---

<!-- Granularity: 12 tasks (T-1000 added per session bugfix authorization + T-1001..T-1010 with T-1007a/b separate). Within TG-2 range (10–30). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
