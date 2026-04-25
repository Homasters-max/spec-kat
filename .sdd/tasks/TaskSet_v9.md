# TaskSet_v9 — Phase 9: Command Envelope Refactor

Spec: specs/Spec_v9_CommandRegistry.md
Plan: plans/Plan_v9.md

---

T-901: Create core/payloads.py — payload dataclasses + registry + factory

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-ENV — Command Envelope Support Layer
Invariants:           I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5
spec_refs:            [Spec_v9 §2, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
produces_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
requires_invariants:  [I-KERNEL-EXT-1]
Inputs:               src/sdd/core/types.py
Outputs:              src/sdd/core/payloads.py
Acceptance:           test_payload_dataclasses_frozen, test_build_command_missing_field, test_build_command_unknown_type
Depends on:           —

---

T-902: Fix commands/update_state.py — remove 4 subclasses, fix main() and handlers

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — update_state.py (CompleteTaskCommand, ValidateTaskCommand, SyncStateCommand, CheckDoDCommand)
Invariants:           I-CMD-ENV-1, I-CMD-ENV-6
spec_refs:            [Spec_v9 §2, Spec_v9 §8, I-CMD-ENV-1, I-CMD-ENV-6]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/update_state.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           test_no_command_subclasses passes for update_state.py; existing tests/unit/commands/test_complete_task.py, test_validate_task.py, test_sync_state.py, test_check_dod.py pass unchanged
Depends on:           T-901

---

T-903: Fix commands/report_error.py — remove ReportErrorCommand subclass

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — report_error.py (ReportErrorCommand)
Invariants:           I-CMD-ENV-1
spec_refs:            [Spec_v9 §2, I-CMD-ENV-1]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/report_error.py
Outputs:              src/sdd/commands/report_error.py
Acceptance:           test_no_command_subclasses passes for report_error.py; tests/unit/commands/test_report_error.py passes unchanged
Depends on:           T-901

---

T-904: Fix commands/validate_invariants.py — remove ValidateInvariantsCommand subclass

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — validate_invariants.py (ValidateInvariantsCommand)
Invariants:           I-CMD-ENV-1
spec_refs:            [Spec_v9 §2, I-CMD-ENV-1]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/validate_invariants.py
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           test_no_command_subclasses passes for validate_invariants.py; tests/unit/commands/test_validate_invariants.py passes unchanged
Depends on:           T-901

---

T-905: Fix commands/activate_phase.py + activate_plan.py — remove subclasses

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — activate_phase.py (ActivatePhaseCommand), activate_plan.py (ActivatePlanCommand)
Invariants:           I-CMD-ENV-1
spec_refs:            [Spec_v9 §2, I-CMD-ENV-1]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/activate_phase.py, src/sdd/commands/activate_plan.py
Outputs:              src/sdd/commands/activate_phase.py, src/sdd/commands/activate_plan.py
Acceptance:           test_no_command_subclasses passes for both files; tests/unit/commands/test_activate_phase.py, test_activate_plan.py pass unchanged
Depends on:           T-901

---

T-906: Fix commands/validate_config.py + metrics_report.py — remove subclasses

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — validate_config.py (ValidateConfigCommand), metrics_report.py (MetricsReportCommand)
Invariants:           I-CMD-ENV-1
spec_refs:            [Spec_v9 §2, I-CMD-ENV-1]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/validate_config.py, src/sdd/commands/metrics_report.py
Outputs:              src/sdd/commands/validate_config.py, src/sdd/commands/metrics_report.py
Acceptance:           test_no_command_subclasses passes for both files; tests/unit/commands/test_validate_config.py, test_metrics_report.py pass unchanged
Depends on:           T-901

---

T-907: Fix commands/record_decision.py — remove RecordDecisionCommand subclass

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-FIX — record_decision.py (RecordDecisionCommand)
Invariants:           I-CMD-ENV-1
spec_refs:            [Spec_v9 §2, I-CMD-ENV-1]
produces_invariants:  [I-CMD-ENV-1]
requires_invariants:  [I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/types.py, src/sdd/core/payloads.py, src/sdd/commands/record_decision.py
Outputs:              src/sdd/commands/record_decision.py
Acceptance:           test_no_command_subclasses passes for record_decision.py; tests/unit/commands/test_record_decision.py passes unchanged
Depends on:           T-901

---

T-908: Create tests/unit/core/test_payloads.py — registry + factory + AST checks

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-TEST, §9 Verification — test_payloads.py (I-CMD-ENV-1..5)
Invariants:           I-CMD-ENV-1, I-CMD-ENV-2, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5
spec_refs:            [Spec_v9 §2, Spec_v9 §9, I-CMD-ENV-1, I-CMD-ENV-2, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
produces_invariants:  [I-CMD-ENV-1, I-CMD-ENV-2, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
requires_invariants:  [I-CMD-ENV-1, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/payloads.py, src/sdd/core/types.py, src/sdd/commands/update_state.py, src/sdd/commands/report_error.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/activate_phase.py, src/sdd/commands/activate_plan.py, src/sdd/commands/validate_config.py, src/sdd/commands/metrics_report.py, src/sdd/commands/record_decision.py
Outputs:              tests/unit/core/test_payloads.py
Acceptance:           pytest tests/unit/core/test_payloads.py passes; covers test_build_command_returns_command, test_build_command_missing_field, test_build_command_unknown_type, test_payload_dataclasses_frozen, test_registry_coverage, test_no_command_subclasses
Depends on:           T-901, T-902, T-903, T-904, T-905, T-906, T-907

---

T-909: Create tests/unit/test_sdd_complete_smoke.py — subprocess end-to-end test

Status:               DONE
Spec ref:             Spec_v9 §2 BC-CMD-TEST, §9 Verification — test_sdd_complete_smoke.py (I-CMD-ENV-6)
Invariants:           I-CMD-ENV-6
spec_refs:            [Spec_v9 §2, Spec_v9 §9, I-CMD-ENV-6]
produces_invariants:  [I-CMD-ENV-6]
requires_invariants:  [I-CMD-ENV-1, I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5]
Inputs:               src/sdd/core/payloads.py, src/sdd/commands/update_state.py
Outputs:              tests/unit/test_sdd_complete_smoke.py
Acceptance:           pytest tests/unit/test_sdd_complete_smoke.py passes; test_sdd_complete_exits_zero uses subprocess + isolated tmp dir fixture with real TaskSet, verifies exit code 0
Depends on:           T-902

---

T-910: Update CLAUDE.md — remove deprecated adapter note in §0.10, document build_command pattern

Status:               DONE
Spec ref:             Spec_v9 §11 — T-910 governance update
Invariants:           governance
spec_refs:            [Spec_v9 §11]
produces_invariants:  []
requires_invariants:  []
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           CLAUDE.md §0.10 references build_command() as the canonical command construction pattern; deprecated adapter notes updated to reflect Phase 9 completion
Depends on:           T-901, T-902, T-903, T-904, T-905, T-906, T-907, T-908, T-909
