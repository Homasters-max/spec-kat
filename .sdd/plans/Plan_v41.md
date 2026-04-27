# Plan_v41 — Phase 41: Phase Navigation Guards

Status: DRAFT
Spec: specs/Spec_v41_PhaseNavigationGuards.md

---

## Logical Context

```
type: none
anchor_phase: —
rationale: "Standard new phase. Implements navigation guard fix and dual phase ordering.
Not a patch or backfill of an existing phase."
```

---

## Milestones

### M1: Data Foundation — FrozenPhaseSnapshot Extension + PhaseOrder Module

```text
Spec:       §2 (BC-41-E, BC-41-F), §4 Types & Interfaces
BCs:        BC-41-E, BC-41-F
Invariants: I-LOGICAL-META-1, I-PHASE-ORDER-EXEC-1
Depends:    — (foundational)
Risks:      FrozenPhaseSnapshot используется в ~8–10 конструкторах в _fold;
            пропуск одного → backward compat нарушен при replay.
            PhaseOrder.sort() с неизвестным logical_type должен fallback, не крашить.
```

**BC-41-E:** Добавить два поля с `default=None` в `FrozenPhaseSnapshot`:
- `logical_type: str | None`
- `anchor_phase_id: int | None`

Обновить `PhaseInitialized` payload в `events.py` (+2 опциональных поля).
Обновить reducer: слепое копирование из payload при `PhaseInitialized`;
проброс из snapshot при `PhaseContextSwitched`; все `FrozenPhaseSnapshot(...)` в `_fold`
получают `logical_type=snap.logical_type, anchor_phase_id=snap.anchor_phase_id`.

**BC-41-F:** Создать `src/sdd/domain/phase_order.py`:
- `PhaseOrderEntry(frozen dataclass)`: `phase_id`, `logical_type`, `anchor_phase_id`
- `PhaseOrder.sort(snapshots)`: pure function, sort key `(anchor_phase_id или phase_id, sub-order, phase_id)`.
  `patch` → после anchor (sub-order=2), `backfill` → до anchor (sub-order=0), `None` → в execution-порядке (sub-order=1).
  Неизвестный anchor → fallback + `logging.warning`.

### M2: Navigation Guard Fix + Visible Failures

```text
Spec:       §2 (BC-41-A, BC-41-B, BC-41-D), §5 Invariants, §6 Pre/Post
BCs:        BC-41-A, BC-41-B, BC-41-D
Invariants: I-GUARD-NAV-1, I-STDERR-1
Depends:    — (независим от M1)
Risks:      Удаление make_phase_guard может открыть навигацию туда, где guards должны
            оставаться. Проверить что SwitchPhaseGuard (CONTEXT-2,3,4) + NormGuard
            полностью покрывают legitimные кейсы.
```

**BC-41-A:** В `src/sdd/commands/switch_phase.py` — удалить `make_phase_guard` из
`_switch_phase_guard_factory`. Оставить только `SwitchPhaseGuard` (I-PHASE-CONTEXT-2,3,4)
и `NormGuard`.

**BC-41-B:** В `switch_phase.py` (и `activate_phase.py`) заменить `except SDDError: return 1`
на:
```python
except SDDError as e:
    import json, sys
    print(json.dumps({"error_type": type(e).__name__, "message": str(e)}), file=sys.stderr)
    return 1
```

**BC-41-D:** Тест `test_switch_phase_from_complete_phase_allowed` и
`test_switch_phase_guard_no_pg3` — проверяют что `switch-phase` разрешён из COMPLETE-фазы.
`test_switch_phase_stderr_on_error` — проверяет JSON-вывод в stderr при guard failure.

### M3: Activation Anchor Guard

```text
Spec:       §2 (BC-41-G), §5 (I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2), §6 Pre/Post
BCs:        BC-41-G
Invariants: I-LOGICAL-ANCHOR-1, I-LOGICAL-ANCHOR-2
Depends:    M1 (anchor_phase_id field in FrozenPhaseSnapshot + events)
Risks:      Guard должен быть NO-OP при logical_type=None — не ломать существующие
            вызовы activate-phase без флагов.
```

**BC-41-G:** В `src/sdd/commands/activate_phase.py` добавить `AnchorGuard` в pipeline:
- Если `anchor_phase_id != None`: проверить `anchor_phase_id ∈ phases_known` (I-LOGICAL-ANCHOR-1)
- Если `logical_type != None XOR anchor_phase_id != None`: reject (I-LOGICAL-ANCHOR-2)
- Если оба `None`: guard-шаг пропускается (backward compat)

Добавить CLI-аргументы `--logical-type` и `--anchor` в `activate-phase`.

Тесты: `test_activate_phase_anchor_not_in_phases_known_denied`,
`test_activate_phase_anchor_consistency_violated`.

### M4: show-state Display Layer

```text
Spec:       §2 (BC-41-C), §5 (I-SHOW-STATE-1)
BCs:        BC-41-C
Invariants: I-SHOW-STATE-1
Depends:    M1 (PhaseOrder.sort() должен быть готов)
Risks:      latest_completed из snapshots может быть None (нет COMPLETE-фаз) —
            обработать gracefully в рендере.
```

**BC-41-C:** В `src/sdd/commands/show_state.py` (или аналоге):
- Вычислить `latest_completed = max(snap.phase_id where phase_status=="COMPLETE", default=None)`
- Добавить поле `phase.latest_completed` в вывод (рядом с `phase.context`)
- Список фаз отображать через `PhaseOrder.sort(state.phases_snapshots)` вместо raw execution order

Тесты: `test_show_state_latest_completed_field`, `test_show_state_context_ne_latest`.

### M5: Session Protocol Updates

```text
Spec:       §11 Agent Prompt Integration
BCs:        §11.1 (изменения в session-файлах)
Invariants: I-AGENT-PLAN-1, I-AGENT-DECOMPOSE-1, I-AGENT-IMPL-1, I-AGENT-STATE-1
Depends:    M1-M4 (описывает семантику реализованных изменений)
Risks:      Изменение session-файлов влияет на поведение LLM в будущих сессиях.
            Формулировки должны быть недвусмысленны.
```

Обновить session-файлы согласно §11.1 спека:
- `.sdd/docs/sessions/plan-phase.md` → добавить шаг оценки logical type; I-AGENT-PLAN-1
- `.sdd/docs/sessions/decompose.md` → читать `logical_context` из плана; I-AGENT-DECOMPOSE-1
- `.sdd/docs/sessions/implement.md` → исключение PIR-1 для patch/backfill; I-AGENT-IMPL-1
- Все сессии → интерпретация `phase.context` vs `phase.latest_completed`; I-AGENT-STATE-1

---

## Risk Notes

- R-1: **FrozenPhaseSnapshot конструкторы в _fold** — нужно обновить все ~8–10 мест;
  пропуск одного поля не вызовет ошибку компилятора (поля имеют default), но сбросит
  logical_type при следующем update того snapshot. Mitigation: grep-тест `test_reducer_copies_logical_fields_blindly`.
- R-2: **Backward compat replay** — существующие `PhaseInitialized` события в EventLog
  не имеют `logical_type`/`anchor_phase_id`. Reducer должен применять `None` как default.
  Mitigation: `default=None` в dataclass + явная проверка в тесте `test_frozen_snapshot_carries_logical_fields`.
- R-3: **I-LOGICAL-META-1 enforcement** — reducer не должен ветвиться на `logical_type`.
  Mitigation: grep/AST-тест `test_logical_meta_not_referenced_in_guards` (спек §9, тест 12).
- R-4: **PhaseOrder с отсутствующим anchor** — `anchor_phase_id` может ссылаться на
  фазу не из snapshots (e.g. архивированная). Fallback + warning; display не крашит.
  Mitigation: тест `test_phase_order_unknown_anchor_fallback`.
