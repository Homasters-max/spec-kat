# TaskSet_v31 — Phase 31: Governance Commands

Spec: specs/Spec_v31_GovernanceCommands.md
Plan: plans/Plan_v31.md

---

T-3101: Add SpecApproved and PlanAmended domain event dataclasses

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-1, BC-31-2 — новые DomainEvent dataclasses
Invariants:           I-HANDLER-PURE-1, I-2
spec_refs:            [Spec_v31 §2 BC-31-1, Spec_v31 §2 BC-31-2, I-HANDLER-PURE-1]
produces_invariants:  [I-HANDLER-PURE-1]
requires_invariants:  [I-2]
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py (SpecApproved, PlanAmended dataclasses добавлены)
Acceptance:           from sdd.core.events import SpecApproved, PlanAmended; assert SpecApproved(phase_id=1, spec_hash="abc", spec_path="x").event_type == "SpecApproved"; assert PlanAmended(phase_id=1, new_plan_hash="def", reason="r").event_type == "PlanAmended"
Depends on:           —

---

T-3102: Change SessionDeclaredEvent.phase_id to Optional[int]

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-3 — тип поля phase_id: int → Optional[int] = None
Invariants:           I-SESSION-PHASE-NULL-1, I-2
spec_refs:            [Spec_v31 §2 BC-31-3, I-SESSION-PHASE-NULL-1]
produces_invariants:  [I-SESSION-PHASE-NULL-1]
requires_invariants:  [I-2]
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py (SessionDeclaredEvent.phase_id тип изменён)
Acceptance:           from sdd.core.events import SessionDeclaredEvent; e = SessionDeclaredEvent(session_type="DRAFT_SPEC"); assert e.phase_id is None
Depends on:           T-3101

---

T-3103: Add ApproveSpecCommand and AmendPlanCommand dataclasses

Status:               DONE
Spec ref:             Spec_v31 §4 Types & Interfaces — command dataclasses
Invariants:           I-2
spec_refs:            [Spec_v31 §4, I-2]
produces_invariants:  [I-2]
requires_invariants:  [I-2]
Inputs:               src/sdd/core/types.py
Outputs:              src/sdd/core/types.py (ApproveSpecCommand, AmendPlanCommand добавлены)
Acceptance:           from sdd.core.types import ApproveSpecCommand, AmendPlanCommand; assert ApproveSpecCommand(phase_id=31).actor == "human"; assert AmendPlanCommand(phase_id=31, reason="x").actor == "human"
Depends on:           —

---

T-3104: Implement ApproveSpecHandler in approve_spec.py

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-1, §6 Pre/Post approve-spec — handler logic
Invariants:           I-2, I-HANDLER-PURE-1, I-ERROR-1, I-DB-1
spec_refs:            [Spec_v31 §2 BC-31-1, Spec_v31 §6, I-HANDLER-PURE-1, I-ERROR-1]
produces_invariants:  [I-HANDLER-PURE-1]
requires_invariants:  [I-2, I-HANDLER-PURE-1, I-ERROR-1]
Inputs:               src/sdd/core/events.py (SpecApproved), src/sdd/core/types.py (ApproveSpecCommand), src/sdd/commands/_base.py (CommandSpec)
Outputs:              src/sdd/commands/approve_spec.py (новый файл: ApproveSpecHandler + approve_spec_spec)
Acceptance:           test: ApproveSpecHandler.handle() возвращает [SpecApproved] без side-effects; guard "spec already in specs/" → raises
Depends on:           T-3101, T-3103

---

T-3105: Write Kernel post-event hook for SpecApproved (shutil.move)

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-1 — post-event hook в execute_and_project
Invariants:           I-2, I-ERROR-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v31 §2 BC-31-1, I-2, I-ERROR-1]
produces_invariants:  [I-ERROR-1]
requires_invariants:  [I-2, I-HANDLER-PURE-1]
Inputs:               src/sdd/commands/_base.py (execute_and_project), src/sdd/core/events.py (SpecApproved)
Outputs:              src/sdd/commands/_base.py (post-event hook: if isinstance(event, SpecApproved) → shutil.move specs_draft → specs; при ошибке mv → emit ErrorEvent, raise)
Acceptance:           integration test: после execute_and_project с SpecApproved файл перемещён specs_draft → specs; при ошибке mv — ErrorEvent в EventLog
comment: Единственным реальным изменением было добавление idempotent=False в запись approve-spec в src/sdd/commands/registry.py — остальные элементы (тесты, __post_init__, ключ "approve-spec" в _EXPECTED_REGISTRY_KEYS) уже были реализованы в рамках T-3106.
Depends on:           T-3104

---

T-3106: Register approve-spec in registry and wire CLI

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-1 — регистрация в REGISTRY + sdd approve-spec CLI
Invariants:           I-2, I-SPEC-EXEC-1
spec_refs:            [Spec_v31 §2 BC-31-1, I-2, I-SPEC-EXEC-1]
produces_invariants:  [I-2]
requires_invariants:  [I-2, I-SPEC-EXEC-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/cli.py, src/sdd/commands/approve_spec.py
Outputs:              src/sdd/commands/registry.py (REGISTRY["approve-spec"] добавлен), src/sdd/cli.py (sdd approve-spec --phase N)
Acceptance:           sdd approve-spec --help → exit 0; REGISTRY["approve-spec"] разрешается без KeyError
Depends on:           T-3104, T-3105

---

T-3107: Implement AmendPlanHandler in amend_plan.py

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-2, §6 Pre/Post amend-plan — handler logic
Invariants:           I-2, I-HANDLER-PURE-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-PHASE-SNAPSHOT-1
spec_refs:            [Spec_v31 §2 BC-31-2, Spec_v31 §6, I-HANDLER-PURE-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE]
produces_invariants:  [I-HANDLER-PURE-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE]
requires_invariants:  [I-2, I-HANDLER-PURE-1, I-ERROR-1]
Inputs:               src/sdd/core/events.py (PlanAmended), src/sdd/core/types.py (AmendPlanCommand), src/sdd/commands/_base.py (CommandSpec)
Outputs:              src/sdd/commands/amend_plan.py (новый файл: AmendPlanHandler + amend_plan_spec)
Acceptance:           test: AmendPlanHandler.handle() возвращает [PlanAmended] без side-effects; guard "phase not activated (PLANNED)" → raises
Depends on:           T-3101, T-3103

---

T-3108: Implement PlanAmended reducer case

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-2 — reducer: PlanAmended → обновить plan_hash в phases_snapshots
Invariants:           I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2
spec_refs:            [Spec_v31 §2 BC-31-2, I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2]
produces_invariants:  [I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-PHASE-SNAPSHOT-1]
requires_invariants:  [I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/core/events.py (PlanAmended)
Outputs:              src/sdd/domain/state/reducer.py (case PlanAmended: plan_hash в phases_snapshots[phase_id] обновлён; absent snapshot → raise Inconsistency per I-PHASE-SNAPSHOT-4)
Acceptance:           test: reducer replay с PlanAmended → phases_snapshots[phase_id].plan_hash == event.new_plan_hash
Depends on:           T-3101

---

T-3109: Register amend-plan in registry and wire CLI

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-2 — регистрация в REGISTRY + sdd amend-plan CLI
Invariants:           I-2, I-SPEC-EXEC-1
spec_refs:            [Spec_v31 §2 BC-31-2, I-2, I-SPEC-EXEC-1]
produces_invariants:  [I-2]
requires_invariants:  [I-2, I-SPEC-EXEC-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/cli.py, src/sdd/commands/amend_plan.py
Outputs:              src/sdd/commands/registry.py (REGISTRY["amend-plan"] добавлен), src/sdd/cli.py (sdd amend-plan --phase N --reason "...")
Acceptance:           sdd amend-plan --help → exit 0; REGISTRY["amend-plan"] разрешается без KeyError
Depends on:           T-3107, T-3108

---

T-3110: Implement _check_i_sdd_hash in validate_invariants.py

Status:               DONE
Spec ref:             Spec_v31 §2 BC-31-4, §7 UC-31-3 — проверка sha256(Spec_vN.md) == spec_hash в SpecApproved
Invariants:           I-2, I-DB-1
spec_refs:            [Spec_v31 §2 BC-31-4, Spec_v31 §7, I-2, I-DB-1]
produces_invariants:  [I-2]
requires_invariants:  [I-2, I-DB-1]
Inputs:               src/sdd/commands/validate_invariants.py, src/sdd/core/events.py (SpecApproved), src/sdd/infra/event_query.py
Outputs:              src/sdd/commands/validate_invariants.py (_check_i_sdd_hash(phase_id) добавлен; sdd validate-invariants --check I-SDD-HASH --phase N)
Acceptance:           sdd validate-invariants --check I-SDD-HASH --phase N → PASS при совпадении hash; FAIL при расхождении; SKIP если SpecApproved не найден
Depends on:           T-3101

---

T-3111: Unit tests — domain events (SpecApproved, PlanAmended, SessionDeclaredEvent Optional[int])

Status:               DONE
Spec ref:             Spec_v31 §9 Verification #5-6 — backward compat и Optional[int] семантика
Invariants:           I-SESSION-PHASE-NULL-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v31 §9 #5-6, I-SESSION-PHASE-NULL-1]
produces_invariants:  [I-SESSION-PHASE-NULL-1]
requires_invariants:  [I-HANDLER-PURE-1]
Inputs:               src/sdd/core/events.py
Outputs:              tests/unit/core/test_events_v31.py (новый файл: тесты SpecApproved, PlanAmended, SessionDeclaredEvent)
Acceptance:           §9 #5: SessionDeclaredEvent(session_type="DRAFT_SPEC").phase_id is None; §9 #6: replay с phase_id=None не изменяет state; frozen=True для SpecApproved и PlanAmended
Depends on:           T-3101, T-3102

---

T-3112: Unit tests — approve-spec handler and Write Kernel hook

Status:               DONE
Spec ref:             Spec_v31 §9 Verification #1-2 — approve-spec PASS и repeat guard
Invariants:           I-HANDLER-PURE-1, I-ERROR-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v31 §9 #1-2, I-HANDLER-PURE-1, I-ERROR-1, I-DB-TEST-1, I-DB-TEST-2]
produces_invariants:  [I-HANDLER-PURE-1, I-ERROR-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/approve_spec.py, src/sdd/commands/_base.py
Outputs:              tests/unit/commands/test_approve_spec.py (новый файл)
Acceptance:           §9 #1: approve-spec → exit 0, SpecApproved в EventLog; §9 #2: повторный approve-spec → exit 1 (guard specs/Spec_vN_*.md уже существует)
Depends on:           T-3104, T-3105, T-3106

---

T-3113: Unit tests — amend-plan handler and reducer

Status:               DONE
Spec ref:             Spec_v31 §9 Verification #3-4 — amend-plan PASS и guard "not activated"
Invariants:           I-HANDLER-PURE-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-PHASE-SNAPSHOT-1
spec_refs:            [Spec_v31 §9 #3-4, I-HANDLER-PURE-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE, I-PHASE-SNAPSHOT-1]
produces_invariants:  [I-PLAN-IMMUTABLE-AFTER-ACTIVATE]
requires_invariants:  [I-HANDLER-PURE-1, I-PHASE-SNAPSHOT-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/amend_plan.py, src/sdd/domain/state/reducer.py
Outputs:              tests/unit/commands/test_amend_plan.py (новый файл)
Acceptance:           §9 #3: amend-plan → exit 0, PlanAmended в EventLog; §9 #4: amend-plan без активации фазы → exit 1; reducer: plan_hash обновлён после replay
Depends on:           T-3107, T-3108, T-3109

---

T-3114: Unit tests — _check_i_sdd_hash

Status:               DONE
Spec ref:             Spec_v31 §9 Verification #7-8 — PASS/FAIL/SKIP семантика
Invariants:           I-2, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v31 §9 #7-8, I-2, I-DB-TEST-1, I-DB-TEST-2]
produces_invariants:  [I-2]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants_v31.py (новый файл)
Acceptance:           §9 #7: hash совпадает → PASS; §9 #8: hash расходится → FAIL с деталями; нет SpecApproved → SKIP (не FAIL)
Depends on:           T-3110

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->
