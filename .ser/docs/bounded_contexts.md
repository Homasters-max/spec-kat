# Bounded Contexts — SER v2.3

## [BC-1] SpecManagement
**Responsibility:** Define, version, and validate Specs; enforce immutability and lineage.
**Entities:** Spec(id, definition_sql, parent_spec_id, version), SpecDelta(source, target, distance), SpecArchive
**Aggregates:** Spec (root), SpecArchive (root)
**UseCases:** Bootstrap System, Propose Spec Delta, Validate Convergence, Archive Indexed Search
**Interfaces:** Exposes: Spec DSL, SpecCreated/SpecDeltaValidated events. Consumes: Evolution deltas, Archive search queries.
**Dependencies:** → Evolution (for SpecDelta validation), Telemetry (observes)

## [BC-2] ExecutionRuntime
**Responsibility:** Event-sourced execution of Specs; partition-aware state materialization via Reducer; environment snapshotting for reproducibility.
**Entities:** Execution(id, spec_version_id, policy_version_id, cost_model_version, guard_policy_version), EventLog, EventDedup, ExecutionEnvironmentSnapshot
**Aggregates:** Execution (root), EventLog (root, append-only)
**UseCases:** Execute Spec, Bind Execution to Spec, Materialize State, Dedup Events, Snapshot Environment
**Interfaces:** Exposes: EventLog entries, ExecutionCreated/ExecutionSpecBinding/ExecutionFinished/ExecutionEnvironmentSnapshot events. Consumes: Spec IDs, cost_model_version.
**Dependencies:** → SpecManagement (reads Spec), Guard (policy_version), ContextAssembly (context binding)
**Consistency Model:** Per-partition total order (I-NEW-22); cross-partition causal consistency; no global total order assumed.
**Liveness:** Scheduler guarantees eventual execution of every ready event under bounded load; starvation forbidden (I-NEW-23).
**Formal Execution Model:** State_{t+1} = Reduce(State_t, Event_t); Reducer is a pure, total, side-effect-free function (I-NEW-30).

## [BC-3] ContextAssembly
**Responsibility:** Deterministic assembly of ContextWindow from execution state; slot management; fragment selection; algorithm and tokenizer versioning.
**Entities:** ContextSpec(fragment_strategy, slot_definitions[], tokenizer_version, algorithm_version), ContextWindow(id, fragments[], strategy, tokenizer_version, algorithm_version), Fragment
**Aggregates:** ContextWindow (root, event-sourced)
**UseCases:** Assemble Context for Agent, Handle Slot Overflow, Select Fragments
**Interfaces:** Exposes: ContextWindowBuilt (includes tokenizer_version, algorithm_version), FragmentSelected, ContextSlotTruncated/Overflowed events. Consumes: execution state, policy weights.
**Dependencies:** → ExecutionRuntime (reads state), Policy (reads fragment_strategy, relevance_weights)
**Drift Prevention (I-NEW-28):** ContextWindowBuilt records tokenizer_version and algorithm_version; replay engine rejects any replay that attempts to use a different tokenizer or algorithm than what was recorded.

## [BC-4] Evaluation
**Responsibility:** Deterministic metric computation; risk modeling; multi-phase simulation and attribution.
**Entities:** MetricSpec(id, definition_sql, version), RiskModel(checksum, seed=42), Simulator(seed)
**Aggregates:** MetricSpec (value object), RiskModel (event-sourced), Simulator (event-sourced, deterministic)
**UseCases:** Evaluate Execution, Compute Metrics, Train Risk Model, Simulate Spec Delta
**Interfaces:** Exposes: MetricComputed, RiskModelTrained, SimulationCompleted, RelevanceWeightsUpdated events. Consumes: execution trace, Specs to compare.
**Dependencies:** → ExecutionRuntime (reads trace), SpecManagement (reads candidates)

## [BC-5] Evolution
**Responsibility:** Spec mutation, proposer-driven candidate generation, adaptive trust region, promotion via ≥2-test statistical validation.
**Entities:** Candidate(spec_delta, phase), ProposerStrategy(seed=42, model_id, PROTECTED), Policy(version, scheduler_weights, guard_config), SpecArchive, TrustRegionState(Δ_t, stability_score, reward_variance, success_rate)
**Aggregates:** Candidate (event-sourced, root), ProposerStrategy (event-sourced, root), Policy (event-sourced, root)
**UseCases:** Propose Spec Delta, Evaluate Candidate, Promote Candidate to Production, Update Policy, Block Self-Targeting, Update Trust Region
**Interfaces:** Exposes: CandidateProposed, PromotionStatisticalTest (per test, includes test_type), AttributionPhase3Complete (includes tests_passed[]), DeltaAccepted/Rejected, ProposerSelfMutationBlocked, PolicyActivated, TrustRegionUpdated events. Consumes: metrics, risk scores, convergence status.
**Dependencies:** → SpecManagement (validates deltas), Evaluation (requests metrics/simulations), Guard (policy_version)
**Adaptive Trust Region (I-NEW-24):** After each cycle, Δ_t = f(stability_score, reward_variance, success_rate); emits TrustRegionUpdated; static Δ_t is forbidden.
**Statistical Validation (I-NEW-25):** Phase 3 requires ≥2 independent tests (e.g. t-test + bootstrap or Mann-Whitney) at alpha=0.05, all passing; single-test promotion is a protocol violation.

## [BC-6] GuardSystem
**Responsibility:** Circuit breaker state management; human gate escalation (event-sourced); deployment gating pre-production; policy rollback gating.
**Entities:** GuardPolicy(cb_error_rate_threshold: 0.1, error_observation_window: 5m, rollback_window: 1h, consecutive_failures: 3)
**Aggregates:** GuardPolicy (event-sourced, root), HumanGateAggregate (event-sourced, root — state derived from HumanGatePending/Approved/Denied events)
**UseCases:** Detect Degradation, Open Circuit Breaker, Request Human Gate, Escalate Timeout, Approve/Deny, Gate Policy Rollback
**Interfaces:** Exposes: CircuitBreakerStateChange, HumanGatePending, HumanGateTimeoutApproaching, HumanGateApproved, HumanGateDenied events. Consumes: error_rate, execution outcomes, PolicyRolledBack requests.
**Dependencies:** → SpecManagement (when rollback triggers), ExecutionRuntime (observes errors), Policy (gates PolicyRolledBack)
**Human Gate Event-Sourcing (I-NEW-27):** Approval state is fully derived by replaying HumanGatePending → HumanGateApproved/HumanGateDenied events; no external side-channel state.
**Policy Rollback Safety (I-NEW-29):** PolicyRolledBack is gated by CircuitBreaker; if high-risk, also by HumanGate; ensures bad policy cannot propagate system-wide without guard review.

## [BC-7] Telemetry
**Responsibility:** Independent observability layer with separate SLA; global event_id registry for exactly-once; schema versioning; upcasting.
**Entities:** TelemetryConfig(sla_budget, schema_versions[]), GlobalEventRegistry(event_id → content_hash, permanent)
**Aggregates:** GlobalEventRegistry (root, permanent hash index — supersedes 24h dedup window for cross-replay/DR exactly-once), SchemaRegistry (root)
**UseCases:** Emit Structured Events, Deduplicate Events (globally), Upcast Old Events, Monitor SLA
**Interfaces:** Exposes: EventDeduped, SchemaVersionMigrated events. Consumes: all domain events.
**Dependencies:** → all layers (all emit events)
**Global Exactly-Once (I-NEW-26):** GlobalEventRegistry stores event_id → content_hash permanently; any replay or DR scenario that tries to reprocess a known event_id is rejected; the 24h dedup window is a fast-path subset of this guarantee.

## [BC-8] Policy
**Responsibility:** Centralized policy configuration; versioning; scheduler weights and guard thresholds via event sourcing; safe rollback.
**Entities:** Policy(version, scheduler_weights, guard_config), PolicyUpdate, PolicyRollback(from_version, to_version, reason)
**Aggregates:** Policy (root, event-sourced)
**UseCases:** Update Policy, Activate Policy, Validate Policy Version, Rollback Policy
**Interfaces:** Exposes: PolicyUpdateProposed, PolicyActivated, PolicyRolledBack events. Consumes: tuning requests, rollback requests from GuardSystem.
**Dependencies:** → ExecutionRuntime (distributes policy_version), ContextAssembly (weights), GuardSystem (thresholds, gates rollback)
**Rollback Safety (I-NEW-29):** Every PolicyActivated version can be reversed by emitting PolicyRolledBack(from_version, to_version, reason); rollback itself is gated by CircuitBreaker (and HumanGate if high-risk); prevents system-wide propagation of bad policy.
