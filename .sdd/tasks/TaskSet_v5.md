# TaskSet_v5 — Phase 5: Critical Fixes

Spec: specs/Spec_v5_CriticalFixes.md
Plan: plans/Plan_v5.md

---

T-501: Core Events, Handlers & Norm Catalog (atomic — C-1)

Status:               DONE
Spec ref:             Spec_v5 §3 — Domain Events; §4.1–4.3 — Commands & Handlers; §8 — Norm Catalog Updates
Invariants:           C-1, I-ACT-1, I-DOMAIN-1, I-REDUCER-2, I-SCHEMA-1
spec_refs:            [Spec_v5 §3, §4.1, §4.2, §4.3, §5, §8, C-1]
produces_invariants:  [C-1, I-ACT-1, I-DOMAIN-1, I-REDUCER-2, I-SCHEMA-1]
requires_invariants:  [I-CMD-2, I-ERR-1, I-ES-1, I-EL-9]
Inputs:               src/sdd/core/events.py
                      src/sdd/core/errors.py
                      src/sdd/domain/state/reducer.py
                      .sdd/norms/norm_catalog.yaml
Outputs:              src/sdd/core/events.py
                      src/sdd/core/errors.py
                      src/sdd/commands/activate_phase.py
                      src/sdd/commands/activate_plan.py
                      src/sdd/domain/state/reducer.py
                      .sdd/norms/norm_catalog.yaml
Acceptance:           All six changes land atomically: PhaseActivatedEvent + PlanActivatedEvent added to V1_L1_EVENT_TYPES, _EVENT_SCHEMA, and as frozen dataclasses; InvalidActor + AlreadyActivated added to errors.py; ActivatePhaseHandler + ActivatePlanHandler created in commands/; _handle_phase_activated + _handle_plan_activated (non-mutating, I-REDUCER-2) added to reducer.py; NORM-ACTOR-ACTIVATE-PHASE + NORM-ACTOR-ACTIVATE-PLAN added to norm_catalog.yaml. No AssertionError on import (C-1).
Depends on:           —

---

T-502: Error Path Consolidation (I-ES-1 final form)

Status:               DONE
Spec ref:             Spec_v5 §2.1 — Canonical Write Path; §4.4 — error_event_boundary; §4.5 — CommandRunner
Invariants:           I-ES-1, I-ES-6, I-CMD-3
spec_refs:            [Spec_v5 §2.1, §4.4, §4.5, §5]
produces_invariants:  [I-ES-1, I-ES-6]
requires_invariants:  [I-CMD-3, I-ERR-1]
Inputs:               src/sdd/commands/_base.py
                      src/sdd/commands/sdd_run.py
Outputs:              src/sdd/commands/_base.py
                      src/sdd/commands/sdd_run.py
Acceptance:           error_event_boundary attaches ErrorEvent to exception via exc._sdd_error_events and re-raises — no sdd_append call inside the decorator. CommandRunner.run() catches exception, reads exc._sdd_error_events, appends via self._store.append(error_events, source="error_boundary"), re-raises original. If EventStore.append itself raises: logging.error() only, original exception still re-raised (I-CMD-3). CommandRunner checks `if events:` before calling append on success path (I-ES-6).
Depends on:           T-501

---

T-503: GuardContext Deduplication

Status:               DONE
Spec ref:             Spec_v5 §2.3 — GuardContext Deduplication; removal protocol
Invariants:           deduplication (no stale GuardContext class in guards/runner.py)
spec_refs:            [Spec_v5 §2.3]
produces_invariants:  [deduplication]
requires_invariants:  []
Inputs:               src/sdd/guards/runner.py
                      src/sdd/domain/guards/context.py
Outputs:              src/sdd/guards/runner.py
Acceptance:           Mandatory removal protocol followed in order: (1) grep -r "guards.runner" src/ tests/ run to identify all import sites; (2) each import site updated to `from sdd.domain.guards.context import GuardContext`; (3) GuardContext class removed from guards/runner.py; (4) final grep confirms no remaining `guards.runner.*GuardContext` references. File kept if it contains other non-duplicate content.
Depends on:           T-501

---

T-504: Reducer Unknown Event Invariant (I-REDUCER-1)

Status:               DONE
Spec ref:             Spec_v5 §2.4 — Reducer Invariant I-REDUCER-1; §4.6 — UnknownEventType; §4.7 — _handle_unknown policy
Invariants:           I-REDUCER-1
spec_refs:            [Spec_v5 §2.4, §4.6, §4.7, §5]
produces_invariants:  [I-REDUCER-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/reducer.py
                      src/sdd/core/errors.py
Outputs:              src/sdd/domain/state/reducer.py
                      src/sdd/core/errors.py
Acceptance:           UnknownEventType added to core/errors.py. _KNOWN_NO_HANDLER set populated by auditing _EVENT_SCHEMA and all event types in existing EventLogs (e.g. MetricRecorded). reducer._reduce_one(): if event_type not in _EVENT_SCHEMA and not in _KNOWN_NO_HANDLER → logging.warning() + NO-OP (strict_mode=False); raise UnknownEventType (strict_mode=True). strict_mode defaults to False.
Depends on:           T-501

---

T-505: Test Suite — Full Coverage of Phase 5 Invariants

Status:               DONE
Spec ref:             Spec_v5 §9 — Verification table (9 test files, ~30 named tests)
Invariants:           I-ES-1, I-ES-6, I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1, I-ACT-1, I-DOMAIN-1, I-PROJ-1, I-PROJ-2, I-CMD-3, Q1, Q3
spec_refs:            [Spec_v5 §9, §7 UC-5-4, §5]
produces_invariants:  [I-ES-1, I-ES-6, I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1, I-ACT-1, I-DOMAIN-1, I-PROJ-1, I-PROJ-2, Q1, Q3]
requires_invariants:  [C-1, I-ACT-1, I-DOMAIN-1, I-REDUCER-1, I-REDUCER-2, I-ES-1, I-ES-6]
Inputs:               src/sdd/core/events.py
                      src/sdd/core/errors.py
                      src/sdd/commands/_base.py
                      src/sdd/commands/sdd_run.py
                      src/sdd/commands/activate_phase.py
                      src/sdd/commands/activate_plan.py
                      src/sdd/domain/state/reducer.py
                      src/sdd/domain/guards/context.py
                      src/sdd/guards/runner.py
                      src/sdd/infra/projections.py
Outputs:              tests/unit/core/test_events_phase5.py
                      tests/unit/domain/state/test_reducer.py
                      tests/unit/commands/test_base.py
                      tests/unit/commands/test_sdd_run.py
                      tests/unit/commands/test_activate_phase.py
                      tests/unit/commands/test_activate_plan.py
                      tests/unit/guards/test_no_duplicate_guard_context.py
                      tests/unit/infra/test_projections.py
                      tests/integration/test_full_chain.py
Acceptance:           All 9 test files exist and all named tests from Spec §9 pass. Tautological `reduce(sdd_replay()) == read_state_from_yaml()` check replaced (not supplemented) by: test_replay_golden_scenario, test_replay_is_deterministic, test_full_chain_activate_phase (Q3). Integration test uses tmp_path fixture with a fresh temporary DuckDB — never the project's .sdd/state/sdd_events.duckdb (R-5). Both I-PROJ-1 and I-PROJ-2 covered by projections tests.
Depends on:           T-501, T-502, T-503, T-504

---

T-506: Guard Pipeline Contract Stabilization

Status:               DONE
Spec ref:             Spec_v5 §4.5 — CommandRunner; §4.11 — run_guard_pipeline;
                      CLAUDE.md §K.10 DDD-3, DDD-4 (domain logic must not depend on infrastructure;
                      reducer layer is pure domain logic)
Invariants:           I-GUARD-1 (Guard contract: every guard is Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]);
                      I-GUARD-2 (CommandRunner contains no inline guard logic — delegates to run_guard_pipeline)
spec_refs:            [Spec_v5 §4.5, §4.11]
produces_invariants:  [I-GUARD-1, I-GUARD-2]
requires_invariants:  [deduplication]
Inputs:               src/sdd/commands/sdd_run.py
                      src/sdd/domain/guards/context.py
                      src/sdd/domain/guards/dependency_guard.py
Outputs:              src/sdd/domain/guards/types.py
                      src/sdd/domain/guards/pipeline.py
                      src/sdd/domain/guards/phase_guard.py
                      src/sdd/domain/guards/task_guard.py
                      src/sdd/domain/guards/norm_guard.py
                      src/sdd/commands/sdd_run.py
Acceptance:           (1) domain/guards/types.py defines Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]].
                      (2) domain/guards/pipeline.py defines run_guard_pipeline(ctx, guards: list[Guard], stop_on_deny=True) → tuple[GuardResult, list[DomainEvent]]; merges events from all guards; stops at first DENY when stop_on_deny=True.
                      (3) Inline phase check, task check, norm check extracted from sdd_run.py into domain/guards/phase_guard.py, task_guard.py, norm_guard.py respectively — each conforms to Guard contract.
                      (4) commands/sdd_run.py.run_guard_pipeline replaced by call to domain pipeline:
                          run_guard_pipeline(ctx, [phase_guard, task_guard, partial(DependencyGuard.check_as_guard, task_id=task_id), norm_guard_fn], stop_on_deny=True).
                      (5) PYTHONPATH=src python3 -m pytest tests/unit/guards/ tests/unit/commands/ -q — all pass.
                      (6) grep -r "inline\|# Step [0-9]" src/sdd/commands/sdd_run.py → no inline guard logic remains.
Depends on:           T-505