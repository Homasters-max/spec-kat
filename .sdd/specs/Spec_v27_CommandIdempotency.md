# Spec_CommandIdempotency — Command Classification: Idempotent vs Navigation

Status: DRAFT — подлежит human approval перед включением в план фазы
Baseline: Spec_v24_PhaseContextSwitch.md (switch-phase введён в Phase 24)
Discovered: Phase 24 close, 2026-04-25

---

## 0. Goal

Phase 24 ввела `switch-phase` — navigation команду для переключения рабочего контекста
между фазами. При закрытии Phase 24 обнаружен фундаментальный архитектурный дефект:

```
switch-phase(24→18) + switch-phase(24→18) = одно событие в EventLog
```

Система не различает два класса команд по семантике идемпотентности:
- **State mutation** (complete, activate-phase) — идемпотентны по природе
- **Navigation** (switch-phase) — каждый вызов = отдельный факт истории

Данная спецификация вводит явную классификацию команд через `CommandSpec.idempotent`
и устраняет дефект D-7 в `execute_command`.

---

## 1. Диагностика

### D-7 — Navigation команда ошибочно идемпотентна

**Место:** `commands/registry.py` → `execute_command`, Step 0 + Step 5.

```python
# Step 0: compute_command_id = sha256(payload_hash)
command_id = compute_command_id(cmd)

# Step 5: EventStore.append с command_id → dedup по (command_id, event_index)
EventStore(_db).append(handler_events, command_id=command_id, expected_head=head_seq)
```

`compute_command_id` использует только payload: `sha256({"cmd": "SwitchPhaseCommand",
"payload": {"from_phase": N, "phase_id": M}})`. Любые два вызова с одинаковыми
`from_phase` и `phase_id` дают одинаковый хэш → второе событие выбрасывается
через `I-IDEM-SCHEMA-1` (`ON CONFLICT (command_id, event_index) DO NOTHING`).

**Следствие:**

```
sdd switch-phase 18   # ✔ PhaseContextSwitched(24→18) записан
sdd switch-phase 24   # ✔ PhaseContextSwitched(18→24) записан
sdd switch-phase 18   # ✗ ТИХИЙ NO-OP. Событие НЕ записано. Exit 0.
```

История навигации «схлопывается». Аудит trail неполный. Replay даёт неверный результат.

### D-8 — Emergency workaround нарушает Write Kernel

При закрытии Phase 24 для обхода D-7 был использован прямой `EventStore.append`
минуя Registry → нарушены I-KERNEL-WRITE-1, I-SPEC-EXEC-1, audit trail.
Этот путь допустим ТОЛЬКО как emergency recovery (I-BOOTSTRAP-1 прецедент).

---

## 2. Scope

### In-Scope

- **BC-CI-1: CommandSpec.idempotent field** — добавить поле, задать значения для всех
  существующих команд, документировать правило.

- **BC-CI-2: execute_command Step 5** — `command_id` передаётся в `EventStore.append`
  ТОЛЬКО для команд с `idempotent=True`. Для `idempotent=False` → `command_id=None`.

- **BC-CI-3: switch-phase REGISTRY entry** — установить `idempotent=False`.

- **BC-CI-4: I-CMD-IDEM-1 инвариант** — добавить в CLAUDE.md §INV.

- **BC-CI-5: Tests** — тест на то, что повторный `switch-phase` с теми же параметрами
  создаёт два отдельных события в EventLog.

### Out of Scope

- Изменение семантики `complete`, `validate`, `activate-phase` — остаются idempotent
- `switch-phase` replay-детерминизм — всегда был детерминирован (порядок событий важен)
- Ретроспективная очистка EventLog от лишних no-op событий

---

## 3. Архитектурная модель

### Классификация команд

| Команда | `idempotent` | Обоснование |
|---------|-------------|-------------|
| `complete` | `True` | Task DONE — повторная пометка = нет эффекта |
| `validate` | `True` | Валидация записывает результат; дубли не нужны |
| `activate-phase` | `True` | Phase lifecycle — повторная активация = нет эффекта |
| `sync-state` | `True` | NoOpHandler — всегда возвращает [] |
| `record-decision` | `True` | Одно решение = один факт |
| `check-dod` | `True` | Phase completion — повторная пометка = нет эффекта |
| **`switch-phase`** | **`False`** | Navigation: каждый переход = уникальный факт истории |

### CommandSpec расширение (BC-CI-1)

```python
@dataclass(frozen=True)
class CommandSpec:
    name:                 str
    handler_class:        type[CommandHandlerBase]
    actor:                str
    action:               str
    projection:           ProjectionType
    uses_task_id:         bool
    event_schema:         tuple[str, ...]
    preconditions:        tuple[str, ...]
    postconditions:       tuple[str, ...]
    requires_active_phase: bool
    apply_task_guard:     bool
    description:          str
    idempotent:           bool = True   # ← NEW: False для navigation команд
```

### execute_command Step 5 (BC-CI-2)

```python
# Существующий код (ДЕФЕКТ):
EventStore(_db).append(
    handler_events,
    source=spec.handler_class.__module__,
    command_id=command_id,         # ← всегда payload-хэш
    expected_head=head_seq,
)

# Исправление:
from uuid import uuid4
effective_command_id = command_id if spec.idempotent else str(uuid4())
EventStore(_db).append(
    handler_events,
    source=spec.handler_class.__module__,
    command_id=effective_command_id,   # uuid4 для navigation → нет dedup, но traceability сохраняется
    expected_head=head_seq,            # optimistic lock сохраняется
)
```

**Важно:** `expected_head` НЕ убирается даже для `idempotent=False`. Optimistic lock
защищает от TOCTOU независимо от idempotency класса команды.

**Почему uuid4() вместо None:** `command_id=None` убивает event-level traceability — audit
tools и debug не смогут скоррелировать события одного run-а. `uuid4()` уникален → dedup
по `(command_id, event_index)` физически не сработает (нет коллизий), но correlation chain
сохраняется. Это безопаснее при сохранении семантики non-idempotent.

### switch-phase REGISTRY entry (BC-CI-3)

```python
# commands/registry.py — REGISTRY["switch-phase"]:
CommandSpec(
    name="switch-phase",
    handler_class=SwitchPhaseHandler,
    actor="human",
    action="switch_phase",
    projection=ProjectionType.STATE_ONLY,
    uses_task_id=False,
    event_schema=(),
    preconditions=("actor == human", "phase_id in phases_known", "phase_id != phase_current"),
    postconditions=("phase.current == phase_id", "flat fields restored from snapshot"),
    requires_active_phase=False,
    apply_task_guard=True,
    description="Switch working context to a previously activated phase",
    idempotent=False,    # ← NAVIGATION: каждый вызов = уникальное событие
)
```

---

## 4. Invariants

### Новые инварианты (добавить в CLAUDE.md §INV)

| ID | Statement | Verification |
|----|-----------|-------------|
| I-CMD-IDEM-1 | Navigation commands (`switch-phase`) MUST NOT be idempotent. `CommandSpec.idempotent=False` → `execute_command` MUST pass `command_id=uuid4()` (NOT `None`) to `EventStore.append`. Each invocation MUST produce a unique event in EventLog. | `test_switch_phase_non_idempotent.py` |
| I-CMD-IDEM-2 | Handler-level idempotency (`_check_idempotent`) MAY exist as an additional guard, but MUST NOT contradict `CommandSpec.idempotent`. If `spec.idempotent=False`, handler MUST NOT silently suppress event emission via noop. | code review + `test_command_spec_idempotent_default` |
| I-CMD-NAV-1 | Navigation events (`PhaseContextSwitched`) are order-sensitive (temporal semantics). Final state is defined by the last event in sequence. Navigation events MUST NOT be deduplicated at any layer. `SwitchPhaseHandler` SHOULD NOT emit event if `phase_id == phase_current` (guard already enforces this — this invariant documents the design intent). | `test_switch_phase_non_idempotent.py` |

### Temporal semantics (явное зафиксирование)

`switch-phase` вводит **temporal semantics** в EventLog:

- Переходы A→B, B→A, A→B — три независимых факта истории
- Состояние определяется последним событием, а не множеством уникальных переходов
- Replay детерминирован: одинаковый EventLog → одинаковое конечное состояние
- Этим navigation events принципиально отличаются от state mutation events (complete, activate-phase)

Это корректное поведение, явно зафиксированное в I-CMD-NAV-1.

### Сохраняемые инварианты

| ID | Statement | Изменение |
|----|-----------|-----------|
| I-OPTLOCK-1 | `execute_command` verifies `EventStore.max_seq() == head_seq` before append | Не меняется — `expected_head` всегда передаётся |
| I-KERNEL-WRITE-1 | `EventStore.append` exclusively inside `execute_command` | Не меняется — emergency workaround запрещён |
| I-IDEM-SCHEMA-1 | `(command_id, event_index)` dedup | Только для `idempotent=True` команд |

---

## 5. Pre/Post Conditions

### BC-CI-2 (execute_command Step 5)

**Pre:**
- `spec.idempotent` field exists in CommandSpec
- `handler_events` non-empty (handler returned events)

**Post:**
- If `spec.idempotent == True`: `EventStore.append(command_id=payload_hash)` — dedup активен
- If `spec.idempotent == False`: `EventStore.append(command_id=uuid4())` — dedup физически невозможен (ключ уникален), traceability сохраняется
- В обоих случаях: `expected_head=head_seq` (optimistic lock активен)
- `command_id` НИКОГДА не передаётся как `None`

### BC-CI-5 (Tests)

**Pre:** `switch-phase` зарегистрирован с `idempotent=False`

**Post:** два последовательных `switch-phase(A→B)` → два события `PhaseContextSwitched`
в EventLog, даже при одинаковых `from_phase` и `to_phase`.

---

## 6. Verification

| # | Тест | Инвариант |
|---|------|-----------|
| 1 | `test_switch_phase_non_idempotent`: два `execute_and_project(switch-phase, A→B)` → два события в EventLog | I-CMD-IDEM-1 |
| 2 | `test_complete_still_idempotent`: два `execute_and_project(complete, T-NNN)` → одно событие в EventLog | I-IDEM-SCHEMA-1 |
| 3 | `test_switch_phase_optlock_preserved`: optimistic lock проверяется даже при `idempotent=False` | I-OPTLOCK-1 |
| 4 | `test_command_spec_idempotent_default`: все REGISTRY entries кроме `switch-phase` имеют `idempotent=True` | I-CMD-IDEM-1 |

---

## 7. Implementation Order

```
BC-CI-1: CommandSpec.idempotent field (добавить поле, дефолт True)
BC-CI-3: switch-phase REGISTRY entry (idempotent=False)
BC-CI-2: execute_command Step 5 (effective_command_id)
BC-CI-4: CLAUDE.md §INV (I-CMD-IDEM-1)
BC-CI-5: Tests
```

---

## 8. Handover Context для новой сессии

### Текущее состояние системы

```
phase.current = 18   (ACTIVE — переключено через PhaseContextSwitched)
Phase 24: COMPLETE
Phase 18: ACTIVE, tasks.completed = 3/13
```

### Что произошло при закрытии Phase 24

1. `reconcile-bootstrap` реализован (стаб снят) — backfill EventLog для 9 задач.
2. Обнаружен D-7: `switch-phase` идемпотентна по ошибке → второй вызов = no-op.
3. Обходное решение: прямой `EventStore.append` (нарушает Write Kernel) — применён
   как emergency, зафиксирован как недопустимый путь.

### Критические файлы для этого фикса

| Файл | Строка | Что менять |
|------|--------|-----------|
| `src/sdd/commands/registry.py` | `CommandSpec` dataclass | Добавить `idempotent: bool = True` |
| `src/sdd/commands/registry.py` | `execute_command` Step 5 (~line 488) | `effective_command_id` |
| `src/sdd/commands/registry.py` | `REGISTRY["switch-phase"]` | `idempotent=False` |
| `CLAUDE.md` | `§INV` | Добавить `I-CMD-IDEM-1` |

### Что НЕ менять

- `EventStore.append` сигнатуру — `command_id` принимает str, uuid4() передаётся как str
- `compute_command_id` — используется для audit/tracing, не только dedup; вызов сохраняется
- Семантику `_check_idempotent` в handlers — handler-level защита; при `idempotent=False` проверить, что handler не делает noop (I-CMD-IDEM-2)

### Взаимодействие handler vs spec (I-CMD-IDEM-2)

Два уровня idempotency существуют независимо:

| Уровень | Механизм | Когда срабатывает |
|---------|----------|------------------|
| Kernel-level | `command_id` dedup в EventStore | Только при `spec.idempotent=True` |
| Handler-level | `_check_idempotent()` в handler | Логика конкретного handler |

**Запрещено:** handler noop при `spec.idempotent=False`. Handler для navigation команды
MUST NOT подавлять событие внутренней проверкой — это нарушает I-CMD-IDEM-2 и I-CMD-NAV-1.

### Связь с Phase 18

Phase 18 содержит `I-NAV-1..9` в M0 (BC-18-NAV Navigation Protocol) — это инварианты
пространственной навигации в Spatial Index, не связаны с `switch-phase`. Путаница
имён возможна — при работе с Phase 18 различать контекст.

---

## 9. Out of Scope

| Item | Причина |
|------|---------|
| `activate-phase` idempotency | Правильно идемпотентна — Phase lifecycle mutation |
| EventLog compaction/dedup | Отдельная задача, не связана |
| Switch-phase history UI | Phase N+2 |
| `--force` флаг для override | Не нужен — switch-phase уже non-idempotent |
