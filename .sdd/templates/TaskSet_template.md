# TaskSet_vN — Phase N: <Title>

Spec: specs/Spec_vN_<title>.md
Plan: plans/Plan_vN.md

---

T-001: <Short title>

Status:               TODO
Spec ref:             Spec_vN §X.X — <section title>
Invariants:           I-NEW-N, I-P-N
spec_refs:            [Spec_vN §X.X, I-NEW-N]
produces_invariants:  [I-NEW-N]
requires_invariants:  [I-P-N]
Inputs:               <existing files/modules/events this task consumes>
Outputs:              <files created or modified — defines allowed modification scope>
Acceptance:           <specific verifiable criterion, usually a test name>
Depends on:           —

---

T-002: <Short title>

Status:               TODO
Spec ref:             Spec_vN §X.X — <section title>
Invariants:           I-NEW-N
spec_refs:            [Spec_vN §X.X, I-NEW-N]
produces_invariants:  [I-NEW-N]
requires_invariants:  [I-P-N]
Inputs:               <inputs>
Outputs:              <outputs>
Acceptance:           <acceptance criterion>
Depends on:           T-001

---

T-003: <Short title>

Status:               TODO
Spec ref:             Spec_vN §X.X
Invariants:           I-NEW-N
spec_refs:            [Spec_vN §X.X]
produces_invariants:  [I-NEW-N]
requires_invariants:  [I-P-N]
Inputs:               <inputs>
Outputs:              <outputs>
Acceptance:           <acceptance criterion>
Depends on:           T-001, T-002

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
