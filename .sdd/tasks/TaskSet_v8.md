# TaskSet_v8 — Phase 8: CLI + Kernel Stabilization

Spec: specs/Spec_v8_CLI.md
Plan: plans/Plan_v8.md

---

T-801: Package Bootstrap — pyproject.toml + __version__

Status:               DONE
Spec ref:             Spec_v8 §2.1 BC-CLI — Package Install + CLI Layer
Invariants:           I-PKG-1
spec_refs:            [Spec_v8 §2.1, I-PKG-1]
produces_invariants:  [I-PKG-1]
requires_invariants:  []
Inputs:               pyproject.toml, src/sdd/__init__.py
Outputs:              pyproject.toml, src/sdd/__init__.py
Acceptance:           PRECHECK: `pytest --collect-only -q` exits 0; `ruff --version` exits 0; THEN: pip install -e . exits 0; python -c "import sdd; print(sdd.__version__)" prints "0.8.0"; entry point `sdd` registered in [project.scripts]; [tool.pytest], [tool.ruff], [tool.mypy] sections present
Depends on:           —

---

T-802: Package Tests

Status:               DONE
Spec ref:             Spec_v8 §2.1 BC-CLI, §9 Test #1 — test_package.py (3 tests)
Invariants:           I-PKG-1, I-PKG-2
spec_refs:            [Spec_v8 §2.1, §9, I-PKG-1, I-PKG-2]
produces_invariants:  []
requires_invariants:  [I-PKG-1]
Inputs:               pyproject.toml, src/sdd/__init__.py
Outputs:              tests/unit/test_package.py
Acceptance:           test_package_importable, test_version_string_is_semver, test_entry_point_registered PASS
Depends on:           T-801

---

T-803: Command Extensions — show_state handler + main() wrappers

Status:               DONE
Spec ref:             Spec_v8 §2.1 BC-CLI — show-state handler; main() added to existing commands; §4.6
Invariants:           I-CLI-2
spec_refs:            [Spec_v8 §2.1, §4.6, I-CLI-2]
produces_invariants:  [I-CLI-2]
requires_invariants:  [I-PKG-1]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/query_events.py, src/sdd/commands/report_error.py, src/sdd/commands/activate_phase.py, src/sdd/commands/metrics_report.py, .sdd/runtime/State_index.yaml
Outputs:              src/sdd/commands/show_state.py, src/sdd/commands/update_state.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/query_events.py, src/sdd/commands/report_error.py, src/sdd/commands/activate_phase.py
main() contract:      Every added main() MUST have signature:
                        def main(args: list[str] | None = None) -> int:
                            if args is None: args = sys.argv[1:]
                            try: ...existing logic...; return 0
                            except KnownSddError: return 1
                            except Exception: return 2
                      Return type int is mandatory (I-CLI-2 exit code contract).
Acceptance:           show_state.main([]) reads State_index.yaml, applies State Guard, returns 0 on success / 1 on MissingState or Inconsistency; every modified command callable as main(args) returning int per contract above
Depends on:           T-801

---

T-804: CLI Router — src/sdd/cli.py

Status:               DONE
Spec ref:             Spec_v8 §2.1 BC-CLI — Click router; §4.5 CLI main
Invariants:           I-CLI-1, I-CLI-3, I-PKG-2
spec_refs:            [Spec_v8 §2.1, §4.5, I-CLI-1, I-CLI-2, I-CLI-3, I-PKG-2]
produces_invariants:  [I-CLI-1, I-CLI-3, I-PKG-2]
requires_invariants:  [I-PKG-1]
Inputs:               src/sdd/commands/show_state.py, src/sdd/commands/update_state.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/query_events.py, src/sdd/commands/report_error.py, src/sdd/commands/activate_phase.py, src/sdd/commands/metrics_report.py
Outputs:              src/sdd/cli.py
Acceptance:           sdd --help exits 0 and lists all 8 subcommands; cli.py contains no direct sdd.infra.*/sdd.domain.*/sdd.guards.* import nodes at module level or inside function bodies (AST-verified); no function in cli.py exceeds 6 lines; all command handlers imported lazily inside @cli.command function bodies
Depends on:           T-801, T-803

---

T-805: CLI Tests

Status:               DONE
Spec ref:             Spec_v8 §9 Test #2 — test_cli.py (10 tests)
Invariants:           I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3
spec_refs:            [Spec_v8 §9, I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3]
produces_invariants:  []
requires_invariants:  [I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3]
Inputs:               src/sdd/cli.py, src/sdd/commands/show_state.py, src/sdd/commands/update_state.py
Outputs:              tests/unit/test_cli.py
I-CLI-3 scope:        equivalence tests check ONLY: (a) exit code identical, (b) L1 EventLog event type sequence identical.
                      stdout/stderr content is explicitly NOT compared (formatting may differ between Click and direct main()).
                      This is the correct interpretation of Spec_v8 §5 I-CLI-3: "same exit code and same event types emitted".
Acceptance:           10 tests PASS: test_help_lists_all_commands, test_cli_is_pure_router, test_exit_code_success, test_exit_code_validation_failure, test_exit_code_unexpected_error, test_complete_routes_to_update_state, test_query_events_pass_through_args, test_show_state_registered, test_cli_vs_main_equivalence_complete, test_cli_vs_main_equivalence_show_state; equivalence tests assert exit code + L1 event types only (no stdout comparison)
Depends on:           T-803, T-804

---

T-806: Metrics Extension — pure functions + data types

Status:               DONE
Spec ref:             Spec_v8 §2.2 BC-METRICS-EXT; §4.0–4.4 — MetricRecord, TrendRecord, AnomalyRecord, load_metrics(), compute_trend(), detect_anomalies()
Invariants:           I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2
spec_refs:            [Spec_v8 §2.2, §4.0, §4.1, §4.2, §4.3, §4.4, I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2]
produces_invariants:  [I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2]
requires_invariants:  [I-EL-9]
Inputs:               src/sdd/infra/metrics.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/metrics.py
Acceptance:           compute_trend and detect_anomalies contain no DuckDB/I/O calls (AST-verifiable); load_metrics is the sole DuckDB entry; compute_trend returns delta=None for first phase; detect_anomalies returns [] when stdev==0 or < 3 data points; no ZeroDivisionError when abs(value) < 1e-9
Depends on:           T-801

---

T-807: Metrics Extension Tests

Status:               DONE
Spec ref:             Spec_v8 §9 Test #4 — test_metrics_report_enhanced.py (10 tests)
Invariants:           I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2
spec_refs:            [Spec_v8 §9, I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2]
produces_invariants:  []
requires_invariants:  [I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2]
Inputs:               src/sdd/infra/metrics.py
Outputs:              tests/unit/commands/test_metrics_report_enhanced.py
Acceptance:           10 tests PASS: test_trend_two_phases, test_trend_first_phase_delta_none, test_trend_direction_up_down_flat, test_trend_pure_no_io, test_trend_direction_zero_value, test_anomaly_empty_below_3_points, test_anomaly_detected_above_2sigma, test_anomaly_not_detected_within_2sigma, test_anomaly_pure_no_io, test_anomaly_empty_on_zero_stdev
Depends on:           T-806

---

T-808: metrics_report Command — --trend/--anomalies flags + main()

Status:               DONE
Spec ref:             Spec_v8 §2.2 BC-METRICS-EXT — metrics_report --trend/--anomalies render; main() updated
Invariants:           I-TREND-1, I-ANOM-1
spec_refs:            [Spec_v8 §2.2, I-TREND-1, I-ANOM-1]
produces_invariants:  [I-TREND-1 (cmd), I-ANOM-1 (cmd)]
requires_invariants:  [I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2]
Inputs:               src/sdd/commands/metrics_report.py, src/sdd/infra/metrics.py
Outputs:              src/sdd/commands/metrics_report.py
Acceptance:           metrics_report --trend renders markdown table with Phase/Metric/Value/Delta/Dir columns; metrics_report --anomalies appends anomaly section; both flags combinable; main(args: list[str] | None = None) -> int added per T-803 contract; load_metrics called once per flag combination
Depends on:           T-803, T-806

---

T-809: Process Hardening — acceptance field + validate_invariants enforcement

Status:               DONE
Spec ref:             Spec_v8 §2.4 BC-PROC — acceptance enforcement; sdd_config.yaml fields
Invariants:           I-ACCEPT-1
spec_refs:            [Spec_v8 §2.4, I-ACCEPT-1]
produces_invariants:  [I-ACCEPT-1]
requires_invariants:  [I-PKG-1]
Inputs:               .sdd/config/project_profile.yaml, src/sdd/commands/validate_invariants.py, .sdd/tasks/TaskSet_v8.md
Outputs:              .sdd/config/project_profile.yaml, .sdd/config/sdd_config.yaml, src/sdd/commands/validate_invariants.py
{outputs} rules:      1. If task Outputs field is empty → SKIP ruff check (not fail); emit warning to stderr.
                      2. If any listed output path does not exist → FAIL immediately with structured error (not ruff failure).
                      3. Outputs are passed as subprocess list (no shell); directory paths passed as-is to ruff (ruff handles them).
                      4. {outputs} template in project_profile.yaml is human-readable only; actual execution uses subprocess list API.
Acceptance:           project_profile.yaml has build.commands.acceptance field; sdd_config.yaml has anomaly_zscore_threshold and trend_epsilon; validate_invariants --task T-NNN expands {outputs} per rules above; ruff+pytest run via subprocess list API; non-zero exit blocks DONE with structured error; empty outputs skips ruff; missing output file fails with explicit error
Depends on:           T-801, T-803

---

T-810: Acceptance Tests for validate_invariants

Status:               DONE
Spec ref:             Spec_v8 §9 Test #5 — test_validate_invariants.py (+4 acceptance tests)
Invariants:           I-ACCEPT-1
spec_refs:            [Spec_v8 §9, I-ACCEPT-1]
produces_invariants:  []
requires_invariants:  [I-ACCEPT-1]
Inputs:               src/sdd/commands/validate_invariants.py, .sdd/config/project_profile.yaml, tests/unit/commands/test_validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           4 new tests PASS: test_acceptance_command_runs, test_acceptance_blocks_done_on_lint_failure, test_acceptance_blocks_done_on_test_failure, test_outputs_expansion (verifies subprocess list, not shell); existing tests in file unaffected
Depends on:           T-809

---

T-811: Pattern A + log_tool Pattern B Thin Adapters

Status:               DONE
Spec ref:             Spec_v8 §2.3 BC-ADAPT — Pattern A (CLI delegation) + log_tool.py Pattern B
Invariants:           I-ADAPT-1, I-ADAPT-3, I-ADAPT-4
spec_refs:            [Spec_v8 §2.3, I-ADAPT-1, I-ADAPT-3, I-ADAPT-4]
produces_invariants:  [I-ADAPT-1 (partial), I-ADAPT-3 (log_tool), I-ADAPT-4]
requires_invariants:  [I-PKG-1]
Inputs:               .sdd/tools/log_tool.py, .sdd/tools/update_state.py, .sdd/tools/validate_invariants.py, .sdd/tools/query_events.py, .sdd/tools/metrics_report.py, .sdd/tools/report_error.py, .sdd/tools/sync_state.py, src/sdd/hooks/log_tool.py
Outputs:              .sdd/tools/log_tool.py, .sdd/tools/update_state.py, .sdd/tools/validate_invariants.py, .sdd/tools/query_events.py, .sdd/tools/metrics_report.py, .sdd/tools/report_error.py, .sdd/tools/sync_state.py
pip hint:             I-ADAPT-3 JSON error MUST include install hint: {"error": "SDD_IMPORT_FAILED", "message": "<str(e)> — run: pip install -e ."}
Acceptance:           log_tool.py is Pattern B (imports sdd.hooks.log_tool.main; no sys.path); remaining 6 scripts are Pattern A (subprocess.call(["sdd", ...] + sys.argv[1:]); sys.exit(code)); all 7 files start with # DEPRECATED comment immediately after shebang line; grep "sys\.path" on each of these 7 files returns empty; exit code passthrough verified (I-ADAPT-4)
Depends on:           T-801, T-804

---

T-812: Pattern B Thin Adapters — guards, context, infra, audit

Status:               DONE
Spec ref:             Spec_v8 §2.3 BC-ADAPT — Pattern B (direct import); I-HOOK-API-2 for log_bash.py
Invariants:           I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-HOOK-API-2
spec_refs:            [Spec_v8 §2.3, I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-HOOK-API-2]
produces_invariants:  [I-ADAPT-1 (complete), I-ADAPT-2, I-ADAPT-3, I-HOOK-API-2]
requires_invariants:  [I-PKG-1]
Inputs:               .sdd/tools/phase_guard.py, .sdd/tools/check_scope.py, .sdd/tools/senar_audit.py, .sdd/tools/log_bash.py, src/sdd/guards/runner.py, src/sdd/context/build_context.py, src/sdd/infra/metrics.py, src/sdd/hooks/log_tool.py
Outputs:              .sdd/tools/phase_guard.py, .sdd/tools/task_guard.py, .sdd/tools/check_scope.py, .sdd/tools/norm_guard.py, .sdd/tools/build_context.py, .sdd/tools/record_metric.py, .sdd/tools/senar_audit.py, .sdd/tools/log_bash.py
PRE-T-812 contract:   Before writing each adapter, verify the target module:
                        1. EXISTS: python -c "import <sdd.module>" exits 0.
                        2. EXPOSES main(): inspect.getattr(<module>, "main") succeeds.
                        3. IF NOT — create a minimal src/sdd/<module>.py with
                           def main(args=None) -> int that wraps the legacy .sdd/tools logic;
                           add that new file to this task's Outputs before proceeding.
                      Modules to verify (from Spec_v8 §2.3 table):
                        sdd.guards.phase, sdd.guards.task, sdd.guards.scope, sdd.guards.norm,
                        sdd.context.build_context, sdd.infra.metrics (record_metric_cli),
                        sdd.infra.audit (audit_cli), sdd.hooks.log_tool
pip hint:             Same as T-811: ImportError message MUST include "run: pip install -e .".
Acceptance:           PRE contract completed for all 8 target modules before adapters written; each adapter file is Pattern B; ImportError caught with JSON stderr + exit 2 + pip hint; non-import exceptions propagate; log_bash.py warns on positional argv to stderr then continues (I-HOOK-API-2); grep "sys\.path" on all 8 output files returns empty; task_guard.py, norm_guard.py, build_context.py, record_metric.py created as new files
Depends on:           T-801, T-811

---

T-813: Adapter Tests

Status:               DONE
Spec ref:             Spec_v8 §9 Test #3 — test_adapters.py (10 tests)
Invariants:           I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2
spec_refs:            [Spec_v8 §9, I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2]
produces_invariants:  []
requires_invariants:  [I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2]
Inputs:               .sdd/tools/update_state.py, .sdd/tools/query_events.py, .sdd/tools/metrics_report.py, .sdd/tools/log_tool.py, .sdd/tools/log_bash.py, .sdd/tools/phase_guard.py
Outputs:              tests/unit/test_adapters.py
legacy boundary:      Add test_no_tools_imported_in_src: grep -r "from .sdd.tools" src/sdd/ and grep -r "import .sdd.tools" src/sdd/ must both return empty. src/sdd/* MUST NOT import from .sdd/tools/*. (Candidate invariant I-LEGACY-0 for Phase 9 Spec; enforced here as acceptance rule.)
Acceptance:           10 tests PASS: test_no_syspath_in_adapters, test_deprecated_comment_present, test_log_tool_is_pattern_b, test_update_state_is_pattern_a, test_update_state_help_parity, test_query_events_help_parity, test_metrics_report_help_parity, test_pattern_b_structured_error_on_import_failure, test_pattern_a_exit_code_passthrough, test_hook_warns_on_positional_argv; PLUS test_no_tools_imported_in_src (legacy boundary)
Depends on:           T-811, T-812

---

T-814: CLAUDE.md — §0.15 Kernel Contract Freeze + §0.10/§0.12 updates

Status:               DONE
Spec ref:             Spec_v8 §2.4 BC-PROC — CLAUDE.md §0.15; §2.4 §0.10/§0.12 updates
Invariants:           I-KERNEL-EXT-1
spec_refs:            [Spec_v8 §2.4, §8, I-KERNEL-EXT-1]
produces_invariants:  [I-KERNEL-EXT-1]
requires_invariants:  []
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           §0.15 section added with Kernel Contract Freeze table (6 frozen modules/interfaces); §0.10 tools table entries marked [DEPRECATED — use sdd CLI]; §0.12 hook section updated noting log_tool.py is now a Pattern B adapter
Depends on:           T-801, T-802, T-803, T-804, T-805, T-806, T-807, T-808, T-809, T-810, T-811, T-812, T-813

---

T-815: Phase Validation Report — §PHASE-INV coverage

Status:               DONE
Spec ref:             Spec_v8 §5 §PHASE-INV — all 16 invariants PASS
Invariants:           I-PKG-1, I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3, I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2, I-ACCEPT-1, I-HOOK-API-2, I-KERNEL-EXT-1
spec_refs:            [Spec_v8 §5, §PHASE-INV]
produces_invariants:  []
requires_invariants:  [I-PKG-1, I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3, I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2, I-ACCEPT-1, I-HOOK-API-2, I-KERNEL-EXT-1]
Inputs:               .sdd/reports/ValidationReport_T-801.md, .sdd/reports/ValidationReport_T-802.md, .sdd/reports/ValidationReport_T-803.md, .sdd/reports/ValidationReport_T-804.md, .sdd/reports/ValidationReport_T-805.md, .sdd/reports/ValidationReport_T-806.md, .sdd/reports/ValidationReport_T-807.md, .sdd/reports/ValidationReport_T-808.md, .sdd/reports/ValidationReport_T-809.md, .sdd/reports/ValidationReport_T-810.md, .sdd/reports/ValidationReport_T-811.md, .sdd/reports/ValidationReport_T-812.md, .sdd/reports/ValidationReport_T-813.md, .sdd/reports/ValidationReport_T-814.md
Outputs:              .sdd/reports/ValidationReport_T-815.md
cli boundary:         Confirm: sdd CLI is the sole external API; .sdd/tools/* are deprecated adapters only; src/sdd/* has zero imports from .sdd/tools (verified by T-813 test_no_tools_imported_in_src).
Acceptance:           all 16 §PHASE-INV invariants confirmed PASS with evidence; report references each individual ValidationReport; I-KERNEL-EXT-1 satisfied by human review gate documentation; CLI boundary and legacy isolation confirmed
Depends on:           T-801, T-802, T-803, T-804, T-805, T-806, T-807, T-808, T-809, T-810, T-811, T-812, T-813, T-814

---

<!-- Granularity: 15 tasks (TG-2: 10–30 per phase ✓). All independently implementable and testable (TG-1). -->
<!-- I-LEGACY-0 (no .sdd/tools imports in src/sdd/*) enforced as acceptance rule in T-813/T-815.   -->
<!-- Formal invariant registration requires Spec_v9 — tracked as candidate in SDD_Improvements.md. -->
