# TaskSet_v17 — Phase 17: Validation Runtime (VR)

Spec: specs/Spec_v17_ValidationRuntime.md
Plan: plans/Plan_v17.md

---

T-1701: ExecutionContext module

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0, §5 I-EXEC-CONTEXT-1 — KernelContextError + context manager
Invariants:           I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1
spec_refs:            [Spec_v17 §2 BC-VR-0, §5 I-EXEC-CONTEXT-1, §6 M0]
produces_invariants:  [I-EXEC-CONTEXT-1]
requires_invariants:  []
Inputs:               src/sdd/core/__init__.py
Outputs:              src/sdd/core/execution_context.py
Acceptance:           Module importable; KernelContextError, _EXECUTION_CTX, kernel_context, assert_in_kernel, current_execution_context all defined; assert_in_kernel raises KernelContextError outside kernel_context block
Depends on:           —

---

T-1702: Registry wraps execute_command in kernel_context

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0, §6 M0 — registry integration
Invariants:           I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1
spec_refs:            [Spec_v17 §2 BC-VR-0, §6 M0]
produces_invariants:  [I-KERNEL-WRITE-1]
requires_invariants:  [I-EXEC-CONTEXT-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/core/execution_context.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           execute_command body wrapped with kernel_context("execute_command"); assert_in_kernel() called inside returns None (no exception)
Depends on:           T-1701

---

T-1703: AST test — all write entry points in kernel_context

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0, §5 I-EXEC-CONTEXT-1 — static verification
Invariants:           I-EXEC-CONTEXT-1
spec_refs:            [Spec_v17 §5 I-EXEC-CONTEXT-1]
produces_invariants:  []
requires_invariants:  [I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1]
Inputs:               src/sdd/core/execution_context.py, src/sdd/commands/registry.py, tests/unit/test_handler_purity.py
Outputs:              tests/unit/test_handler_purity.py
Acceptance:           test_handler_purity.py extended with AST-scan asserting all write entry points (execute_command) are wrapped; pytest tests/unit/test_handler_purity.py passes
Depends on:           T-1702

---

T-1704: Harness API — execute_sequence, replay, fork, rollback

Status:               DONE
Spec ref:             Spec_v17 §4 Harness API, §2 BC-VR-1, §6 M1
Invariants:           I-VR-API-1, I-VR-HARNESS-1
spec_refs:            [Spec_v17 §2 BC-VR-1, §4, §6 M1, I-VR-API-1, I-VR-HARNESS-1]
produces_invariants:  [I-VR-API-1, I-VR-HARNESS-1]
requires_invariants:  [I-KERNEL-WRITE-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/core/execution_context.py
Outputs:              tests/harness/__init__.py, tests/harness/api.py
Acceptance:           execute_sequence, replay, fork, rollback callable; API uses ONLY execute_command + get_current_state; no direct internal module calls
Depends on:           T-1702

---

T-1705: Harness fixtures and generators

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-1, §6 M1 — fixtures + generators
Invariants:           I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4
spec_refs:            [Spec_v17 §2 BC-VR-1, §6 M1, I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4]
produces_invariants:  [I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4]
requires_invariants:  [I-VR-API-1]
Inputs:               tests/harness/api.py
Outputs:              tests/harness/fixtures.py, tests/harness/generators.py
Acceptance:           db_factory, event_factory, state_builder, make_minimal_event in fixtures.py; valid_command_sequence, edge_payload, adversarial_sequence, independent_command_pair in generators.py; each tmp_path-isolated (I-VR-HARNESS-4)
Depends on:           T-1704

---

T-1706: Harness unit tests covering I-VR-HARNESS-1..4

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-1, §6 M1 — harness self-validation
Invariants:           I-VR-HARNESS-1, I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4
spec_refs:            [Spec_v17 §2 BC-VR-1, §6 M1]
produces_invariants:  []
requires_invariants:  [I-VR-HARNESS-1, I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py, tests/harness/generators.py
Outputs:              tests/unit/commands/test_harness.py
Acceptance:           pytest tests/unit/commands/test_harness.py passes; covers all four I-VR-HARNESS invariants
Depends on:           T-1705

---

T-1707: Add hypothesis>=6.100 to pyproject.toml [dev]

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-2, §6 M2 — dependency
Invariants:           I-VR-STABLE-1
spec_refs:            [Spec_v17 §2 BC-VR-2, §6 M2]
produces_invariants:  []
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              pyproject.toml
Acceptance:           hypothesis>=6.100 present in [dev] section; pip install -e .[dev] succeeds; import hypothesis works
Depends on:           T-1705

---

T-1708: Property tests P-1..P-5 (determinism, confluence, prefix, safety, hidden-state)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-2, §6 M2, Appendix B — P-1..P-5
Invariants:           I-VR-STABLE-1, I-VR-STABLE-2, I-VR-STABLE-3, I-STATE-DETERMINISTIC-1, I-CONFLUENCE-STRONG-1
spec_refs:            [Spec_v17 §2 BC-VR-2, §6 M2, §7 UC-17-1, Appendix B]
produces_invariants:  [I-VR-STABLE-1, I-VR-STABLE-2, I-VR-STABLE-3, I-STATE-DETERMINISTIC-1]
requires_invariants:  [I-VR-API-1, I-VR-HARNESS-1, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py, tests/harness/generators.py
Outputs:              tests/property/__init__.py, tests/property/test_determinism.py, tests/property/test_confluence.py, tests/property/test_prefix_consistency.py, tests/property/test_invariant_safety.py, tests/property/test_no_hidden_state.py
Acceptance:           pytest tests/property/test_determinism.py tests/property/test_confluence.py tests/property/test_prefix_consistency.py tests/property/test_invariant_safety.py tests/property/test_no_hidden_state.py --hypothesis-seed=0 passes
Depends on:           T-1706, T-1707

---

T-1709: Property tests P-6..P-10 (integrity, idempotency, concurrency, schema, performance)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-2, §6 M2, Appendix B — P-6..P-10
Invariants:           I-VR-STABLE-6, I-VR-STABLE-7, I-VR-STABLE-8, I-VR-STABLE-9, I-PERF-SCALING-1
spec_refs:            [Spec_v17 §2 BC-VR-2, §6 M2, Appendix B, I-PERF-SCALING-1]
produces_invariants:  [I-VR-STABLE-6, I-VR-STABLE-7, I-VR-STABLE-8, I-VR-STABLE-9, I-PERF-SCALING-1]
requires_invariants:  [I-VR-API-1, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py, tests/harness/generators.py
Outputs:              tests/property/test_event_integrity.py, tests/property/test_idempotency.py, tests/property/test_concurrency.py, tests/property/test_schema_evolution.py, tests/property/test_performance.py
Acceptance:           pytest tests/property/test_event_integrity.py tests/property/test_idempotency.py tests/property/test_concurrency.py tests/property/test_schema_evolution.py tests/property/test_performance.py --hypothesis-seed=0 passes; P-10 slope ratio < 2.5 at N>=1000; P-8 yields one StaleStateError
Depends on:           T-1708

---

T-1710: Relational property tests RP-1..RP-3 (state transition deltas)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-2, §6 M3 — RP-1..RP-3
Invariants:           I-STATE-TRANSITION-1
spec_refs:            [Spec_v17 §2 BC-VR-2, §6 M3, I-STATE-TRANSITION-1]
produces_invariants:  [I-STATE-TRANSITION-1]
requires_invariants:  [I-VR-API-1, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py
Outputs:              tests/property/test_state_transitions.py
Acceptance:           pytest tests/property/test_state_transitions.py passes; RP-1 (TaskCompleted delta correct), RP-2 (PhaseStarted resets counters), RP-3 (DecisionRecorded no side-effect on unrelated fields)
Depends on:           T-1708

---

T-1711: Fuzz tests — adversarial (G4)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-3, §6 M4, §7 UC-17-3 — G4 adversarial
Invariants:           I-VR-STABLE-4, I-VR-STABLE-7
spec_refs:            [Spec_v17 §2 BC-VR-3, §6 M4, §7 UC-17-3, I-VR-STABLE-4, I-VR-STABLE-7]
produces_invariants:  [I-VR-STABLE-4]
requires_invariants:  [I-VR-API-1, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py, tests/harness/generators.py
Outputs:              tests/fuzz/__init__.py, tests/fuzz/test_adversarial.py
Acceptance:           pytest tests/fuzz/test_adversarial.py passes; G4 covers concurrent writes, stale head, duplicates, schema corrupt scenarios
Depends on:           T-1705, T-1709

---

T-1712: Fuzz tests — interleaving (G5)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-3, §6 M4, §7 UC-17-3 — G5 interleaving
Invariants:           I-CONFLUENCE-STRONG-1
spec_refs:            [Spec_v17 §2 BC-VR-3, §6 M4, I-CONFLUENCE-STRONG-1]
produces_invariants:  []
requires_invariants:  [I-CONFLUENCE-STRONG-1, I-VR-HARNESS-4]
Inputs:               tests/harness/api.py, tests/harness/generators.py, tests/fuzz/__init__.py
Outputs:              tests/fuzz/test_interleaving.py
Acceptance:           pytest tests/fuzz/test_interleaving.py passes; [cmd_a, cmd_b] and [cmd_b, cmd_a] yield equal state_hash; independent_command_pair guarantees no shared state
Depends on:           T-1711

---

T-1713: Runtime enforcement integration tests (4 traps)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-4, §6 M5, §7 UC-17-2
Invariants:           I-VR-STABLE-5, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-STATE-ACCESS-LAYER-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v17 §2 BC-VR-4, §6 M5, §7 UC-17-2]
produces_invariants:  [I-VR-STABLE-5]
requires_invariants:  [I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1]
Inputs:               src/sdd/core/execution_context.py, src/sdd/commands/registry.py, src/sdd/infra/event_store.py
Outputs:              tests/integration/test_runtime_enforcement.py
Acceptance:           pytest tests/integration/test_runtime_enforcement.py passes; test 1: execute_and_project inside kernel_context → assert_in_kernel PASS; test 2: EventStore.append outside context → KernelContextError; test 3: rebuild_state outside project_all → trap; test 4: get_current_state outside guards/projections → trap
Depends on:           T-1702

---

T-1714: Evolution fixtures — v1_events.json

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-5, §6 M6, §7 UC-17-4 — compatibility fixtures
Invariants:           I-EVENT-UPCAST-1
spec_refs:            [Spec_v17 §2 BC-VR-5, §6 M6, I-EVENT-UPCAST-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/core/events.py
Outputs:              compatibility/fixtures/v1_events.json
Acceptance:           v1_events.json contains >=5 distinct historical v1 event types; JSON valid; each entry has event_type, payload, schema_version=1
Depends on:           T-1705

---

T-1715: Evolution validator integration tests (6 tests)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-5, §6 M6, §7 UC-17-4
Invariants:           I-VR-STABLE-8, I-EVENT-UPCAST-1, I-EVOLUTION-FORWARD-1
spec_refs:            [Spec_v17 §2 BC-VR-5, §6 M6, §7 UC-17-4, I-EVENT-UPCAST-1, I-EVOLUTION-FORWARD-1]
produces_invariants:  [I-EVOLUTION-FORWARD-1]
requires_invariants:  [I-VR-API-1, I-EVENT-UPCAST-1]
Inputs:               tests/harness/api.py, compatibility/fixtures/v1_events.json
Outputs:              tests/integration/test_evolution.py
Acceptance:           pytest tests/integration/test_evolution.py passes; all 6 tests pass: upcast correctness, forward unknown event safe, no data loss, unknown fields ignored, backward compat state_hash, evolution idempotent
Depends on:           T-1704, T-1714

---

T-1716: Failure semantics integration tests (3 tests)

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-8, §6 M7, §7 UC-17-5
Invariants:           I-FAIL-DETERMINISTIC-1
spec_refs:            [Spec_v17 §2 BC-VR-8, §6 M7, §7 UC-17-5, I-FAIL-DETERMINISTIC-1]
produces_invariants:  [I-FAIL-DETERMINISTIC-1]
requires_invariants:  [I-VR-API-1]
Inputs:               tests/harness/api.py, tests/harness/fixtures.py
Outputs:              tests/integration/test_failure_semantics.py
Acceptance:           pytest tests/integration/test_failure_semantics.py passes; test 1: invalid command ×2 → identical error_type + message; test 2: StaleStateError ×2 → reproducible same seq + same error; test 3: corrupted log → replay → concrete SDDError (not generic Exception)
Depends on:           T-1704

---

T-1717: Mutation engine config — mutmut + .mutmut.toml

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-6, §6 M8, Appendix A
Invariants:           I-VR-MUT-1
spec_refs:            [Spec_v17 §2 BC-VR-6, §6 M8, Appendix A, I-VR-MUT-1]
produces_invariants:  [I-VR-MUT-1]
requires_invariants:  [I-VR-STABLE-1, I-VR-STABLE-4]
Inputs:               pyproject.toml, tests/property/, tests/fuzz/
Outputs:              pyproject.toml, .mutmut.toml
Acceptance:           mutmut present in [dev]; .mutmut.toml defines 6 target modules + runner; mutmut run --no-progress exits without config error
Depends on:           T-1709, T-1712

---

T-1718: Kill rate assertion script

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-6, §6 M8, Appendix A — assert_kill_rate.py
Invariants:           I-VR-MUT-1, I-MUT-CRITICAL-1, I-VR-STABLE-10
spec_refs:            [Spec_v17 §2 BC-VR-6, Appendix A, I-MUT-CRITICAL-1, I-VR-STABLE-10]
produces_invariants:  [I-MUT-CRITICAL-1, I-VR-STABLE-10]
requires_invariants:  [I-VR-MUT-1]
Inputs:               .mutmut.toml
Outputs:              scripts/assert_kill_rate.py
Acceptance:           scripts/assert_kill_rate.py --min 0.95 --critical-min 1.0 exits 0 when rates met; exits 1 with named surviving CRITICAL mutants when threshold violated
Depends on:           T-1717

---

T-1719: Makefile VR targets

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-7, §6 M9, §7 UC-17-6
Invariants:           I-VR-STABLE-10
spec_refs:            [Spec_v17 §2 BC-VR-7, §6 M9, §7 UC-17-6, I-VR-STABLE-10]
produces_invariants:  []
requires_invariants:  [I-VR-MUT-1, I-MUT-CRITICAL-1]
Inputs:               Makefile, scripts/assert_kill_rate.py
Outputs:              Makefile
Acceptance:           Makefile contains targets: vr-fast, vr-full, vr-stress, vr-mutation, vr-release; check and ci targets updated to include vr-fast; make vr-fast exits 0 on green suite
Depends on:           T-1718

---

T-1720: VR Report generator script

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-7, §6 M9, §7 UC-17-6
Invariants:           I-VR-REPORT-1
spec_refs:            [Spec_v17 §2 BC-VR-7, §6 M9, I-VR-REPORT-1]
produces_invariants:  [I-VR-REPORT-1]
requires_invariants:  [I-VR-STABLE-10]
Inputs:               Makefile, scripts/assert_kill_rate.py
Outputs:              scripts/generate_vr_report.py
Acceptance:           generate_vr_report.py collects P-1..P-10, RP-1..RP-3, kill rate, commit hash, seed; outputs valid JSON; status: "STABLE" iff all checks PASS; exits 1 if UNSTABLE
Depends on:           T-1719

---

T-1721: Generate VR_Report_v17.json — status STABLE

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-7, §9 Verification, §6 M9
Invariants:           I-VR-REPORT-1, I-VR-STABLE-10
spec_refs:            [Spec_v17 §9 Verification, I-VR-REPORT-1, I-VR-STABLE-10]
produces_invariants:  []
requires_invariants:  [I-VR-REPORT-1, I-FAIL-DETERMINISTIC-1, I-EVOLUTION-FORWARD-1, I-VR-STABLE-5]
Inputs:               scripts/generate_vr_report.py, Makefile, tests/integration/test_runtime_enforcement.py, tests/integration/test_evolution.py, tests/integration/test_failure_semantics.py
Outputs:              .sdd/reports/VR_Report_v17.json
Acceptance:           make vr-release exits 0; .sdd/reports/VR_Report_v17.json exists; jq .status returns "STABLE"; report contains commit_hash, seed, all property names
Depends on:           T-1720, T-1713, T-1715, T-1716

---

T-1723: Fix activate-phase idempotency — include phase_id in payload

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0 — kernel correctness; I-IDEM-SCHEMA-1
Invariants:           I-IDEM-SCHEMA-1, I-IDEM-LOG-1
spec_refs:            [Spec_v17 §2 BC-VR-0, I-IDEM-SCHEMA-1, I-IDEM-LOG-1]
produces_invariants:  [I-IDEM-SCHEMA-1]
requires_invariants:  [I-KERNEL-WRITE-1]
Inputs:               src/sdd/commands/activate_phase.py
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           ActivatePhaseCommand.payload contains phase_id and tasks_total; compute_command_id produces distinct hash per (phase_id, tasks_total) pair; two runs of activate-phase N --tasks T with same N and T are idempotent (no-op); two runs with different T produce distinct events; pytest tests/unit/commands/test_activate_phase.py passes
Depends on:

---

T-1724: Fix DependencyGuard — em-dash sentinel + missing reason field

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0 — kernel correctness; I-CMD-11, I-GUARD-REASON-1
Invariants:           I-CMD-11, I-GUARD-REASON-1
spec_refs:            [I-CMD-11, I-GUARD-REASON-1]
produces_invariants:  [I-CMD-11, I-GUARD-REASON-1]
requires_invariants:  []
Inputs:               src/sdd/domain/guards/context.py, src/sdd/domain/guards/dependency_guard.py, tests/unit/guards/test_dependency_guard.py
Outputs:              src/sdd/domain/guards/context.py, src/sdd/domain/guards/dependency_guard.py, tests/unit/guards/test_dependency_guard.py
Acceptance:           load_dag filters sentinel values ("—", "-", "") from task.depends_on so they are not treated as real task_ids; DependencyGuard.check populates GuardResult.reason=reason on DENY (not only message); sdd complete T-1701 exits 0 after fix; new tests cover: task with depends_on="—" → ALLOW, task with unmet real dep → GuardViolationError with non-empty reason; existing tests pass
Depends on:           —

---

---

T-1725: Fix PhaseGuard missing reason field + event_factory invalid source default

Status:               DONE
Spec ref:             Spec_v17 §2 BC-VR-0 — kernel correctness; I-GUARD-REASON-1
Invariants:           I-GUARD-REASON-1
spec_refs:            [I-GUARD-REASON-1]
produces_invariants:  [I-GUARD-REASON-1]
requires_invariants:  [I-GUARD-REASON-1, I-KERNEL-WRITE-1]
Inputs:               src/sdd/domain/guards/phase_guard.py, tests/harness/fixtures.py
Outputs:              src/sdd/domain/guards/phase_guard.py, tests/harness/fixtures.py
Acceptance:           (1) GuardResult on all three PhaseGuard DENY paths (PG-1, PG-2, PG-3) populates reason="GUARD_DENY.PhaseGuard.PG-N" — registry.py A-15 check (I-GUARD-REASON-1) passes and guard rejection raises GuardViolationError, not KernelInvariantError; (2) make_minimal_event and event_factory default event_source changed from "test" to "runtime" so that events produced by event_factory() without overrides are accepted by sdd_append_batch/_validate_source without ValueError; (3) new unit tests cover: PhaseGuard DENY on each of PG-1/PG-2/PG-3 emits GuardResult with non-empty reason matching "GUARD_DENY.PhaseGuard.PG-[123]"; event_factory() default produces event with event_source == "runtime"; (4) all existing 560+ tests pass without regression
Depends on:           T-1724

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->
