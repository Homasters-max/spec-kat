# TaskSet_v6 — Phase 6: Query, Metrics & Reporting

Spec: specs/Spec_v6_QueryMetrics.md
Plan: plans/Plan_v6.md

---

T-601: EventLogQuerier + QueryFilters (BC-QUERY infra)

Status:               DONE
Spec ref:             Spec_v6 §2.2, §4.1, §4.2 — QueryFilters, EventLogQuerier, EventRecord
Invariants:           I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §2.2, §4.1, §4.2, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2]
produces_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2]
requires_invariants:  [I-EL-9, I-PK-1]
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/event_query.py
Acceptance:           EventLogQuerier.query(filters) returns tuple[EventRecord, ...] ordered by seq; no writes to DB; EventRecord is a frozen dataclass with fields matching the events table schema (seq, event_type, payload, event_source, level, expired, caused_by_meta_seq)
Depends on:           —

---

T-602: Tests for EventLogQuerier

Status:               DONE
Spec ref:             Spec_v6 §9 row 1 — test_event_query.py
Invariants:           I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §9, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2]
produces_invariants:  []
requires_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2]
Inputs:               src/sdd/infra/event_query.py, src/sdd/infra/db.py
Outputs:              tests/unit/infra/test_event_query.py
Acceptance:           All of: test_query_order_asc, test_query_order_desc, test_query_source_filter_meta, test_query_source_filter_runtime, test_query_source_filter_none, test_query_phase_id_filter, test_query_excludes_expired_by_default, test_query_includes_expired_when_flag_set, test_query_limit, test_query_deterministic, test_querier_no_shared_state pass
Depends on:           T-601

---

T-603: QueryEventsHandler + QueryHandler Protocol (BC-QUERY commands)

Status:               DONE
Spec ref:             Spec_v6 §2.2, §4.3 — QueryHandler Protocol, QueryEventsCommand, QueryEventsResult, QueryEventsHandler
Invariants:           I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §2.2, §4.3, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2]
produces_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2]
requires_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4]
Inputs:               src/sdd/infra/event_query.py
Outputs:              src/sdd/commands/query_events.py
Acceptance:           QueryEventsHandler conforms to QueryHandler Protocol (not CommandHandler); QueryEventsHandler.execute() returns QueryEventsResult; handler is NOT registered with CommandRunner; no DB writes on execute
Depends on:           T-601

---

T-604: Tests for QueryEventsHandler

Status:               DONE
Spec ref:             Spec_v6 §9 row 2 — test_query_events.py
Invariants:           I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §9, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2]
produces_invariants:  []
requires_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-2]
Inputs:               src/sdd/commands/query_events.py, src/sdd/infra/event_query.py
Outputs:              tests/unit/commands/test_query_events.py
Acceptance:           All of: test_execute_returns_result, test_no_db_write_on_query, test_handler_conforms_to_query_handler_protocol pass
Depends on:           T-603

---

T-605: MetricRecord + MetricsSummary + MetricsAggregator (BC-METRICS domain)

Status:               DONE
Spec ref:             Spec_v6 §2.3, §4.4, §4.5, §4.6 — MetricRecord, MetricsSummary, MetricsAggregator
Invariants:           I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §2.3, §4.4, §4.5, §4.6, I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2]
produces_invariants:  [I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2]
requires_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4]
Inputs:               src/sdd/infra/event_query.py
Outputs:              src/sdd/domain/metrics/__init__.py, src/sdd/domain/metrics/aggregator.py
Acceptance:           MetricsAggregator.aggregate(tc_events, mr_events, phase_id) returns MetricsSummary; aggregate() is a pure function (no I/O, no sdd_append calls); I-MR-1 correlation is by task_id only (no seq-proximity)
Depends on:           T-601

---

T-606: Tests for MetricsAggregator

Status:               DONE
Spec ref:             Spec_v6 §9 row 3 — test_aggregator.py
Invariants:           I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2
spec_refs:            [Spec_v6 §9, I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2]
produces_invariants:  []
requires_invariants:  [I-MR-1, I-MR-2, I-PROJ-CONST-1, I-PROJ-CONST-2]
Inputs:               src/sdd/domain/metrics/aggregator.py
Outputs:              tests/unit/domain/metrics/__init__.py, tests/unit/domain/metrics/test_aggregator.py
Acceptance:           All of: test_aggregator_deterministic, test_im1_violation_detected, test_no_im1_violation_when_metric_present, test_im1_correlation_by_task_id_only, test_summary_counts_correct, test_aggregator_pure_no_io pass
Depends on:           T-605

---

T-607: MetricsReportHandler (BC-METRICS commands)

Status:               DONE
Spec ref:             Spec_v6 §2.3, §4.7 — MetricsReportCommand, MetricsReportHandler
Invariants:           I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3
spec_refs:            [Spec_v6 §2.3, §4.7, §2.1, I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3]
produces_invariants:  [I-MR-1, I-MR-2, I-CHAIN-1, I-PROJ-CONST-3]
requires_invariants:  [I-MR-1, I-MR-2, I-ES-6, I-QE-1, I-QE-2, I-QE-3, I-QE-4]
Inputs:               src/sdd/infra/event_query.py, src/sdd/domain/metrics/aggregator.py, src/sdd/commands/_base.py
Outputs:              src/sdd/commands/metrics_report.py
Acceptance:           MetricsReportHandler.handle() calls EventLogQuerier directly (NOT QueryEventsHandler — I-CHAIN-1); returns []; renders Markdown and writes to output_path when set; same db_path+phase_id → same output (I-MR-2, I-PROJ-CONST-3)
Depends on:           T-601, T-605

---

T-608: Tests for MetricsReportHandler

Status:               DONE
Spec ref:             Spec_v6 §9 row 4 — test_metrics_report.py
Invariants:           I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3
spec_refs:            [Spec_v6 §9, I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3]
produces_invariants:  []
requires_invariants:  [I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-3]
Inputs:               src/sdd/commands/metrics_report.py, src/sdd/infra/event_query.py, src/sdd/domain/metrics/aggregator.py
Outputs:              tests/unit/commands/test_metrics_report.py
Acceptance:           All of: test_report_renders_markdown, test_report_returns_empty_events, test_report_deterministic, test_report_writes_file_when_output_path_set, test_no_query_handler_in_report, test_report_no_handler_cache pass
Depends on:           T-607

---

T-609: validate_invariants.py — add check_im1_invariant (BC-VALIDATION-EXT)

Status:               DONE
Spec ref:             Spec_v6 §4.8, §5 (I-M-1-CHECK) — check_im1_invariant
Invariants:           I-M-1-CHECK, I-CHAIN-1
spec_refs:            [Spec_v6 §4.8, §5, I-M-1-CHECK, I-CHAIN-1]
produces_invariants:  [I-M-1-CHECK, I-CHAIN-1]
requires_invariants:  [I-MR-1, I-QE-1, I-QE-2, I-QE-3, I-QE-4]
Inputs:               src/sdd/commands/validate_invariants.py, src/sdd/infra/event_query.py, src/sdd/domain/metrics/aggregator.py
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           check_im1_invariant(db_path, phase_id) returns InvariantCheckResult FAIL when any TaskCompleted event lacks paired MetricRecorded(task.lead_time); returns PASS otherwise; calls EventLogQuerier + MetricsAggregator directly — no CommandHandler calls (I-CHAIN-1); existing tests in test_validate_invariants.py still pass (CEP-3)
Depends on:           T-601, T-605

---

T-610: Tests for check_im1_invariant in validate_invariants

Status:               DONE
Spec ref:             Spec_v6 §9 row 5 — test_validate_invariants.py additions
Invariants:           I-M-1-CHECK, I-CHAIN-1
spec_refs:            [Spec_v6 §9, I-M-1-CHECK, I-CHAIN-1]
produces_invariants:  []
requires_invariants:  [I-M-1-CHECK, I-CHAIN-1]
Inputs:               src/sdd/commands/validate_invariants.py, tests/unit/commands/test_validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           All of: test_check_im1_pass, test_check_im1_fail_missing_metric, test_check_im1_fail_reports_task_ids, test_no_command_handler_in_im1_check added and passing; existing tests unmodified and passing
Depends on:           T-609

---

T-611: hooks/log_tool.py + C-1 event registration (BC-HOOKS + BC-CORE + BC-STATE)

Status:               DONE
Spec ref:             Spec_v6 §2.4, §3, §4.9, §5 (I-HOOK-1..4, I-HOOKS-ISO, C-1) — log_tool.py, ToolUseStartedEvent, ToolUseCompletedEvent, HookErrorEvent, _KNOWN_NO_HANDLER, V1_L1_EVENT_TYPES
Invariants:           I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, C-1
spec_refs:            [Spec_v6 §2.4, §3, §4.9, §5, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, C-1]
produces_invariants:  [I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, C-1]
requires_invariants:  [I-EL-7, I-EL-9, I-PK-1]
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py, src/sdd/infra/event_log.py, .sdd/config/project_profile.yaml
Outputs:              src/sdd/hooks/log_tool.py, src/sdd/core/events.py, src/sdd/domain/state/reducer.py, .sdd/config/project_profile.yaml
Acceptance:           All three new event types (ToolUseStarted, ToolUseCompleted, HookError) added atomically to _KNOWN_NO_HANDLER and V1_L1_EVENT_TYPES; C-1 import-time assertion still passes; log_tool.py always exits 0 (normal + double-failure paths); ToolUseStarted/ToolUseCompleted written with event_source="meta", level="L2"; HookError written with level="L3"; hooks/ imports only from infra/event_log.py, core/events.py, and stdlib (I-HOOKS-ISO); project_profile.yaml grep rule added for I-HOOKS-ISO enforcement
Depends on:           —

---

T-612: hooks/log_bash.py — legacy stub

Status:               DONE
Spec ref:             Spec_v6 §2.4, §1 — log_bash.py delegates to log_tool.py
Invariants:           —
spec_refs:            [Spec_v6 §2.4]
produces_invariants:  []
requires_invariants:  [I-HOOK-2]
Inputs:               src/sdd/hooks/log_tool.py
Outputs:              src/sdd/hooks/log_bash.py
Acceptance:           log_bash.py delegates all arguments to log_tool.py and exits 0; no independent logic; no imports from commands/domain/guards (I-HOOKS-ISO)
Depends on:           T-611

---

T-613: Tests for hooks/log_tool.py (subprocess only)

Status:               DONE
Spec ref:             Spec_v6 §9 rows 6–7 — tests/unit/hooks/__init__.py, test_log_tool.py
Invariants:           I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO
spec_refs:            [Spec_v6 §9, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO]
produces_invariants:  []
requires_invariants:  [I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO]
Inputs:               src/sdd/hooks/log_tool.py, src/sdd/hooks/log_bash.py, src/sdd/infra/db.py
Outputs:              tests/unit/hooks/__init__.py, tests/unit/hooks/test_log_tool.py
Acceptance:           All of: test_hook_exits_zero_on_success, test_hook_exits_zero_on_exception, test_hook_exits_zero_on_double_failure, test_hook_uses_meta_source, test_hook_event_level_l2, test_hook_error_event_level_l3, test_hook_pre_emits_tool_use_started, test_hook_post_emits_tool_use_completed, test_hook_emits_error_event_on_failure, test_hook_logs_stderr_on_double_failure pass; all tests invoke log_tool.py via subprocess.run only (no direct import — I-HOOKS-ISO); existing test_c1_assert_phase5_import still passes
Depends on:           T-611, T-612

---

T-614: Phase Integration Verification (§PHASE-INV coverage)

Status:               DONE
Spec ref:             Spec_v6 §5 §PHASE-INV — all Phase 6 invariants PASS
Invariants:           I-CHAIN-1, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-MR-1, I-MR-2, I-M-1-CHECK, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, I-PROJ-CONST-1, I-PROJ-CONST-2, I-PROJ-CONST-3, C-1
spec_refs:            [Spec_v6 §5, §PHASE-INV]
produces_invariants:  []
requires_invariants:  [I-CHAIN-1, I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-MR-1, I-MR-2, I-M-1-CHECK, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, I-PROJ-CONST-1, I-PROJ-CONST-2, I-PROJ-CONST-3, C-1]
Inputs:               src/sdd/infra/event_query.py, src/sdd/commands/query_events.py, src/sdd/domain/metrics/aggregator.py, src/sdd/commands/metrics_report.py, src/sdd/commands/validate_invariants.py, src/sdd/hooks/log_tool.py, src/sdd/hooks/log_bash.py, src/sdd/core/events.py, src/sdd/domain/state/reducer.py, tests/unit/infra/test_event_query.py, tests/unit/commands/test_query_events.py, tests/unit/domain/metrics/test_aggregator.py, tests/unit/commands/test_metrics_report.py, tests/unit/commands/test_validate_invariants.py, tests/unit/hooks/test_log_tool.py
Outputs:              .sdd/reports/ValidationReport_T-614.md
Acceptance:           ValidationReport confirms all §PHASE-INV invariants PASS; all T-601..T-613 DONE; existing test_c1_assert_phase5_import still passes; no code produced in this task
Depends on:           T-601, T-602, T-603, T-604, T-605, T-606, T-607, T-608, T-609, T-610, T-611, T-612, T-613

---

<!-- Granularity: 14 tasks (TG-2 compliant: 10–30 range). Each task independently implementable and testable (TG-1). -->
