# TaskSet_v15 — Phase 15: Kernel Unification & Event-Sourced Control Plane

Spec: specs/Spec_v15_KernelUnification.md
Plan: plans/Plan_v15.md

---

## M1: Event & Reducer Foundation — Add Core Infrastructure

T-1501: core/events.py + domain/state/reducer.py — atomic event+reducer commit

Status:               DONE
Spec ref:             Spec_v15 §2 BC-1 core/events.py; §2 BC-2 reducer.py; §3 Domain Events
Invariants:           I-C1-ATOMIC-1, I-PHASE-STARTED-1, I-PHASE-COMPLETE-1, I-PHASE-RESET-1, I-PHASE-SEQ-1, I-PHASE-ORDER-1
spec_refs:            [Spec_v15 §2 BC-1, Spec_v15 §2 BC-2, Spec_v15 §3, I-C1-ATOMIC-1]
produces_invariants:  [I-C1-ATOMIC-1, I-PHASE-STARTED-1, I-PHASE-COMPLETE-1, I-PHASE-RESET-1, I-PHASE-SEQ-1, I-PHASE-ORDER-1]
requires_invariants:  []
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Acceptance:           pytest tests/ -q green; PhaseStartedEvent, TaskSetDefinedEvent, ErrorEvent importable from core.events; reducer handlers for PhaseCompleted, PhaseStarted, TaskSetDefined, PhaseInitialized pass unit tests
Depends on:           —

---

T-1502: infra/projections.py — RebuildMode + pure-reduce path

Status:               DONE
Spec ref:             Spec_v15 §2 BC-2 infra/projections.py; §1 Scope (projections)
Invariants:           I-REBUILD-STRICT-1, I-REBUILD-EMERGENCY-1, I-REBUILD-EMERGENCY-2, I-ES-REPLAY-1
spec_refs:            [Spec_v15 §2 BC-2, I-REBUILD-STRICT-1, I-REBUILD-EMERGENCY-1, I-ES-REPLAY-1]
produces_invariants:  [I-REBUILD-STRICT-1, I-REBUILD-EMERGENCY-1, I-REBUILD-EMERGENCY-2, I-ES-REPLAY-1]
requires_invariants:  [I-PHASE-STARTED-1]
Inputs:               src/sdd/infra/projections.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/infra/projections.py
Acceptance:           pytest tests/ -q green; RebuildMode.STRICT default path ignores YAML; EMERGENCY requires SDD_EMERGENCY=1 env var; rebuild_taskset guards missing file gracefully
Depends on:           T-1501

---

T-1503: core/errors.py — SDDError subclass hierarchy

Status:               DONE
Spec ref:             Spec_v15 §4 Types & Interfaces; §2 BC-15-REGISTRY (error hierarchy)
Invariants:           I-ERROR-1, I-ERROR-L2-1, I-ERROR-SINGLE-TYPE-1, I-ERROR-PHASE-NULL-1
spec_refs:            [Spec_v15 §4, Spec_v15 §2 BC-15-REGISTRY, I-ERROR-1, I-ERROR-SINGLE-TYPE-1]
produces_invariants:  [I-ERROR-1, I-ERROR-L2-1, I-ERROR-SINGLE-TYPE-1, I-ERROR-PHASE-NULL-1]
requires_invariants:  []
Inputs:               src/sdd/core/errors.py
Outputs:              src/sdd/core/errors.py
Acceptance:           pytest tests/ -q green; all 7 SDDError subclasses importable (GuardViolationError error_code=1 … KernelInvariantError error_code=7); DomainEvent.phase_id declared as int|None=None
Depends on:           —

---

T-1504: core/events.py + domain/guards/context.py — compute_command_id, compute_trace_id, compute_context_hash; GuardResult extensions

Status:               DONE
Spec ref:             Spec_v15 §2 BC-15-REGISTRY execute_command A-7, A-9, A-10, A-13, A-22; §4 Types & Interfaces
Invariants:           I-IDEM-1, I-DIAG-1, I-TRACE-FALLBACK-1, I-CONTEXT-HASH-SENTINEL-1
spec_refs:            [Spec_v15 §2 BC-15-REGISTRY, Spec_v15 §4, I-IDEM-1, I-DIAG-1, I-TRACE-FALLBACK-1]
produces_invariants:  [I-IDEM-1, I-DIAG-1, I-TRACE-FALLBACK-1, I-CONTEXT-HASH-SENTINEL-1]
requires_invariants:  [I-ERROR-PHASE-NULL-1]
Inputs:               src/sdd/core/events.py, src/sdd/domain/guards/context.py
Outputs:              src/sdd/core/events.py, src/sdd/domain/guards/context.py
Acceptance:           pytest tests/ -q green; compute_command_id returns 32-hex deterministic from dataclasses.asdict+json.dumps; compute_trace_id falls back to sha256 when head_seq is None; context_hash is str always non-None; GuardResult has reason/human_reason/violated_invariant optional fields
Depends on:           T-1501, T-1503

---

T-1505: guards/pipeline.py — run_guard_pipeline moved from sdd_run.py

Status:               DONE
Spec ref:             Spec_v15 §2 BC-15-GUARDS-PIPELINE; §1 Scope (Amendment A-3)
Invariants:           I-PIPELINE-HOME-1
spec_refs:            [Spec_v15 §2 BC-15-GUARDS-PIPELINE, I-PIPELINE-HOME-1]
produces_invariants:  [I-PIPELINE-HOME-1]
requires_invariants:  []
Inputs:               src/sdd/commands/sdd_run.py, src/sdd/guards/pipeline.py
Outputs:              src/sdd/guards/pipeline.py
Acceptance:           pytest tests/ -q green; from sdd.guards.pipeline import run_guard_pipeline importable; sdd_run.py retains its copy (deletion deferred to T-1522)
Depends on:           T-1503, T-1504

---

T-1506: commands/registry.py — CommandSpec, REGISTRY, execute_command, project_all, execute_and_project; DuckDB schema migration

Status:               DONE
Spec ref:             Spec_v15 §2 BC-15-REGISTRY (execute_command steps 0–5, A-7..A-22); §2 REGISTRY dict (6 entries); §2 DuckDB schema
Invariants:           I-IDEM-SCHEMA-1, I-IDEM-LOG-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1, I-ATOMICITY-1, I-RETRY-POLICY-1, I-CMD-PAYLOAD-PHASE-1, I-CMD-PHASE-RESOLVE-1, I-SYNC-NO-PHASE-GUARD-1, I-DECISION-AUDIT-1, I-READ-ONLY-EXCEPTION-1
spec_refs:            [Spec_v15 §2 BC-15-REGISTRY, I-IDEM-SCHEMA-1, I-OPTLOCK-ATOMIC-1, I-ATOMICITY-1, I-SYNC-NO-PHASE-GUARD-1]
produces_invariants:  [I-IDEM-SCHEMA-1, I-IDEM-LOG-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1, I-ATOMICITY-1, I-RETRY-POLICY-1, I-SYNC-NO-PHASE-GUARD-1, I-DECISION-AUDIT-1]
requires_invariants:  [I-PIPELINE-HOME-1, I-IDEM-1, I-DIAG-1]
Inputs:               src/sdd/core/events.py, src/sdd/core/types.py, src/sdd/core/errors.py, src/sdd/domain/guards/context.py, src/sdd/guards/pipeline.py, src/sdd/infra/event_store.py, src/sdd/infra/projections.py, src/sdd/infra/paths.py, src/sdd/commands/_base.py
Outputs:              src/sdd/commands/registry.py, src/sdd/infra/event_store.py
Acceptance:           pytest tests/ -q green (including tmp_path isolated DuckDB tests); execute_command passes guard pipeline + emits events atomically; UNIQUE(command_id, event_index) present in schema; ON CONFLICT DO NOTHING idempotent; all 6 REGISTRY entries importable; execute_and_project wraps project_all with ProjectionError boundary
                      # I-KERNEL-FLOW-1 реализован здесь фактически, но формально закреплён в T-1520 (AST) + T-1522 (CLAUDE.md)
Depends on:           T-1501, T-1502, T-1503, T-1504, T-1505

---

T-1507: commands/_base.py — NoOpHandler

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands
Invariants:           I-HANDLER-PURE-1
spec_refs:            [Spec_v15 §2 BC-4, I-HANDLER-PURE-1]
produces_invariants:  [I-HANDLER-PURE-1]
requires_invariants:  []
Inputs:               src/sdd/commands/_base.py, src/sdd/core/types.py
Outputs:              src/sdd/commands/_base.py
Acceptance:           pytest tests/ -q green; NoOpHandler().handle(cmd) returns []; NoOpHandler is subclass of CommandHandlerBase
Depends on:           —

---

## M2: Command Routing — Switch Each Command Through the Kernel

T-1510: commands/update_state.py — sync-state via NoOpHandler + execute_and_project

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands; §7 UC-15-5; Amendment A-20
Invariants:           I-SPEC-EXEC-1, I-SYNC-NO-PHASE-GUARD-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1
spec_refs:            [Spec_v15 §2 BC-4, Spec_v15 §7 UC-15-5, I-SPEC-EXEC-1, I-SYNC-NO-PHASE-GUARD-1]
produces_invariants:  []
                      # I-SYNC-NO-PHASE-GUARD-1 уже произведён T-1506; T-1510 подтверждает применение к sync-state
requires_invariants:  [I-ATOMICITY-1, I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/registry.py, src/sdd/commands/_base.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           pytest tests/ -q green; sdd sync-state routes through execute_and_project(REGISTRY["sync-state"]); SyncStateHandler replaced with NoOpHandler; PhaseGuard is skipped (requires_active_phase=False)
Depends on:           T-1506, T-1507

---

T-1511: commands/update_state.py — complete via purified handler + execute_and_project

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands; §7 UC-15-1; I-HANDLER-PURE-1
Invariants:           I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v15 §2 BC-4, Spec_v15 §7 UC-15-1, I-HANDLER-PURE-1, I-KERNEL-WRITE-1]
produces_invariants:  [I-KERNEL-WRITE-1]
                      # I-HANDLER-PURE-1 уже произведён T-1507; I-KERNEL-WRITE-1 — первый handler, убирающий EventStore.append из handle()
requires_invariants:  [I-ATOMICITY-1, I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           pytest tests/ -q green; CompleteTaskHandler.handle() has no EventStore.append or sync_projections calls; sdd complete routes through execute_and_project(REGISTRY["complete"])
Depends on:           T-1506, T-1510

---

T-1512: commands/update_state.py — validate via purified handler + execute_and_project

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands; §7 UC-15-2; I-HANDLER-PURE-1
Invariants:           I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v15 §2 BC-4, Spec_v15 §7 UC-15-2, I-HANDLER-PURE-1, I-KERNEL-WRITE-1]
produces_invariants:  [I-KERNEL-PROJECT-1]
                      # I-KERNEL-PROJECT-1 — первый handler, убирающий rebuild_state из handle(); I-KERNEL-WRITE-1 уже произведён T-1511
requires_invariants:  [I-ATOMICITY-1, I-IDEM-SCHEMA-1, I-KERNEL-WRITE-1]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           pytest tests/ -q green; ValidateTaskHandler.handle() has no EventStore.append or rebuild_state calls; sdd validate routes through execute_and_project(REGISTRY["validate"])
Depends on:           T-1506, T-1511

---

T-1513: commands/update_state.py — check-dod via purified handler + execute_and_project

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands; I-HANDLER-PURE-1
Invariants:           I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v15 §2 BC-4, I-HANDLER-PURE-1, I-KERNEL-WRITE-1]
produces_invariants:  [I-HANDLER-PURE-1]
requires_invariants:  [I-ATOMICITY-1, I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/update_state.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/update_state.py
Acceptance:           pytest tests/ -q green; CheckDoDHandler.handle() has no EventStore.append calls; sdd check-dod (validate --check-dod) routes through execute_and_project(REGISTRY["check-dod"])
Depends on:           T-1506, T-1512

---

T-1514: activate_phase.py + projections.py + registry.py — [PhaseStarted, PhaseInitialized] atomic batch; get_current_state(); remove PhaseActivated; handler purity (Phase_v15.5)

Status:               DONE
Spec ref:             Spec_v15 §2 BC-4 Commands; Amendment A-14; I-HANDLER-BATCH-PURE-1; specs_draft/Phase_v15.5.md §3–§7
Invariants:           I-PHASE-EMIT-1, I-PHASE-EVENT-PAIR-1, I-PROJECTION-READ-1, I-PROJECTION-READ-2,
                      I-EVENT-FORMAT-1, I-EVENT-LEVEL-1, I-REDUCER-LEGACY-1, I-LEGACY-STATE-WEAKNESS-1,
                      I-HANDLER-PURE-1, I-HANDLER-BATCH-PURE-1, I-COMMAND-RESULT-1,
                      I-STATE-ACCESS-LAYER-1
spec_refs:            [Spec_v15 §2 BC-4, I-HANDLER-BATCH-PURE-1, Phase_v15.5 §4]
produces_invariants:  [I-PHASE-EMIT-1, I-PHASE-EVENT-PAIR-1, I-PROJECTION-READ-1, I-PROJECTION-READ-2,
                       I-EVENT-FORMAT-1, I-HANDLER-BATCH-PURE-1, I-REDUCER-LEGACY-1,
                       I-STATE-ACCESS-LAYER-1, I-COMMAND-RESULT-1]
requires_invariants:  [I-C1-ATOMIC-1, I-ATOMICITY-1, I-IDEM-SCHEMA-1, I-REBUILD-STRICT-1]
Inputs:               src/sdd/commands/activate_phase.py,
                      src/sdd/infra/projections.py,
                      src/sdd/commands/registry.py,
                      src/sdd/domain/state/reducer.py,
                      tests/unit/commands/test_activate_phase.py
Outputs:              src/sdd/commands/activate_phase.py,
                      src/sdd/infra/projections.py,
                      src/sdd/commands/registry.py,
                      src/sdd/domain/state/reducer.py,
                      tests/unit/commands/test_activate_phase.py,
                      tests/unit/infra/test_projections.py,
                      tests/unit/test_event_format_contract.py
Acceptance:           pytest tests/ -q green;
                      I-PHASE-EVENT-PAIR-1 (strict): len(ActivatePhaseHandler(db).handle(cmd)) == 2 exactly;
                      result[0] is PhaseStartedEvent, result[1] is PhaseInitializedEvent (exact type + exact order);
                      result[0].phase_id == result[1].phase_id (pair consistency);
                      I-STATE-ACCESS-LAYER-1: get_current_state() callable ONLY from guards and projections;
                        activate_phase.py MUST NOT import or call get_current_state();
                        phase_guard.py MUST use get_current_state() (verified in T-1517);
                      I-PROJECTION-READ-1 (strict): get_current_state() performs full replay from seq=0;
                        no partial replay, no snapshot-based reconstruction, no caching;
                      get_current_state() в projections.py: pure, no compat fallback;
                      I-COMMAND-RESULT-1 (strict): handler.handle() return value MUST NOT be used as
                        source of truth by any caller; only persisted EventStore events define state;
                        no caller may branch on result truthiness to decide system state;
                      registry.py event_schema for activate-phase == (PhaseStartedEvent, PhaseInitializedEvent);
                      grep -rn "PhaseActivated" src/sdd/commands/ → 0 matches;
                      "PhaseActivated" in EventReducer._EVENT_SCHEMA (I-REDUCER-LEGACY-1);
                      AST test: no reduce(sdd_replay()) in src/sdd/ (I-EVENT-FORMAT-1);
                      grep -rn "sdd_replay" src/sdd/ | grep -v event_log.py → 0 matches;
                      test_activate_phase_emits_atomic_pair PASS (order + exact count + consistency);
                      test_projections.py: 3 новых теста get_current_state (no_compat_fallback, deterministic, partial_legacy);
                        + 1 тест: get_current_state replay starts at seq=0 (full history);
                      test_event_format_contract.py: absolute path, assert files_checked > 0;
                      no circular imports; pytest tests/ -v → all PASS
Depends on:           T-1506, T-1513

---

T-1514b: infra/projections.py — rebuild_state делегирует в get_current_state()

Status:               DONE
Spec ref:             specs_draft/Phase_v15.5.md §8 Q3; I-PROJECTION-READ-1; I-REBUILD-STRICT-1
Invariants:           I-PROJECTION-READ-1, I-REBUILD-STRICT-1, I-REBUILD-EMERGENCY-1, I-PROJECTION-SHARED-CORE-1
spec_refs:            [Phase_v15.5 §8 Q3, I-PROJECTION-READ-1]
produces_invariants:  [I-PROJECTION-SHARED-CORE-1]
                      # I-PROJECTION-READ-1 уже произведён T-1514; T-1514b расширяет его через I-PROJECTION-SHARED-CORE-1
requires_invariants:  [I-REBUILD-STRICT-1, I-STATE-ACCESS-LAYER-1, I-PROJECTION-READ-1]
Inputs:               src/sdd/infra/projections.py
Outputs:              src/sdd/infra/projections.py
Acceptance:           pytest tests/ -q green;
                      I-PROJECTION-SHARED-CORE-1: get_current_state() is the single source of truth for
                        EventLog → SDDState mapping; rebuild_state() MUST delegate to get_current_state()
                        and MUST NOT duplicate replay logic;
                      compat fallback (I-PROJ-2) применяется поверх результата get_current_state(), не дублирует логику;
                      rebuild_state и get_current_state не расходятся в логике replay;
                      если get_current_state() изменится, rebuild_state() подхватит изменение автоматически;
                      pytest tests/unit/infra/test_projections.py -v → all PASS
Depends on:           T-1514

---

T-1514c: registry.py step 1 + projections.py — единый replay-путь через get_current_state()

Status:               DONE
Spec ref:             Phase_v15.5 §8 Q3; I-REPLAY-PATH-1; I-PROJECTION-SHARED-CORE-1;
                      I-OPTLOCK-1; I-OPTLOCK-ATOMIC-1
Invariants:           I-REPLAY-PATH-1, I-OPTLOCK-REPLAY-1
produces_invariants:  [I-REPLAY-PATH-1, I-OPTLOCK-REPLAY-1]
requires_invariants:  [I-PROJECTION-SHARED-CORE-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/infra/projections.py
Outputs:              src/sdd/commands/registry.py, src/sdd/infra/projections.py
Acceptance:           pytest tests/ -q green;

                      I-OPTLOCK-REPLAY-1 (TOCTOU mitigation):
                        execute_command MUST capture head_seq = EventStore.max_seq() at step 0 (before replay);
                        step 1 calls get_current_state(_db) — pure replay, returns SDDState, does NOT return head_seq;
                        EventStore.append receives expected_head=head_seq from step 0 (unchanged);
                        head_seq and get_current_state() are independent calls — never conflated;
                        assert: head_seq assignment line precedes get_current_state() call in execute_command;

                      I-REPLAY-PATH-1 (production path):
                        execute_command step 1 calls get_current_state(_db) instead of _fetch_events_for_reduce;
                        _fetch_events_for_reduce() deleted from registry.py;
                        _replay_all() deleted from projections.py (absorbed into get_current_state());
                        grep -rn "_fetch_events_for_reduce\|_replay_all" src/sdd/ → 0 matches;
                        grep -n "get_current_state" src/sdd/commands/registry.py → ровно 1 match;

                      I-PROJECTION-SHARED-CORE-1 (precondition verification):
                        assert rebuild_state() is implemented as wrapper over get_current_state();
                        confirm: projections.py rebuild_state body contains call to get_current_state();
                        (гарантирует, что T-1514b выполнен перед T-1514c)
Depends on:           T-1514b

---

T-1515: commands/record_decision.py + cli.py — purify handler; add to REGISTRY; wire cli.py (Amendment A-1)

Status:               DONE
Spec ref:             Spec_v15 §1 Scope (Amendment A-1); §2 REGISTRY dict record-decision entry
Invariants:           I-HANDLER-PURE-1, I-DECISION-AUDIT-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v15 §1 Scope, Spec_v15 §2 BC-15-REGISTRY, I-HANDLER-PURE-1, I-DECISION-AUDIT-1]
produces_invariants:  [I-DECISION-AUDIT-1]
requires_invariants:  [I-ATOMICITY-1, I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/record_decision.py, src/sdd/commands/registry.py, src/sdd/cli.py,
                      src/sdd/core/events.py
Outputs:              src/sdd/commands/record_decision.py, src/sdd/cli.py
                      # REGISTRY["record-decision"] уже создан T-1506 (6-й entry); reducer._KNOWN_NO_HANDLER уже содержит
                      # "DecisionRecorded" (T-1501 DONE) — T-1515 не трогает registry.py и reducer.py
Acceptance:           pytest tests/ -q green;
                      RecordDecisionHandler.handle() returns [DecisionRecordedEvent] with no EventStore.append;
                      REGISTRY["record-decision"] exists (T-1506 DONE — verify, не modify);
                      "DecisionRecorded" in EventReducer._KNOWN_NO_HANDLER (T-1501 DONE — verify, не modify);
                      cli.py record-decision routes through execute_and_project(REGISTRY["record-decision"]);
                      cli.py НЕ читает State_index.yaml напрямую (убрать yaml.safe_load из record_decision CLI handler)
Depends on:           T-1506, T-1514

---

T-1516: commands/validate_config.py + cli.py + commands/__init__.py + core/payloads.py — replace handler with plain function; remove from payloads REGISTRY (Amendment A-2)

Status:               DONE
Spec ref:             Spec_v15 §1 Scope (Amendment A-2); §2 BC-15-REGISTRY Read-Only Path Architecture; I-READ-ONLY-EXCEPTION-1
Invariants:           I-READ-ONLY-EXCEPTION-1, I-2
spec_refs:            [Spec_v15 §1 Scope, Spec_v15 §2 BC-15-REGISTRY, I-READ-ONLY-EXCEPTION-1]
produces_invariants:  [I-READ-ONLY-EXCEPTION-1]
requires_invariants:  []
Inputs:               src/sdd/commands/validate_config.py, src/sdd/cli.py, src/sdd/commands/__init__.py, src/sdd/core/payloads.py
Outputs:              src/sdd/commands/validate_config.py, src/sdd/cli.py, src/sdd/commands/__init__.py, src/sdd/core/payloads.py
Acceptance:           pytest tests/ -q green; ValidateConfigHandler class deleted; ValidateConfigCommand dataclass deleted from payloads.py; validate_project_config(phase_id, config_path) plain function exists; cli.py validate-config calls it directly (no .handle()); ValidateConfig absent from REGISTRY (commands/registry.py)
Depends on:           T-1506, T-1515

---

T-1517: guards/phase.py + core/errors.py — remove YAML fallback; add InvalidPhaseSequence; AlreadyActivated + I-PHASE-SEQ-FORWARD-1 guard (Phase_v15.5)

Status:               DONE
Spec ref:             Spec_v15 §1 Scope (Amendment A-4); §2 BC-4 Guards; I-GUARD-CLI-1;
                      specs_draft/Phase_v15.5.md §8 Q1; I-PHASE-SEQ-FORWARD-1; I-PROJECTION-GUARD-1
Invariants:           I-GUARD-CLI-1, I-1, I-PHASE-SEQ-FORWARD-1, I-PROJECTION-GUARD-1, I-STATE-ACCESS-LAYER-1
spec_refs:            [Spec_v15 §1 Scope, Spec_v15 §2 BC-4 Guards, I-GUARD-CLI-1, Phase_v15.5 §8 Q1]
produces_invariants:  [I-GUARD-CLI-1, I-PHASE-SEQ-FORWARD-1, I-PROJECTION-GUARD-1]
requires_invariants:  [I-REBUILD-STRICT-1, I-PROJECTION-READ-1, I-STATE-ACCESS-LAYER-1]
Inputs:               src/sdd/guards/phase.py,
                      src/sdd/core/errors.py,
                      src/sdd/infra/projections.py
Outputs:              src/sdd/guards/phase.py,
                      src/sdd/core/errors.py,
                      tests/unit/guards/test_phase_guard.py
Acceptance:           pytest tests/ -q green;
                      lines 59–65 YAML fallback block absent;
                      missing --state arg exits 1 with JSON error;
                      guard pipeline itself does not call sys.exit (I-GUARD-CLI-1);
                      core/errors.py содержит InvalidPhaseSequence(SDDError);
                      phase_guard: phase_id <= state.phase_current → raises AlreadyActivated;
                      phase_guard: phase_id > state.phase_current + 1 → raises InvalidPhaseSequence;
                      phase_guard: phase_id == state.phase_current + 1 → passes (happy path);
                      I-STATE-ACCESS-LAYER-1: guard использует get_current_state() — не sdd_replay/reduce напрямую;
                        phase_guard.py MUST import and call get_current_state() from projections;
                      pytest tests/unit/guards/test_phase_guard.py -v → all PASS (3 cases above)
Depends on:           T-1502, T-1514, T-1516

---

T-1518: guards/task.py — remove YAML fallback block; migrate to get_current_state() (Amendment A-4)

Status:               DONE
Spec ref:             Spec_v15 §1 Scope (Amendment A-4); §2 BC-4 Guards; I-GUARD-CLI-1
Invariants:           I-GUARD-CLI-1, I-1, I-PROJECTION-GUARD-1, I-STATE-ACCESS-LAYER-1
spec_refs:            [Spec_v15 §1 Scope, Spec_v15 §2 BC-4 Guards, I-GUARD-CLI-1]
produces_invariants:  [I-GUARD-CLI-1, I-PROJECTION-GUARD-1]
                      # I-PROJECTION-GUARD-1 здесь — для task guard; T-1517 производит его для phase guard
requires_invariants:  [I-REBUILD-STRICT-1, I-PROJECTION-READ-1, I-STATE-ACCESS-LAYER-1]
Inputs:               src/sdd/guards/task.py, src/sdd/infra/projections.py
Outputs:              src/sdd/guards/task.py
Acceptance:           pytest tests/ -q green;
                      lines 98–105 YAML fallback block absent;
                      missing --state arg exits 1 with JSON error;
                      guard pipeline itself does not call sys.exit (I-GUARD-CLI-1);
                      I-STATE-ACCESS-LAYER-1: task_guard.py использует get_current_state() из projections — не sdd_replay/reduce напрямую;
                      grep -n "sdd_replay\|yaml.safe_load" src/sdd/guards/task.py → 0 matches
Depends on:           T-1502, T-1517

---

## M3: CI Enforcement — Grep Rules, AST Tests, Deprecation

T-1519: Makefile — check-handler-purity target with 3 grep-rules

Status:               DONE
Spec ref:             Spec_v15 §2 CI grep-rules; §9 checks #17–18, #21–23, #41; I-CI-PURITY-1..3; I-PHASE16-MIGRATION-STRICT-1
Invariants:           I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1, I-IMPL-ORDER-1
spec_refs:            [Spec_v15 §2 CI grep-rules, Spec_v15 §9, I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1]
produces_invariants:  [I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1, I-IMPL-ORDER-1]
requires_invariants:  [I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1]
Inputs:               Makefile, src/sdd/commands/validate_invariants.py, src/sdd/commands/report_error.py
Outputs:              Makefile
Acceptance:           make check-handler-purity exits 0; whitelist contains exactly validate_invariants.py and report_error.py (no 3rd file); target enforces I-KERNEL-WRITE-1 (no EventStore.append in handle()), I-KERNEL-PROJECT-1 (no rebuild_state in handle()), I-HANDLER-PURE-1 (no .handle( call inside handle()); target integrated into default make or make ci
Depends on:           T-1518

---

T-1520: tests/unit/test_handler_purity.py + tests/unit/test_registry_contract.py — AST-based enforcement

Status:               DONE
Spec ref:             Spec_v15 §2 CI grep-rules; §9 checks; I-REGISTRY-COMPLETE-1, I-READ-ONLY-EXCEPTION-1, I-PHASE16-MIGRATION-STRICT-1
Invariants:           I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-REGISTRY-COMPLETE-1, I-READ-ONLY-EXCEPTION-1, I-PHASE16-MIGRATION-STRICT-1, I-2, I-3, I-EVENT-FORMAT-1, I-KERNEL-FLOW-1
spec_refs:            [Spec_v15 §2 CI grep-rules, Spec_v15 §9, I-REGISTRY-COMPLETE-1, I-READ-ONLY-EXCEPTION-1, I-CI-PURITY-1]
produces_invariants:  [I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-REGISTRY-COMPLETE-1, I-READ-ONLY-EXCEPTION-1, I-EVENT-FORMAT-1, I-KERNEL-FLOW-1,
                       I-REPLAY-PATH-1, I-READ-PATH-1, I-GUARD-STATELESS-1, I-PIPELINE-SINGLE-SOURCE-1]
requires_invariants:  [I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-COMMAND-RESULT-1, I-STATE-ACCESS-LAYER-1,
                       I-REPLAY-PATH-1, I-OPTLOCK-REPLAY-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/commands/_base.py, src/sdd/commands/validate_config.py, src/sdd/commands/activate_phase.py
Outputs:              tests/unit/test_handler_purity.py, tests/unit/test_registry_contract.py
Acceptance:           pytest tests/unit/test_handler_purity.py tests/unit/test_registry_contract.py -v all pass;
                      AST test verifies no EventStore/rebuild_state/.handle( inside any handle() body;
                      I-STATE-ACCESS-LAYER-1 (AST): no get_current_state() call inside any handle() method body;
                      I-EVENT-FORMAT-1 (strict AST): walk all call nodes; reject any node where:
                        callee name == "reduce" AND any argument is itself a call to "sdd_replay";
                        also reject indirect pattern: variable assigned from sdd_replay() then passed to reduce();
                        assert files_checked > 0 to prevent silent pass on empty scan;
                      I-KERNEL-FLOW-1 (AST enforcement): scan src/sdd/ excluding registry.py;
                        assert no direct calls to EventStore.append() outside execute_command;
                        assert no direct calls to run_guard_pipeline() outside execute_command;
                        assert no direct calls to rebuild_state()/get_current_state() inside handle() methods;
                        this formally establishes I-KERNEL-FLOW-1 (implemented in T-1506, enforced here);
                      test_registry_write_commands_complete;
                      test_validate_config_is_not_in_registry;
                      test_ci_purity_whitelist_count_at_most_two;
                      test_activate_phase_handler_has_no_check_idempotent;

                      I-REPLAY-PATH-1 (AST — production bypass):
                        scan src/sdd/ excluding projections.py and tests/;
                        FORBIDDEN: any call to EventReducer().reduce() where argument comes from a DB call
                          (detect: pattern EventReducer().reduce() where argument contains db/conn/execute);
                        FORBIDDEN: sdd_replay() called as argument to reduce() in production paths;
                        ALLOWED: reduce() in tests/, in offline analysis scripts;
                        assert files_checked > 0;

                      I-READ-PATH-1 (контракт-тест в test_registry_contract.py):
                        assert set(REGISTRY.keys()) == {"complete", "validate", "check-dod",
                          "activate-phase", "sync-state", "record-decision"};
                        assert "validate-config" not in REGISTRY;
                        assert all show-* commands absent from REGISTRY;
                        Read-only commands MAY call get_current_state() internally,
                          but MUST NOT cache result outside projections scope,
                          MUST NOT call write_state() or EventStore.append();

                      I-GUARD-STATELESS-1 (AST — attribute access chain detection):
                        scan src/sdd/guards/ + src/sdd/domain/guards/;
                        FORBIDDEN attribute access chains:
                          EventStore(...).append — detect constructor+method chain;
                          write_state(...)
                          rebuild_state(...)
                          db.execute(...) or conn.execute(...) — any DB write call;
                          open(..., "w") or open(..., "a") — any file write;
                        NOTE: get_current_state() called to BUILD GuardContext is ALLOWED (outside guard functions);
                          guards receive pre-built GuardContext — they MUST NOT call get_current_state() themselves;
                        AST check: no function call named get_current_state inside any function in guards/ dirs;
                        assert files_checked > 0;

                      I-PIPELINE-SINGLE-SOURCE-1 (AST — single pipeline definition):
                        scan src/sdd/ excluding domain/guards/pipeline.py;
                        assert no function definition named run_guard_pipeline outside domain/guards/pipeline.py;
                        assert guards/pipeline.py (adapter) does NOT define run_guard_pipeline (file deleted in T-1522);

                      I-OPTLOCK-REPLAY-1 (AST): verify execute_command structure:
                        head_seq assignment line (EventStore.max_seq()) precedes get_current_state() call;
                        both exist in execute_command function body;
Depends on:           T-1519

---

T-1521: commands/sdd_run.py — structured deprecation comment

Status:               DONE
Spec ref:             Spec_v15 §11 Step 3 (deprecation prep); I-SDDRUN-DEAD-1 (prep)
Invariants:           I-SDDRUN-DEAD-1
spec_refs:            [Spec_v15 §11 Step 3, I-SDDRUN-DEAD-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/commands/sdd_run.py
Outputs:              src/sdd/commands/sdd_run.py
Acceptance:           sdd_run.py contains structured deprecation comment above CommandRunner class as two separate Python comment lines:
                        # DEPRECATED — Phase 15: superseded by execute_command in commands/registry.py.
                        # Deleted in T-1522. Do not add new callers.
                      pytest tests/ -q green
Depends on:           T-1520

---

## M4: Dead Code Deletion + CLAUDE.md Governance

T-1522: commands/sdd_run.py deleted; commands/__init__.py cleaned; tests/unit/commands/test_sdd_run.py deleted; CLAUDE.md governance updates

Status:               DONE
Spec ref:             Spec_v15 §11 Step 4 — Delete; §8 Integration — CLAUDE.md changes; I-SDDRUN-DEAD-1, I-1, I-2, I-3
Invariants:           I-SDDRUN-DEAD-1, I-1, I-2, I-3, I-SPEC-EXEC-1, I-KERNEL-FLOW-1
spec_refs:            [Spec_v15 §11 Step 4, Spec_v15 §8, I-SDDRUN-DEAD-1, I-1, I-2, I-3]
produces_invariants:  [I-SDDRUN-DEAD-1, I-1, I-2, I-3]
                      # I-KERNEL-FLOW-1 уже произведён T-1520 (AST enforcement); T-1522 документирует в CLAUDE.md §0.16
requires_invariants:  [I-PIPELINE-HOME-1, I-HANDLER-PURE-1, I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-KERNEL-FLOW-1]
Inputs:               src/sdd/commands/sdd_run.py, src/sdd/commands/__init__.py, tests/unit/commands/test_sdd_run.py, CLAUDE.md
Outputs:              src/sdd/commands/__init__.py, CLAUDE.md,
                      src/sdd/guards/pipeline.py (deleted — git rm)
Acceptance:           Precondition — grep -rn "CommandRunner" src/sdd/ | grep -v "sdd_run.py" | wc -l == 0
                        (sdd_run.py ещё не удалён — grep должен исключить его);
                      sdd_run.py deleted (git rm); test_sdd_run.py deleted (git rm);
                      pytest tests/ -q green;

                      Precondition — pipeline adapter unused:
                        grep -rn "from sdd.guards.pipeline" src/sdd/ | grep -v "guards/pipeline.py" → 0 matches;
                        grep -rn "import sdd.guards.pipeline" src/sdd/ → 0 matches;
                      guards/pipeline.py deleted (git rm);
                      python3 -c "import sdd.guards.pipeline" → ModuleNotFoundError (runtime verification);

                      I-PIPELINE-SINGLE-SOURCE-1 (runtime):
                        python3 -c "from sdd.domain.guards.pipeline import run_guard_pipeline; print('OK')" → OK;
                        run_guard_pipeline defined ONLY in sdd.domain.guards.pipeline;

                      src/sdd/commands/__init__.py: удалены re-exports CommandRunner и run_guard_pipeline;
                        grep -n "CommandRunner\|run_guard_pipeline" src/sdd/commands/__init__.py → 0 matches;

                      CLAUDE.md updated per §8 (I-1/I-2/I-3 в §0; §0.5 sdd activate-phase N replaces Direct YAML edit; SEM-10+SEM-11 в §0.8; §0.10 activate-phase row; §0.15 registry.py+pipeline.py+errors.py frozen; §0.16 Phase 15 invariants including I-KERNEL-FLOW-1 + I-STATE-ACCESS-LAYER-1 + I-PROJECTION-SHARED-CORE-1; §0.17 Phase FSM; §0.18 Responsibility Matrix; §0.19 Error Semantics);
                      CLAUDE.md §0.16 дополнения:
                        I-SYNC-1 moot note: sync_projections() superseded by project_all() in registry.py;
                        guards/pipeline.py deleted in T-1522 — use sdd.domain.guards.pipeline directly;
                        execute_command pipeline stages (formal checkpoint names):
                          STAGE BUILD_CONTEXT: head_seq capture + get_current_state() → SDDState + GuardContext
                          STAGE GUARD:         run_guard_pipeline() → GuardResult
                          STAGE EXECUTE:       handler.handle() → events (pure)
                          STAGE COMMIT:        EventStore.append(expected_head=head_seq) → persisted
                          STAGE PROJECT:       project_all() → YAML/TaskSet rebuilt
                        I-OPTLOCK-REPLAY-1, I-REPLAY-PATH-1, I-GUARD-STATELESS-1 in §0.16 invariant table;
Depends on:           T-1521

---

<!-- Granularity: 22 tasks total (TG-2 compliant). All tasks independently implementable and testable (TG-1). -->
<!-- NOTE: State_index.yaml shows tasks.total=20 (from original EventLog TaskSetDefined event). T-1514b and T-1514c were added as planning addenda. State will reconcile when implementation emits updated TaskSetDefined or PhaseInitialized event. -->
<!-- R-1: Phase 16 COMPLETE before Phase 15 — verify codebase for already-implemented tasks before implementing; use sdd complete T-NNNN for pre-existing work without re-implementing. -->
<!-- R-3: State_index.yaml was reset to phase.current=15 before decompose. Verify sdd show-state before first sdd complete. -->

<!-- INVARIANT DEFINITIONS (Phase 15 additions + clarifications) -->
<!--
=== NEW INVARIANTS (added in TaskSet review) ===

I-KERNEL-FLOW-1:
  execute_command (commands/registry.py) is the sole entry point for:
    guard execution, handler invocation, event persistence, and projection.
  No other component may bypass this flow.
  Реализован фактически в T-1506 (DONE). Формально: T-1520 (AST enforcement), T-1522 (CLAUDE.md §0.16).
  Canonical producer: T-1520.

I-KERNEL-WRITE-1:
  handler.handle() MUST NOT call EventStore.append() directly.
  Only execute_command (via event_store) may persist events.
  Canonical producer: T-1511 (первый handler, убирающий append из handle()).

I-KERNEL-PROJECT-1:
  handler.handle() MUST NOT call rebuild_state() or project_all() directly.
  Only execute_and_project (registry.py) may trigger projections.
  Canonical producer: T-1512 (первый handler, убирающий rebuild_state из handle()).

I-STATE-ACCESS-LAYER-1:
  get_current_state() вызывается ТОЛЬКО из guards и projections.
  Command handlers MUST NOT вызывать get_current_state(), sdd_replay() или reduce() напрямую.
  Produced by: T-1514. Required by: T-1517, T-1518, T-1514b. AST enforced by: T-1520.

I-PROJECTION-SHARED-CORE-1:
  get_current_state() — единственный источник правды для EventLog → SDDState.
  rebuild_state() MUST делегировать в get_current_state(); дублирование replay-логики запрещено.
  Produced by: T-1514b.

I-COMMAND-RESULT-1 (strict, supersedes advisory form):
  Возвращаемое значение handler.handle() MUST NOT использоваться как source of truth.
  Только persisted events в EventStore определяют состояние системы.
  Нельзя ветвиться по truthiness результата handle().
  Produced by: T-1514. AST enforced by: T-1520.

I-PHASE-EVENT-PAIR-1 (strict form):
  ActivatePhaseHandler MUST emit EXACTLY два события: [PhaseStartedEvent, PhaseInitializedEvent]
  в этом точном порядке. len(result)==2, type(result[0])==PhaseStartedEvent, type(result[1])==PhaseInitializedEvent.
  Produced by: T-1514.

I-PROJECTION-READ-1 (full-replay addendum):
  get_current_state() MUST выполнять full replay from seq=0.
  Partial replay и snapshot-based reconstruction запрещены (если не введены новым spec).
  Produced by: T-1514, T-1514b.

=== SPEC-LEVEL INVARIANTS (определены в Spec_v15 §2/§9 — здесь краткий справочник) ===

I-1 (Spec_v15): guard pipeline не вызывает sys.exit; только CLI layer вызывает sys.exit.
  Referenced in: T-1517, T-1518.

I-2 (Spec_v15): validate-config исключён из execute_command flow (Read-Only Exception).
  Referenced in: T-1516, T-1520, T-1522.

I-3 (Spec_v15): sdd_run.py/CommandRunner полностью удалён; нет активных callers в src/sdd/.
  Referenced in: T-1520, T-1522.

I-IMPL-ORDER-1 (Spec_v15 §9): M2 tasks (T-1510..T-1514b) MUST complete before M3 (T-1519+).
  Produced by: T-1519.

=== NEW INVARIANTS (Phase 15 Architecture Remediation — additive) ===

I-REPLAY-PATH-1 [refined]:
  PRODUCTION state reconstruction MUST use get_current_state() (infra/projections.py).
  Прямой вызов EventReducer().reduce() вне projections.py ЗАПРЕЩЁН в production paths.
  РАЗРЕШЕНО: tests/, simulation code, offline analysis scripts — reduce() там легитимен.
  Запрет применяется только к production bypass, не к самому reduce().
  Produced by: T-1514c. AST enforced by: T-1520 (production paths only).

I-OPTLOCK-REPLAY-1:
  execute_command MUST capture head_seq = EventStore.max_seq() BEFORE calling get_current_state().
  head_seq и state — независимые вызовы (не conflated). head_seq передаётся как expected_head
  в EventStore.append(). Гарантирует, что оптимистичная блокировка покрывает весь
  интервал от чтения state до коммита (closes TOCTOU Risk-1; extends I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1).
  get_current_state() MUST NOT return or accept head_seq — it is a pure replay function.
  Produced by: T-1514c. Referenced by: I-OPTLOCK-1. AST enforced by: T-1520.

I-READ-PATH-1:
  Read-only команды (validate-config, show-*, query-events) MUST NOT вызывать
  execute_command() или писать события в EventStore, MUST NOT запускать guard pipeline.
  Read-only команды MAY вызывать get_current_state() для чтения, но:
    MUST NOT кэшировать результат вне projections scope;
    MUST NOT вызывать write_state() или EventStore.append() с результатом.
  Явно исключены из REGISTRY (только write-команды в REGISTRY).
  Produced by: T-1516. Formally documented and contract-tested by: T-1520, T-1522.

I-GUARD-STATELESS-1 [extended]:
  Guards получают предпостроенный GuardContext — они MUST NOT вызывать get_current_state()
  самостоятельно (контекст уже построен в execute_command STAGE BUILD_CONTEXT).
  Guards MUST NOT выполнять любой I/O:
    - DB-запросы (db.execute, conn.execute)
    - файловые операции (open, write_state)
    - сетевые вызовы
    - мутации состояния (rebuild_state, EventStore.append)
  Guards MUST NOT зависеть от недетерминированных источников при принятии решений.
  Guards — чистые функции над GuardContext: (ctx) → (GuardResult, list[DomainEvent]).
  Прежняя формулировка (T-1505 area) запрещала только append/write/rebuild; эта расширяет
  запрет до любого I/O и явно запрещает get_current_state() внутри guard-функций.
  Produced by: T-1520 (AST enforcement). Referenced by: T-1517, T-1518.

I-PIPELINE-SINGLE-SOURCE-1:
  run_guard_pipeline определён ТОЛЬКО в sdd.domain.guards.pipeline.
  Никакой другой модуль не должен определять функцию с этим именем.
  sdd.guards.pipeline (adapter) удалён в T-1522 (closes Bug-D).
  AST enforced by: T-1520. Runtime enforced by: T-1522 acceptance.

I-PROJECTION-READ-1 [temporal annotation]:
  Phase-bound: MUST для Phase ≤15 (полный replay с seq=0).
  MAY быть ослаблен будущей спекой (snapshot/incremental-replay модель).
  Аннотация предотвращает преждевременный lock-in на этой реализации.
  (No code change — governance constraint only.)

I-COMMAND-RESULT-1 [clarification — supersedes advisory form]:
  Contract-тесты, проверяющие тип и количество событий из handle() — ЛЕГИТИМНЫ.
  ЗАПРЕЩЕНО: ветвление production-кода по truthiness результата handle() для вывода
  о состоянии: `if len(result) > 0: mark_phase_active()` — VIOLATION.
  РАЗРЕШЕНО: `assert len(result) == 2` в тестах — легитимная контрактная проверка.
  (Уточнение, не изменение — I-COMMAND-RESULT-1 произведён T-1514.)

error_code range [governance]:
  Коды 1..7 заморожены (T-1503). Новый SDDError с новым кодом = новый task + Spec amendment.
  (No code change — governance constraint only.)

=== ПРИМЕЧАНИЯ ===

NOTE — error_code range: T-1503 (DONE) устанавливает коды 1..7 (KernelInvariantError=7).
  Любой новый SDDError subclass требует нового task + spec amendment.
  Прежние "1..6 frozen" ссылки в более ранних фазах superseded T-1503 acceptance.
-->
