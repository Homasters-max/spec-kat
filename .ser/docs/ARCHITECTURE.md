# SER v2.3 — Self-Evolving Runtime Architecture

## 1. System Overview

SER is a deterministic, self-evolving execution system that mutates and validates its own specifications through event-sourced causality, multi-phase statistical attribution, and production-grade safeguards.

**Core Guarantees:**
- Determinism: Given identical state/seed, execution produces identical output.
- Causal Correctness: All state changes immutably logged and replayable.
- Evolutionary Safety: Spec mutations validated before promotion via Phase 1-3 statistical testing.
- Production Safety: Circuit breaker + human gate protect against degradation.

**When to use:** Real-time adaptive systems requiring human-in-the-loop evolution with formal guarantees of determinism and safety.

**Formal Definition:**
```
SER := ⟨L0, L1, L2, L3, G, C, T⟩
L0 = Spec (immutable DAG, convergence pre-validated)
L1 = Execution (event-sourced, partition-aware, environment-snapshotted)
L2 = Evaluation (deterministic metrics, risk modeling, ≥2-test simulation)
L3 = Evolution (proposer-driven, adaptive trust region, Phase 3 multi-test)
G  = Guard (circuit breaker + human gate event-sourced + policy rollback)
C  = Context (deterministic assembly, slot boundaries, versioned algorithm)
T  = Telemetry (independent SLA, global event_id registry, schema upcasting)

Formal Execution Model:
  State_{t+1} = Reduce(State_t, Event_t)
  Reducer: (State × Event) → State  — pure, total, deterministic function
```

**Layer Model:**
- **L0:** Spec versioning, DSL validation, lineage DAG, immutability guarantee.
- **L1:** Event-sourced execution, partition-aware state materialization, environment snapshot at execution start, per-partition total order + cross-partition causal consistency, scheduler liveness guarantee (no starvation under bounded load).
- **L2:** Deterministic metrics, risk classification (seed=42), Phase 1 simulator; Phase 3 requires ≥2 independent statistical tests agreeing.
- **L3:** Candidate proposer (immutable strategy), Phase 1-3 evaluation, adaptive trust region Δ_t = f(stability, variance, success_rate).
- **G:** Circuit breaker (0.1 error threshold, 5m window), human gate event-sourced (approvals are events), policy rollback guard-controlled.
- **C:** Fragment selection (TRUNCATE_ONLY|TEXRANK_SEED_0), slot token budgets, deterministic assembly; tokenizer + algorithm versioned.
- **T:** Global event_id registry (hash index) for exactly-once beyond 24h; schema registry with upcasting; independent observability SLA.

---

## 2. End-to-End Pipeline

```
INPUT: Spec DSL
  ↓
[SpecManagement] Validate syntax, compile to SQL IR
  Invariant: I-P-1 (Immutability) — spec immutable once created
  ↓
[L0→L1] Emit SpecCreated(spec_id, parent_spec_id, version, definition_sql)
  Invariant: I-P-5 (Lineage DAG) — parent_spec_id recorded for every spec except Spec_0
  ↓
[Bootstrap] 1000-step entropy test on Spec_0
  Emit: ConvergenceValidated(entropy_trajectory, passed=true)
  Invariant: I-NEW-11 — bootstrap blocked if convergence test fails
  ↓
[ExecutionRuntime] Freeze cost_model_version, guard_policy_version, policy_version
  Emit: ExecutionCreated(execution_id, spec_version_id, cost_model_version, policy_version, guard_policy_version)
  Emit: ExecutionEnvironmentSnapshot(execution_id, python_version, lib_versions, sql_engine_version, hardware_class)
  Invariant: I-NEW-2 — cost_model(version) used throughout; no mutations
  Invariant: I-NEW-21 — replay requires identical environment snapshot
  ↓
[ExecutionRuntime] Emit ExecutionSpecBinding(execution_id, spec_version_id) BEFORE execution
  Invariant: I-NEW-5 — ExecutionSpecBinding precedes ExecutionFinished
  ↓
[Scheduler] readyEvents(partition_key, state_version, policy_id)
  → SortedList via (priority DESC, partition_key, event_id)
  Invariant: I-NEW-12 — identical state → identical ExecSet
  ↓
[ExecutionRuntime] Apply events (dedup 24h window via event_id)
  On duplicate: emit EventDeduped, skip
  Invariant: I-NEW-16 — each event_id processed once within 24h
  ↓
[Reducer] Materialize state (partition-aware); apply schema upcasting if needed
  Emit: SchemaVersionMigrated on upcast
  Invariant: I-NEW-17 — old events upgraded before processing
  ↓
[ExecutionRuntime] Emit ExecutionFinished(execution_id, final_state, spec_version_id)
  Invariant: I-P-3 — replaying same events → same final_state
  ↓
[Evaluation] Compute deterministic metrics (no RNG, no APIs)
  Emit: MetricComputed(metric_id, execution_id, metric_spec_version, value, snapshot_id)
  Invariant: I-NEW-19 — identical inputs → identical metric value
  ↓
[ContextAssembly] Select fragments via (relevance DESC, source_id, fragment_id)
  Emit: FragmentSelected(slot, fragment_id, selected_index) per fragment
  Apply ContextSlotBoundary: if overflow → TRUNCATE (ContextSlotTruncated) or REJECT (ContextSlotOverflowed)
  Invariant: I-NEW-7 (Fragment Tie-Breaking), I-NEW-8 (Slot Boundaries)
  ↓
[ContextAssembly] Emit ContextWindowBuilt(execution_id, fragments[], strategy, hash, tokenizer_version, algorithm_version)
  Invariant: I-NEW-1 — identical state/policy → identical ContextWindow hash
  Invariant: I-NEW-28 — tokenizer_version + algorithm_version recorded; replay with different version rejected
  ↓
[Evaluation] RiskModel(seed=42) infers risk_score; emit RiskModelTrained if outdated
  Invariant: I-NEW-14 — same seed/features → same risk_score
  ↓
[Evolution] Phase 1: Simulator(seed=hash(sample_id, spec_ids))
  Emit: SimulationCompleted(seed, sample_hash, estimated_delta, confidence, p_value)
  Invariant: I-NEW-15 — same seed/sample → same confidence
  ↓
[Evolution] Phase 2: Shadow deployment; measure divergence (no user impact)
  ↓
[Evolution] Phase 3: ≥2 independent statistical tests (e.g. t-test + bootstrap or Mann-Whitney, alpha=0.05)
  Emit: PromotionStatisticalTest(candidate_id, test_type, p_value, effect_size, sample_n) — once per test
  Emit: AttributionPhase3Complete(confidence_score ≥ 0.7, recommendation, tests_passed[])
  Invariant: I-NEW-6 — DeltaAccepted requires p_value < 0.05, confidence ≥ 0.7
  Invariant: I-NEW-25 — all ≥2 tests must agree; single-test promotion forbidden
  ↓
[Evolution] Update adaptive trust region: Δ_t = f(stability_score, reward_variance, success_rate)
  Emit: TrustRegionUpdated(cycle_id, Δ_t_prev, Δ_t_new, stability_score, success_rate)
  Invariant: I-NEW-24 — Δ_t is adaptive, not static
  ↓
[Evolution] Validate: d(parent_spec, new_spec) ≤ Δ_t
  Emit: SpecDeltaValidated(delta_id, distance_computed, Δ_t, passed)
  Invariant: I-NEW-9 — reject if distance > Δ_t
  ↓
[Evolution] Validate: target_spec_id ≠ proposer_spec_id
  If violated: emit ProposerSelfMutationBlocked; reject
  Invariant: I-NEW-10 — proposer cannot mutate itself
  ↓
[GuardSystem] Check CircuitBreaker (frozen guard_policy_version)
  If error_rate > 0.1 (5m) or consecutive_failures ≥ 3 → OPEN
  Emit: CircuitBreakerStateChange(state, trigger_reason, error_count)
  Invariant: I-NEW-13 — thresholds immutable within execution
  ↓
[GuardSystem] If high_risk: emit HumanGatePending(deadline, approvers, link)
  Emit: HumanGateTimeoutApproaching at deadline−20h (escalate)
  Await: HumanGateApproved(approver_id, timestamp) OR HumanGateDenied(approver_id, reason)
  Invariant: I-P-9 — every deployment gated by CB and HG
  Invariant: I-NEW-27 — human gate decisions are first-class domain events (event-sourced)
  ↓
[Evolution] Emit DeltaAccepted(candidate_id, deployment_strategy=canary)
  ↓
[Deployment] Canary rollout → monitor for degradation
  If degradation: emit CircuitBreakerStateChange(OPEN) + Rollback(to=parent_spec_id)
  Else: full production rollout
  ↓
OUTPUT: Production Spec Active
```

---

## 3. Bounded Contexts

### [BC-1] SpecManagement
**Responsibility:** Define, version, validate Specs; enforce immutability and lineage.
**Key Entities:** Spec(id, definition_sql, parent_spec_id, version), SpecDelta(source, target, distance), SpecArchive
**Key Events:** SpecCreated, SpecDeltaValidated, ConvergenceValidated, ArchiveIndexUpdated
**Dependencies:** → Evolution (for SpecDelta validation), Telemetry

### [BC-2] ExecutionRuntime
**Responsibility:** Event-sourced execution; partition-aware state materialization via pure Reducer; environment snapshotting.
**Key Entities:** Execution(id, spec_version_id, policy_version_id, cost_model_version, guard_policy_version), EventLog, ExecutionEnvironmentSnapshot
**Key Events:** ExecutionCreated, ExecutionEnvironmentSnapshot, ExecutionSpecBinding, ExecutionFinished, EventDeduped, CostModelError
**Key Invariants:** I-NEW-21 (env snapshot), I-NEW-22 (partition consistency model), I-NEW-23 (scheduler liveness), I-NEW-30 (Reducer pure)
**Dependencies:** → SpecManagement (reads Spec), Guard (policy_version), ContextAssembly

### [BC-3] ContextAssembly
**Responsibility:** Deterministic ContextWindow assembly from execution state; slot boundaries; fragment tie-breaking; algorithm and tokenizer versioning.
**Key Entities:** ContextSpec(fragment_strategy, slot_definitions[], tokenizer_version, algorithm_version), ContextWindow(id, fragments[], strategy, tokenizer_version, algorithm_version), Fragment
**Key Events:** ContextWindowBuilt (includes tokenizer_version, algorithm_version), FragmentSelected, ContextSlotTruncated, ContextSlotOverflowed
**Key Invariants:** I-NEW-28 (context algorithm versioned; replay with different version rejected)
**Dependencies:** → ExecutionRuntime (reads state), Policy (fragment_strategy, relevance_weights)

### [BC-4] Evaluation
**Responsibility:** Deterministic metrics; risk modeling; multi-phase simulation and attribution.
**Key Entities:** MetricSpec(id, definition_sql, version), RiskModel(checksum, seed=42), Simulator(seed)
**Key Events:** MetricComputed, RiskModelTrained, SimulationCompleted, RelevanceWeightsUpdated
**Dependencies:** → ExecutionRuntime (reads trace), SpecManagement (reads candidates)

### [BC-5] Evolution
**Responsibility:** Spec mutation, candidate generation, adaptive trust region, Phase 3 multi-test promotion.
**Key Entities:** Candidate(spec_delta, phase), ProposerStrategy(seed=42, PROTECTED ACL), Policy(version, scheduler_weights), TrustRegionState(Δ_t, stability_score, reward_variance, success_rate)
**Key Events:** CandidateProposed, PromotionStatisticalTest (one per test; ≥2 required), AttributionPhase3Complete (tests_passed[]), TrustRegionUpdated, DeltaAccepted, DeltaRejected, ProposerSelfMutationBlocked, PolicyActivated
**Key Invariants:** I-NEW-24 (adaptive Δ_t), I-NEW-25 (≥2 tests must agree)
**Dependencies:** → SpecManagement, Evaluation, Guard

### [BC-6] GuardSystem
**Responsibility:** Circuit breaker state management; human gate escalation (fully event-sourced); pre-deployment gating; policy rollback gating.
**Key Entities:** GuardPolicy(cb_error_rate: 0.1, error_window: 5m, rollback_window: 1h, consecutive_failures: 3), HumanGateAggregate (event-sourced)
**Key Events:** CircuitBreakerStateChange, HumanGatePending, HumanGateTimeoutApproaching, HumanGateApproved, HumanGateDenied, Rollback
**Key Invariants:** I-NEW-27 (human gate decisions are domain events), I-NEW-29 (policy rollback gated by CB and HG)
**Dependencies:** → SpecManagement (rollback), ExecutionRuntime (observes errors), Policy (gates PolicyRolledBack)

### [BC-7] Telemetry
**Responsibility:** Independent observability; global exactly-once event registry; schema versioning and upcasting.
**Key Entities:** GlobalEventRegistry(event_id → content_hash, permanent), SchemaRegistry(event_type, version, upcast_rules)
**Key Events:** EventDeduped, SchemaVersionMigrated; consumes all domain events
**Key Invariants:** I-NEW-26 (global event_id registry — exactly-once across replay and DR, supersedes 24h window)
**Dependencies:** → all layers

### [BC-8] Policy
**Responsibility:** Centralized versioned configuration; scheduler weights and guard thresholds via event sourcing; safe guard-controlled rollback.
**Key Entities:** Policy(version, scheduler_weights, guard_config), PolicyRollback(from_version, to_version, reason)
**Key Events:** PolicyUpdateProposed, PolicyActivated, PolicyRolledBack, SchedulerWeightsChanged
**Key Invariants:** I-NEW-29 (every PolicyActivated reversible; rollback gated by CB and HG)
**Dependencies:** → ExecutionRuntime, ContextAssembly, GuardSystem

---

## 4. Core Invariants (42 Total)

### New Invariants (I-NEW-1..20)

| # | Name | Statement |
|---|------|-----------|
| I-NEW-1 | Deterministic Context Assembly | Identical (task_id, policy_id, spec_id, snapshot_id) → identical ContextWindow hash. |
| I-NEW-2 | Cost Model Immutability | ExecutionCreated freezes cost_model_version; no mutations through ExecutionFinished. |
| I-NEW-3 | Policy Event Sourcing | Policy state = Reduce([PolicyInitialized, PolicyUpdateProposed*, PolicyActivated*]). |
| I-NEW-4 | ProposerStrategy Immutability | ProposerStrategy(V) immutable; changes only via ProposerStrategyTrained event. |
| I-NEW-5 | Execution-Spec Causal Binding | ExecutionSpecBinding(execution_id, spec_version_id) precedes ExecutionFinished. |
| I-NEW-6 | Attribution Confidence | DeltaAccepted requires p_value < 0.05 and confidence ≥ 0.7. |
| I-NEW-7 | Fragment Tie-Breaking | Fragment selection: (slot, relevance DESC, source_id, fragment_id) — deterministic. |
| I-NEW-8 | Slot Boundary Enforcement | sum(slot.tokens) ≤ max_tokens; overflow applies TRUNCATE or REJECT strategy. |
| I-NEW-9 | Trust Region Containment | Every promoted Spec: d(S_parent, S) ≤ Δ_t (current trust radius). |
| I-NEW-10 | Proposer Not Self-Targeting | target_spec_id ≠ current_proposer_spec_id; rejected if equal. |
| I-NEW-11 | Convergence Verified Before Bootstrap | ConvergenceValidated event required before Spec_0; 1000-step entropy test. |
| I-NEW-12 | Scheduler Deterministic Tie-Breaking | ReadyEvents sorted by (priority DESC, partition_key, event_id). |
| I-NEW-13 | Guardian Policy Thresholds Immutable | GuardPolicy thresholds immutable within execution; versioned by guard_policy_version. |
| I-NEW-14 | RiskModel Deterministic | RiskModel(seed=42, features) → same risk_score always. |
| I-NEW-15 | Simulator Deterministic | Simulator(spec_old, spec_new, sample, seed) → same SimulationCompleted always. |
| I-NEW-16 | Exactly-Once Event Processing | Each event_id processed once; 24h dedup window via EventDedup aggregate. |
| I-NEW-17 | Schema Upcasting | When event_schema_version < current, Reducer applies upcast function before processing. |
| I-NEW-18 | Agent Output Validation | Every agent output validated against AgentOutput JSON Schema; invalid rejected. |
| I-NEW-19 | Metric Computation Deterministic | MetricComputed: no RNG, no external APIs; identical inputs → identical value. |
| I-NEW-20 | Fragment Summarization Deterministic | fragment_strategy ∈ {TRUNCATE_ONLY, TEXRANK_SEED_0}; LLM-based forbidden. |
| I-NEW-21 | Execution Environment Snapshot | ExecutionEnvironmentSnapshot(execution_id, python_version, lib_versions, sql_engine_version, hardware_class) emitted at ExecutionCreated; replay requires identical snapshot. |
| I-NEW-22 | Event Log Consistency Model | Within a partition: total order. Cross-partition: causal consistency. No global total order required or assumed. |
| I-NEW-23 | Scheduler Liveness | Under bounded load, every ready event is eventually scheduled; infinite starvation is forbidden. |
| I-NEW-24 | Adaptive Trust Region | Δ_t updated after each evolution cycle: Δ_t = f(stability_score, reward_variance, success_rate); change emitted as TrustRegionUpdated event. |
| I-NEW-25 | Multi-Test Statistical Agreement | Phase 3 promotion requires ≥2 independent tests (e.g. t-test + bootstrap, or t-test + Mann-Whitney) all passing at alpha=0.05; single-test approval forbidden. |
| I-NEW-26 | Global Exactly-Once Event Processing | Global event_id registry (hash index) prevents any reprocessing ever, including across replay and DR scenarios; 24h dedup window is a subset of this guarantee. |
| I-NEW-27 | Human Gate Event-Sourced | HumanGateApproved/HumanGateDenied are first-class domain events; approval state is derived by replaying these events, not from external side-channel. |
| I-NEW-28 | Context Algorithm Versioned | ContextWindowBuilt records tokenizer_version and algorithm_version; replay with a different version is rejected. |
| I-NEW-29 | Policy Rollback Safety | Every PolicyActivated can be reversed by emitting PolicyRolledBack; rollback gated by CircuitBreaker and (if high-risk) HumanGate. |
| I-NEW-30 | Reducer Is Pure | Reducer: (State × Event) → State is a total, side-effect-free, deterministic function; any I/O or randomness in Reducer is a protocol violation. |

### Modified Invariants (I-MOD-1..7)

| # | Was | Now |
|---|-----|-----|
| I-MOD-1 | E[ΔH_t] → 0 (stated) | + 1000-step synthetic test; ConvergenceValidated event mandatory before bootstrap. |
| I-MOD-2 | Determinism promised | All randomness fixed-seed event-sourced; 5 new events verify determinism. |
| I-MOD-3 | Replayability promised | ContextWindowBuilt, PolicyActivated, ProposerStrategyTrained — fully event-sourced. |
| I-MOD-4 | Cost model could mutate mid-exec | Frozen at ExecutionCreated; Reducer rejects mid-execution mutations. |
| I-MOD-5 | Simulator undefined, Phase 3 circular | Phase 1 simulator deterministic; Phase 3 requires PromotionStatisticalTest. |
| I-MOD-6 | Convergence unverified, trust unenforced | Convergence empirically verified; trust region validated; self-targeting blocked. |
| I-MOD-7 | ExecutionFinished lacked spec_version_id | ExecutionSpecBinding mandatory; ExecutionFinished includes spec_version_id. |

### Preserved Invariants (I-P-1..15)

| # | Name | Statement |
|---|------|-----------|
| I-P-1 | Spec Immutability | Spec(id) immutable once created; new versions only via SpecDelta. |
| I-P-2 | Partition-Aware Parallelism | Partitions disjoint; one Reducer per partition. |
| I-P-3 | Event Idempotency | Same event applied twice → same state once. |
| I-P-4 | Causal Event Ordering | Events applied respecting dependency graph order. |
| I-P-5 | Spec Version Lineage | Every Spec has parent_spec_id (except Spec_0); forms DAG. |
| I-P-6 | Archive Immutability | Specs added once; never modified. |
| I-P-7 | Novelty Distance Validity | Novelty = min(distance(Spec, Archive_neighbors)); metric space properties hold. |
| I-P-8 | Multi-Objective Pareto Dominance | Frontier = non-dominated Specs on (reward, cost, risk, novelty). |
| I-P-9 | Guard System Pre-Deployment | CB and HG apply before every deployment. |
| I-P-10 | EventLog Append-Only | No deletions or mutations. |
| I-P-11 | Metric Computation Isolation | Metrics computed from execution state; no side effects. |
| I-P-12 | Safety Filter Non-Passthrough | Fragments not passed to agent without SafetyFilter.check. |
| I-P-13 | Rollback Semantics | On degradation, Rollback reverts to previous Spec version. |
| I-P-14 | Proposer Proposal Constraints | Candidates respect trust region and diversity. |
| I-P-15 | Learning Disabled for Critical Components | ProposerStrategy frozen in MVP. |

---

## 5. Key Use Cases (8 Total)

### [UC-1] Bootstrap System
**Input:** Spec_0 DSL, entropy_threshold
1. Validate Spec_0 syntax; run 1000-step entropy test.
2. Emit ConvergenceValidated(entropy_trajectory, passed).
3. Compile Spec_0 to SQL IR; emit SpecCreated.
4. Emit PolicyActivated(version=0, weights, guard_config).

**Output Events:** ConvergenceValidated, SpecCreated, PolicyActivated, ArchiveIndexUpdated

### [UC-2] Execute Spec
**Input:** Spec_version_id, input_data, execution_id
1. Freeze cost_model_version; emit ExecutionCreated.
2. Emit ExecutionEnvironmentSnapshot (I-NEW-21).
3. Emit ExecutionSpecBinding before execution.
4. Scheduler.readyEvents → sorted ExecSet via (priority DESC, partition_key, event_id); starvation-free (I-NEW-23).
5. Reducer (pure function, I-NEW-30) applies events; dedup via GlobalEventRegistry then 24h window (I-NEW-26); materialize state with upcasting.
6. Emit ExecutionFinished.

**Output Events:** ExecutionCreated, ExecutionEnvironmentSnapshot, ExecutionSpecBinding, EventDeduped*, ExecutionFinished

### [UC-3] Evaluate Execution
**Input:** execution_id, MetricSpec_version_ids[]
1. Compute deterministic metrics (no RNG/APIs); emit MetricComputed* (with snapshot_id).
2. Select fragments via tie-breaker; apply slot boundaries; emit ContextWindowBuilt.
3. Load frozen RiskModel(seed=42); compute risk_score; emit RiskModelTrained if outdated.

**Output Events:** MetricComputed*, ContextWindowBuilt, RiskModelTrained*, ContextSlotTruncated/Overflowed*

### [UC-4] Propose Spec Delta
**Input:** Parent_spec_id, phase ∈ {exploration, exploitation}
1. Update adaptive trust region: Δ_t = f(stability_score, reward_variance, success_rate); emit TrustRegionUpdated (I-NEW-24).
2. Load ProposerStrategy(seed=42, immutable); generate SpecDelta within new Δ_t.
3. Validate: target_spec_id ≠ proposer_spec_id (emit ProposerSelfMutationBlocked if violated).
4. Validate: d(parent, new) ≤ Δ_t; emit SpecDeltaValidated(passed=true|false).
5. Emit CandidateProposed.

**Output Events:** TrustRegionUpdated, ProposerSelfMutationBlocked*, SpecDeltaValidated, CandidateProposed

### [UC-5] Promote Candidate to Production
**Input:** Candidate_id, Phase 1/2 results
1. Run ≥2 independent tests (e.g. t-test + bootstrap); emit PromotionStatisticalTest per test (I-NEW-25).
2. If any test fails → DeltaRejected. Validate confidence ≥ 0.7; emit AttributionPhase3Complete(tests_passed[]).
3. Check CircuitBreaker (if OPEN → DeltaRejected); emit HumanGatePending if high_risk.
4. Await HumanGateApproved or HumanGateDenied (event-sourced, I-NEW-27); Denied → DeltaRejected.
5. Emit DeltaAccepted; initiate Canary; monitor; Rollback on degradation.

**Output Events:** PromotionStatisticalTest*, AttributionPhase3Complete, DeltaAccepted/DeltaRejected, HumanGatePending*, HumanGateApproved/Denied*, Rollback*

### [UC-6] Rollback on Degradation
**Input:** execution_id, threshold_breach
1. Detect degradation (error_rate > 0.1 or reward_delta < threshold).
2. Emit CircuitBreakerStateChange(OPEN, trigger_reason).
3. Load parent_spec_id; emit Rollback(from, to=parent); cancel canary.

**Output Events:** CircuitBreakerStateChange, Rollback, HumanGatePending*

### [UC-7] Assemble Context for Agent
**Input:** execution_id, ContextSpec
1. Select fragments per slot via (relevance DESC, source_id, fragment_id); emit FragmentSelected*.
2. Apply ContextSlotBoundary: TRUNCATE (ContextSlotTruncated) or REJECT (ContextSlotOverflowed).
3. Apply SafetyFilter.check; emit ContextWindowBuilt.

**Output Events:** FragmentSelected*, ContextSlotTruncated/Overflowed*, ContextWindowBuilt

### [UC-8] Update Policy
**Input:** policy_update{scheduler_weights?, guard_config?}
1. Validate schema (weights sum ≤ 1.0, all ≥ 0, timeouts > 0).
2. Emit PolicyUpdateProposed; await approval.
3. Emit PolicyActivated(version+1); new executions use updated version.

**Output Events:** PolicyUpdateProposed, PolicyActivated, SchedulerWeightsChanged*

### [UC-9] Rollback Policy
**Input:** from_version, to_version, reason
1. Check CircuitBreaker; if high-risk emit HumanGatePending and await HumanGateApproved (I-NEW-29).
2. Validate to_version exists in policy event history.
3. Emit PolicyRolledBack(from_version, to_version, reason, guard_state).
4. New executions use to_version; ongoing executions retain frozen policy_version.

**Output Events:** HumanGatePending*, HumanGateApproved*, PolicyRolledBack

---

## 6. Event Catalog

| Event | Emitted By | Key Data | Consumed By |
|-------|-----------|----------|------------|
| SpecCreated | SpecManagement | spec_id, parent_spec_id, version, definition_sql | Archive, Evolution, Telemetry |
| SpecDeltaValidated | Evolution | delta_id, distance_computed, Δ_t, passed | Evolution (gates DeltaAccepted), Telemetry |
| ConvergenceValidated | Bootstrap | entropy_trajectory[], passed | Bootstrap (gates init), Telemetry |
| ExecutionCreated | ExecutionRuntime | execution_id, spec_version_id, cost_model_version, policy_version, guard_policy_version | Scheduler, Reducer, Telemetry |
| ExecutionSpecBinding | ExecutionRuntime | execution_id, spec_version_id | Reducer (validates ExecutionFinished), Telemetry |
| ExecutionFinished | ExecutionRuntime | execution_id, final_state, spec_version_id | Evaluation, Evolution, Guard, Telemetry |
| EventDeduped | EventLog/Reducer | event_id, event_type, payload_hash | Telemetry |
| MetricComputed | Evaluation | metric_id, execution_id, metric_spec_version, value, snapshot_id | Evolution, Guard, Telemetry |
| ContextWindowBuilt | ContextAssembly | execution_id, fragments[], strategy, context_hash | Evaluation, Evolution, Reducer, Telemetry |
| FragmentSelected | ContextAssembly | slot, fragment_id, selected_index | Reducer, Telemetry |
| ContextSlotTruncated | ContextAssembly | slot, tokens_removed, strategy | Telemetry, Reducer |
| ContextSlotOverflowed | ContextAssembly | slot, tokens_over, rejected_fragment_id | Telemetry, Reducer |
| RiskModelTrained | Evaluation | model_checksum, sklearn_version, xgboost_version, seed=42 | Evolution, Telemetry |
| SimulationCompleted | Simulator | seed, sample_hash, estimated_delta, confidence, p_value | Evolution, Telemetry |
| PromotionStatisticalTest | Evolution | candidate_id, p_value, effect_size, sample_n | Evolution (gates DeltaAccepted), Telemetry |
| AttributionPhase3Complete | Evolution | confidence_score, p_value, recommendation | Evolution (gates DeltaAccepted), Telemetry |
| CandidateProposed | Evolution/Proposer | candidate_id, spec_delta, phase | Evolution (routes to evaluation), Telemetry |
| DeltaAccepted | Evolution | candidate_id, spec_version_id, deployment_strategy | Guard, Canary, Telemetry |
| DeltaRejected | Evolution | candidate_id, rejection_reason | Evolution, Telemetry |
| ProposerSelfMutationBlocked | Evolution | proposer_spec_id, target_spec_id | Evolution, Guard, Telemetry |
| CircuitBreakerStateChange | Guard | state (CLOSED/OPEN/HALF_OPEN), trigger_reason, error_count | DeltaAccepted block, Rollback, Telemetry |
| HumanGatePending | Guard | candidate_id, deadline, approver_ids[], slack_link/github_pr | Slack/GitHub API, Telemetry |
| HumanGateApproved | Guard | candidate_id, approver_id, timestamp | Canary deployment, Telemetry |
| HumanGateTimeoutApproaching | Guard | candidate_id, deadline | Escalation channel, Telemetry |
| PolicyUpdateProposed | Policy | update_id, proposed_config, author, timestamp | Review process, Telemetry |
| PolicyActivated | Policy | version, scheduler_weights, guard_config, applied_time | Scheduler, ContextEngine, Guard, Telemetry |
| SchedulerWeightsChanged | Scheduler | version, new_weights | Scheduler, Telemetry |
| ProposerStrategyTrained | Evolution | model_id, training_data_hash, seed=42, version | Evolution, Telemetry |
| CostModelRetrained | Scheduler | model_checksum, feature_list, seed, RMSE | Scheduler, Telemetry |
| CostModelError | Execution | actual_cost, estimated_cost, error_ratio | Scheduler (triggers retraining), Telemetry |
| RelevanceWeightsUpdated | ContextAssembly | policy_version, new_weights, changed_slots | ContextEngine, Telemetry |
| ArchiveIndexUpdated | Archive | index_type, index_hash, updated_spec_ids[] | Evolution (nearest-neighbor), Telemetry |
| AgentDecisionValidated | Evolution | agent_output, schema_errors[] | Evolution, Telemetry |
| SchemaVersionMigrated | Reducer | old_version, new_version, upcast_rule | Reducer, Telemetry |
| Rollback | Guard/Evolution | spec_to_revert_from, spec_to_revert_to, reason | Execution, Telemetry |
| ExecutionEnvironmentSnapshot | ExecutionRuntime | execution_id, python_version, lib_versions, sql_engine_version, hardware_class | Telemetry, Replay validator |
| TrustRegionUpdated | Evolution | cycle_id, Δ_t_prev, Δ_t_new, stability_score, reward_variance, success_rate | Evolution (next candidate), Telemetry |
| HumanGateDenied | Guard | candidate_id, approver_id, reason, timestamp | Evolution (reject), Telemetry |
| PolicyRolledBack | Policy | from_version, to_version, reason, guard_state | ExecutionRuntime, Scheduler, Telemetry |

---

## 7. Weak Points & Mitigations

### W1: Cost Model Staleness During Long-Running Executions
**Issue:** Cost model trained offline; new patterns emerge mid-execution.
**Consequence:** Scheduler misallocates resources; SLA violated.
**Mitigation:** CostModelError event tracked; mean_error > 0.2 triggers CostModelDegraded → retraining. New cost_model_version freezes in next ExecutionCreated.

### W2: Context Window Overflow Edge Cases
**Issue:** Fragment selection tie-breaker may not scale with new fragment types.
**Consequence:** ContextWindowBuilt hash changes across versions; replay diverges.
**Mitigation:** TRUNCATE_ONLY default is trivial and deterministic. TEXRANK_SEED_0 optional. Fragment registry versioned per policy_version.

### W3: RiskModel Training Imbalance
**Issue:** Failure class rare; SMOTE may not capture tail risks.
**Consequence:** risk_score underestimates actual failure probability.
**Mitigation:** class_weight='balanced' + SMOTE. RiskModelTrained event captures sklearn_version, xgboost_version, seed=42. Phase 1 simulator provides additional validation.

### W4: ProposerStrategy Learning Disabled in MVP
**Issue:** Proposer frozen; no online learning.
**Consequence:** Evolution explores naively; slower convergence.
**Mitigation:** ProposerStrategyTrained event schema defined; Phase 2 enables online update (PROTECTED ACL enforced by I-NEW-4).

### W5: Human Gate Deadline Variability
**Issue:** Approver absent; deadline missed.
**Consequence:** High-risk spec stalls; evolution blocked.
**Mitigation:** HumanGateTimeoutApproaching at deadline−20h; escalate to backup. Emergency stop via admin force-reject console.

### W6: Spec Distance Metric Subjectivity
**Issue:** SpecSpace distance(S1, S2) depends on feature vector quality.
**Consequence:** Trust region may be too loose or tight; affects evolution diversity.
**Mitigation:** Distance via KD-tree on [complexity, reward_variance, cost_mean]. Pareto front ensures diversity on (reward, cost, risk, novelty). Step annealing reduces Δ_t over time.

### W7: Exactly-Once Semantics Across Partition Failures
**Issue:** Dedup 24h window may miss replays after partition leader crash or DR scenario.
**Consequence:** Event processed twice; state diverges.
**Mitigation:** Global event_id registry (hash index) replaces 24h-window as authoritative guard (I-NEW-26). EventDedup aggregate event-sourced; registry replayed before Reducer on crash.

### W8a: No Backpressure Model
**Issue:** System has no explicit backpressure mechanism; fast producers can overwhelm Reducers.
**Consequence:** Scheduler queue grows unbounded; liveness (I-NEW-23) violated under spike load.
**Mitigation (Phase 2):** Per-partition admission control; Scheduler emits BackpressureSignal when queue depth > threshold; producers throttle on receipt.

### W8b: No Latency SLA on Individual Executions
**Issue:** Only error-rate is enforced; a slow execution never triggers the circuit breaker.
**Consequence:** Tail latencies can silently degrade without rollback.
**Mitigation (Phase 2):** p99 latency added as circuit-breaker trigger; LatencySLABreached event emitted and consumed by GuardSystem.

### W8c: No Failure Domain Isolation
**Issue:** A single noisy tenant or partition can exhaust shared Reducer threads.
**Consequence:** Cross-partition contamination; determinism of other partitions at risk.
**Mitigation (Phase 2):** Partition-level resource quotas; failure domains isolated by Reducer process boundaries.

### W8d: No Multi-Tenant Isolation
**Issue:** Multiple tenants share event log and Reducer without namespace separation.
**Consequence:** One tenant's burst affects another's latency and liveness.
**Mitigation (Phase 2):** Tenant-scoped partitions; per-tenant GuardPolicy and latency SLA.

### W9: Policy Activation Race Condition
**Issue:** New policy_version activated; some executions use old version, others new.
**Consequence:** Scheduler weights differ across concurrent executions; divergence.
**Mitigation:** ExecutionCreated freezes policy_version; ongoing executions unaffected. PolicyActivated applies only to subsequent ExecutionCreated (I-NEW-2, I-NEW-13). Bad policy reversible via PolicyRolledBack (I-NEW-29).

---

## 8. Production Readiness Gaps (Phase 2)

**Proposer & Evolution:**
- ProposerStrategy online learning disabled (frozen in MVP, I-P-15)
- Multi-objective lexicographic ordering not implemented (Pareto dominance only)
- Trust region annealing (Δ_t decay schedule) not implemented
- Multi-proposer selection and coordination (G-M7) deferred

**Context & Relevance:**
- Context relevance learned ranking deferred (manual weights; no online tuning)
- Deterministic summarization (TEXRANK_SEED_0) not fully specified
- Multi-agent context isolation enforcement (G-M18) deferred

**Resilience:**
- R-CONSENSUS-1: Raft consensus for Spec promotion (centralized approval for MVP)
- R-PARTITION-1: Dynamic partition rebalancing (static partitions in MVP)
- R-COST-2: Gradient-based cost model anomaly detection deferred

**Safety & Observability:**
- Fairness metrics (reward parity by cohort) deferred (G-M7)
- Cost variance / tail risk modeling deferred (G-M11)
- Domain-specific safety metrics deferred (G-M13..G-M19)

**System-Level (from Critical Gap Analysis):**
- Backpressure model: per-partition admission control, BackpressureSignal event (W8a)
- Latency SLA enforcement: p99 circuit-breaker trigger, LatencySLABreached event (W8b)
- Failure domain isolation: Reducer process boundaries, per-partition resource quotas (W8c)
- Multi-tenant isolation: tenant-scoped partitions, per-tenant GuardPolicy (W8d)

**Simplifications Not Applied (SC-1..8):**
- SC-1: Cost model offline only; no streaming update
- SC-2: Rollback automation (requires human approval; no auto-revert)
- SC-3..SC-8: Optimization layer (A/B test interaction, smart escalation) deferred

---

## 9. Glossary (50 Core Terms)

| Term | Type | Definition (≤10 words) |
|------|------|----------------------|
| Archive | Aggregate | Immutable Spec collection with KD-tree/FAISS search index |
| AttributionPhase3Complete | Event | Final causal inference: confidence ≥ 0.7, p_value, recommendation |
| Candidate | Aggregate | Proposed Spec under Phase 1-3 evaluation |
| Canary | Deployment | Limited production test before full rollout |
| CircuitBreaker | Pattern | CLOSED/OPEN/HALF_OPEN gate on error threshold |
| ContextAssembly | BC | Deterministic fragment selection and slot management |
| ContextWindow | Aggregate | Assembled context slots; deterministic; event-sourced |
| ConvergenceValidated | Event | 1000-step entropy test passed before bootstrap |
| CostModel | Function | Execution cost estimation; frozen per execution |
| DeltaAccepted | Event | Candidate promotion approved; canary initiated |
| DeltaRejected | Event | Candidate rejected (p_value ≥ 0.05 or guard open) |
| Determinism | Property | Identical input+seed → identical output always |
| EventLog | Aggregate | Append-only source of truth; no mutations |
| ExecutionCreated | Event | Execution start; all versions frozen |
| ExecutionSpecBinding | Event | Causal link: execution → spec_version_id |
| Evolution | BC | Spec mutation, evaluation, promotion, policy updates |
| Execution | Aggregate | Spec instance over input; event-sourced state machine |
| Fragment | Data Unit | Context element scored by relevance; slot-assigned |
| GuardPolicy | Aggregate | CB thresholds + HG escalation rules; versioned |
| GuardSystem | BC | Circuit breaker, human gate, pre-deployment gating |
| HumanGate | Pattern | Manual approval for high-risk deployments |
| HumanGatePending | Event | Approval required; deadline, Slack/GitHub link |
| Invariant | Constraint | Boolean property guaranteed by design (42 total) |
| MetricSpec | Value Object | Deterministic metric definition; versioned SQL |
| Policy | Aggregate | Versioned weights for Scheduler + guard thresholds |
| PolicyActivated | Event | Policy state change; version incremented |
| PromotionStatisticalTest | Event | Phase 3 t-test; p_value, effect_size, sample_n |
| ProposerStrategy | Aggregate | Immutable mutation generator; seed=42; PROTECTED |
| RiskModel | Aggregate | Failure classifier; SMOTE+XGBoost; seed=42 |
| Rollback | Operation | Revert to parent Spec on degradation |
| SafetyFilter | Component | Prevents PII/secrets leakage to agent |
| Scheduler | Component | Deterministic event prioritizer; tie-breaker applied |
| SimulationCompleted | Event | Phase 1 output; seed, estimated_delta, confidence |
| Simulator | Aggregate | Deterministic Phase 1 replay engine |
| Slot | Concept | Named context section with token budget |
| Spec | Aggregate | Immutable DAG of typed nodes; versioned |
| SpecDelta | Value Object | Incremental Spec change; versioned; distance-validated |
| SpecDeltaValidated | Event | Trust region check: d(parent, new) ≤ Δ_t |
| SpecSpace | Geometry | Formal metric space of valid Specs |
| SQL IR | Language | Deterministic canonical execution representation |
| Telemetry | BC | Independent observability; event dedup; schema upcasting |
| TrustRegion | Constraint | N(S_t, Δ_t) limiting Spec changes per step |
| UseCase | Pattern | Multi-BC orchestration (UC-1..8) |
| Evaluation | BC | Deterministic metrics, risk model, Phase 1-2 simulation |
| EventDeduped | Event | Duplicate event_id rejected; 24h window |
| FragmentSelected | Event | Fragment selection captured; deterministic index |
| Idempotency | Property | Same event applied twice → same state |
| MetricComputed | Event | Deterministic metric; no RNG or APIs |
| CostModelError | Event | Actual vs estimated cost; triggers retraining |
| ArchiveIndex | Data Structure | KD-tree/FAISS for nearest-neighbor Spec search |

---

**Document:** SER v2.3 — Unified Architecture (Critical Gaps Incorporated)
**Invariants:** 52 total (30 new, 7 modified, 15 preserved)
**Bounded Contexts:** 8
**Use Cases:** 8
**Events:** 39+
**Phase:** Production MVP (Phase 2 gaps listed in Section 8)

**Critical Gap Coverage:**
- Gap 1 (Reproducibility): I-NEW-21, ExecutionEnvironmentSnapshot event
- Gap 2 (Event Log Consistency): I-NEW-22, per-partition total order + causal cross-partition
- Gap 3 (Scheduler Liveness): I-NEW-23, starvation-free guarantee
- Gap 4 (Adaptive Trust Region): I-NEW-24, TrustRegionUpdated event
- Gap 5 (Statistical Validation): I-NEW-25, ≥2 tests required, PromotionStatisticalTest carries test_type
- Gap 6 (Global Exactly-Once): I-NEW-26, global event_id registry
- Gap 7 (Human Gate as Events): I-NEW-27, HumanGateApproved/Denied as domain events
- Gap 8 (Context Algorithm Drift): I-NEW-28, tokenizer_version + algorithm_version in ContextWindowBuilt
- Gap 9 (Policy Rollback Safety): I-NEW-29, PolicyRolledBack event + guard gating
- Gap 10 (Formal Execution Model): I-NEW-30, State_{t+1} = Reduce(State_t, Event_t), Reducer is pure
