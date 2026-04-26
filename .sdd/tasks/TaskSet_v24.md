# TaskSet_v24 — Phase 24: PhaseContextSwitch

Spec: specs/Spec_v24_PhaseContextSwitch.md
Plan: plans/Plan_v24.md

---

T-2401: PhaseStarted reducer hotfix — zero mutations + DEBUG log

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-0; §3 Reducer dispatcher (PhaseStarted branch); §5 M0
Invariants:           I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1
spec_refs:            [Spec_v24 §2 BC-PC-0, §3, I-PHASE-AUTH-1, I-PHASE-STARTED-1]
produces_invariants:  [I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           AC-1: `sdd complete T-NNN` → no ERROR в stderr при нормальной работе;
                      PhaseStarted(regression) → DEBUG log, state неизменно
Depends on:           —

---

T-2402: FrozenPhaseSnapshot dataclass + SDDState multi-phase fields + REDUCER_VERSION=2

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-9; §3 FrozenPhaseSnapshot dataclass, SDDState расширение; §9 Step 1
Invariants:           I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-3, I-PHASES-KNOWN-2
spec_refs:            [Spec_v24 §2 BC-PC-9, §3 SDDState расширение, I-PHASE-SNAPSHOT-1..4]
produces_invariants:  [I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-3, I-PHASES-KNOWN-2]
requires_invariants:  [I-PHASE-AUTH-1]
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           FrozenPhaseSnapshot frozen dataclass присутствует; SDDState содержит
                      phases_known: frozenset[int] и phases_snapshots: tuple[FrozenPhaseSnapshot, ...];
                      REDUCER_VERSION = 2; _make_empty_state() возвращает корректные дефолты
Depends on:           T-2401

---

T-2403: PhaseContextSwitchedEvent в events.py + V1_L1_EVENT_TYPES

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-1; §3 PhaseContextSwitchedEvent dataclass; §9 Step 2
Invariants:           I-PHASE-CONTEXT-1
spec_refs:            [Spec_v24 §2 BC-PC-1, §3 PhaseContextSwitchedEvent, I-PHASE-CONTEXT-1]
produces_invariants:  [I-PHASE-CONTEXT-1]
requires_invariants:  []
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py
Acceptance:           PhaseContextSwitchedEvent dataclass присутствует в events.py с полями
                      phase_id, actor, timestamp; "PhaseContextSwitched" добавлен в V1_L1_EVENT_TYPES
                      (НЕ в _EVENT_SCHEMA — это Step 3/T-2404)
Depends on:           T-2402

---

T-2404: Reducer _fold — полный update (PhaseContextSwitched, snapshots, _check_snapshot_coherence)

Status:               DONE
Spec ref:             Spec_v24 §3 Reducer полный dispatcher; §9 Step 3; C-1 constraint; §5 M1
Invariants:           I-PHASE-AUTH-1, I-PHASE-LIFECYCLE-1, I-PHASE-LIFECYCLE-2,
                      I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-3, I-PHASE-SNAPSHOT-4,
                      I-PHASES-KNOWN-1, I-PHASES-KNOWN-2, I-PHASE-REDUCER-1, I-PHASE-CONTEXT-1
spec_refs:            [Spec_v24 §3 Reducer dispatcher, §5 M1, C-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-4]
produces_invariants:  [I-PHASE-LIFECYCLE-1, I-PHASE-LIFECYCLE-2, I-PHASE-SNAPSHOT-4, I-PHASES-KNOWN-1]
requires_invariants:  [I-PHASE-AUTH-1, I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-CONTEXT-1]
Inputs:               src/sdd/domain/state/reducer.py,
                      src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           AC-12: import sdd.domain.state.reducer не падает (C-1 assert проходит);
                      AC-15: _check_snapshot_coherence(state) == True после full rebuild;
                      AC-7: reduce(events) идентичен при двух вызовах (детерминизм);
                      AC-11: phases_known == {s.phase_id for s in phases_snapshots};
                      AC-16: PhaseContextSwitched без snapshot → Inconsistency
Depends on:           T-2402, T-2403

---

T-2405: yaml_state.py — поддержка phases_known и phases_snapshots + REDUCER_VERSION mismatch

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-2; §3 REDUCER_VERSION mismatch; §7 Migration Note; §9 Step 4
Invariants:           I-PHASE-SNAPSHOT-1, I-PHASES-KNOWN-2
spec_refs:            [Spec_v24 §2 BC-PC-2, §3 REDUCER_VERSION mismatch, §7]
produces_invariants:  [I-PHASE-SNAPSHOT-1, I-PHASES-KNOWN-2]
requires_invariants:  [I-PHASE-SNAPSHOT-2, I-PHASES-KNOWN-1]
Inputs:               src/sdd/domain/state/yaml_state.py,
                      src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/state/yaml_state.py
Acceptance:           AC-14: REDUCER_VERSION=2 и phases_snapshots сериализованы в State_index.yaml;
                      read_state + write_state round-trip корректен для phases_known и phases_snapshots;
                      REDUCER_VERSION < 2 в кэше → get_current_state() сбрасывает snapshot_event_id=None
                      и выполняет full replay с seq=0
Depends on:           T-2404

---

T-2406: ActivatePhaseGuard — make_activate_phase_guard + подключение в _build_spec_guards

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-4; §3 ActivatePhaseGuard; §5 M2; §9 Step 5
Invariants:           I-PHASE-SEQ-1
spec_refs:            [Spec_v24 §2 BC-PC-4, §3 ActivatePhaseGuard, I-PHASE-SEQ-1]
produces_invariants:  [I-PHASE-SEQ-1]
requires_invariants:  [I-PHASE-AUTH-1, I-PHASE-SNAPSHOT-1]
Inputs:               src/sdd/domain/state/reducer.py,
                      src/sdd/commands/registry.py,
                      src/sdd/commands/activate_phase.py
Outputs:              src/sdd/domain/guards/activate_phase_guard.py (новый),
                      src/sdd/commands/registry.py
Acceptance:           AC-4: sdd activate-phase 19 при phase_current=18 → exit 0;
                      AC-5: sdd activate-phase 20 при phase_current=18 → exit 1, Inconsistency,
                      сообщение содержит "switch-phase 20"
Depends on:           T-2404

---

T-2407: switch-phase command + SwitchPhaseGuard + REGISTRY registration

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-3; §3 SwitchPhaseGuard, Команды финальная модель; §5 M2; §9 Step 6
Invariants:           I-PHASE-CONTEXT-1, I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4
spec_refs:            [Spec_v24 §2 BC-PC-3, §3 SwitchPhaseGuard, I-PHASE-CONTEXT-1..4]
produces_invariants:  [I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4]
requires_invariants:  [I-PHASE-CONTEXT-1, I-PHASES-KNOWN-1, I-PHASE-LIFECYCLE-1]
Inputs:               src/sdd/domain/state/reducer.py,
                      src/sdd/commands/registry.py
Outputs:              src/sdd/commands/switch_phase.py (новый),
                      src/sdd/domain/guards/switch_phase_guard.py (новый),
                      src/sdd/commands/registry.py
Acceptance:           AC-2: sdd switch-phase 18 (phases_known={15,17,18,22,23}) → exit 0,
                      phase_current=18, plan_version=18, tasks_completed=<phase18 count>;
                      AC-3: sdd switch-phase 999 → exit 1, MissingContext;
                      AC-6: sdd switch-phase 18 при phase_current==18 → exit 1, MissingContext;
                      AC-8: switch-phase на COMPLETE фазу → phase_status="COMPLETE" (не ACTIVE);
                      AC-9: switch(18)→switch(23) → tasks_completed = phase 23 count;
                      AC-10: после switch(18) → plan_version=18, tasks_version=18
Depends on:           T-2404, T-2406

---

T-2408: Удалить check_phase_activation_guard из guards/phase.py

Status:               DONE
Spec ref:             Spec_v24 §2 BC-PC-8; §1 D-1; §5 M3; §9 Step 7
Invariants:           I-PHASE-SEQ-1
spec_refs:            [Spec_v24 §2 BC-PC-8, §1 D-1]
produces_invariants:  [I-PHASE-SEQ-1]
requires_invariants:  [I-PHASE-SEQ-1]
Inputs:               src/sdd/guards/phase.py
Outputs:              src/sdd/guards/phase.py
Acceptance:           AC-13: check_phase_activation_guard отсутствует в codebase (grep → 0 matches);
                      все существующие тесты guards/test_phase_guard.py проходят
Depends on:           T-2406

---

T-2409: Тесты reducer и yaml_state (7 файлов)

Status:               DONE
Spec ref:             Spec_v24 §6 Test Matrix #1..4, #9..11; §9 Step 8 (порядок: 9→1→4→3→11→2→10)
Invariants:           I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1,
                      I-PHASE-LIFECYCLE-1, I-PHASE-LIFECYCLE-2,
                      I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-3, I-PHASE-SNAPSHOT-4,
                      I-PHASES-KNOWN-1, I-PHASES-KNOWN-2
spec_refs:            [Spec_v24 §6 #1,#2,#3,#4,#9,#10,#11]
produces_invariants:  [I-PHASE-SNAPSHOT-2, I-PHASES-KNOWN-2]
requires_invariants:  [I-PHASE-AUTH-1, I-PHASE-LIFECYCLE-1, I-PHASE-SNAPSHOT-1, I-PHASES-KNOWN-1]
Inputs:               src/sdd/domain/state/reducer.py,
                      src/sdd/domain/state/yaml_state.py,
                      src/sdd/core/events.py
Outputs:              tests/unit/domain/state/test_reducer_c1.py (новый),
                      tests/unit/domain/state/test_reducer_phase_auth.py (новый),
                      tests/unit/domain/state/test_reducer_phases_known.py (новый),
                      tests/unit/domain/state/test_reducer_snapshots.py (новый),
                      tests/unit/domain/state/test_reducer_phase_lifecycle.py (новый),
                      tests/unit/domain/state/test_reducer_phase_context.py (новый),
                      tests/unit/domain/state/test_yaml_state_snapshots.py (новый)
Acceptance:           Все 7 файлов проходят pytest; покрывают инварианты §6 #1..4,#9..11 полностью;
                      C-1 assert тест: import sdd.domain.state.reducer не падает
Depends on:           T-2404, T-2405

---

T-2410: Тесты guards, switch-phase command и integration (4 файла)

Status:               DONE
Spec ref:             Spec_v24 §6 Test Matrix #5,#6,#7,#8; §9 Step 8 (порядок: 5→6→7→8)
Invariants:           I-PHASE-SEQ-1, I-PHASE-CONTEXT-1, I-PHASE-CONTEXT-2,
                      I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4
spec_refs:            [Spec_v24 §6 #5,#6,#7,#8, I-PHASE-SEQ-1, I-PHASE-CONTEXT-1..4]
produces_invariants:  [I-PHASE-SEQ-1, I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4]
requires_invariants:  [I-PHASE-SEQ-1, I-PHASE-CONTEXT-1, I-PHASE-LIFECYCLE-1]
Inputs:               src/sdd/domain/guards/activate_phase_guard.py,
                      src/sdd/domain/guards/switch_phase_guard.py,
                      src/sdd/commands/switch_phase.py,
                      src/sdd/domain/state/reducer.py
Outputs:              tests/unit/guards/test_activate_phase_guard.py (новый),
                      tests/unit/guards/test_switch_phase_guard.py (новый),
                      tests/unit/commands/test_switch_phase.py (новый),
                      tests/integration/test_switch_phase_flow.py (новый)
Acceptance:           Все 4 файла проходят pytest; integration test воспроизводит полный сценарий
                      §6 #8: activate(18)→impl×3→activate(23)→impl×2→switch(18)→assert→switch(23)
                      →assert→complete(23)→switch(COMPLETE)→assert; replay дважды → идентичный state
Depends on:           T-2407, T-2409

---

T-2411: Обновить CLAUDE.md §INV — 16 новых инвариантов Phase 24

Status:               DONE
Spec ref:             Spec_v24 §4 Invariants; §2 BC-PC-6; §5 M3; §9 Step 9
Invariants:           I-PHASE-SEQ-1, I-PHASE-AUTH-1, I-PHASE-STARTED-1,
                      I-PHASE-CONTEXT-1, I-PHASE-CONTEXT-2, I-PHASE-CONTEXT-3, I-PHASE-CONTEXT-4,
                      I-PHASE-LIFECYCLE-1, I-PHASE-LIFECYCLE-2, I-PHASE-REDUCER-1,
                      I-PHASES-KNOWN-1, I-PHASES-KNOWN-2,
                      I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2, I-PHASE-SNAPSHOT-3, I-PHASE-SNAPSHOT-4
spec_refs:            [Spec_v24 §4, §2 BC-PC-6]
produces_invariants:  [I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-CONTEXT-1..4,
                       I-PHASE-LIFECYCLE-1..2, I-PHASE-REDUCER-1, I-PHASES-KNOWN-1..2,
                       I-PHASE-SNAPSHOT-1..4]
requires_invariants:  []
Inputs:               CLAUDE.md,
                      Spec_v24 §4 (таблица инвариантов)
Outputs:              CLAUDE.md
Acceptance:           AC (M3): CLAUDE.md §INV содержит все 16 инвариантов из таблицы §4;
                      I-PHASE-SEQ-1 обновлён согласно новой формулировке спека
Depends on:           T-2408, T-2410
