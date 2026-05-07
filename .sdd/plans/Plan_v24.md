# Plan_v24 — Phase 24: PhaseContextSwitch

Status: ACTIVE
Spec: specs/Spec_v24_PhaseContextSwitch.md

---

## Milestones

### M0: Reducer hotfix — PhaseStarted → zero mutations

```text
Spec:       §2 In-Scope: BC-PC-0; §5 M0 Pre/Post; §3 Reducer dispatcher
BCs:        BC-PC-0
Invariants: I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1
Depends:    — (first; unblocks all subsequent milestones)
Risks:      Regression если другой код опирается на PhaseStarted мутации; проверить
            что только PhaseInitialized изменяет phase_current
```

**Acceptance (AC-1):** `sdd complete T-NNN` → no ERROR в stderr при нормальной работе.

---

### M1: FrozenPhaseSnapshot + SDDState multi-phase fields + PhaseContextSwitched event

```text
Spec:       §3 Архитектурная модель (FrozenPhaseSnapshot, SDDState расширение,
            Reducer dispatcher полный); §5 M1 Pre/Post; §2 BC-PC-1,2,9
BCs:        BC-PC-1, BC-PC-2, BC-PC-9
Invariants: I-PHASE-AUTH-1, I-PHASE-LIFECYCLE-1, I-PHASE-SNAPSHOT-1..4,
            I-PHASES-KNOWN-1..2, I-PHASE-CONTEXT-1, I-PHASE-REDUCER-1
Depends:    M0
Risks:      C-1 import-time assert в reducer.py:131 — PhaseContextSwitched ДОЛЖЕН
            быть добавлен одновременно в V1_L1_EVENT_TYPES И _EVENT_SCHEMA.
            REDUCER_VERSION mismatch → full replay; yaml_state несовместим со старым кэшем.
```

**Шаги реализации (строгий порядок — dependency graph §9):**

1. **Step 1 (BC-PC-9):** `FrozenPhaseSnapshot` frozen dataclass в `reducer.py`;
   поля `phases_known: frozenset[int]` и `phases_snapshots: tuple[FrozenPhaseSnapshot, ...]`
   в `SDDState`; `REDUCER_VERSION = 2`; обновить `_make_empty_state()`.

2. **Step 2 (BC-PC-1):** `PhaseContextSwitchedEvent` dataclass в `core/events.py`;
   добавить `"PhaseContextSwitched"` в `V1_L1_EVENT_TYPES`.

3. **Step 3 (BC-PC-0 + BC-PC-1 reducer):** Добавить `"PhaseContextSwitched"` в
   `EventReducer._EVENT_SCHEMA` (C-1 assert проходит); обновить все handler branches
   в `_fold` по §3; добавить `_check_snapshot_coherence`; accumulator block и
   SDDState construction.

4. **Step 4 (BC-PC-2):** `yaml_state.py` — `write_state`/`read_state` поддержка
   `phases_known` и `phases_snapshots`; REDUCER_VERSION mismatch → full rebuild.

**Acceptance (AC-7, AC-11..16):**
- C-1 assert проходит (import не падает)
- `_check_snapshot_coherence` возвращает True после full rebuild
- `phases_known == {s.phase_id for s in phases_snapshots}` после любого replay
- `PhaseContextSwitched` при отсутствии snapshot → `Inconsistency`
- `REDUCER_VERSION=2`; `phases_snapshots` сериализованы в State_index.yaml

---

### M2: switch-phase command + ActivatePhaseGuard + SwitchPhaseGuard

```text
Spec:       §3 Команды (финальная модель), ActivatePhaseGuard, SwitchPhaseGuard;
            §5 M2 Pre/Post; §2 BC-PC-3..5
BCs:        BC-PC-3, BC-PC-4, BC-PC-5
Invariants: I-PHASE-SEQ-1, I-PHASE-CONTEXT-1..4
Depends:    M1
Risks:      ActivatePhaseGuard должен быть подключён в _build_spec_guards для
            activate-phase (сейчас D-1: dead guard). Без этого I-PHASE-SEQ-1 не
            обеспечивается.
```

**Шаги реализации:**

5. **Step 5 (BC-PC-4):** `domain/guards/activate_phase_guard.py` — `make_activate_phase_guard`;
   подключить в `_build_spec_guards` для `activate-phase` CommandSpec.

6. **Step 6 (BC-PC-3+5):** `commands/switch_phase.py` + `domain/guards/switch_phase_guard.py`
   (`make_switch_phase_guard`); регистрация в REGISTRY.

**Acceptance (AC-2..6, AC-8..10):**
- `sdd switch-phase 18` (phases_known={15,17,18,22,23}) → exit 0, `phase_current=18`, `plan_version=18`
- `sdd switch-phase 999` → exit 1, `error_type=MissingContext`
- `sdd activate-phase 19` при `phase_current=18` → exit 0
- `sdd activate-phase 20` при `phase_current=18` → exit 1; сообщение содержит `"switch-phase 20"`
- `sdd switch-phase 18` при `phase_current==18` → exit 1, `error_type=MissingContext`
- `sdd switch-phase 18` при COMPLETE phase 18 → `phase_status="COMPLETE"` (не ACTIVE)

---

### M3: Tests + Dead code removal + CLAUDE.md §INV

```text
Spec:       §6 Test Matrix; §5 M3 Pre/Post; §2 BC-PC-6..8
BCs:        BC-PC-6, BC-PC-7, BC-PC-8
Invariants: Все 16 инвариантов из §4 должны присутствовать в CLAUDE.md §INV
Depends:    M0, M1, M2
Risks:      Test execution order §9: 9→1→4→3→11→2→10→5→6→7→8.
            check_phase_activation_guard используется где-то → проверить grep перед удалением.
```

**Шаги реализации:**

7. **Step 7 (BC-PC-8):** Удалить `check_phase_activation_guard` из `guards/phase.py`.

8. **Step 8 (BC-PC-7):** Реализовать 11 test files по матрице §6 в порядке:
   `test_reducer_c1` → `test_reducer_phase_auth` → `test_reducer_phases_known` →
   `test_reducer_snapshots` → `test_reducer_phase_lifecycle` → `test_reducer_phase_context` →
   `test_yaml_state_snapshots` → `test_activate_phase_guard` → `test_switch_phase_guard` →
   `test_switch_phase` → `test_switch_phase_flow` (integration).

9. **Step 9 (BC-PC-6):** Обновить CLAUDE.md §INV — добавить 16 инвариантов из §4:
   I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-CONTEXT-1..4, I-PHASE-LIFECYCLE-1..2,
   I-PHASE-REDUCER-1, I-PHASES-KNOWN-1..2, I-PHASE-SNAPSHOT-1..4; обновить I-PHASE-SEQ-1.

**Acceptance (AC-13, тесты 100% coverage BC-PC-1..5):**
- `check_phase_activation_guard` отсутствует в codebase
- Все 11 test files проходят
- CLAUDE.md §INV содержит все 16 инвариантов

---

## Risk Notes

- R-1: **C-1 import-time assert** — PhaseContextSwitched добавляется в `V1_L1_EVENT_TYPES`
  (events.py) и `_EVENT_SCHEMA` (reducer.py) атомарно в рамках одного шага (Step 2+3 нельзя
  разрывать между задачами). Нарушение → `ImportError` при старте CLI.

- R-2: **REDUCER_VERSION mismatch** — после внедрения Step 1 существующий YAML-кэш
  `State_index.yaml` имеет `REDUCER_VERSION < 2`. Первый `sdd show-state` выполнит full
  replay. Это ожидаемо, не ошибка.

- R-3: **Migration Note §7** — существующий event log содержит `PhaseInitialized(18)`
  на seq 22638 после фаз 22-23. После внедрения спеки replay корректен: snapshot 18
  создаётся/перезаписывается. Компенсирующих событий не нужно.

- R-4: **activate-phase 24 при phase_current=18** — текущее состояние технически нарушает
  I-PHASE-SEQ-1 (ожидается 19, а не 24). Human gate: активация Phase 24 производится до
  внедрения ActivatePhaseGuard (Step 5). После Step 5 guard вступает в силу для будущих фаз.
