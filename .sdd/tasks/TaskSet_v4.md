# TaskSet_v4 — Phase 4: Commands Layer

Spec: specs/Spec_v4_Commands.md
Plan: plans/Plan_v4.md

---

T-401: Core event dataclasses + reducer handlers (C-1 atomic)

Status:               DONE
Spec ref:             Spec_v4 §3 Domain Events, §8 C-1 Compliance
Invariants:           I-CMD-9
spec_refs:            [Spec_v4 §3, Spec_v4 §8, I-CMD-9]
produces_invariants:  [I-CMD-9]
requires_invariants:  [I-TS-2, I-EL-9, I-ST-10]
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Acceptance:           TaskImplementedEvent, TaskValidatedEvent, PhaseCompletedEvent, DecisionRecordedEvent
                      are frozen dataclasses; DecisionRecorded in V1_L1_EVENT_TYPES;
                      TaskImplemented + TaskValidated in _EVENT_SCHEMA; PhaseCompleted + DecisionRecorded
                      in _KNOWN_NO_HANDLER; import-time C-1 assert passes
Depends on:           —

---

T-402: Tests — core event dataclasses + reducer (C-1)

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 1
Invariants:           I-CMD-9
spec_refs:            [Spec_v4 §9, I-CMD-9]
produces_invariants:  []
requires_invariants:  [I-CMD-9]
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              tests/unit/core/test_events_commands.py
Acceptance:           test_task_implemented_event_is_frozen, test_c1_assert_passes_after_import,
                      test_decision_recorded_in_v1_l1_types, test_reducer_handles_task_implemented,
                      test_reducer_handles_task_validated all pass
Depends on:           T-401

---

T-403: EventStore — single atomic write path (infra/event_store.py NEW)

Status:               DONE
Spec ref:             Spec_v4 §4.12 EventStore, §2.0 Canonical Data Flow
Invariants:           I-ES-1
spec_refs:            [Spec_v4 §4.12, Spec_v4 §2.0, I-ES-1]
produces_invariants:  [I-ES-1]
requires_invariants:  [I-EL-9, I-PK-2, I-PK-3]
Inputs:               src/sdd/infra/db.py, src/sdd/core/events.py, src/sdd/core/types.py
Outputs:              src/sdd/infra/event_store.py
Acceptance:           EventStore.append() routes through sdd_append_batch (I-EL-9); atomic on batch;
                      no direct duckdb.connect; EventStoreError raised on DB write failure
Depends on:           T-401

---

T-404: Tests — EventStore atomic write path

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 2a
Invariants:           I-ES-1
spec_refs:            [Spec_v4 §9, I-ES-1]
produces_invariants:  []
requires_invariants:  [I-ES-1]
Inputs:               src/sdd/infra/event_store.py, src/sdd/infra/db.py
Outputs:              tests/unit/infra/test_event_store.py
Acceptance:           test_append_is_atomic, test_append_only_write_path,
                      test_crash_before_append_leaves_files_unchanged,
                      test_event_store_routes_through_infra_db all pass
Depends on:           T-403

---

T-405: Projections — rebuild_taskset + rebuild_state (infra/projections.py NEW)

Status:               DONE
Spec ref:             Spec_v4 §2 BC-INFRA extensions, I-ES-4, I-ES-5
Invariants:           I-ES-4, I-ES-5
spec_refs:            [Spec_v4 §2, I-ES-4, I-ES-5]
produces_invariants:  [I-ES-4, I-ES-5]
requires_invariants:  [I-ES-1, I-PK-5, I-ST-9]
Inputs:               src/sdd/infra/event_store.py, src/sdd/infra/db.py,
                      src/sdd/domain/state/reducer.py, src/sdd/domain/tasks/parser.py
Outputs:              src/sdd/infra/projections.py
Acceptance:           rebuild_taskset writes TaskSet.md from EventLog replay; rebuild_state writes
                      State_index.yaml from EventLog replay; crash-recovery after partial failure
                      rebuilds correct state on next call (I-ES-5); atomic_write used (I-PK-5)
Depends on:           T-403

---

T-406: EventLog query extensions — exists_command, exists_semantic, get_error_count

Status:               DONE
Spec ref:             Spec_v4 §4.14
Invariants:           I-CMD-10, I-CMD-2b
spec_refs:            [Spec_v4 §4.14, I-CMD-10, I-CMD-2b]
produces_invariants:  [I-CMD-10, I-CMD-2b]
requires_invariants:  [I-EL-9]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           exists_command returns bool with no writes; exists_semantic uses sha256
                      canonical_json (sorted keys, no whitespace, ISO8601 UTC, no sci notation);
                      get_error_count counts ErrorEvent by command_id; no direct duckdb.connect (I-EL-9)
Depends on:           T-401

---

T-407: Tests — projections + event_log query extensions

Status:               DONE
Spec ref:             Spec_v4 §9 Verification rows 2b
Invariants:           I-CMD-10, I-CMD-2b, I-ES-5
spec_refs:            [Spec_v4 §9, I-CMD-10, I-CMD-2b, I-ES-5]
produces_invariants:  []
requires_invariants:  [I-CMD-10, I-CMD-2b, I-ES-5]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/projections.py
Outputs:              tests/unit/infra/test_event_log_commands.py,
                      tests/unit/infra/test_projections.py
Acceptance:           test_exists_command_returns_false_when_absent,
                      test_exists_command_returns_true_after_append,
                      test_exists_semantic_returns_false_when_absent,
                      test_exists_semantic_prevents_duplicate_effect,
                      test_get_error_count_zero_on_no_errors,
                      test_get_error_count_increments,
                      test_exists_command_no_side_effects,
                      test_no_direct_duckdb_connect,
                      test_rebuild_recovers_after_partial_crash all pass
Depends on:           T-405, T-406

---

T-408: CommandHandlerBase + error_event_boundary (_base.py)

Status:               DONE
Spec ref:             Spec_v4 §4.1 error_event_boundary, §4.2 CommandHandlerBase
Invariants:           I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3
spec_refs:            [Spec_v4 §4.1, Spec_v4 §4.2, I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3]
produces_invariants:  [I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3]
requires_invariants:  [I-CMD-10, I-ES-1]
Inputs:               src/sdd/infra/event_store.py, src/sdd/infra/event_log.py,
                      src/sdd/infra/db.py, src/sdd/core/types.py, src/sdd/core/events.py
Outputs:              src/sdd/commands/_base.py
Acceptance:           error_event_boundary calls same low-level sdd_append as EventStore.append()
                      internally (I-ERR-1); idempotency check runs BEFORE try/except (I-CMD-2b);
                      emit failure logs to fallback_log and re-raises original exception (I-CMD-3);
                      CommandHandlerBase holds only db_path — no EventStore reference
Depends on:           T-403, T-406

---

T-409: Tests — CommandHandlerBase + error_event_boundary

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 3
Invariants:           I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3
spec_refs:            [Spec_v4 §9, I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3]
produces_invariants:  []
requires_invariants:  [I-ERR-1, I-CMD-2, I-CMD-2b, I-CMD-3]
Inputs:               src/sdd/commands/_base.py
Outputs:              tests/unit/commands/test_base.py
Acceptance:           test_error_boundary_emits_before_reraise,
                      test_error_boundary_reraises_always,
                      test_error_boundary_does_not_suppress,
                      test_retry_count_zero_on_first_error,
                      test_retry_count_increments_on_second_error,
                      test_emit_failure_reraises_original_not_emit_error,
                      test_emit_failure_logs_to_fallback,
                      test_idempotent_check_skips_boundary,
                      test_semantic_idempotent_skips_boundary all pass
Depends on:           T-408

---

T-410: CompleteTaskHandler (commands/update_state.py)

Status:               DONE
Spec ref:             Spec_v4 §4.3, §6 Pre/Post Conditions, §7 UC-4-1, UC-4-2
Invariants:           I-CMD-1, I-CMD-4, I-ES-2
spec_refs:            [Spec_v4 §4.3, Spec_v4 §6, Spec_v4 §7, I-CMD-1, I-CMD-4, I-ES-2]
produces_invariants:  [I-CMD-1, I-CMD-4, I-ES-2]
requires_invariants:  [I-ERR-1, I-CMD-2, I-CMD-2b, I-ES-1, I-ES-4, I-EL-11, I-TS-1]
Inputs:               src/sdd/commands/_base.py, src/sdd/infra/event_store.py,
                      src/sdd/infra/projections.py, src/sdd/domain/tasks/parser.py,
                      src/sdd/core/events.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           emit-first: EventStore.append([TaskImplementedEvent, MetricRecorded]) called
                      atomically BEFORE rebuild_taskset (I-ES-1, I-ES-2, I-CMD-4);
                      idempotent on command_id and semantic key (I-CMD-1, I-CMD-2b);
                      MissingContext if task not found; InvalidState if task already DONE
Depends on:           T-401, T-403, T-405, T-408

---

T-411: Tests — CompleteTaskHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 4
Invariants:           I-CMD-1, I-CMD-4, I-ES-1, I-ES-2, I-ES-4
spec_refs:            [Spec_v4 §9, I-CMD-1, I-CMD-4, I-ES-1, I-ES-2, I-ES-4]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-CMD-4, I-ES-1, I-ES-2, I-ES-4]
Inputs:               src/sdd/commands/update_state.py
Outputs:              tests/unit/commands/test_complete_task.py
Acceptance:           test_complete_task_appends_event_before_file_write,
                      test_complete_task_rebuilds_projection_after_append,
                      test_complete_task_emits_batch,
                      test_complete_task_idempotent,
                      test_complete_task_semantic_idempotent,
                      test_complete_task_missing_task_raises,
                      test_complete_task_already_done_raises,
                      test_batch_is_atomic_on_failure,
                      test_no_direct_file_write_in_handler all pass
Depends on:           T-410

---

T-412: ValidateTaskHandler (commands/update_state.py extension)

Status:               DONE
Spec ref:             Spec_v4 §4.4, §6 Pre/Post Conditions
Invariants:           I-CMD-1, I-ES-2
spec_refs:            [Spec_v4 §4.4, Spec_v4 §6, I-CMD-1, I-ES-2]
produces_invariants:  [I-CMD-1, I-ES-2]
requires_invariants:  [I-ERR-1, I-CMD-2, I-ES-1, I-ES-4, I-ST-3]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/_base.py,
                      src/sdd/infra/event_store.py, src/sdd/infra/projections.py,
                      src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           emit-first: EventStore.append([TaskValidatedEvent, MetricRecorded]) BEFORE
                      rebuild_state (I-ES-1, I-ES-4); State_index.yaml NEVER written before append;
                      idempotent by command_id (I-CMD-1)
Depends on:           T-410

---

T-413: Tests — ValidateTaskHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 5
Invariants:           I-CMD-1, I-ES-2
spec_refs:            [Spec_v4 §9, I-CMD-1, I-ES-2]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-ES-2]
Inputs:               src/sdd/commands/update_state.py
Outputs:              tests/unit/commands/test_validate_task.py
Acceptance:           test_validate_pass_updates_state, test_validate_fail_updates_state,
                      test_validate_task_idempotent, test_validate_emits_task_validated_event all pass
Depends on:           T-412

---

T-414: SyncStateHandler (commands/update_state.py extension)

Status:               DONE
Spec ref:             Spec_v4 §4.5
Invariants:           I-CMD-1, I-CMD-8, I-ES-2
spec_refs:            [Spec_v4 §4.5, I-CMD-1, I-CMD-8, I-ES-2]
produces_invariants:  [I-CMD-1, I-CMD-8, I-ES-2]
requires_invariants:  [I-ERR-1, I-CMD-2, I-ES-1, I-ES-4, I-PK-5]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/_base.py,
                      src/sdd/infra/event_store.py, src/sdd/infra/projections.py,
                      src/sdd/core/events.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           emit-first: StateSyncedEvent appended before rebuild_state (I-ES-1);
                      atomic_write used by rebuild_state (I-PK-5); idempotent (I-CMD-1)
Depends on:           T-412

---

T-415: Tests — SyncStateHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 6
Invariants:           I-CMD-1, I-CMD-8, I-ES-2
spec_refs:            [Spec_v4 §9, I-CMD-1, I-CMD-8, I-ES-2]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-CMD-8, I-ES-2]
Inputs:               src/sdd/commands/update_state.py
Outputs:              tests/unit/commands/test_sync_state.py
Acceptance:           test_sync_state_writes_atomically, test_sync_state_emits_synced_event,
                      test_sync_state_idempotent, test_sync_uses_atomic_write all pass
Depends on:           T-414

---

T-416: CheckDoDHandler (commands/update_state.py extension) + DoDNotMet (core/errors.py)

Status:               DONE
Spec ref:             Spec_v4 §4.6, §4.15, §7 UC-4-4
Invariants:           I-CMD-1, I-CMD-5, I-ES-2
spec_refs:            [Spec_v4 §4.6, Spec_v4 §4.15, Spec_v4 §7, I-CMD-1, I-CMD-5, I-ES-2]
produces_invariants:  [I-CMD-1, I-CMD-5, I-ES-2]
requires_invariants:  [I-ERR-1, I-CMD-2, I-ES-1, I-ST-3]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/_base.py,
                      src/sdd/infra/event_store.py, src/sdd/domain/state/reducer.py,
                      src/sdd/core/events.py, src/sdd/core/errors.py
Outputs:              src/sdd/commands/update_state.py, src/sdd/core/errors.py
Acceptance:           DoDNotMet(SDDError) defined in core/errors.py; CheckDoDHandler emits
                      PhaseCompletedEvent + MetricRecorded atomically only when all three DoD
                      conditions pass; raises DoDNotMet otherwise (I-CMD-5); idempotent (I-CMD-1)
Depends on:           T-414

---

T-417: Tests — CheckDoDHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 7
Invariants:           I-CMD-1, I-CMD-5
spec_refs:            [Spec_v4 §9, I-CMD-1, I-CMD-5]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-CMD-5]
Inputs:               src/sdd/commands/update_state.py, src/sdd/core/errors.py
Outputs:              tests/unit/commands/test_check_dod.py
Acceptance:           test_check_dod_emits_phase_completed_when_all_pass,
                      test_check_dod_raises_if_tasks_incomplete,
                      test_check_dod_raises_if_invariants_fail,
                      test_check_dod_raises_if_tests_fail,
                      test_check_dod_idempotent,
                      test_phase_completed_batch_atomic all pass
Depends on:           T-416

---

T-418: ValidateInvariantsHandler (commands/validate_invariants.py)

Status:               DONE
Spec ref:             Spec_v4 §4.7, I-CMD-6, I-CMD-13
Invariants:           I-CMD-1, I-CMD-6, I-CMD-13, I-ES-2
spec_refs:            [Spec_v4 §4.7, I-CMD-1, I-CMD-6, I-CMD-13, I-ES-2]
produces_invariants:  [I-CMD-1, I-CMD-6, I-CMD-13, I-ES-2]
requires_invariants:  [I-ERR-1, I-CMD-2, I-ES-1, I-PK-4]
Inputs:               src/sdd/commands/_base.py, src/sdd/infra/event_store.py,
                      src/sdd/core/events.py, src/sdd/core/types.py,
                      .sdd/config/project_profile.yaml
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           pure emitter — handler does NOT call EventStore; runs all build.commands
                      in order with explicit cwd/env_whitelist/timeout_secs; stdout normalized to
                      ≤4096 bytes with ANSI stripped; individual failure does not abort loop (I-CMD-6);
                      no os.environ fallback (I-CMD-13); idempotent by command_id (I-CMD-1)
Depends on:           T-401, T-403, T-408

---

T-419: Tests — ValidateInvariantsHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 8
Invariants:           I-CMD-1, I-CMD-6, I-CMD-13
spec_refs:            [Spec_v4 §9, I-CMD-1, I-CMD-6, I-CMD-13]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-CMD-6, I-CMD-13]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           test_runs_all_build_commands, test_emits_metric_per_command,
                      test_continues_on_failure, test_no_extra_commands,
                      test_validate_inv_idempotent,
                      test_subprocess_uses_explicit_cwd,
                      test_subprocess_env_whitelist,
                      test_subprocess_timeout_raises all pass
Depends on:           T-418

---

T-420: ValidateConfigHandler (commands/validate_config.py)

Status:               DONE
Spec ref:             Spec_v4 §4.8
Invariants:           I-CMD-1
spec_refs:            [Spec_v4 §4.8, I-CMD-1]
produces_invariants:  [I-CMD-1]
requires_invariants:  [I-ERR-1, I-CMD-2, I-ES-1, I-PK-4]
Inputs:               src/sdd/commands/_base.py, src/sdd/infra/event_store.py,
                      src/sdd/core/types.py, src/sdd/core/errors.py,
                      .sdd/config/project_profile.yaml
Outputs:              src/sdd/commands/validate_config.py
Acceptance:           raises ConfigValidationError with field path on schema violation;
                      returns [] on success (no events); re-running is safe by design;
                      _check_idempotent call retained for structural consistency
Depends on:           T-401, T-403, T-408

---

T-421: Tests — ValidateConfigHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 9
Invariants:           I-CMD-1
spec_refs:            [Spec_v4 §9, I-CMD-1]
produces_invariants:  []
requires_invariants:  [I-CMD-1]
Inputs:               src/sdd/commands/validate_config.py
Outputs:              tests/unit/commands/test_validate_config.py
Acceptance:           test_valid_config_returns_empty, test_missing_required_field_raises,
                      test_validate_config_idempotent all pass
Depends on:           T-420

---

T-422: ReportErrorHandler (commands/report_error.py) + RecordDecisionHandler (commands/record_decision.py)

Status:               DONE
Spec ref:             Spec_v4 §4.9, §4.10, §7 UC-4-6
Invariants:           I-CMD-1
spec_refs:            [Spec_v4 §4.9, Spec_v4 §4.10, Spec_v4 §7, I-CMD-1, I-CMD-9]
produces_invariants:  [I-CMD-1]
requires_invariants:  [I-ERR-1, I-CMD-2, I-CMD-9, I-ES-1]
Inputs:               src/sdd/commands/_base.py, src/sdd/infra/event_store.py,
                      src/sdd/core/events.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/report_error.py, src/sdd/commands/record_decision.py
Acceptance:           ReportErrorHandler emits ErrorEvent with retry_count=0 (never calls
                      get_error_count); RecordDecisionHandler validates decision_id matches D-*
                      pattern and summary ≤ 500 chars; semantic idempotency keyed on
                      decision_id + phase_id; both idempotent by command_id (I-CMD-1)
Depends on:           T-401, T-403, T-408

---

T-423: Tests — ReportErrorHandler + RecordDecisionHandler

Status:               DONE
Spec ref:             Spec_v4 §9 Verification rows 10–11
Invariants:           I-CMD-1, I-CMD-9
spec_refs:            [Spec_v4 §9, I-CMD-1, I-CMD-9]
produces_invariants:  []
requires_invariants:  [I-CMD-1, I-CMD-9]
Inputs:               src/sdd/commands/report_error.py, src/sdd/commands/record_decision.py
Outputs:              tests/unit/commands/test_report_error.py,
                      tests/unit/commands/test_record_decision.py
Acceptance:           test_report_error_emits_error_event, test_report_error_retry_count_zero,
                      test_report_error_idempotent,
                      test_record_decision_emits_event, test_record_decision_idempotent,
                      test_decision_recorded_event_fields all pass
Depends on:           T-422

---

T-424: DependencyGuard + GuardContext.task_graph + NormCatalog default=DENY

Status:               DONE
Spec ref:             Spec_v4 §4.13 GuardContext, §4.11 guard pipeline step 3,
                      I-CMD-11, I-CMD-12, I-ES-3
Invariants:           I-CMD-11, I-CMD-12, I-ES-3
spec_refs:            [Spec_v4 §4.13, Spec_v4 §4.11, I-CMD-11, I-CMD-12, I-ES-3]
produces_invariants:  [I-CMD-11, I-CMD-12, I-ES-3]
requires_invariants:  [I-GRD-4, I-GRD-1, I-GRD-2, I-GRD-3, I-GRD-5, I-GRD-6,
                       I-GRD-7, I-GRD-8, I-GRD-9]
Inputs:               src/sdd/domain/guards/context.py, src/sdd/domain/norms/catalog.py,
                      src/sdd/infra/db.py, src/sdd/domain/state/reducer.py,
                      src/sdd/core/types.py
Outputs:              src/sdd/domain/guards/dependency_guard.py,
                      src/sdd/domain/guards/context.py,
                      src/sdd/domain/norms/catalog.py
Acceptance:           DependencyGuard is pure: returns (GuardResult, list[DomainEvent]) with NO I/O
                      or mutations (I-ES-3); DENY if any dependency not DONE in EventLog;
                      GuardContext.task_graph field added; state built from EventLog replay not
                      YAML projection (I-CMD-11); NormCatalog default=DENY for any unlisted
                      actor/action pair (I-CMD-12)
Depends on:           T-401, T-403

---

T-425: Tests — DependencyGuard + NormCatalog default=DENY + GuardContext from replay

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 12 (guards portion)
Invariants:           I-CMD-11, I-CMD-12
spec_refs:            [Spec_v4 §9, I-CMD-11, I-CMD-12]
produces_invariants:  []
requires_invariants:  [I-CMD-11, I-CMD-12]
Inputs:               src/sdd/domain/guards/dependency_guard.py,
                      src/sdd/domain/guards/context.py,
                      src/sdd/domain/norms/catalog.py
Outputs:              tests/unit/guards/test_dependency_guard.py,
                      tests/unit/guards/test_norm_guard_default_deny.py,
                      tests/unit/guards/test_guard_context_from_replay.py
Acceptance:           test_dependency_guard_deny_if_dependency_not_done,
                      test_dependency_guard_allow_if_all_dependencies_done,
                      test_dependency_guard_is_pure_no_io,
                      test_norm_guard_default_deny_for_unlisted_action,
                      test_guard_context_state_from_eventlog_replay all pass
Depends on:           T-424

---

T-426: CommandRunner + run_guard_pipeline + commands/__init__.py (sdd_run.py)

Status:               DONE
Spec ref:             Spec_v4 §4.11 CommandRunner, §7 UC-4-5, §8 Integration
Invariants:           I-CMD-7, I-ES-3
spec_refs:            [Spec_v4 §4.11, Spec_v4 §7, Spec_v4 §8, I-CMD-7, I-ES-3]
produces_invariants:  [I-CMD-7, I-ES-3]
requires_invariants:  [I-CMD-1, I-ES-1, I-ES-5, I-GRD-4, I-CMD-11, I-CMD-12]
Inputs:               src/sdd/commands/_base.py, src/sdd/commands/update_state.py,
                      src/sdd/commands/validate_invariants.py, src/sdd/commands/validate_config.py,
                      src/sdd/commands/report_error.py, src/sdd/commands/record_decision.py,
                      src/sdd/infra/event_store.py, src/sdd/infra/projections.py,
                      src/sdd/domain/guards/dependency_guard.py,
                      src/sdd/domain/guards/context.py, src/sdd/domain/norms/catalog.py,
                      src/sdd/domain/state/reducer.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/sdd_run.py, src/sdd/commands/__init__.py
Acceptance:           run_guard_pipeline is a standalone pure module-level function (I-GRD-4);
                      guard DENY → CommandRunner appends audit_events via EventStore, returns [],
                      handler NOT called (I-CMD-7); GuardContext.state from EventLog replay
                      (I-CMD-11); DependencyGuard wired as step 3; pre-run rebuild (step 1) and
                      post-append rebuild (step 7) are structurally separate; __init__.py re-exports
                      all Command dataclasses, all Handler classes, CommandRunner, error_event_boundary
Depends on:           T-403, T-405, T-408, T-410, T-412, T-414, T-416, T-418, T-420, T-422, T-424

---

T-427: Tests — CommandRunner + run_guard_pipeline + §PHASE-INV ValidationReport

Status:               DONE
Spec ref:             Spec_v4 §9 Verification row 12, §5 §PHASE-INV
Invariants:           I-CMD-7, I-ES-3, I-ES-1, I-ES-2, I-ES-3, I-ES-4, I-ES-5,
                      I-CMD-1, I-CMD-2, I-CMD-2b, I-CMD-3, I-CMD-4, I-CMD-5, I-CMD-6,
                      I-CMD-7, I-CMD-8, I-CMD-9, I-CMD-10, I-CMD-11, I-CMD-12, I-CMD-13, I-ERR-1
spec_refs:            [Spec_v4 §9, Spec_v4 §5, I-CMD-7, I-ES-3]
produces_invariants:  []
requires_invariants:  [I-CMD-7, I-ES-3, I-CMD-11, I-CMD-12]
Inputs:               src/sdd/commands/sdd_run.py, src/sdd/commands/__init__.py,
                      tests/unit/commands/test_complete_task.py,
                      tests/unit/commands/test_validate_task.py,
                      tests/unit/commands/test_sync_state.py,
                      tests/unit/commands/test_check_dod.py,
                      tests/unit/commands/test_validate_invariants.py,
                      tests/unit/commands/test_validate_config.py,
                      tests/unit/commands/test_report_error.py,
                      tests/unit/commands/test_record_decision.py,
                      tests/unit/commands/test_base.py,
                      tests/unit/infra/test_event_store.py,
                      tests/unit/infra/test_projections.py,
                      tests/unit/infra/test_event_log_commands.py,
                      tests/unit/guards/test_dependency_guard.py,
                      tests/unit/guards/test_norm_guard_default_deny.py
Outputs:              tests/unit/commands/test_sdd_run.py,
                      tests/unit/commands/test_run_guard_pipeline.py,
                      .sdd/reports/ValidationReport_T-427.md
Acceptance:           test_guard_deny_skips_handler, test_guard_allow_runs_handler,
                      test_guard_deny_returns_empty,
                      test_guard_deny_appends_audit_events_via_event_store,
                      test_guard_deny_emits_no_handler_events,
                      test_guards_are_pure_no_side_effects,
                      test_dependency_guard_wired_as_step3,
                      test_norm_default_deny, test_all_guards_wired,
                      test_runner_does_not_catch_handler_exceptions all pass;
                      ValidationReport_T-427.md documents coverage of all §PHASE-INV invariants
                      [I-ES-1..5, I-CMD-1..13, I-ERR-1]
Depends on:           T-426, T-409, T-411, T-413, T-415, T-417, T-419, T-421, T-423, T-425

---

<!-- Granularity: 27 tasks (TG-2 range: 10–30). All tasks independently implementable and testable (TG-1). -->
