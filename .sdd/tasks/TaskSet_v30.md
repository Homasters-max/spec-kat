# TaskSet_v30 — Phase 30: Documentation Fixes

Spec: specs/Spec_v30_DocFixes.md
Plan: plans/Plan_v30.md

---

T-3001: tool-reference.md — строка 55: добавить исключение DECOMPOSE

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-1), §2 Architecture (BC-30-1), §5 AC BC-30-1
Invariants:           I-SESSION-AUTO-1, I-SESSION-ACTOR-1
spec_refs:            [Spec_v30 §2 BC-30-1, I-SESSION-AUTO-1]
produces_invariants:  [I-SESSION-AUTO-1]
requires_invariants:  [I-SESSION-ACTOR-1]
Inputs:               .sdd/docs/ref/tool-reference.md
Outputs:              .sdd/docs/ref/tool-reference.md
Acceptance:           grep "HUMAN-ONLY gate" .sdd/docs/ref/tool-reference.md | grep -q "EXCEPT in DECOMPOSE"
Depends on:           —

---

T-3002: tool-reference.md — строка 57: обновить описание executed_by

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-1), §2 Architecture (BC-30-1), §5 AC BC-30-1
Invariants:           I-SESSION-AUTO-1, I-SESSION-ACTOR-1
spec_refs:            [Spec_v30 §2 BC-30-1, I-SESSION-ACTOR-1]
produces_invariants:  [I-SESSION-ACTOR-1]
requires_invariants:  []
Inputs:               .sdd/docs/ref/tool-reference.md
Outputs:              .sdd/docs/ref/tool-reference.md
Acceptance:           grep "executed_by" .sdd/docs/ref/tool-reference.md | grep -q "llm"
Depends on:           T-3001

---

T-3003: decompose.md — удалить раздел "After TaskSet is Written"

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-2), §2 Architecture (BC-30-2), §5 AC BC-30-2
Invariants:           I-SESSION-AUTO-1, I-SESSION-VISIBLE-1
spec_refs:            [Spec_v30 §2 BC-30-2, I-SESSION-AUTO-1]
produces_invariants:  [I-SESSION-AUTO-1]
requires_invariants:  []
Inputs:               .sdd/docs/sessions/decompose.md
Outputs:              .sdd/docs/sessions/decompose.md
Acceptance:           grep -c "After TaskSet is Written" .sdd/docs/sessions/decompose.md | grep -q "^0$"
Depends on:           —

---

T-3004: decompose.md — добавить recovery path для StaleStateError

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-4), §2 Architecture (BC-30-4), §5 AC BC-30-4
Invariants:           I-SESSION-AUTO-1, SEM-12
spec_refs:            [Spec_v30 §2 BC-30-4, SEM-12]
produces_invariants:  []
requires_invariants:  [I-SESSION-AUTO-1]
Inputs:               .sdd/docs/sessions/decompose.md
Outputs:              .sdd/docs/sessions/decompose.md
Acceptance:           grep -q "StaleStateError" .sdd/docs/sessions/decompose.md && grep -q "RD-2" .sdd/docs/sessions/decompose.md
Depends on:           T-3003

---

T-3005: plan-phase.md — исправить секцию "After Plan is Written"

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-3), §2 Architecture (BC-30-3), §7 UC-30-2, §5 AC BC-30-3
Invariants:           I-SESSION-AUTO-1, I-SESSION-VISIBLE-1
spec_refs:            [Spec_v30 §2 BC-30-3, I-SESSION-AUTO-1]
produces_invariants:  [I-SESSION-AUTO-1]
requires_invariants:  []
Inputs:               .sdd/docs/sessions/plan-phase.md
Outputs:              .sdd/docs/sessions/plan-phase.md
Acceptance:           ! grep -q "LLM waits" .sdd/docs/sessions/plan-phase.md && ! grep -q "sdd activate-phase N \[--tasks T\]" .sdd/docs/sessions/plan-phase.md
Depends on:           —

---

T-3006: dev-cycle-map.md — закрыть §5.1–5.4 (ссылки на реализованные BC)

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-5), §2 Architecture (BC-30-5 таблица §5.1–5.4)
Invariants:           I-1
spec_refs:            [Spec_v30 §2 BC-30-5, I-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/specs_draft/dev-cycle-map.md
Outputs:              .sdd/specs_draft/dev-cycle-map.md
Acceptance:           grep -q "ЗАКРЫТО: BC-30-1" .sdd/specs_draft/dev-cycle-map.md && grep -q "ЗАКРЫТО: BC-30-4" .sdd/specs_draft/dev-cycle-map.md
Depends on:           T-3002, T-3004, T-3005

---

T-3007: dev-cycle-map.md — закрыть §5.5 (plan mutability decision)

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-5), §2 Architecture (BC-30-5 §5.5)
Invariants:           I-1
spec_refs:            [Spec_v30 §2 BC-30-5 §5.5, I-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/specs_draft/dev-cycle-map.md
Outputs:              .sdd/specs_draft/dev-cycle-map.md
Acceptance:           grep -q "I-PLAN-IMMUTABLE-AFTER-ACTIVATE" .sdd/specs_draft/dev-cycle-map.md && grep -q "phase_plan_versions" .sdd/specs_draft/dev-cycle-map.md
Depends on:           T-3006

---

T-3008: dev-cycle-map.md — закрыть §5.6 (Optional[int] для phase_id) и обновить §1

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-5), §2 Architecture (BC-30-5 §5.6)
Invariants:           I-1, I-SESSION-DECLARED-1
spec_refs:            [Spec_v30 §2 BC-30-5 §5.6, I-SESSION-DECLARED-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/specs_draft/dev-cycle-map.md
Outputs:              .sdd/specs_draft/dev-cycle-map.md
Acceptance:           grep -q "I-SESSION-PHASE-NULL-1" .sdd/specs_draft/dev-cycle-map.md && ! grep -q "open choice" .sdd/specs_draft/dev-cycle-map.md
Depends on:           T-3007

---

T-3009: CLAUDE.md — добавить подраздел "Declared (not enforced)" в §INV

Status:               DONE
Spec ref:             Spec_v30 §1 Scope (BC-30-6), §2 Architecture (BC-30-6), §5 AC BC-30-6
Invariants:           I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-SESSION-PHASE-NULL-1
spec_refs:            [Spec_v30 §2 BC-30-6, I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-SESSION-PHASE-NULL-1]
produces_invariants:  [I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-SESSION-PHASE-NULL-1]
requires_invariants:  []
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           grep -q "Declared (not enforced)" CLAUDE.md && grep -q "I-PLAN-IMMUTABLE-AFTER-ACTIVATE" CLAUDE.md && grep -q "I-SESSION-PHASE-NULL-1" CLAUDE.md
Depends on:           T-3008

---

<!-- Granularity: 9 tasks (TG-2: 10–30 recommended; phase is doc-only, 9 tasks justified). -->
<!-- Every task independently implementable and testable via grep acceptance checks (TG-1). -->
