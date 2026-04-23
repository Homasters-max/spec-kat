# Index — SER v2.3

## By Concept

| Query | Section | File |
|-------|---------|------|
| how context is built | Deterministic Context Assembly, slot boundaries, tie-breaking | bounded_contexts.md#BC-3, use_cases.md#UC-7 |
| spec mutation | Evolution trust region, self-targeting block | bounded_contexts.md#BC-5, use_cases.md#UC-4 |
| execution safety | Circuit breaker, human gate escalation | bounded_contexts.md#BC-6, use_cases.md#UC-5 |
| metric computation | Deterministic evaluation, risk model, simulator | bounded_contexts.md#BC-4, use_cases.md#UC-3 |
| policy management | Versioned weights, guard thresholds | bounded_contexts.md#BC-8, use_cases.md#UC-8 |
| event sourcing | Reducer, replay, EventLog immutability | bounded_contexts.md#BC-2, glossary.md (EventLog, Reducer) |
| rollback trigger | Degradation detection, parent spec revert | bounded_contexts.md#BC-6, use_cases.md#UC-6 |
| canary deployment | Phase 3 statistical test, human approval | use_cases.md#UC-5, glossary.md (Canary, PromotionStatisticalTest) |
| cost model freezing | Per-execution immutability, determinism | bounded_contexts.md#BC-2, use_cases.md#UC-2, glossary.md (CostModelVersion) |
| event deduplication | 24-hour dedup window, schema upcasting | bounded_contexts.md#BC-7, use_cases.md#UC-2 |
| candidate promotion | Phase 1-3, confidence quantification | bounded_contexts.md#BC-5, use_cases.md#UC-5 |
| spec distance validation | Trust region enforcement, SpecSpace metric | bounded_contexts.md#BC-5, use_cases.md#UC-4, glossary.md (SpecDeltaValidated) |
| convergence bootstrap | 1000-step entropy test before Spec_0 | bounded_contexts.md#BC-1, use_cases.md#UC-1, glossary.md (ConvergenceValidated) |
| context slot overflow | TRUNCATE_ONLY vs REJECT strategy | bounded_contexts.md#BC-3, use_cases.md#UC-7, glossary.md (ContextSlotBoundary) |
| observability SLA | Event dedup, schema versioning | bounded_contexts.md#BC-7, glossary.md (Telemetry, EventDeduped) |
| environment reproducibility | Execution environment snapshot, replay guard | bounded_contexts.md#BC-2, use_cases.md#UC-2, glossary.md (ExecutionEnvironmentSnapshot) |
| event log consistency | Per-partition total order, causal cross-partition | bounded_contexts.md#BC-2, glossary.md (PartitionConsistencyModel) |
| scheduler liveness | Starvation-free scheduling, bounded load guarantee | bounded_contexts.md#BC-2, glossary.md (SchedulerLiveness) |
| adaptive trust region | Δ_t = f(stability, variance, success_rate) | bounded_contexts.md#BC-5, use_cases.md#UC-4, glossary.md (AdaptiveTrustRegion) |
| multi-test statistical validation | ≥2 independent tests required for Phase 3 | bounded_contexts.md#BC-4, use_cases.md#UC-5, glossary.md (MultiTestAgreement) |
| global exactly-once | Global event_id registry beyond 24h window | bounded_contexts.md#BC-7, use_cases.md#UC-2, glossary.md (GlobalEventRegistry) |
| human gate event-sourcing | Approvals as first-class domain events | bounded_contexts.md#BC-6, use_cases.md#UC-5, glossary.md (HumanGateDenied) |
| context algorithm versioning | tokenizer + algorithm version in ContextWindowBuilt | bounded_contexts.md#BC-3, use_cases.md#UC-3, glossary.md (ContextAlgorithmVersion) |
| policy rollback safety | PolicyRolledBack event, guard-gated | bounded_contexts.md#BC-8, bounded_contexts.md#BC-6, use_cases.md#UC-9 |
| formal execution model | State_{t+1} = Reduce(State_t, Event_t), pure Reducer | bounded_contexts.md#BC-2, glossary.md (FormalExecutionModel) |

---

## By Component

| Component | Definition | Key Events | Key Invariants |
|-----------|------------|-----------|-----------------|
| Spec | Immutable DAG of typed nodes with execution contract | SpecCreated, SpecDeltaValidated, ConvergenceValidated | I-P-1, I-P-5, I-NEW-9 |
| Execution | Instance of Spec over input; event-sourced state machine | ExecutionCreated, ExecutionSpecBinding, ExecutionFinished | I-NEW-5, I-NEW-2, I-P-3, I-P-4, I-NEW-12, I-NEW-16 |
| EventLog | Append-only source of truth; no mutations | All domain events, EventDeduped | I-P-10, I-NEW-16, I-NEW-17 |
| Scheduler | Deterministic prioritizer; tie-breaker (priority DESC, partition_key, event_id) | SchedulerWeightsChanged, CostModelRetrained, ExecutionCreated | I-NEW-12, I-P-2 |
| ContextEngine | Deterministic fragment selection; slot boundary enforcement | ContextWindowBuilt, FragmentSelected, ContextSlotTruncated/Overflowed | I-NEW-1, I-NEW-7, I-NEW-8 |
| RiskModel | Cost-sensitive classifier; seed=42, SMOTE+XGBoost frozen | RiskModelTrained | I-NEW-14, I-NEW-3 |
| Simulator | Phase 1 replay engine; seed=hash(sample_id, spec_ids) | SimulationCompleted | I-NEW-15 |
| Candidate | Proposed Spec; phases 1-3 evaluation | CandidateProposed, PromotionStatisticalTest, AttributionPhase3Complete, DeltaAccepted | I-NEW-6, I-P-8 |
| ProposerStrategy | Immutable mutation generator; PROTECTED ACL | ProposerStrategyTrained, ProposerSelfMutationBlocked | I-NEW-4, I-NEW-10 |
| Policy | Versioned weights and guard thresholds; rollback-safe | PolicyUpdateProposed, PolicyActivated, PolicyRolledBack | I-NEW-3, I-NEW-12, I-NEW-13, I-NEW-29 |
| GuardPolicy | CB thresholds + HG escalation, versioned; gates policy rollback | CircuitBreakerStateChange, HumanGatePending, HumanGateApproved, HumanGateDenied | I-NEW-13, I-NEW-27, I-NEW-29, I-P-9 |
| Archive | Immutable Spec collection with KD-tree/FAISS index | SpecCreated, ArchiveIndexUpdated | I-P-6, I-P-7 |
| Reducer | Pure deterministic state materializer (State_{t+1} = Reduce(State_t, Event_t)) | All event subscriptions | I-P-3, I-P-4, I-P-2, I-NEW-30 |
| MetricSpec | Deterministic metric; versioned SQL, no APIs | MetricComputed | I-NEW-19, I-P-11 |
| GlobalEventRegistry | Permanent event_id hash-index; exactly-once across replay and DR | EventDeduped | I-NEW-26 |
| TrustRegionState | Adaptive Δ_t derived from stability, variance, success_rate | TrustRegionUpdated | I-NEW-24 |
| HumanGateAggregate | Event-sourced approval state (Pending → Approved/Denied) | HumanGatePending, HumanGateApproved, HumanGateDenied | I-NEW-27 |
| ExecutionEnvironmentSnapshot | Captures runtime environment for reproducible replay | ExecutionEnvironmentSnapshot | I-NEW-21 |

---

## By Invariant Type

| Type | Invariants |
|------|-----------|
| **Determinism** | I-NEW-1 (Context Assembly), I-NEW-7 (Fragment Tie-Breaking), I-NEW-12 (Scheduler), I-NEW-14 (RiskModel), I-NEW-15 (Simulator), I-NEW-19 (Metric), I-NEW-20 (Summarization), I-NEW-28 (Context Algorithm Versioned), I-NEW-30 (Reducer Pure) |
| **Event Sourcing** | I-NEW-3 (Policy), I-NEW-4 (ProposerStrategy), I-NEW-16 (Exactly-Once 24h), I-NEW-17 (Schema Upcasting), I-NEW-26 (Global Exactly-Once), I-NEW-27 (Human Gate Event-Sourced), I-NEW-29 (Policy Rollback), I-P-10 (Append-Only), I-MOD-3 (Full Replayability) |
| **Causal Correctness** | I-NEW-5 (Execution-Spec Binding), I-NEW-22 (Event Log Consistency Model), I-P-4 (Causal Ordering), I-NEW-17 (Schema Upcasting) |
| **Evolution Safety** | I-NEW-6 (Attribution Confidence), I-NEW-9 (Trust Region Containment), I-NEW-10 (Not Self-Targeting), I-NEW-11 (Convergence Verified), I-NEW-24 (Adaptive Trust Region), I-NEW-25 (Multi-Test Agreement), I-MOD-6 (Safe Evolution) |
| **Guard/Safety** | I-NEW-13 (Guardian Policy Thresholds), I-NEW-18 (Agent Output Validation), I-NEW-27 (Human Gate Event-Sourced), I-NEW-29 (Policy Rollback Safety), I-P-9 (Guard Pre-Deployment), I-P-12 (Safety Filter Non-Passthrough) |
| **Execution Model** | I-P-2 (Partition-Aware), I-P-3 (Idempotency), I-NEW-2 (Cost Immutability), I-NEW-8 (Slot Boundaries), I-NEW-21 (Environment Snapshot), I-NEW-23 (Scheduler Liveness), I-NEW-30 (Reducer Pure), I-MOD-4 (Cost Stability) |
| **Spec Model** | I-P-1 (Immutability), I-P-5 (Lineage DAG), I-P-6 (Archive Immutability), I-P-7 (Novelty Distance Validity) |
| **Multi-Objective** | I-P-8 (Pareto Dominance), I-P-14 (Proposer Constraints) |
| **Isolation** | I-P-11 (Metric Isolation), I-P-12 (Safety Filter), I-P-13 (Rollback Semantics) |
| **Reproducibility** | I-NEW-21 (Environment Snapshot), I-NEW-22 (Partition Consistency), I-NEW-26 (Global Exactly-Once), I-NEW-28 (Context Algorithm Versioned) |
| **Liveness** | I-NEW-23 (Scheduler Liveness — no starvation under bounded load) |

---

## By Event

| Event | Emitted When | Consumed By |
|-------|-------------|------------|
| SpecCreated | New Spec version created | Archive (indexes), Evolution (context), Telemetry |
| SpecDeltaValidated | Trust region check completed | Evolution (gates DeltaAccepted), Telemetry |
| ConvergenceValidated | 1000-step entropy test passes | Bootstrap (gates init), Telemetry |
| ExecutionCreated | Execution starts; versions frozen | Scheduler (references versions), Reducer (init), Telemetry |
| ExecutionSpecBinding | Before execution starts | Reducer (validates ExecutionFinished), Causal correctness |
| ExecutionFinished | Execution ends | Evaluation (metrics), Evolution (decisions), Guard (errors), Telemetry |
| EventDeduped | Duplicate event_id detected | Telemetry, Audit logs |
| MetricComputed | Deterministic evaluation complete | Evaluation (RiskModel input), Evolution (decisions), Telemetry |
| ContextWindowBuilt | Deterministic assembly completes; includes tokenizer_version, algorithm_version (I-NEW-28) | Evaluation (RiskModel), Evolution (inference), Reducer (record), Telemetry |
| FragmentSelected | Fragment selected via tie-breaker | Reducer (records ordering), Telemetry |
| ContextSlotTruncated | Slot overflow; TRUNCATE applied | Telemetry, Reducer (records strategy) |
| ContextSlotOverflowed | Slot overflow; REJECT applied | Telemetry, Reducer (records strategy) |
| RiskModelTrained | Risk model updated | Evolution (uses model), Telemetry |
| SimulationCompleted | Phase 1 simulation done | Evolution (Phase 1→2 decision), Telemetry |
| PromotionStatisticalTest | One per test in Phase 3 (≥2 required); carries test_type | Evolution (gates DeltaAccepted only if all pass), Telemetry |
| AttributionPhase3Complete | Final attribution decision | Evolution (gates DeltaAccepted), Telemetry |
| CandidateProposed | Proposer generates candidate | Evolution (routes to evaluation), Telemetry |
| DeltaAccepted | Statistical test passed; promotion approved | Guard (CB/HG checks), Telemetry, Canary initiation |
| DeltaRejected | Candidate failed or guard opened | Evolution (archives, learns), Telemetry |
| ProposerSelfMutationBlocked | Proposer targets itself | Evolution (records), Guard (escalates), Telemetry |
| CircuitBreakerStateChange | Error rate threshold breached | DeltaAccepted block, Rollback trigger, Telemetry |
| HumanGatePending | High-risk deployment requires approval | Slack/GitHub API, Telemetry |
| HumanGateApproved | Approver grants authorization (domain event, I-NEW-27) | Canary deployment, HumanGateAggregate, Telemetry |
| HumanGateDenied | Approver explicitly rejects (domain event, I-NEW-27) | Evolution (DeltaRejected), HumanGateAggregate, Telemetry |
| HumanGateTimeoutApproaching | 20h before HG deadline | Escalation channel, Telemetry |
| PolicyUpdateProposed | Policy change submitted | Review process, Telemetry |
| PolicyActivated | Policy version incremented | Scheduler, ContextEngine, Guard, Telemetry |
| ProposerStrategyTrained | Proposer version updated | Evolution (proposes with new strategy), Telemetry |
| CostModelRetrained | Cost model updated | Scheduler (new version if error > 0.2), Telemetry |
| CostModelError | Cost estimation mismatch | Scheduler (triggers retraining), Telemetry |
| RelevanceWeightsUpdated | Context relevance policy changed | ContextEngine (re-scores fragments), Telemetry |
| ArchiveIndexUpdated | Archive search index refreshed | Evolution (nearest-neighbor), Novelty computation, Telemetry |
| AgentDecisionValidated | Agent output schema valid | Evolution (processes decision), Telemetry |
| SchemaVersionMigrated | Old event upcasted | Reducer (upcast before processing), Telemetry |
| ExecutionEnvironmentSnapshot | Execution start; captures runtime environment (I-NEW-21) | Telemetry, Replay validator (rejects mismatched env) |
| TrustRegionUpdated | After each evolution cycle; Δ_t_prev → Δ_t_new (I-NEW-24) | Evolution (next proposal), Telemetry |
| PolicyRolledBack | Policy reverted; guard-gated (I-NEW-29) | ExecutionRuntime (next executions), Scheduler, Telemetry |
