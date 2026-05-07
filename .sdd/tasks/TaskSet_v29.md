# TaskSet_v29 — Phase 29: Streamlined Session Flow

Spec: specs/Spec_v29_StreamlinedWorkflow.md
Plan: plans/Plan_v29.md

---

T-2901: SessionDeclaredEvent + plan_hash field (events infrastructure)

Status:               DONE
Spec ref:             Spec_v29 §2 (SessionDeclaredEvent), §4 (plan_hash в PhaseInitializedEvent)
Invariants:           I-SESSION-DECLARED-1, I-SESSION-PLAN-HASH-1
spec_refs:            [Spec_v29 §2, Spec_v29 §4, I-SESSION-DECLARED-1, I-SESSION-PLAN-HASH-1]
produces_invariants:  [I-SESSION-DECLARED-1, I-SESSION-PLAN-HASH-1]
requires_invariants:  [I-1]
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py
Acceptance:           `SessionDeclaredEvent` импортируется без ошибок; `PhaseInitializedEvent` имеет поле `plan_hash: str = ""`; `python3 -c "from sdd.core.events import SessionDeclaredEvent, PhaseInitializedEvent"` exit 0
Depends on:           —

---

T-2902: Reducer — SessionDeclared no-op branch

Status:               DONE
Spec ref:             Spec_v29 §2 (Reducer: SessionDeclared → DEBUG log only, no state mutation)
Invariants:           I-SESSION-DECLARED-1, I-PHASE-STARTED-1
spec_refs:            [Spec_v29 §2, I-SESSION-DECLARED-1, I-PHASE-STARTED-1]
produces_invariants:  [I-SESSION-DECLARED-1]
requires_invariants:  [I-SESSION-DECLARED-1]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           Reducer содержит case `SessionDeclared` с logging.debug и возвратом state без мутации; replay лога с SessionDeclaredEvent не меняет state (тест T-2909 покроет)
Depends on:           T-2901

---

T-2903: record-session CLI command + registry registration

Status:               DONE
Spec ref:             Spec_v29 §2 (causal chain), §6 (Session FSM — emit SessionDeclared), §8 (BC-SW-2)
Invariants:           I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1, I-2
spec_refs:            [Spec_v29 §2, Spec_v29 §6, Spec_v29 §8, I-SESSION-DECLARED-1, I-2]
produces_invariants:  [I-SESSION-DECLARED-1, I-2]
requires_invariants:  [I-SESSION-DECLARED-1, I-2]
Inputs:               src/sdd/commands/registry.py, src/sdd/core/events.py, src/sdd/infra/event_store.py
Outputs:              src/sdd/commands/record_session.py (новый), src/sdd/commands/registry.py
Acceptance:           `sdd record-session --type PLAN --phase 29` завершается exit 0; SessionDeclaredEvent появляется в EventLog; команда зарегистрирована в REGISTRY
Depends on:           T-2901, T-2902

---

T-2904: activate_phase.py — --executed-by arg + plan_hash computation

Status:               DONE
Spec ref:             Spec_v29 §3 (actor + executed_by), §4 (plan_hash computation), §8 (BC-SW-4, BC-SW-6)
Invariants:           I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1
spec_refs:            [Spec_v29 §3, Spec_v29 §4, I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1]
produces_invariants:  [I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1]
requires_invariants:  [I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-PHASE-AUTH-1]
Inputs:               src/sdd/commands/activate_phase.py, src/sdd/infra/paths.py, src/sdd/core/events.py
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           `sdd activate-phase N --executed-by llm` → PhaseInitializedEvent.payload содержит `executed_by="llm"` и `plan_hash=sha256(Plan_vN.md)[:16]`; без флага — payload без `executed_by`; VALID_ACTORS остаётся {"human"}
Depends on:           T-2901

---

T-2905: Update decompose.md — новые preconditions + Auto-actions

Status:               DONE
Spec ref:             Spec_v29 §6 (DECOMPOSE в Revised Session FSM), §9 (I-SESSION-AUTO-1)
Invariants:           I-SESSION-AUTO-1, I-SESSION-PI-6
spec_refs:            [Spec_v29 §6, Spec_v29 §9, I-SESSION-AUTO-1]
produces_invariants:  [I-SESSION-AUTO-1]
requires_invariants:  [I-SESSION-AUTO-1]
Inputs:               .sdd/docs/sessions/decompose.md
Outputs:              .sdd/docs/sessions/decompose.md
Acceptance:           decompose.md не содержит precondition "Plan Status = ACTIVE"; содержит content check (Milestones + Risk Notes); содержит Auto-actions блок (record-session + activate-phase --executed-by llm)
Depends on:           T-2903, T-2904

---

T-2906: Update plan-phase.md — Phases_index auto-action + PI-6

Status:               DONE
Spec ref:             Spec_v29 §5 (Phases_index Consistency), §6 (PLAN в Revised Session FSM), §9 (I-SESSION-PI-6, I-PHASES-INDEX-1)
Invariants:           I-SESSION-PI-6, I-PHASES-INDEX-1
spec_refs:            [Spec_v29 §5, Spec_v29 §6, Spec_v29 §9, I-SESSION-PI-6, I-PHASES-INDEX-1]
produces_invariants:  [I-SESSION-PI-6, I-PHASES-INDEX-1]
requires_invariants:  [I-SESSION-PI-6, I-PHASES-INDEX-1]
Inputs:               .sdd/docs/sessions/plan-phase.md
Outputs:              .sdd/docs/sessions/plan-phase.md
Acceptance:           plan-phase.md содержит Auto-action блок: обновление Phases_index.md + валидация I-PHASES-INDEX-1; содержит PI-6 в Phase Index Invariants
Depends on:           T-2903

---

T-2907: Update tool-reference.md — исправить --tasks, добавить record-session + --executed-by

Status:               DONE
Spec ref:             Spec_v29 §8 (BC-SW-9), §0 (F-3 — --tasks флаг устарел)
Invariants:           I-SESSION-DECLARED-1, I-SESSION-ACTOR-1
spec_refs:            [Spec_v29 §8, Spec_v29 §0, I-SESSION-DECLARED-1]
produces_invariants:  [I-SESSION-DECLARED-1]
requires_invariants:  [I-SESSION-DECLARED-1, I-SESSION-ACTOR-1]
Inputs:               .sdd/docs/ref/tool-reference.md
Outputs:              .sdd/docs/ref/tool-reference.md
Acceptance:           tool-reference.md: `--tasks` помечен [DEPRECATED] или удалён; `record-session --type T --phase N` добавлен; `activate-phase --executed-by` добавлен с пояснением actor vs executed_by
Depends on:           T-2903, T-2904

---

T-2908: Update CLAUDE.md — §SESSION FSM, §ROLES, §INV

Status:               DONE
Spec ref:             Spec_v29 §6 (Revised Session FSM), §3 (Actor Model Revision), §9 (все I-SESSION-* + I-PHASES-INDEX-1), §8 (BC-SW-10)
Invariants:           I-SESSION-AUTO-1, I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1, I-SESSION-ACTOR-1, I-SESSION-PI-6, I-PHASES-INDEX-1
spec_refs:            [Spec_v29 §6, Spec_v29 §3, Spec_v29 §9, I-SESSION-AUTO-1, I-PHASES-INDEX-1]
produces_invariants:  [I-SESSION-AUTO-1, I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1, I-SESSION-ACTOR-1, I-SESSION-PI-6, I-PHASES-INDEX-1]
requires_invariants:  [I-SESSION-AUTO-1, I-PHASES-INDEX-1]
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           CLAUDE.md §SESSION FSM содержит авто-действия LLM (record-session, activate-phase); §ROLES: "LLM MUST NOT activate-phase" уточнён (запрет снят для DECOMPOSE с --executed-by llm); §INV содержит все I-SESSION-* и I-PHASES-INDEX-1
Depends on:           T-2905, T-2906, T-2907

---

T-2909: Tests — SessionDeclared emitted + no state mutation

Status:               DONE
Spec ref:             Spec_v29 §10 (тест 1: test_session_declared_emitted, тест 2: test_session_declared_no_state_mutation)
Invariants:           I-SESSION-DECLARED-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v29 §10, I-SESSION-DECLARED-1, I-DB-TEST-1]
produces_invariants:  [I-SESSION-DECLARED-1]
requires_invariants:  [I-SESSION-DECLARED-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/record_session.py, src/sdd/domain/state/reducer.py, tests/conftest.py
Outputs:              tests/unit/commands/test_record_session.py (новый)
Acceptance:           `pytest tests/unit/commands/test_record_session.py -v` — оба теста GREEN; tmp_path используется (не production DB)
Depends on:           T-2902, T-2903

---

T-2910: Tests — activate-phase --executed-by + plan_hash

Status:               DONE
Spec ref:             Spec_v29 §10 (тест 3: test_activate_phase_executed_by_llm, тест 4: test_activate_phase_plan_hash)
Invariants:           I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-DB-TEST-1
spec_refs:            [Spec_v29 §10, I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-DB-TEST-1]
produces_invariants:  [I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1]
requires_invariants:  [I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/activate_phase.py, tests/conftest.py, .sdd/plans/ (tmp fixtures)
Outputs:              tests/unit/commands/test_activate_phase_v29.py (новый)
Acceptance:           `pytest tests/unit/commands/test_activate_phase_v29.py -v` — оба теста GREEN; plan_hash вычисляется через hashlib.sha256; tmp_path используется
Depends on:           T-2904

---

T-2911: Tests — phases_known ⊆ Phases_index consistency

Status:               DONE
Spec ref:             Spec_v29 §10 (тест 5: test_phases_index_consistency), §5 (I-PHASES-INDEX-1)
Invariants:           I-PHASES-INDEX-1, I-PHASES-KNOWN-1, I-PHASES-KNOWN-2, I-DB-TEST-1
spec_refs:            [Spec_v29 §10, Spec_v29 §5, I-PHASES-INDEX-1, I-PHASES-KNOWN-1]
produces_invariants:  [I-PHASES-INDEX-1]
requires_invariants:  [I-PHASES-INDEX-1, I-PHASES-KNOWN-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/domain/state/reducer.py, .sdd/plans/Phases_index.md, tests/conftest.py
Outputs:              tests/unit/test_phases_index_consistency.py (новый)
Acceptance:           `pytest tests/unit/test_phases_index_consistency.py -v` — тест GREEN; проверяет что phases_known из EventLog replay ⊆ IDs в Phases_index.md; tmp_path используется
Depends on:           T-2901, T-2902
