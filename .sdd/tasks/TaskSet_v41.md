# TaskSet_v41 — Phase 41: Phase Navigation Guards

Spec: specs/Spec_v41_PhaseNavigationGuards.md
Plan: plans/Plan_v41.md

---

T-4101: BC-41-A — Remove make_phase_guard from switch-phase guard factory

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-A — Switch-Phase Guard Factory
Invariants:           I-GUARD-NAV-1
spec_refs:            [Spec_v41 §2 BC-41-A, I-GUARD-NAV-1]
produces_invariants:  [I-GUARD-NAV-1]
requires_invariants:  [I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4]
Inputs:               src/sdd/commands/switch_phase.py
Outputs:              src/sdd/commands/switch_phase.py
Acceptance:           _switch_phase_guard_factory contains only SwitchPhaseGuard + NormGuard; no call to make_phase_guard; PG-1, PG-2, PG-3 removed from pipeline
Depends on:           —

---

T-4102: BC-41-B — Visible SDDError: stderr JSON in switch_phase + activate_phase

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-B — Visible Guard Failures
Invariants:           I-STDERR-1
spec_refs:            [Spec_v41 §2 BC-41-B, I-STDERR-1]
produces_invariants:  [I-STDERR-1]
requires_invariants:  [I-ERROR-1]
Inputs:               src/sdd/commands/switch_phase.py, src/sdd/commands/activate_phase.py
Outputs:              src/sdd/commands/switch_phase.py, src/sdd/commands/activate_phase.py
Acceptance:           both files replace `except SDDError: return 1` with JSON stderr emit; format: {"error_type": type(e).__name__, "message": str(e)}
Depends on:           —

---

T-4103: Tests M2 — BC-41-D: navigation guard + stderr tests

Status:               DONE
Spec ref:             Spec_v41 §9 tests #1-3 — Verification
Invariants:           I-GUARD-NAV-1, I-STDERR-1
spec_refs:            [Spec_v41 §9, I-GUARD-NAV-1, I-STDERR-1]
produces_invariants:  []
requires_invariants:  [I-GUARD-NAV-1, I-STDERR-1]
Inputs:               src/sdd/commands/switch_phase.py, src/sdd/commands/activate_phase.py
Outputs:              tests/unit/commands/test_switch_phase_nav_guard.py
Acceptance:           test_switch_phase_from_complete_phase_allowed PASS; test_switch_phase_guard_no_pg3 PASS; test_switch_phase_stderr_on_error PASS
Depends on:           T-4101, T-4102

---

T-4104: BC-41-E (1/2) — FrozenPhaseSnapshot + PhaseInitialized extension

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-E, §4 Types & Interfaces
Invariants:           I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1
spec_refs:            [Spec_v41 §2 BC-41-E, §4, I-LOGICAL-META-1]
produces_invariants:  [I-LOGICAL-META-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Acceptance:           FrozenPhaseSnapshot gains logical_type: str|None=None and anchor_phase_id: int|None=None; PhaseInitialized payload accepts both optional fields; existing test suite PASS (backward compat via default=None)
Depends on:           —

---

T-4105: BC-41-E (2/2) — Reducer _fold: copy logical fields in all FrozenPhaseSnapshot constructors

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-E, §8 Reducer Extensions
Invariants:           I-LOGICAL-META-1
spec_refs:            [Spec_v41 §2 BC-41-E, §8, I-LOGICAL-META-1]
produces_invariants:  [I-LOGICAL-META-1]
requires_invariants:  [I-LOGICAL-META-1]
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           all ~8-10 FrozenPhaseSnapshot(...) constructors in _fold include logical_type=snap.logical_type, anchor_phase_id=snap.anchor_phase_id; PhaseInitialized handler blindly copies from payload; PhaseContextSwitched passes through from snapshot
Depends on:           T-4104

---

T-4106: BC-41-F — PhaseOrder module (pure view)

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-F, §4 PhaseOrderEntry + PhaseOrder
Invariants:           I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1
spec_refs:            [Spec_v41 §2 BC-41-F, §4, I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1]
produces_invariants:  [I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/phase_order.py
Acceptance:           PhaseOrderEntry frozen dataclass with phase_id/logical_type/anchor_phase_id; PhaseOrder.sort() is pure (no I/O, no state mutation); sort key: patch→after anchor, backfill→before anchor, None→execution order; unknown anchor→fallback+logging.warning
Depends on:           T-4104

---

T-4107: Tests M1 — BC-41-E, BC-41-F + I-LOGICAL-META-1 AST/grep test

Status:               DONE
Spec ref:             Spec_v41 §9 tests #6-9, #12-14
Invariants:           I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1
spec_refs:            [Spec_v41 §9, I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1]
produces_invariants:  []
requires_invariants:  [I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1]
Inputs:               src/sdd/domain/phase_order.py, src/sdd/domain/state/reducer.py, src/sdd/domain/guards/
Outputs:              tests/unit/domain/test_phase_order.py, tests/unit/domain/state/test_reducer_v41.py
Acceptance:           test_phase_order_sort_patch_after_anchor PASS; test_phase_order_sort_backfill_before_anchor PASS; test_phase_order_sort_none_is_execution_order PASS; test_phase_order_unknown_anchor_fallback PASS; test_frozen_snapshot_carries_logical_fields PASS; test_reducer_copies_logical_fields_blindly PASS; test_logical_meta_not_referenced_in_guards PASS (grep guards/*.py for logical_type/anchor_phase_id outside blind copy → zero matches)
Depends on:           T-4105, T-4106

---

T-4108: BC-41-G — AnchorGuard in activate_phase + --logical-type/--anchor CLI args

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-G, §6 Pre/Post Conditions (activate-phase with logical metadata)
Invariants:           I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2
spec_refs:            [Spec_v41 §2 BC-41-G, §6, I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2]
produces_invariants:  [I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2]
requires_invariants:  [I-PHASE-SEQ-1]
Inputs:               src/sdd/commands/activate_phase.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           --logical-type and --anchor CLI args added; AnchorGuard rejects anchor_phase_id ∉ phases_known (I-LOGICAL-ANCHOR-1); AnchorGuard rejects logical_type XOR anchor_phase_id (I-LOGICAL-ANCHOR-2); both None → guard-шаг пропускается (backward compat)
Depends on:           T-4104, T-4102

---

T-4109: Tests M3 — BC-41-G anchor guard tests

Status:               DONE
Spec ref:             Spec_v41 §9 tests #10-11
Invariants:           I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2
spec_refs:            [Spec_v41 §9, I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2]
produces_invariants:  []
requires_invariants:  [I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2]
Inputs:               src/sdd/commands/activate_phase.py
Outputs:              tests/unit/commands/test_anchor_guard.py
Acceptance:           test_activate_phase_anchor_not_in_phases_known_denied PASS; test_activate_phase_anchor_consistency_violated PASS
Depends on:           T-4108

---

T-4110: BC-41-C — show-state: phase.latest_completed + PhaseOrder logical display

Status:               DONE
Spec ref:             Spec_v41 §2 BC-41-C, §6 Post Conditions (show-state)
Invariants:           I-SHOW-STATE-1
spec_refs:            [Spec_v41 §2 BC-41-C, §6, I-SHOW-STATE-1]
produces_invariants:  [I-SHOW-STATE-1]
requires_invariants:  []
Inputs:               src/sdd/commands/show_state.py, src/sdd/domain/phase_order.py
Outputs:              src/sdd/commands/show_state.py
Acceptance:           show-state output contains phase.latest_completed = max(COMPLETE phase_id, default=None); phases list rendered via PhaseOrder.sort(state.phases_snapshots); graceful handling of latest_completed=None
Depends on:           T-4106

---

T-4111: Tests M4 — BC-41-C show-state extension tests

Status:               DONE
Spec ref:             Spec_v41 §9 tests #4-5
Invariants:           I-SHOW-STATE-1
spec_refs:            [Spec_v41 §9, I-SHOW-STATE-1]
produces_invariants:  []
requires_invariants:  [I-SHOW-STATE-1]
Inputs:               src/sdd/commands/show_state.py
Outputs:              tests/unit/commands/test_show_state_v41.py
Acceptance:           test_show_state_latest_completed_field PASS; test_show_state_context_ne_latest PASS
Depends on:           T-4110

---

T-4112: M5 — Session file updates (Agent Prompt Integration)

Status:               DONE
Spec ref:             Spec_v41 §11 Agent Prompt Integration, §11.1
Invariants:           I-AGENT-PLAN-1, I-AGENT-DECOMPOSE-1, I-AGENT-IMPL-1, I-AGENT-STATE-1
spec_refs:            [Spec_v41 §11, §11.1, I-AGENT-PLAN-1, I-AGENT-DECOMPOSE-1, I-AGENT-IMPL-1, I-AGENT-STATE-1]
produces_invariants:  [I-AGENT-PLAN-1, I-AGENT-DECOMPOSE-1, I-AGENT-IMPL-1, I-AGENT-STATE-1]
requires_invariants:  []
Inputs:               .sdd/docs/sessions/plan-phase.md, .sdd/docs/sessions/decompose.md, .sdd/docs/sessions/implement.md
Outputs:              .sdd/docs/sessions/plan-phase.md, .sdd/docs/sessions/decompose.md, .sdd/docs/sessions/implement.md
Acceptance:           plan-phase.md includes logical_context evaluation step + I-AGENT-PLAN-1; decompose.md reads logical_context and conditionally passes --logical-type/--anchor + I-AGENT-DECOMPOSE-1; implement.md documents PIR-1 exception for patch/backfill + I-AGENT-IMPL-1; all three files document phase.context vs phase.latest_completed interpretation + I-AGENT-STATE-1
Depends on:           T-4101, T-4106, T-4108, T-4110

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий (Spec_v39).
NOTE: Phase 41 добавляет НЕ новые event types, только расширяет payload PhaseInitialized — это BC-41-E, не new event.
