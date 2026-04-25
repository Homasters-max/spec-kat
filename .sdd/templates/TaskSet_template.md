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
