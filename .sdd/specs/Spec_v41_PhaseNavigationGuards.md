# Spec_v41 — Phase 41: Phase Navigation Guards

Status: Draft
Baseline: Spec_v33_CommandSpecGuardFactory.md, Spec_v24_PhaseContextSwitch.md

---

## 0. Goal

Устранить тупик при навигации между фазами: исправить неправильный guard в `switch-phase`,
сделать guard-отказы видимыми в stderr, и улучшить вывод `show-state` для явного различения
навигационного контекста и последней завершённой фазы.

**Корневая причина:** `make_phase_guard` (PG-1..PG-3) проектировался для task lifecycle команд
(`complete`, `validate`, `check-dod`), но был ошибочно применён к навигационной команде
`switch-phase`. PG-3 (`phase.status == "ACTIVE"`) блокирует навигацию от любой COMPLETE-фазы,
делая `switch-phase` непригодным после завершения фазы.

Дополнительно: формализовать **dual phase ordering** — разделение execution-порядка (phase_id,
SSOT, immutable) и logical-порядка (для display, LLM-навигации, next-tasks). Logical metadata
хранится в EventLog (I-1 сохраняется), переносится в `FrozenPhaseSnapshot` как opaque data,
интерпретируется только в `PhaseOrder` (pure view module). Guards и reducer не используют
logical metadata.

---

## 1. Scope

### In-Scope

- BC-41-A: Навигационный guard для `switch-phase` — удаление `make_phase_guard` из guard factory
- BC-41-B: Видимые guard-отказы — stderr JSON output при `SDDError` в command-модулях
- BC-41-C: `show-state` расширение — `phase.latest_completed` + logical order via `PhaseOrder`
- BC-41-D: Тест: `switch-phase N` когда `phase_current.status == "COMPLETE"` → ALLOW
- BC-41-E: `FrozenPhaseSnapshot` + `PhaseInitialized` payload — поля `logical_type`, `anchor_phase_id`
- BC-41-F: Новый модуль `PhaseOrder` — pure sort function, единственная точка интерпретации logical metadata
- BC-41-G: `activate-phase` anchor guard — I-LOGICAL-ANCHOR-1 (anchor ∈ phases_known)

### Out of Scope

Формализация lifecycle vs. navigation категорий в `CommandSpec` (candidate для Spec_v42).
Изменение I-PHASE-SEQ-1 или `activate_phase_guard.py` — не трогаем.

---

## 2. Architecture / BCs

### BC-41-A: Switch-Phase Guard Factory

**Проблема:** `_switch_phase_guard_factory` применяет `make_phase_guard("switch-phase", None)`,
который содержит PG-3: `phase.status != "ACTIVE" → DENY`. Статус — свойство *текущей* фазы,
не цели навигации. Навигация не является mutation и не требует ACTIVE-фазы.

```
src/sdd/commands/
  switch_phase.py    # _switch_phase_guard_factory: удалить make_phase_guard
```

**Guard pipeline после fix:**

```
switch-phase N:
  [1] SwitchPhaseGuard   ← I-PHASE-CONTEXT-2,3,4 (target ∈ phases_known, target ≠ current)
  [2] NormGuard          ← actor == human
```

**Удаляется:** PG-1 (`phase_current == task.phase_id`) — бессмысленно для навигации.
**Удаляется:** PG-2 (version alignment) — только для task-команд.
**Удаляется:** PG-3 (`phase.status == "ACTIVE"`) — блокирует легитимную навигацию.

### BC-41-B: Visible Guard Failures

**Проблема:** Паттерн `except SDDError: return 1` в command-модулях поглощает ошибку молча.
Top-level handler в `cli.py::main()` умеет эмитировать JSON в stderr, но до него ошибка
не доходит: command-модули возвращают int, не бросают исключение.

```
src/sdd/commands/
  switch_phase.py      # except SDDError as e: → stderr JSON + return 1
  activate_phase.py    # аналогично
```

Формат совместим с `_emit_json_error` из `cli.py`:

```python
except SDDError as e:
    import json, sys
    print(json.dumps({"error_type": type(e).__name__, "message": str(e)}), file=sys.stderr)
    return 1
```

### BC-41-C: show-state Latest Completed + Logical Order

**Проблема:** `phase.current = 32` визуально неотличим от "я завершил фазу 32 и нахожусь в 32".
На самом деле: пользователь переключился на 32 через `switch-phase 32`, а фазы 33, 34 — COMPLETE.
Кроме того, список фаз в `show-state` отображается в execution-порядке, который не совпадает
с логическим (patch/backfill фазы стоят не там, где ожидает пользователь).

```
src/sdd/commands/
  show_state.py    # _render(): добавить phase.latest_completed; использовать PhaseOrder.sort()
```

`phase.latest_completed` вычисляется из снапшотов (данные уже есть):

```python
latest_completed = max(
    (snap.phase_id for snap in state.phases_snapshots if snap.phase_status == "COMPLETE"),
    default=None,
)
```

Список фаз рендерится через `PhaseOrder.sort(state.phases_snapshots)` — logical order.

**Новый вывод show-state:**

| Field | Value |
|-------|-------|
| phase.context | 32 |
| phase.latest_completed | 34 |
| phase.status | COMPLETE |
| phases (logical order) | 32 → 35[patch] → 33 → 36[backfill→34] → 34 |

### BC-41-E: FrozenPhaseSnapshot + PhaseInitialized Extension

**Проблема:** Нет формализованного места для logical metadata. Без него `PhaseOrder` не может
строить logical ordering — ему нечего читать.

```
src/sdd/domain/state/reducer.py    # FrozenPhaseSnapshot: +logical_type, +anchor_phase_id
src/sdd/core/events.py             # PhaseInitialized payload: +logical_type, +anchor_phase_id
```

**FrozenPhaseSnapshot — два новых поля:**

```python
# I-LOGICAL-META-1: opaque data — только PhaseOrder читает, guards/reducer не ветвятся
logical_type:     str | None = None   # "backfill" | "patch" | None
anchor_phase_id:  int | None = None   # phase_id anchor для logical positioning
```

**PhaseInitialized payload — опциональные поля:**

```python
# logical_type: str | None   — "backfill" | "patch" | None
# anchor_phase_id: int | None
```

Reducer читает их при `PhaseInitialized` аналогично `plan_hash` — слепое копирование,
без ветвлений. `PhaseContextSwitched` пробрасывает их из snapshot (как остальные поля).

**Backward compat:** `logical_type = None`, `anchor_phase_id = None` → обычная фаза
в execution-порядке. Все существующие фазы остаются корректными без миграции.

**Механическая стоимость:** ~8–10 конструкторов `FrozenPhaseSnapshot(...)` в `_fold` —
обновить все, добавив `logical_type=..., anchor_phase_id=...`.

### BC-41-F: PhaseOrder Module

**Проблема:** Logical ordering — это STATE (влияет на LLM, next-tasks, навигацию → I-1),
но его интерпретация должна быть изолирована от reducer и guards.

```
src/sdd/domain/phase_order.py    # новый файл
```

```python
@dataclass(frozen=True)
class PhaseOrderEntry:
    phase_id:        int
    logical_type:    str | None
    anchor_phase_id: int | None

class PhaseOrder:
    @staticmethod
    def sort(snapshots: Iterable[FrozenPhaseSnapshot]) -> list[PhaseOrderEntry]:
        """Pure view: logical ordering of phases.
        I-LOGICAL-META-1: единственная точка интерпретации logical_type / anchor_phase_id.
        No state mutations, no I/O.
        """
```

**Sort key:**

```python
def _sort_key(snap: FrozenPhaseSnapshot) -> tuple[int, int, int]:
    match snap.logical_type:
        case None:       return (snap.phase_id,        1, snap.phase_id)
        case "backfill": return (snap.anchor_phase_id, 0, snap.phase_id)
        case "patch":    return (snap.anchor_phase_id, 2, snap.phase_id)
        case _:          return (snap.phase_id,        1, snap.phase_id)  # unknown → fallback
```

Семантика: `patch` → ПОСЛЕ anchor; `backfill` → ДО anchor. Execution-порядок (phase_id)
служит тайбрейкером при одинаковом anchor.

**Edge case:** `anchor_phase_id` ссылается на фазу не из `snapshots` →
fallback к `(phase_id, 1, phase_id)` + `logging.warning`. View не крашит display.

**Callers:** `show-state`, `next-tasks`, LLM routing. Guards и reducer не вызывают `PhaseOrder`.

### BC-41-G: activate-phase Anchor Guard

**Проблема:** Без валидации `anchor_phase_id` можно создать patch/backfill к несуществующей
фазе. `PhaseOrder.sort()` упадёт или вернёт мусор.

```
src/sdd/commands/activate_phase.py    # новый guard-шаг: I-LOGICAL-ANCHOR-1
```

Guard-шаг добавляется в guard pipeline `activate-phase`:

```
activate-phase N:
  [existing guards]
  [new] AnchorGuard: если payload содержит anchor_phase_id != None →
        anchor_phase_id MUST ∈ phases_known (I-LOGICAL-ANCHOR-1)
```

Если `logical_type = None` и `anchor_phase_id = None` — guard-шаг пропускается (backward compat).

### Dependencies

```text
BC-41-A → BC-41-D : тест покрывает исправленный guard
BC-41-B → (no deps)
BC-41-C → BC-41-F : show-state использует PhaseOrder.sort()
BC-41-E → BC-41-F : PhaseOrder читает поля из FrozenPhaseSnapshot
BC-41-E → BC-41-G : AnchorGuard проверяет anchor_phase_id из payload
BC-41-F → BC-41-C : show-state, next-tasks потребляют PhaseOrder
```

---

## 3. Domain Events

Новых событий нет. Все изменения — в guard pipeline, payload extension, и projection layer.

**PhaseInitialized payload extension (BC-41-E):**

Существующее событие `PhaseInitialized` получает два опциональных поля:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `logical_type` | `str \| None` | `None` | `"backfill"` \| `"patch"` \| `None` |
| `anchor_phase_id` | `int \| None` | `None` | phase_id anchor для logical positioning |

Оба поля отсутствуют → None; одно из двух присутствует → нарушение I-LOGICAL-ANCHOR-2.

---

## 4. Types & Interfaces

### FrozenPhaseSnapshot (BC-41-E)

Два новых поля с default=None (backward compat):

```python
logical_type:     str | None = None   # "backfill" | "patch" | None
anchor_phase_id:  int | None = None   # reference phase for logical positioning
```

`SDDState.phases_snapshots` используется как есть — новые поля просто в нём присутствуют.

### PhaseOrderEntry + PhaseOrder (BC-41-F)

```python
# src/sdd/domain/phase_order.py

@dataclass(frozen=True)
class PhaseOrderEntry:
    phase_id:        int
    logical_type:    str | None
    anchor_phase_id: int | None

class PhaseOrder:
    @staticmethod
    def sort(snapshots: Iterable[FrozenPhaseSnapshot]) -> list[PhaseOrderEntry]: ...
```

Interface is the test surface: `PhaseOrder.sort()` — единственный публичный метод.
Callers получают `list[PhaseOrderEntry]`, не сырые snapshots.

---

## 5. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-GUARD-NAV-1 | Navigation commands (`switch-phase`) MUST NOT include phase lifecycle guards (PG-1..PG-3). Guard pipeline for navigation MUST contain only navigation-specific guards and NormGuard. | 41 |
| I-STDERR-1 | Every command-module `main()` MUST emit JSON to stderr before returning non-zero exit code when catching `SDDError`. Silent `except SDDError: return 1` is forbidden. | 41 |
| I-SHOW-STATE-1 | `show-state` output MUST include `phase.latest_completed` field alongside `phase.context`. These fields MUST be derived from `SDDState.phases_snapshots`, never from flat `phase_current` alone. | 41 |
| I-LOGICAL-META-1 | `logical_type` и `anchor_phase_id` в `FrozenPhaseSnapshot` являются opaque data для reducer и всех guard factories. ЕДИНСТВЕННЫЙ модуль, имеющий право читать и интерпретировать эти поля: `PhaseOrder.sort()`. Код-тест: вхождение `logical_type` или `anchor_phase_id` в `guards/*.py` или ветвях `reducer.py` (кроме слепого копирования) → FAIL. | 41 |
| I-LOGICAL-ANCHOR-1 | Если `PhaseInitialized` payload содержит `anchor_phase_id != None`, то `anchor_phase_id` MUST ∈ `phases_known` на момент события. Enforcement: AnchorGuard в `activate-phase` pipeline. | 41 |
| I-LOGICAL-ANCHOR-2 | `logical_type != None ↔ anchor_phase_id != None`. Оба присутствуют или оба отсутствуют. Enforcement: `PhaseInitialized` payload validation в `activate-phase`. | 41 |
| I-PHASE-ORDER-EXEC-1 | Все guards и replay используют только `phase_id` (execution order). `I-PHASE-SEQ-1` (`activate-phase N` требует `N == current + 1`) не изменяется. Logical metadata не влияет на execution guard pipeline. | 41 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-PHASE-CONTEXT-1 | `switch-phase` MUST emit `PhaseContextSwitched`; MUST NOT emit `PhaseStarted` or `PhaseInitialized` |
| I-PHASE-CONTEXT-2 | `switch-phase` MUST target a phase in `phases_known` |
| I-PHASE-CONTEXT-3 | `switch-phase` MUST fail if `phases_known` is empty |
| I-PHASE-CONTEXT-4 | `switch-phase N` where `N == phase_current` MUST be rejected |
| I-PHASE-SEQ-1 | `activate-phase` MUST satisfy `phase_id == current + 1` (declared; not code-enforced) |
| I-CMD-IDEM-1 | Navigation commands MUST NOT be idempotent |
| I-PHASE-LIFECYCLE-1 | `PhaseContextSwitched` MUST NOT override `phase_status`; MUST restore snapshot value |

---

## 6. Pre/Post Conditions

### switch-phase N (after BC-41-A)

**Pre:**
- `N ∈ phases_known` (I-PHASE-CONTEXT-2)
- `N != phase_current` (I-PHASE-CONTEXT-4)
- `phases_known` non-empty (I-PHASE-CONTEXT-3)
- actor == "human" (NormGuard)
- _Removed:_ phase_current.status == "ACTIVE"

**Post:**
- `phase_current == N`
- flat state restored from `phases_snapshots[N]`
- `phase_status == phases_snapshots[N].phase_status` (может быть COMPLETE)

### show-state (after BC-41-C)

**Post:**
- Output contains `phase.context` = `phase_current`
- Output contains `phase.latest_completed` = max completed phase_id, or None
- Phase list rendered in logical order via `PhaseOrder.sort(state.phases_snapshots)`

### activate-phase N with logical metadata (after BC-41-G)

**Pre (дополнительно к существующим):**
- Если payload содержит `anchor_phase_id != None`: `anchor_phase_id ∈ phases_known` (I-LOGICAL-ANCHOR-1)
- `logical_type != None ↔ anchor_phase_id != None` (I-LOGICAL-ANCHOR-2)

**Post:**
- `PhaseInitialized` payload содержит `logical_type`, `anchor_phase_id` (могут быть None)
- `phases_snapshots[N].logical_type` и `.anchor_phase_id` установлены из payload

---

## 7. Use Cases

### UC-41-1: Навигация из COMPLETE-фазы к другой COMPLETE-фазе

**Actor:** human
**Trigger:** `sdd switch-phase 34` когда `phase_current = 32, phase_status = COMPLETE`
**Pre:** 34 ∈ phases_known, 34 ≠ 32
**Steps:**
1. SwitchPhaseGuard: 34 ∈ phases_known → ALLOW (I-GUARD-NAV-1: PG-3 не применяется)
2. NormGuard: actor == human → ALLOW
3. Handler: emit PhaseContextSwitchedEvent(from=32, to=34)
4. Reducer: restore flat state from phases_snapshots[34]
5. Projection: write State_index.yaml
**Post:** `phase_current = 34`, `phase_status = COMPLETE` (snapshot restored)

### UC-41-2: Видимый guard-отказ

**Actor:** human
**Trigger:** `sdd switch-phase 99` (phase 99 not in phases_known)
**Steps:**
1. SwitchPhaseGuard: 99 ∉ phases_known → DENY
2. GuardViolationError raised, ErrorEvent appended
3. `except SDDError as e:` → JSON emitted to stderr, return 1
**Post:** exit 1 + stderr: `{"error_type": "GuardViolationError", "message": "I-PHASE-CONTEXT-2: phase 99 not in phases_known=..."}`

### UC-41-3: show-state с отставшим контекстом

**Actor:** human
**Trigger:** `sdd show-state` когда phase_current=32 но latest_completed=34
**Post:** вывод содержит оба поля; user видит что context ≠ latest_completed

### UC-41-4: Создание patch-фазы

**Actor:** human
**Trigger:** `sdd activate-phase 35 --logical-type patch --anchor 32`
  когда phases_known={32,33,34}, phase_current=34
**Pre:** 35 == 34+1 (I-PHASE-SEQ-1); 32 ∈ phases_known (I-LOGICAL-ANCHOR-1)
**Steps:**
1. AnchorGuard: 32 ∈ phases_known → ALLOW (I-LOGICAL-ANCHOR-1)
2. I-LOGICAL-ANCHOR-2: оба поля присутствуют → OK
3. Handler: emit PhaseInitialized(phase_id=35, logical_type="patch", anchor_phase_id=32, ...)
4. Reducer: phases_snapshots[35] = FrozenPhaseSnapshot(..., logical_type="patch", anchor_phase_id=32)
5. PhaseOrder.sort([32,33,34,35]) → [32, 35(patch→32), 33, 34]
**Post:** `phase_current=35`; `sdd show-state` показывает 35 сразу после 32 в logical order

### UC-41-5: Создание backfill-фазы

**Actor:** human
**Trigger:** `sdd activate-phase 36 --logical-type backfill --anchor 34`
  когда phases_known={32,33,34,35}
**Pre:** 36 == 35+1 (I-PHASE-SEQ-1); 34 ∈ phases_known (I-LOGICAL-ANCHOR-1)
**Steps:**
1. AnchorGuard: 34 ∈ phases_known → ALLOW
2. Handler: emit PhaseInitialized(phase_id=36, logical_type="backfill", anchor_phase_id=34, ...)
3. PhaseOrder.sort([32,33,34,35,36]) → [32, 35(patch→32), 33, 36(backfill→34), 34]
**Post:** `sdd show-state` показывает 36 перед 34 в logical order (backfill = ДО anchor)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-24 PhaseContextSwitch | this uses | PhaseContextSwitchedEvent, SwitchPhaseGuard |
| BC-33 CommandSpecGuardFactory | this modifies | guard factory for switch-phase |
| BC-34 EventLogDeepModule | this uses | GuardViolationError surfacing via ErrorEvent |
| BC-PC-9 FrozenPhaseSnapshot | this extends | +logical_type, +anchor_phase_id fields |

### Reducer Extensions

`FrozenPhaseSnapshot` получает два новых поля (BC-41-E). Reducer обновляет их при
`PhaseInitialized` (слепое копирование из payload) и пробрасывает при `PhaseContextSwitched`
(как все остальные snapshot-поля). Никаких ветвлений на эти поля в reducer не добавляется.

Все остальные места с явным конструктором `FrozenPhaseSnapshot(...)` в `_fold` (~8–10 мест)
получают `logical_type=snap.logical_type, anchor_phase_id=snap.anchor_phase_id` для сохранения
значений при обновлениях других полей.

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_switch_phase_from_complete_phase_allowed` | I-GUARD-NAV-1 |
| 2 | `test_switch_phase_guard_no_pg3` | I-GUARD-NAV-1 |
| 3 | `test_switch_phase_stderr_on_error` | I-STDERR-1 |
| 4 | `test_show_state_latest_completed_field` | I-SHOW-STATE-1 |
| 5 | `test_show_state_context_ne_latest` | I-SHOW-STATE-1 |
| 6 | `test_phase_order_sort_patch_after_anchor` | I-LOGICAL-META-1, UC-41-4 |
| 7 | `test_phase_order_sort_backfill_before_anchor` | I-LOGICAL-META-1, UC-41-5 |
| 8 | `test_phase_order_sort_none_is_execution_order` | I-PHASE-ORDER-EXEC-1 |
| 9 | `test_phase_order_unknown_anchor_fallback` | I-LOGICAL-META-1 |
| 10 | `test_activate_phase_anchor_not_in_phases_known_denied` | I-LOGICAL-ANCHOR-1 |
| 11 | `test_activate_phase_anchor_consistency_violated` | I-LOGICAL-ANCHOR-2 |
| 12 | `test_logical_meta_not_referenced_in_guards` | I-LOGICAL-META-1 (grep/AST) |
| 13 | `test_frozen_snapshot_carries_logical_fields` | BC-41-E |
| 14 | `test_reducer_copies_logical_fields_blindly` | I-LOGICAL-META-1 |

**Smoke test (CLI):**
```bash
sdd switch-phase 34    # exit 0 (was: exit 1, PG-3 DENY)
sdd show-state         # phase.context=34, phase.latest_completed=34; logical order rendered
sdd switch-phase 99    # exit 1 + JSON stderr (was: exit 1, silent)
sdd activate-phase 35 --logical-type patch --anchor 32   # exit 0; show-state: 35 после 32
sdd activate-phase 36 --logical-type patch               # exit 1; I-LOGICAL-ANCHOR-2 violation
```

---

## 11. Agent Prompt Integration

Logical ordering — это STATE, влияющий на поведение LLM (I-1, выбор в §0).
Агенты должны понимать dual ordering и менять поведение в соответствии с ним.
Ниже — конкретные изменения в session-файлах `.sdd/docs/sessions/`.

---

### 11.1 Изменения в session-файлах

#### `plan-phase.md` — оценка логического типа новой фазы

**Текущее поведение:** план создаётся с привязкой к phase_id; тип фазы не указывается.

**Новое поведение:** перед написанием Plan_vN.md LLM MUST оценить:
- Является ли новая фаза исправлением существующей? → `patch`, anchor = phase_id исправляемой фазы
- Заполняет ли пробел, пропущенный ранее? → `backfill`, anchor = phase_id, перед которой логически стоит
- Обычная новая фаза? → logical metadata не указывается

Результат оценки фиксируется в Plan_vN.md в новом поле `logical_context`:

```markdown
## Logical Context
type: patch          # или backfill, или отсутствует
anchor_phase: 32     # phase_id anchor
rationale: "Исправляет ошибку в BC-32-2, обнаруженную в ходе фазы 34."
```

Это поле читается DECOMPOSE-сессией для передачи флагов в `activate-phase`.

**Инвариант поведения:**
`I-AGENT-PLAN-1`: В конце PLAN-сессии LLM MUST явно указать logical_context в Plan_vN.md
(даже если тип = None — тогда указывается `type: none` с rationale "standard phase").

---

#### `decompose.md` — передача logical metadata в activate-phase

**Текущее поведение:**
```bash
sdd activate-phase N --executed-by llm
```

**Новое поведение:** если Plan_vN.md содержит `logical_context.type != none`:
```bash
sdd activate-phase N --executed-by llm --logical-type patch --anchor 32
```

LLM MUST читать `logical_context` из Plan_vN.md перед auto-action (шаг 2 в DECOMPOSE).
Если `logical_context` отсутствует в плане — использовать обычный вызов без флагов.

**Инвариант поведения:**
`I-AGENT-DECOMPOSE-1`: `sdd activate-phase` в DECOMPOSE MUST передавать `--logical-type`
и `--anchor`, если и только если Plan_vN.md содержит непустой `logical_context.type`.

---

#### `implement.md` — загрузка контекста anchor-фазы

**Текущее поведение:**
PIR-1: MUST NOT читать TaskSet_vM, Plan_vM, Spec_vM где M ≠ current phase N.

**Новое поведение:** для patch/backfill фаз — разрешённое исключение PIR-1:

```
[Auto-action] sdd show-state
```
Если `phase.logical_type == "patch"` или `"backfill"`:
```
[Auto-action] sdd show-plan --phase <anchor_phase_id>
[Auto-action] sdd show-spec --phase <anchor_phase_id>
```

Цель: понять что именно исправляется/заполняется. Без этого patch-фаза реализуется вслепую.

**Инвариант поведения:**
`I-AGENT-IMPL-1`: В IMPLEMENT-сессии для фазы с `logical_type != None` LLM MUST загрузить
план и спек anchor-фазы через CLI до начала реализации. Прямое чтение файлов `.sdd/plans/`
и `.sdd/specs/` по-прежнему запрещено (NORM-SCOPE-004); использовать только `sdd show-*`.

---

#### Все сессии — интерпретация show-state с dual ordering

**Текущее поведение:** LLM читает `phase_current` из `sdd show-state` и работает с ним напрямую.

**Новое поведение:** при наличии `phase.latest_completed` и `phase.context` LLM MUST:
1. Если `phase.context ≠ phase.latest_completed` — явно сообщить пользователю:
   `"Контекст = фаза N (навигация), последняя завершённая = M"`
2. Использовать logical order (из `PhaseOrder`) при перечислении фаз в любом выводе,
   а не execution order

**Инвариант поведения:**
`I-AGENT-STATE-1`: LLM MUST NOT представлять `phase.context` как "текущую активную фазу",
если `phase.context ≠ phase.latest_completed`. Обе величины MUST быть явно названы.

---

### 11.2 Итоговая таблица изменений в session-файлах

| Session file | Что меняется | Новый инвариант |
|---|---|---|
| `plan-phase.md` | Добавить шаг оценки logical type; писать `logical_context` в Plan_vN.md | I-AGENT-PLAN-1 |
| `decompose.md` | Читать `logical_context` из плана; передавать `--logical-type`/`--anchor` в activate-phase | I-AGENT-DECOMPOSE-1 |
| `implement.md` | Исключение PIR-1 для patch/backfill: загружать план и спек anchor-фазы через CLI | I-AGENT-IMPL-1 |
| Все сессии | Интерпретировать `phase.context` vs `phase.latest_completed`; использовать logical order | I-AGENT-STATE-1 |

### 11.3 Что НЕ меняется в поведении агентов

- LLM по-прежнему использует только `phase_id` для CLI-команд (`complete`, `validate`, `activate-phase`)
- Execution order (I-PHASE-SEQ-1) не меняется — `activate-phase N` требует `N == current + 1`
- Logical order используется исключительно для отображения и загрузки контекста, не для guard-команд

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| CommandSpec.command_category (lifecycle vs. navigation) | Spec_v42 |
| Enforce I-PHASE-SEQ-1 in code | Not planned |
| Refactor всех command-модулей (B2: propagate SDDError to top-level) | Spec_v42+ |
| CLI флаги `--logical-type` / `--anchor` для `activate-phase` | BC-41-G реализует guard; CLI parsing — в рамках той же фазы |
