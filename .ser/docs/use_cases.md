# Core Use Cases — SER v2.3

## [UC-1] Bootstrap System
**Input:** Spec_0 DSL + convergence test parameters (1000 steps, entropy threshold)
**Steps:**
1. Validate Spec_0 syntax via Parser.
2. Run 1000-step entropy test on Spec_0 (E[ΔH_t] → 0).
3. Emit ConvergenceValidated(entropy_trajectory, passed).
4. Compile Spec_0 to SQL IR.
5. Create Spec_0 aggregate in Archive, emit SpecCreated.
6. Emit PolicyActivated(version=0, weights, guard_config).
7. System ready for execution.
**Output Events:** ConvergenceValidated, SpecCreated, PolicyActivated, ArchiveIndexUpdated

---

## [UC-2] Execute Spec
**Input:** Spec_version_id, input_data, execution_id
**Steps:**
1. Load Spec from Archive; freeze cost_model_version at ExecutionCreated.
2. Emit ExecutionCreated(execution_id, spec_version_id, cost_model_version, guard_policy_version).
3. Emit ExecutionEnvironmentSnapshot(execution_id, python_version, lib_versions, sql_engine_version, hardware_class) — required for reproducibility (I-NEW-21).
4. Emit ExecutionSpecBinding(execution_id, spec_version_id) before execution starts.
5. Scheduler.readyEvents(partition_key, state_version, policy_id) returns sorted ExecSet via tie-breaker (priority DESC, partition_key, event_id); starvation-free under bounded load (I-NEW-23).
6. Reducer applies events from EventLog; dedup via GlobalEventRegistry then 24h window (emit EventDeduped on dup) (I-NEW-26).
7. Materialize state with partition-aware Reducer (pure function, I-NEW-30); apply schema upcasting if needed.
8. Emit ExecutionFinished(execution_id, final_state).
**Output Events:** ExecutionCreated, ExecutionEnvironmentSnapshot, ExecutionSpecBinding, EventDeduped*, ExecutionFinished

---

## [UC-3] Evaluate Execution
**Input:** execution_id, MetricSpec_version_ids[]
**Steps:**
1. Fetch Execution state from EventLog.
2. For each MetricSpec_id: compute deterministic metric (no RNG, no APIs), emit MetricComputed(metric_id, execution_id, version, value, snapshot_id).
3. Build ContextWindow: read ContextSpec (strategy ∈ {TRUNCATE_ONLY, TEXRANK_SEED_0}, tokenizer_version, algorithm_version), select fragments via tie-breaker (relevance DESC, source_id, fragment_id), apply ContextSlotBoundary rules.
4. Emit ContextWindowBuilt(execution_id, fragments[], strategy, hash, tokenizer_version, algorithm_version) (I-NEW-28).
5. Load frozen RiskModel(seed=42); compute risk_score from execution features.
6. Emit RiskModelTrained if model outdated.
**Output Events:** MetricComputed*, ContextWindowBuilt, RiskModelTrained (if triggered), ContextSlotTruncated/Overflowed (if overflow)

---

## [UC-4] Propose Spec Delta
**Input:** Candidate_phase ∈ {exploration, exploitation}, Parent_spec_id
**Steps:**
1. Load ProposerStrategy(seed=42, immutable).
2. Update adaptive trust region: Δ_t = f(stability_score, reward_variance, success_rate); emit TrustRegionUpdated(cycle_id, Δ_t_prev, Δ_t_new, ...) (I-NEW-24).
3. Generate SpecDelta via proposer (respecting new Δ_t and novelty constraints).
4. Validate self-targeting: if target_spec_id == ProposerStrategy spec_id → emit ProposerSelfMutationBlocked, reject.
5. Validate trust region: d(Parent_spec, New_spec) ≤ Δ_t, emit SpecDeltaValidated(delta_id, distance_computed, Δ_t, passed).
6. Reject if passed=false.
7. Emit CandidateProposed(spec_delta, phase).
8. Queue candidate for evaluation.
**Output Events:** TrustRegionUpdated, ProposerSelfMutationBlocked (if violated), SpecDeltaValidated, CandidateProposed

---

## [UC-5] Promote Candidate to Production
**Input:** Candidate_id, attribution_results
**Steps:**
1. Load Candidate with prior Phase 1/2 results (confidence, effect_size).
2. Run ≥2 independent statistical tests at alpha=0.05 (e.g. t-test + bootstrap, or t-test + Mann-Whitney):
   - For each test: emit PromotionStatisticalTest(candidate_id, test_type, p_value, effect_size, sample_n).
3. All tests must pass; if any fail → emit DeltaRejected (I-NEW-25). Single-test promotion is forbidden.
4. Validate confidence ≥ 0.7; emit AttributionPhase3Complete(confidence, recommendation, tests_passed[]).
5. If recommendation=reject → emit DeltaRejected.
6. Check CircuitBreaker: if state=OPEN → emit DeltaRejected.
7. If high_risk=true: emit HumanGatePending (event-sourced, I-NEW-27); await HumanGateApproved or HumanGateDenied event.
8. If HumanGateDenied → emit DeltaRejected.
9. Emit DeltaAccepted(candidate_id); create Canary deployment.
10. Monitor for degradation; on rollback trigger emit Rollback event.
**Output Events:** PromotionStatisticalTest (one per test), AttributionPhase3Complete, DeltaAccepted or DeltaRejected, HumanGatePending/Approved/Denied (if triggered)

---

## [UC-6] Rollback on Degradation
**Input:** Execution_id, degradation_metric, threshold_breach
**Steps:**
1. Detect degradation: error_rate > 0.1 OR reward_delta < threshold.
2. Open CircuitBreaker: emit CircuitBreakerStateChange(OPEN, trigger_reason, error_count).
3. Mark current Spec as degraded.
4. Load parent_spec_id from Archive lineage.
5. Propose revert: emit Rollback(spec_to_revert_from, spec_to_revert_to).
6. Execute parent Spec; cancel ongoing canary.
7. If human approval needed: emit HumanGatePending with escalation link.
**Output Events:** CircuitBreakerStateChange, Rollback, HumanGatePending (if triggered)

---

## [UC-7] Assemble Context for Agent
**Input:** execution_id, ContextSpec
**Steps:**
1. Load ContextSpec: slots[], max_tokens_per_slot, strategy ∈ {TRUNCATE_ONLY, TEXRANK_SEED_0}.
2. Fetch execution state fragments from ExecutionRuntime.
3. For each slot: select fragments via tie-breaker (relevance_score DESC, source_id, fragment_id).
4. Emit FragmentSelected(slot, fragment_id, selected_index) for each selection.
5. Check ContextSlotBoundary: if total_tokens > max_tokens apply strategy.
6. TRUNCATE: emit ContextSlotTruncated. REJECT: emit ContextSlotOverflowed.
7. Apply SafetyFilter.check (secrets/PII rejection).
8. Emit ContextWindowBuilt(task_id, context_hash, fragments[], strategy).
**Output Events:** FragmentSelected*, ContextSlotTruncated/Overflowed (if triggered), ContextWindowBuilt

---

## [UC-8] Update Policy
**Input:** policy_update{scheduler_weights?, guard_config?, fragment_strategy?}
**Steps:**
1. Validate policy_update schema (weights sum ≤ 1.0, all ≥ 0, timeouts > 0).
2. Emit PolicyUpdateProposed(update_id, proposed_config, author, timestamp).
3. Await review/approval.
4. On approval: increment version (version = prev_version + 1).
5. Emit PolicyActivated(version, scheduler_weights, guard_config, applied_time).
6. All new Executions use updated policy_version.
7. Ongoing Executions use frozen policy_version from ExecutionCreated.

## [UC-9] Rollback Policy
**Input:** from_version, to_version, reason
**Steps:**
1. Check CircuitBreaker state: if OPEN or policy is marked high-risk, emit HumanGatePending; await HumanGateApproved (I-NEW-29).
2. Validate to_version < from_version and exists in policy event history.
3. Emit PolicyRolledBack(from_version, to_version, reason, guard_state).
4. All new Executions use to_version policy.
5. Ongoing Executions retain their frozen policy_version from ExecutionCreated.
**Output Events:** HumanGatePending* (if high-risk), HumanGateApproved*, PolicyRolledBack
