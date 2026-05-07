# TaskSet_v3 — Phase 3: Norm, Guards & Scheduler

Spec: specs/Spec_v3_Guards.md
Plan: plans/Plan_v3.md

---

T-301: C-1 Core Extensions

Status:               DONE
Spec ref:             Spec_v3 §2 BC-CORE extensions, §3 Domain Events, §8 C-1 Compliance
Invariants:           I-ST-10
spec_refs:            [Spec_v3 §2, §3, §8, I-ST-10]
produces_invariants:  [I-ST-10]
requires_invariants:  []
Inputs:               src/sdd/core/errors.py, src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/core/errors.py, src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Acceptance:           Import of sdd.core.events succeeds with no AssertionError; "NormViolated" and "TaskStartGuardRejected" present in V1_L1_EVENT_TYPES and _KNOWN_NO_HANDLER; CyclicDependency and ParallelGroupConflict importable from sdd.core.errors
Depends on:           —
Parallel group:       —

---

T-302: BC-NORMS — Norm Catalog

Status:               DONE
Spec ref:             Spec_v3 §2 BC-NORMS, §4.8, §5 I-NRM-1..3, §6 load_catalog pre/post
Invariants:           I-NRM-1, I-NRM-2, I-NRM-3
spec_refs:            [Spec_v3 §2, §4.8, §5, §6, I-NRM-1, I-NRM-2, I-NRM-3]
produces_invariants:  [I-NRM-1, I-NRM-2, I-NRM-3]
requires_invariants:  []
Inputs:               src/sdd/core/errors.py, src/sdd/domain/norms/__init__.py, .sdd/norms/norm_catalog.yaml
Outputs:              src/sdd/domain/norms/catalog.py, src/sdd/domain/norms/__init__.py, tests/unit/domain/norms/__init__.py, tests/unit/domain/norms/test_catalog.py
Acceptance:           All 9 test cases in test_catalog.py pass; NormCatalog, NormEntry, load_catalog importable from sdd.domain.norms; strict=False is the default
Depends on:           T-301
Parallel group:       bc-extensions

---

T-303: BC-TASKS Extension — depends_on + parallel_group

Status:               DONE
Spec ref:             Spec_v3 §2 BC-SCHEDULER (BC-TASKS extension), §4.9
Invariants:           I-TS-1
spec_refs:            [Spec_v3 §2, §4.9, I-TS-1]
produces_invariants:  [I-TS-1]
requires_invariants:  []
Inputs:               src/sdd/domain/tasks/parser.py, tests/unit/domain/tasks/test_parser.py
Outputs:              src/sdd/domain/tasks/parser.py, tests/unit/domain/tasks/test_parser.py
Acceptance:           3 new test cases pass (test_parse_task_has_depends_on_field, test_parse_task_has_parallel_group_field, test_parse_missing_new_fields_default_empty); all pre-existing parser tests continue to pass; Task.depends_on defaults to () and Task.parallel_group defaults to None when fields absent from TaskSet
Depends on:           T-301
Parallel group:       bc-extensions

---

T-304: BC-SCHEDULER — DAG Builder & Topological Order

Status:               DONE
Spec ref:             Spec_v3 §2 BC-SCHEDULER, §4.10, §5 I-SCH-1..6, §6 build_dag/topological_order pre/post
Invariants:           I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6
spec_refs:            [Spec_v3 §2, §4.10, §5, §6, I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6]
produces_invariants:  [I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6]
requires_invariants:  [I-TS-1]
Inputs:               src/sdd/domain/tasks/parser.py, src/sdd/domain/tasks/__init__.py, src/sdd/core/errors.py
Outputs:              src/sdd/domain/tasks/scheduler.py, src/sdd/domain/tasks/__init__.py, tests/unit/domain/tasks/test_scheduler.py
Acceptance:           All 11 test cases in test_scheduler.py pass; TaskNode, build_dag, topological_order importable from sdd.domain.tasks; ParallelGroupConflict and CyclicDependency are distinct error types that are never swapped
Depends on:           T-301, T-303
Parallel group:       guard-foundations

---

T-305: Guard Runner — EmitFn, GuardContext, GuardOutcome, GuardResult, run_guard_pipeline

Status:               DONE
Spec ref:             Spec_v3 §4.0 EmitFn + GuardContext, §4.1 GuardOutcome + GuardResult, §4.7 run_guard_pipeline
Invariants:           I-GRD-4
spec_refs:            [Spec_v3 §4.0, §4.1, §4.7, I-GRD-4]
produces_invariants:  [I-GRD-4]
requires_invariants:  [I-ST-10]
Inputs:               src/sdd/core/events.py, src/sdd/core/errors.py, src/sdd/domain/state/__init__.py, src/sdd/domain/norms/catalog.py, src/sdd/guards/__init__.py
Outputs:              src/sdd/guards/runner.py, tests/unit/guards/test_runner.py
Acceptance:           All 5 test cases in test_runner.py pass; EmitFn, GuardContext, GuardOutcome, GuardResult, run_guard_pipeline importable from sdd.guards.runner; GuardContext is a frozen dataclass; run_guard_pipeline does not inspect guard logic
Depends on:           T-301, T-302
Parallel group:       guard-foundations

---

T-306: Integrity Guards — ScopeGuard + TaskGuard

Status:               DONE
Spec ref:             Spec_v3 §2.1, §4.2 ScopeGuard, §4.4 TaskGuard, §5 I-GRD-1, I-GRD-2, I-GRD-5
Invariants:           I-GRD-1, I-GRD-2, I-GRD-5
spec_refs:            [Spec_v3 §2.1, §4.2, §4.4, §5, I-GRD-1, I-GRD-2, I-GRD-5, I-GRD-9]
produces_invariants:  [I-GRD-1, I-GRD-2, I-GRD-5]
requires_invariants:  [I-GRD-4, I-TS-1]
Inputs:               src/sdd/guards/runner.py, src/sdd/core/errors.py, src/sdd/domain/tasks/parser.py, src/sdd/infra/config_loader.py
Outputs:              src/sdd/guards/scope.py, src/sdd/guards/task.py, tests/unit/guards/test_scope.py, tests/unit/guards/test_task.py
Acceptance:           All 5 test cases in test_scope.py pass; all 4 test cases in test_task.py pass; ScopeGuard never calls ctx.emit; TaskGuard raises InvalidState (DONE) vs MissingContext (not found) — never swapped; check_write always raises ScopeViolation for .sdd/specs/** regardless of config
Depends on:           T-305, T-303
Parallel group:       —

---

T-307: PhaseGuard

Status:               DONE
Spec ref:             Spec_v3 §2.1, §3, §4.3 PhaseGuard, §5 I-GRD-3, I-GRD-8, §6 pre/post, §8 integration
Invariants:           I-GRD-3, I-GRD-8
spec_refs:            [Spec_v3 §2.1, §3, §4.3, §5, §6, §8, I-GRD-3, I-GRD-8]
produces_invariants:  [I-GRD-3]
requires_invariants:  [I-GRD-4, I-ST-10]
Inputs:               src/sdd/guards/runner.py, src/sdd/core/events.py, src/sdd/domain/state/__init__.py
Outputs:              src/sdd/guards/phase.py, tests/unit/guards/test_phase.py
Acceptance:           All 8 test cases in test_phase.py pass including test_phase_guard_emit_called_before_return and test_phase_guard_emit_failure_propagates; PhaseGuard never raises on DENY; SDDEventRejected payload fields match §3 exactly
Depends on:           T-305, T-301
Parallel group:       policy-guards

---

T-308: TaskStartGuard

Status:               DONE
Spec ref:             Spec_v3 §2.1, §4.5 TaskStartGuard, §4.5.1 parsing contract, §5 I-GRD-6, I-GRD-8, I-GRD-10
Invariants:           I-GRD-6, I-GRD-10
spec_refs:            [Spec_v3 §2.1, §4.5, §4.5.1, §5, I-GRD-6, I-GRD-8, I-GRD-10, I-EL-9]
produces_invariants:  [I-GRD-6, I-GRD-10]
requires_invariants:  [I-GRD-4, I-ST-10]
Inputs:               src/sdd/guards/runner.py, src/sdd/core/events.py
Outputs:              src/sdd/guards/task_start.py, tests/unit/guards/test_task_start.py
Acceptance:           All 9 test cases in test_task_start.py pass including test_task_start_canonical_report_format_pass, test_task_start_canonical_report_format_fail, and test_task_start_no_direct_db_calls; grep confirms no duckdb.connect in task_start.py; §4.5.1 exact regex patterns used (not ad-hoc)
Depends on:           T-305, T-301
Parallel group:       policy-guards

---

T-309: NormGuard

Status:               DONE
Spec ref:             Spec_v3 §2.1, §4.6 NormGuard, §5 I-GRD-7, I-GRD-8, §6 pre/post
Invariants:           I-GRD-7
spec_refs:            [Spec_v3 §2.1, §4.6, §5, §6, I-GRD-7, I-GRD-8, I-NRM-2, I-NRM-3, I-EL-9]
produces_invariants:  [I-GRD-7]
requires_invariants:  [I-GRD-4, I-NRM-1]
Inputs:               src/sdd/guards/runner.py, src/sdd/core/events.py, src/sdd/domain/norms/catalog.py
Outputs:              src/sdd/guards/norm.py, tests/unit/guards/test_norm.py
Acceptance:           All 7 test cases in test_norm.py pass including test_norm_emit_called_before_return and test_norm_no_direct_db_calls; grep confirms no duckdb.connect in norm.py; NormGuard does not load YAML itself — catalog taken from ctx
Depends on:           T-305, T-302
Parallel group:       policy-guards

---

T-310: guards/__init__.py — Package Re-exports

Status:               DONE
Spec ref:             Spec_v3 §2 BC-GUARDS __init__.py, §5 I-GRD-8, I-GRD-9, §8 Integration
Invariants:           I-GRD-8, I-GRD-9
spec_refs:            [Spec_v3 §2, §5, §8, I-GRD-8, I-GRD-9]
produces_invariants:  [I-GRD-8, I-GRD-9]
requires_invariants:  [I-GRD-1, I-GRD-2, I-GRD-3, I-GRD-5, I-GRD-6, I-GRD-7]
Inputs:               src/sdd/guards/runner.py, src/sdd/guards/scope.py, src/sdd/guards/task.py, src/sdd/guards/phase.py, src/sdd/guards/task_start.py, src/sdd/guards/norm.py
Outputs:              src/sdd/guards/__init__.py
Acceptance:           `from sdd.guards import EmitFn, GuardContext, GuardOutcome, GuardResult, run_guard_pipeline, ScopeGuard, PhaseGuard, TaskGuard, TaskStartGuard, NormGuard` succeeds without error; all 38 guard unit tests pass (test_runner: 5, test_scope: 5, test_task: 4, test_phase: 8, test_task_start: 9, test_norm: 7); grep confirms no duckdb.connect in any file under src/sdd/guards/
Depends on:           T-306, T-307, T-308, T-309
Parallel group:       —

---

<!-- Granularity: 10 tasks (TG-2 satisfied). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
<!-- Parallel execution layers: -->
<!--   Layer 0: T-301 -->
<!--   Layer 1: T-302, T-303 (parallel_group: bc-extensions) -->
<!--   Layer 2: T-304, T-305 (parallel_group: guard-foundations) -->
<!--   Layer 3: T-306, T-307, T-308, T-309 (T-307/T-308/T-309 in policy-guards) -->
<!--   Layer 4: T-310 -->
