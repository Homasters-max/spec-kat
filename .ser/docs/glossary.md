# Glossary — SER v2.3

| Term | Type | Definition (≤15 words) |
|------|------|----------------------|
| AgentDecisionValidated | Event | Agent output schema validation completion against AgentOutput JSON Schema |
| AgentOutput | Schema | Validated JSON: decision, reasoning, proposed_delta?, confidence (0-1) |
| Archive | Aggregate | Immutable collection of all Specs with KD-tree search index |
| ArchiveIndex | Data Structure | KD-tree or FAISS index for nearest-neighbor search in SpecSpace |
| ArchiveIndexUpdated | Event | Archive search index updated when new Spec created |
| Attribution | Process | Pre/shadow/post-canary causal inference quantifying delta effect |
| AttributionPhase3Complete | Event | Final attribution decision with confidence score and effect_size |
| Bootstrap | Process | Initial Spec_0 creation with seed configuration and convergence test |
| Candidate | Aggregate | Proposed Spec under multi-phase evaluation, not yet production |
| CandidateProposed | Event | Spec mutation proposed for evaluation phases 1-3 |
| Canary | Deployment | Limited production test before full rollout, monitored for degradation |
| CircuitBreaker | Pattern | CLOSED/OPEN/HALF_OPEN automatic deployment gate on error rate |
| CircuitBreakerStateChange | Event | CB state transition with trigger reason and error count |
| Consensus | Protocol | Distributed agreement via Raft/HLC for Spec changes |
| ContextAssembly | BC | Deterministic context assembly from execution state via slots |
| ContextEngine | Component | Deterministic context builder, event-sourced, DuckDB-materialized |
| ContextPolicy | Aggregate | Token budgets, quotas, safety rules for context assembly |
| ContextSlotBoundary | Configuration | Max token limit and overflow strategy per slot |
| ContextSlotOverflowed | Event | Context slot boundary violation handled via rejection of fragment |
| ContextSlotTruncated | Event | Context slot boundary violation handled via truncation |
| ContextSpec | Configuration | Slots, sources, ordering rules for context assembly |
| ContextWindow | Aggregate | Assembled context slots for LLM agent reasoning, fully deterministic |
| ContextWindowBuilt | Event | Emitted after deterministic context assembly completion |
| ConvergenceValidated | Event | 1000-step entropy test passed; entropy_trajectory captured before bootstrap |
| Convergence Controller | Component | Entropy monitor, variance bound, annealing policy (Φ) |
| CostModel | Function | Estimation of execution cost: CPU, IO, memory, latency |
| CostModelDegraded | Event | Mean cost estimation error > 0.2; retraining triggered |
| CostModelError | Event | Actual vs estimated cost tracking for degradation detection |
| CostModelRetrained | Event | Cost model updated; Online regression, deterministic seed |
| CostModelVersion | Configuration | Immutable cost model reference per execution lifecycle |
| Darwin Controller | Component | Population-based evolution with multi-objective selection |
| DataLake | System | DuckDB-based data warehouse for all SER layers |
| DeltaAccepted | Event | Candidate promotion approved; canary deployment initiated |
| DeltaRejected | Event | Candidate rejected; statistical test failed or guard opened |
| Determinism | Property | Same input state yields same decision/output always |
| DevTask | Entity | Application-level work unit with defined success criteria |
| Domain Model | Architecture | Rich entities, aggregates, value objects with invariants |
| Domain Service | Pattern | Cross-aggregate stateless logic |
| Emergency Stop | Pattern | Immediate rollback trigger; pauses all evolution |
| Evaluation | BC | Deterministic metrics, risk modeling, multi-phase simulation |
| Event | Immutable Fact | Immutable change in EventLog with causal parents |
| EventDeduped | Event | Duplicate event rejected; 24-hour dedup window applied |
| EventLog | Aggregate | Append-only source of truth; immutable events only |
| Event Sourcing | Architecture | All state derived deterministically from immutable event log |
| Evolution | BC | Spec mutation, candidate evaluation, promotion, policy updates |
| Evolution Memory | Data Structure | Versioned history of Specs, traces, scores, lineage |
| Execution | Aggregate | Instance of Spec over input; event-sourced state machine |
| ExecutionCreated | Event | Execution started; cost_model_version and policy_version frozen |
| ExecutionFinished | Event | Execution completed; final state materialized |
| ExecutionRuntime | BC | Event-sourced execution; partition-aware state materialization |
| ExecutionSpecBinding | Event | Causal link between execution and spec_version_id |
| ExecSet | Selection | Events selected for parallel execution within one tick |
| Exploration | Strategy | Diversity-seeking high-Δ mutations near frontier |
| Exploitation | Strategy | Performance-seeking low-Δ mutations exploiting current frontier |
| Fragment | Data Unit | Minimal context element, scored and ranked per slot |
| FragmentSelected | Event | Fragment selection captured; slot, fragment_id, index |
| Frontier | Data Structure | Set of non-dominated Spec candidates (Pareto front) |
| GuardPolicy | Aggregate | CB thresholds and HG escalation rules, versioned and immutable |
| Guard System | BC | Circuit breaker, human gate, pre-deployment gating |
| HumanGate | Pattern | Manual approval required for high-risk Spec deployments |
| HumanGateApproved | Event | Human approval completed with approver identity |
| HumanGatePending | Event | HG approval required; deadline and GitHub PR/Slack link |
| HumanGateTimeoutApproaching | Event | Escalation trigger 20 hours before HG deadline |
| Idempotency | Property | Applying same event twice yields identical state once |
| L0 Layer | Architecture | Specification and DSL layer |
| L1 Layer | Architecture | Execution runtime and event emission |
| L2 Layer | Architecture | Metrics, evaluation policies, scoring |
| L3 Layer | Architecture | Spec mutation, proposer, archive management |
| LoopGuard | Component | Detects repeated failures; escalates blocked agents |
| LLM Runtime Adapter | Component | Thin I/O layer calling LLM, no domain logic |
| Lyapunov Function | Formal | Stability metric minimized to guarantee convergence (V) |
| Materialized View | SQL | Cached query result for fast repeated access |
| MetricSpec | Value Object | Deterministic metric definition with versioned SQL |
| Metric Registry | Data Store | Centralized catalog of all metrics in system |
| MetricComputed | Event | Metric computed deterministically; no RNG or external APIs |
| MigrationClass | Classification | REVERSIBLE, LOSSY, or BREAKING data schema change |
| Micro-Reducer | Function | Event-specific state transition function |
| Multi-Objective Optimization | Pattern | Pareto-based selection balancing reward, cost, risk, novelty |
| Novelty | Metric | Distance of Spec from Archive neighbors; exploration bonus |
| Pareto Front | Concept | Set of solutions non-dominated on multi-objectives |
| Partition | Execution | Disjoint state owned by one Reducer instance |
| Planner | Component | Cost-based SQL IR optimizer; rule-based and CBO |
| Policy | Aggregate | Weights and rules for Scheduler and Proposer behavior |
| PolicyActivated | Event | Policy state change; version incremented by one |
| PolicyUpdateProposed | Event | Policy change proposed before activation |
| Population Layer | Data Structure | Bounded set of candidate Specs with diversity constraint |
| Proposer | Agent | Strategy-driven Spec mutation generator; immutable strategy |
| ProposerStrategy | Aggregate | Immutable proposer with seed=42, model_id, PROTECTED ACL |
| ProposerStrategyTrained | Event | Immutable proposer version with training metadata and seed |
| ProposerSelfMutationBlocked | Event | Prevention of proposer self-targeting mutations |
| PromotionStatisticalTest | Event | Phase 3 significance test; p_value, effect_size, sample_n |
| ReadyEvents | Queue | Events satisfying causality and scheduling preconditions |
| ReadyFragments | Data Structure | Sorted fragment list deterministic via tie-breaker |
| Reducer | Function | Deterministic state materializer from EventLog |
| RelevanceWeightsUpdated | Event | Policy-versioned context relevance scoring parameters |
| Replay | Operation | Reconstruct historical state by reapplying events |
| Replayability | Property | Ability to reconstruct any past state deterministically |
| Risk | Metric | Model of failure probability; class-balanced trained |
| RiskModel | Aggregate | Cost-sensitive classifier of Spec failure; seed=42, frozen |
| RiskModelTrained | Event | Risk model updated with fixed seeds and version tracking |
| Rollback | Operation | Revert to previous Spec on degradation |
| Reward | Metric | Execution success measure, main optimization goal |
| SafetyFilter | Component | Prevents secrets/sensitive data leakage to agent |
| Scheduler | Component | Deterministic event prioritizer respecting resources and causality |
| SchedulerWeights | Configuration | Policy-level weights for multi-objective scheduling |
| SchedulerWeightsChanged | Event | Scheduler weights updated only via PolicyActivated |
| Schema Registry | Data Store | Central catalog of event schemas, versions, upcast rules |
| SDSS | Pattern | Spec-Driven State Machine; deterministic executor |
| Shadow Deployment | Pattern | Production test with no user traffic impact |
| SimulationCompleted | Event | Phase 1 simulator output; seed, sample_hash, delta, confidence |
| Simulator | Aggregate | Deterministic Phase 1 replay engine with seed support |
| Slot (Context) | Concept | Named context section (GOAL, CONSTRAINTS, STATE, etc.) |
| Snapshot | Optimization | Frozen state checkpoint to avoid full replays |
| Spec | Aggregate | Immutable DAG of typed nodes with execution contract |
| SpecArchive | Aggregate | Immutable versioned collection of all Specs |
| SpecComplexity | Metric | Structural complexity score of a Spec |
| SpecCreated | Event | New Spec version created; parent lineage recorded |
| SpecDelta | Value Object | Incremental change to Spec; versioned and immutable |
| SpecDeltaValidated | Event | Trust region containment verified with distance metric |
| SpecLibrary | Data Structure | Reusable Spec patterns and validated subgraphs |
| SpecManagement | BC | Spec definition, versioning, validation, immutability |
| SpecSpace | Geometry | Formal metric space of valid Specs with distance/topology (Ω) |
| SQL IR | Language | Canonical intermediate representation; deterministic, side-effect-free |
| Step Annealing | Control | Decay of Δ_t over iterations toward convergence |
| TEL | System | Trusted Execution Layer; sandboxed with signed logs |
| Telemetry | BC | Independent observability layer with separate SLA |
| Trust Region | Constraint | Neighborhood N(S_t, Δ_t) limiting spec changes per step |
| Use Case | Pattern | Application layer orchestration of domain logic |
| Value Object | Pattern | Immutable object with semantic meaning |
| Verification Pipeline | Process | Syntax, static analysis, tests before code application |
| AdaptiveTrustRegion | Control | Δ_t updated each cycle via f(stability, variance, success_rate); static trust region forbidden |
| ExecutionEnvironmentSnapshot | Event | Captures python_version, lib_versions, sql_engine_version, hardware_class at execution start; required for replay |
| GlobalEventRegistry | Aggregate | Permanent hash-index of all event_ids; prevents reprocessing across replay, DR, and beyond 24h window |
| HumanGateDenied | Event | Approver explicitly rejects high-risk deployment; triggers DeltaRejected |
| PolicyRolledBack | Event | Policy reverted to prior version; gated by CircuitBreaker and (if high-risk) HumanGate |
| TrustRegionUpdated | Event | Records Δ_t_prev, Δ_t_new, stability_score, reward_variance, success_rate after each evolution cycle |
| FormalExecutionModel | Principle | State_{t+1} = Reduce(State_t, Event_t); Reducer must be a pure, total, deterministic function (I-NEW-30) |
| MultiTestAgreement | Protocol | Phase 3 requires ≥2 independent tests (t-test + bootstrap or Mann-Whitney); all must pass at alpha=0.05 |
| ContextAlgorithmVersion | Configuration | tokenizer_version + algorithm_version recorded in ContextWindowBuilt; mismatched replay is rejected |
| PartitionConsistencyModel | Property | Per-partition: total order. Cross-partition: causal consistency. No global total order assumed (I-NEW-22) |
| SchedulerLiveness | Property | Every ready event is eventually scheduled under bounded load; infinite starvation is forbidden (I-NEW-23) |
