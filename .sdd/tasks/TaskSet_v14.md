# TaskSet_v14 — Phase 14: Control Plane Migration

Spec: specs/Spec_v14_ControlPlaneMigration.md
Plan: plans/Plan_v14.md

---

T-1401: Create `src/sdd/infra/paths.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-14-PATHS), §4 (paths.py frozen interface)
Invariants:           I-PATH-1, I-PATH-2, I-PATH-3, I-PATH-4, I-PATH-5
spec_refs:            [Spec_v14 §2, Spec_v14 §4, I-PATH-2, I-PATH-4, I-PATH-5]
produces_invariants:  [I-PATH-1, I-PATH-2, I-PATH-4, I-PATH-5]
requires_invariants:  —
Inputs:               (none — new file; Spec_v14 §2 and §4 are the authoritative reference)
Outputs:              src/sdd/infra/paths.py
Acceptance:           pytest tests/integration/test_sdd_home_isolation.py::test_paths_module_no_sdd_imports -v exits 0; all 16 public functions present; imports only os and pathlib; _AUDIT_LOG_DEFAULT sentinel pattern used (no "" sentinel)
Depends on:           —

---

T-1402: Migrate `src/sdd/infra/db.py` — remove SDD_EVENTS_DB constant

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-1 Infra), §4 (db.py sentinel extension), §6 (open_sdd_connection post-condition)
Invariants:           I-PATH-1, I-KERNEL-EXT-1
spec_refs:            [Spec_v14 §2, Spec_v14 §4, Spec_v14 §6, I-PATH-1, I-KERNEL-EXT-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/db.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/db.py
Acceptance:           python -c "import sdd.infra.db as m; assert not hasattr(m, 'SDD_EVENTS_DB'), 'constant still exported'"; open_sdd_connection() resolves path via event_store_file() when db_path is None
Depends on:           T-1401

---

T-1403: Migrate `src/sdd/infra/audit.py` — remove _AUDIT_LOG_DEFAULT constant

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-1 Infra), §4 (audit.py sentinel extension)
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §4, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/audit.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/audit.py
Acceptance:           python -c "import inspect, sdd.infra.audit as a; src = inspect.getsource(a); assert '_AUDIT_LOG_DEFAULT' not in src, 'constant still present'"; log_action audit_log_path default is None
Depends on:           T-1401

---

T-1404: Migrate `src/sdd/infra/event_log.py` — six functions to `str | None = None` sentinel

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-1 Infra), §4 (event_log.py frozen interface extension), §8 (backward-compat extensions)
Invariants:           I-PATH-1, I-KERNEL-EXT-1
spec_refs:            [Spec_v14 §2, Spec_v14 §4, Spec_v14 §8, I-PATH-1, I-KERNEL-EXT-1]
produces_invariants:  [I-PATH-1, I-KERNEL-EXT-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           python -c "import inspect, sdd.infra.event_log as el; [assert inspect.signature(getattr(el, fn)).parameters['db_path'].default is None for fn in ('sdd_append','sdd_append_batch','sdd_replay','exists_command','exists_semantic','get_error_count')]"; SDD_EVENTS_DB constant removed
Depends on:           T-1401

---

T-1405: Migrate `src/sdd/guards/scope.py` — Path.resolve() comparison replacing string prefix

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-3 Guards), §4 (guards/scope.py Path.resolve comparison), Plan v14 M3 risk R-4
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §4, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/guards/scope.py, src/sdd/infra/paths.py
Outputs:              src/sdd/guards/scope.py
Acceptance:           sdd check-scope read /abs/path/.sdd/specs/Spec_v14.md exits 1 (absolute path rejected via resolve comparison); Python <3.9 fallback present (str().startswith())
Depends on:           T-1401, T-1402

---

T-1406: Migrate `src/sdd/guards/task.py`, `phase.py`, `norm.py` — replace hardcoded `.sdd/` literals

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-3 Guards), §1 Scope
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §1, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/guards/task.py, src/sdd/guards/phase.py, src/sdd/guards/norm.py, src/sdd/infra/paths.py
Outputs:              src/sdd/guards/task.py, src/sdd/guards/phase.py, src/sdd/guards/norm.py
Acceptance:           grep -n '\.sdd/' src/sdd/guards/task.py src/sdd/guards/phase.py src/sdd/guards/norm.py returns empty
Depends on:           T-1401

---

T-1407: Migrate commands group A — `report_error.py`, `query_events.py`, `update_state.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-4 Commands), §1 Scope — "7 command files — replace SDD_DB_PATH / SDD_STATE_PATH"
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §1, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/commands/report_error.py, src/sdd/commands/query_events.py, src/sdd/commands/update_state.py, src/sdd/infra/paths.py
Outputs:              src/sdd/commands/report_error.py, src/sdd/commands/query_events.py, src/sdd/commands/update_state.py
Acceptance:           grep -rn 'SDD_DB_PATH\|SDD_STATE_PATH\|\.sdd/' src/sdd/commands/report_error.py src/sdd/commands/query_events.py src/sdd/commands/update_state.py returns empty
Depends on:           T-1401, T-1402, T-1404

---

T-1408: Migrate commands group B — `validate_invariants.py`, `metrics_report.py`, `activate_phase.py`, `show_state.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-4 Commands), §1 Scope — "7 command files — replace SDD_DB_PATH / SDD_STATE_PATH"
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §1, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/commands/validate_invariants.py, src/sdd/commands/metrics_report.py, src/sdd/commands/activate_phase.py, src/sdd/commands/show_state.py, src/sdd/infra/paths.py
Outputs:              src/sdd/commands/validate_invariants.py, src/sdd/commands/metrics_report.py, src/sdd/commands/activate_phase.py, src/sdd/commands/show_state.py
Acceptance:           grep -rn 'SDD_DB_PATH\|SDD_STATE_PATH\|\.sdd/' src/sdd/commands/validate_invariants.py src/sdd/commands/metrics_report.py src/sdd/commands/activate_phase.py src/sdd/commands/show_state.py returns empty
Depends on:           T-1401, T-1402, T-1404

---

T-1409: Migrate `src/sdd/hooks/log_tool.py` + `src/sdd/context/build_context.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-Hooks, BC-5 Context), §5 (I-CONFIG-PATH-1), §6 (build_context.py post-condition)
Invariants:           I-PATH-1, I-CONFIG-PATH-1
spec_refs:            [Spec_v14 §2, Spec_v14 §5, Spec_v14 §6, I-PATH-1, I-CONFIG-PATH-1]
produces_invariants:  [I-PATH-1, I-CONFIG-PATH-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/hooks/log_tool.py, src/sdd/context/build_context.py, src/sdd/infra/paths.py, .sdd/config/project_profile.yaml
Outputs:              src/sdd/hooks/log_tool.py, src/sdd/context/build_context.py
Acceptance:           grep -n 'SDD_DB_PATH\|state_path\|phases_index_path\|\.sdd/' src/sdd/hooks/log_tool.py src/sdd/context/build_context.py returns empty; build_context.py contains no subprocess/shell calls to sdd show-*
Depends on:           T-1401, T-1402

---

T-1410: Create `src/sdd/commands/show_task.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-8 CLI additions), §4 (CLI output schema for show-task), §6 (show-task pre/post), §7 (UC-14-1), §9 (rows 6, 12)
Invariants:           I-CLI-READ-1, I-CLI-READ-2, I-CLI-SCHEMA-1, I-CLI-SCHEMA-2, I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-CLI-SSOT-1, I-CLI-SSOT-2, I-SCOPE-CLI-1, I-SCOPE-CLI-2
spec_refs:            [Spec_v14 §2, Spec_v14 §4, Spec_v14 §6, Spec_v14 §7, I-CLI-SCHEMA-1, I-CLI-SCHEMA-2]
produces_invariants:  [I-CLI-SCHEMA-1, I-CLI-SCHEMA-2, I-CLI-READ-1, I-CLI-FAILSAFE-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/paths.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/show_task.py
Acceptance:           python -c "from sdd.commands.show_task import show_task" succeeds; output contains exactly these sections in order: "## Task:", "### Inputs", "### Outputs", "### Invariants Covered", "### Acceptance Criteria"; TaskNotFound exits 1 with JSON {error_type: "TaskNotFound", exit_code: 1}
Depends on:           T-1401, T-1404

---

T-1411: Create `src/sdd/commands/show_spec.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-8 CLI additions), §4 (AmbiguousSpec guard + resolution SSOT), §6 (show-spec pre/post), §7 (UC-14-3), §9 (rows 7, 9)
Invariants:           I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-SPEC-RESOLVE-1, I-SPEC-RESOLVE-2, I-SCOPE-CLI-1
spec_refs:            [Spec_v14 §2, Spec_v14 §4, Spec_v14 §6, Spec_v14 §7, I-SPEC-RESOLVE-1, I-SPEC-RESOLVE-2]
produces_invariants:  [I-SPEC-RESOLVE-1, I-SPEC-RESOLVE-2, I-CLI-FAILSAFE-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/paths.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/show_spec.py
Acceptance:           python -c "from sdd.commands.show_spec import show_spec" succeeds; spec resolved via Phases_index.md spec field (not sorted()[0]); two Spec_v14_*.md files cause exit 1 with JSON {error_type: "AmbiguousSpec"}; SpecNotFound exits 1 with JSON
Depends on:           T-1401

---

T-1412: Create `src/sdd/commands/show_plan.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-8 CLI additions), §6 (show-plan pre/post), §9 (row 8)
Invariants:           I-CLI-READ-1, I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-SCOPE-CLI-1
spec_refs:            [Spec_v14 §2, Spec_v14 §6, I-CLI-READ-1, I-CLI-FAILSAFE-1]
produces_invariants:  [I-CLI-READ-1, I-CLI-FAILSAFE-1]
requires_invariants:  [I-PATH-2]
Inputs:               src/sdd/infra/paths.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/show_plan.py
Acceptance:           python -c "from sdd.commands.show_plan import show_plan" succeeds; outputs plan file content verbatim; PlanNotFound exits 1 with JSON {error_type: "PlanNotFound", exit_code: 1}
Depends on:           T-1401

---

T-1413: Wire `show-task`, `show-spec`, `show-plan` in `src/sdd/cli.py`

Status:               DONE
Spec ref:             Spec_v14 §2 (BC-8 CLI additions), §9 (rows 6-8)
Invariants:           I-CLI-FAILSAFE-1, I-CLI-SSOT-1
spec_refs:            [Spec_v14 §2, Spec_v14 §9, I-CLI-FAILSAFE-1, I-CLI-SSOT-1]
produces_invariants:  [I-CLI-SSOT-1]
requires_invariants:  [I-CLI-SCHEMA-1, I-SPEC-RESOLVE-2, I-CLI-READ-1]
Inputs:               src/sdd/cli.py, src/sdd/commands/show_task.py, src/sdd/commands/show_spec.py, src/sdd/commands/show_plan.py
Outputs:              src/sdd/cli.py
Acceptance:           sdd show-task --help exits 0; sdd show-spec --help exits 0; sdd show-plan --help exits 0; sdd --help lists all three commands
Depends on:           T-1410, T-1411, T-1412

---

T-1414: Create `tests/integration/test_sdd_home_isolation.py`

Status:               DONE
Spec ref:             Spec_v14 §1 (Test infrastructure), §7 (UC-14-2), §9 (rows 1-4)
Invariants:           I-EXEC-ISOL-1, I-PATH-1, I-PATH-2, I-PATH-3
spec_refs:            [Spec_v14 §1, Spec_v14 §7, Spec_v14 §9, I-EXEC-ISOL-1, I-PATH-1, I-PATH-2, I-PATH-3]
produces_invariants:  [I-PATH-1, I-PATH-2, I-PATH-3, I-EXEC-ISOL-1]
requires_invariants:  [I-PATH-5]
Inputs:               src/sdd/infra/paths.py, src/sdd/infra/db.py, src/sdd/infra/audit.py, src/sdd/infra/event_log.py
Outputs:              tests/integration/test_sdd_home_isolation.py
Acceptance:           pytest tests/integration/test_sdd_home_isolation.py -v exits 0; all three required tests present: test_sdd_home_redirects_all_paths, test_no_hardcoded_sdd_paths_in_src, test_paths_module_no_sdd_imports
Depends on:           T-1401, T-1402, T-1403, T-1404, T-1405, T-1406, T-1407, T-1408, T-1409, T-1410, T-1411, T-1412, T-1413

---

T-1415: Update `tests/regression/test_kernel_contract.py` — expect `None` defaults for event_log.py

Status:               DONE
Spec ref:             Spec_v14 §1 (Test infrastructure), §4 (event_log.py frozen interface extension), §9 (row 5)
Invariants:           I-KERNEL-EXT-1
spec_refs:            [Spec_v14 §1, Spec_v14 §4, Spec_v14 §9, I-KERNEL-EXT-1]
produces_invariants:  [I-KERNEL-EXT-1]
requires_invariants:  [I-PATH-1]
Inputs:               tests/regression/test_kernel_contract.py, src/sdd/infra/event_log.py
Outputs:              tests/regression/test_kernel_contract.py
Acceptance:           pytest tests/regression/test_kernel_contract.py::test_frozen_modules_signatures -v exits 0; expected default for all six event_log.py functions is None (not SDD_EVENTS_DB string)
Depends on:           T-1404

---

T-1416: Update `.sdd/config/project_profile.yaml` — add I-PATH-1 forbidden pattern block

Status:               DONE
Spec ref:             Spec_v14 §8 (project_profile.yaml — I-PATH-1 enforcement)
Invariants:           I-PATH-1
spec_refs:            [Spec_v14 §8, I-PATH-1]
produces_invariants:  [I-PATH-1]
requires_invariants:  [I-PATH-1]
Inputs:               .sdd/config/project_profile.yaml
Outputs:              .sdd/config/project_profile.yaml
Acceptance:           sdd validate-invariants --check I-PATH-1 --scope full-src exits 0; project_profile.yaml contains forbidden_pattern \.sdd[/\\] with exclude src/sdd/infra/paths.py and severity hard
Depends on:           T-1401, T-1402, T-1403, T-1404, T-1405, T-1406, T-1407, T-1408, T-1409, T-1414, T-1415

---

T-1417: Update `CLAUDE.md` — §R.1, §R.2, §0.15, §0.10, §K.4, §K.6

Status:               DONE
Spec ref:             Spec_v14 §8 (CLAUDE.md changes), §2 (CLI-only read model), §5 (new invariants I-CLI-SSOT-1/2)
Invariants:           I-CLI-SSOT-1, I-CLI-SSOT-2, I-SCOPE-CLI-2
spec_refs:            [Spec_v14 §8, Spec_v14 §2, Spec_v14 §5, I-CLI-SSOT-1, I-CLI-SSOT-2, I-SCOPE-CLI-2]
produces_invariants:  [I-CLI-SSOT-1, I-CLI-SSOT-2, I-SCOPE-CLI-2]
requires_invariants:  [I-PATH-1]
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           grep -c 'SDD_DB_PATH\|SDD_STATE_PATH' CLAUDE.md returns 0; §R.2 lists sdd show-state/show-task/show-spec/show-plan as ONLY authorized SDD data sources; §0.15 includes paths.py frozen row; §0.10 includes show-task/spec/plan rows; §K.6 steps 2/4 reference CLI commands
Depends on:           T-1401, T-1402, T-1403, T-1404, T-1405, T-1406, T-1407, T-1408, T-1409, T-1410, T-1411, T-1412, T-1413, T-1414, T-1415, T-1416

<!-- Granularity: 17 tasks for Phase 14 (TG-2: 10–30 range satisfied). -->
<!-- Every task independently implementable and independently testable (TG-1). -->
