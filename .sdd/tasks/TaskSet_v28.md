# TaskSet_v28 — Phase 28: Write Kernel Guard & Event Invalidation

Spec: .sdd/specs/Spec_v28_WriteKernelGuard.md
Plan: .sdd/plans/Plan_v28.md

---

T-2801: EventInvalidatedEvent — domain event definition + registration

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-1, §3 Domain Events, §5 (I-EL-6, C-1)
Invariants:           I-EL-6, C-1
spec_refs:            [Spec_v28 §2 BC-WG-1, §3, I-EL-6, C-1]
produces_invariants:  [I-EL-6, C-1]
requires_invariants:  []
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Scope-extension:      reducer.py added — EventInvalidated in V1_L1_EVENT_TYPES requires I-ST-10 classification in EventReducer._KNOWN_NO_HANDLER; omission breaks import; one logical operation
Risk-note:            RISK: duplicated _KNOWN_NO_HANDLER (events.py vs reducer.py) — potential drift, manual sync required; refactor out-of-scope for v28
Acceptance:           unit test verifying "EventInvalidated" ∈ _KNOWN_NO_HANDLER AND ∈ V1_L1_EVENT_TYPES AND ∈ V2_L1_EVENT_TYPES; C-1 assertion passes (_KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES); import sdd.domain.state.reducer succeeds (I-ST-10)
Depends on:           —

---

T-2802: idx_event_type — add DB index to ensure_sdd_schema

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-2 (schema section)
Invariants:           I-DB-1
spec_refs:            [Spec_v28 §2 BC-WG-2]
produces_invariants:  [I-DB-1]
requires_invariants:  []
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/db.py
Acceptance:           unit test verifying idx_event_type exists in DuckDB schema after ensure_sdd_schema() call on tmp_db
Depends on:           —

---

T-2803: EventStore replay pre-filter — _invalidated_cache + _get_invalidated_seqs + replay()

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-2 (cache/filter section), §5 I-INVALID-2, I-INVALID-CACHE-1
Invariants:           I-INVALID-2, I-INVALID-CACHE-1
spec_refs:            [Spec_v28 §2 BC-WG-2, I-INVALID-2, I-INVALID-CACHE-1]
produces_invariants:  [I-INVALID-2, I-INVALID-CACHE-1]
requires_invariants:  [I-EL-6]
Inputs:               src/sdd/infra/event_store.py
Outputs:              src/sdd/infra/event_store.py
Acceptance:           test_replay_skips_invalidated_seq, test_replay_no_warning_for_invalidated, test_cache_invalidated_after_append (new file: tests/unit/infra/test_event_invalidation.py)
Depends on:           T-2801, T-2802

---

T-2804: EventStore.append kernel guard — AllowOutsideKernel type + guard + caller updates

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-3, §4 Types & Interfaces, §5 I-DB-WRITE-2, §6 Pre/Post Conditions BC-WG-3
Invariants:           I-DB-WRITE-2, I-KERNEL-WRITE-1, I-SPEC-EXEC-1
spec_refs:            [Spec_v28 §2 BC-WG-3, §4, I-DB-WRITE-2]
produces_invariants:  [I-DB-WRITE-2]
requires_invariants:  [I-INVALID-CACHE-1]
Inputs:               src/sdd/infra/event_store.py, src/sdd/core/execution_context.py, src/sdd/commands/reconcile_bootstrap.py, tests/harness/fixtures.py
Outputs:              src/sdd/infra/event_store.py, src/sdd/commands/reconcile_bootstrap.py, tests/harness/fixtures.py
Acceptance:           test_write_kernel_guard_raise_outside_context, test_write_kernel_guard_allow_inside_context, test_write_kernel_guard_bootstrap_bypass, test_write_kernel_guard_invalid_bypass_value (new file: tests/unit/infra/test_write_kernel_guard.py); reconcile_bootstrap.py passes all_outside_kernel="bootstrap"; fixtures.py passes allow_outside_kernel="test"
Depends on:           T-2803

---

T-2805: sdd_append production-path guard — I-DB-WRITE-3

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-4, §5 I-DB-WRITE-3, §6 Pre/Post Conditions BC-WG-4
Invariants:           I-DB-WRITE-3, I-KERNEL-WRITE-1
spec_refs:            [Spec_v28 §2 BC-WG-4, I-DB-WRITE-3]
produces_invariants:  [I-DB-WRITE-3]
requires_invariants:  []
Inputs:               src/sdd/infra/event_log.py, src/sdd/core/execution_context.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           test_sdd_append_prod_guard_raise_outside_kernel, test_sdd_append_nonprod_allowed_outside_kernel (appended to tests/unit/infra/test_write_kernel_guard.py)
Depends on:           —

---

T-2806: invalidate-event command — handler + REGISTRY + CLI

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-5, §4 Types & Interfaces (CLI), §5 I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1
Invariants:           I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1
spec_refs:            [Spec_v28 §2 BC-WG-5, §4, I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1]
produces_invariants:  [I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1]
requires_invariants:  [I-EL-6, I-DB-WRITE-2]
Inputs:               src/sdd/core/events.py, src/sdd/infra/event_store.py, src/sdd/commands/registry.py, src/sdd/commands/_base.py, src/sdd/cli.py
Outputs:              src/sdd/commands/invalidate_event.py (new), src/sdd/commands/registry.py, src/sdd/cli.py
Acceptance:           test_invalidate_nonexistent_seq_raises, test_invalidate_invalidated_raises, test_invalidate_state_event_raises, test_invalidate_idempotent (new file: tests/unit/commands/test_invalidate_event.py); `sdd invalidate-event --seq N --reason "..."` exits 0
Depends on:           T-2801, T-2804

---

T-2807: Incident backfill + integration test — BC-WG-6

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-6, §7 UC-28-1, §9 Test 14
Invariants:           I-INVALID-2, I-INVALID-IDEM-1
spec_refs:            [Spec_v28 §2 BC-WG-6, §9 Test 14, UC-28-1]
produces_invariants:  [I-INVALID-2, I-INVALID-IDEM-1]
requires_invariants:  [I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1]
Inputs:               src/sdd/commands/invalidate_event.py, src/sdd/infra/event_store.py
Outputs:              tests/integration/test_incident_backfill.py (new)
Acceptance:           test_incident_backfill_no_warnings passes (tmp_db end-to-end: 6 TestEvent → invalidate all → replay no WARNING); production backfill: `sdd show-state 2>&1 | grep -c "WARNING.*unknown event_type"` == 0
Depends on:           T-2806

---

T-2808: Fix InvalidateEventCommand.payload — include target_seq + reason for unique command_id

Status:               DONE
Spec ref:             Spec_v28 §2 BC-WG-5 (I-INVALID-IDEM-1, A-7)
Invariants:           I-INVALID-IDEM-1, I-CMD-IDEM-2
spec_refs:            [Spec_v28 §2 BC-WG-5, A-7, I-CMD-IDEM-2]
produces_invariants:  [I-INVALID-IDEM-1, I-CMD-IDEM-2]
requires_invariants:  [I-INVALID-1, I-INVALID-3, I-INVALID-4]
Inputs:               src/sdd/commands/invalidate_event.py
Outputs:              src/sdd/commands/invalidate_event.py, tests/unit/commands/test_invalidate_event.py
Acceptance:           (1) sha256(payload{target_seq=X}) ≠ sha256(payload{target_seq=Y}) for X≠Y; (2) sdd invalidate-event --seq 25973 --reason "..." exits 0 AND EventInvalidated written to EventLog; (3) existing unit tests pass; (4) sdd show-state | grep -c "WARNING.*unknown event_type" == 0
Depends on:           T-2807

---

<!-- Granularity: 8 tasks (TG-2: recommended 10–30; justified by BC count — 6 BCs map to 7 tasks + 1 hotfix for command_id collision, splitting further violates TG-1 independent testability) -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
