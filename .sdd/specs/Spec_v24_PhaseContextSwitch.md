# Spec_PhaseContextSwitch — Phase Lifecycle vs Context Navigation

Status: ACTIVE
Baseline: Spec_v18_SpatialIndex.md

---

## 0. Goal

Phase 18 выявила фундаментальный дефект модели: `activate-phase` использовался для
возврата к ранее созданной фазе (18 после 23). Это нарушает event sourcing — история
перестаёт быть историей — и вызывает ERROR-шум при каждом replay.

Корень проблемы: система не разделяет два разных понятия:

```
lifecycle   := создание новой фазы (PhaseStarted + PhaseInitialized, immutable)
context     := указатель "где я сейчас работаю" (mutable, navigatable)
```

Без этого разделения невозможно реализовать сценарий:

```
activate-phase 23 → switch-phase 18 → implement → switch-phase 23 → activate-phase 24
```

Эта спецификация вводит явное разделение и закрывает все связанные дефекты.

Вторичная находка: SDDState с flat fields не может поддерживать multi-phase context
switching без per-phase snapshots. BC-PC-9 вводит `FrozenPhaseSnapshot` и
`phases_snapshots` — это необратимый архитектурный переход к multi-phase state machine.
Дальнейшая логика системы будет phase-scoped; инварианты I-PHASE-SNAPSHOT-* обязательны
для стабильности.

---

## 1. Диагностика дефектов

### D-1 — Мёртвый гард activate-phase

`check_phase_activation_guard` в `guards/phase.py:144` определён, но нигде не вызывается.
`_build_spec_guards` добавляет `make_phase_guard` только при `requires_active_phase=True`,
а `activate-phase` имеет `requires_active_phase=False`. Защита от регрессии отсутствует.

### D-2 — Асимметрия reducer

`PhaseStarted` при регрессии: `logging.error(...)` + skip (не авторитет).
`PhaseInitialized` при регрессии: молча применяет `phase_current = phase_id` (авторитет).
Результат: ERROR-шум при каждом replay, хотя состояние корректно устанавливается через
`PhaseInitialized`. Reducer нарушает DDD-3: содержит бизнес-логику интерпретации intent.

### D-3 — Неопределённая семантика rollback

Система не различает «регрессия-ошибка» и «intentional context switch».
Любой `activate-phase N` при `N <= current` молча принимается редьюсером через
`PhaseInitialized`, что делает rollback неявным и неконтролируемым.

### D-4 — Двойная авторитетность PhaseStarted vs PhaseInitialized

`PhaseStarted(phase_id > phase_current)` в реальном reducer (`reducer.py:293-300`)
мутирует `phase_current`, `phase_status`, `plan_status`, `tasks_total`, `tasks_completed`.
`PhaseInitialized` делает то же самое. Оба события изменяют одни поля — replay
перестаёт быть детерминированным при перестановке событий. Нарушает I-1.

Фикс: PhaseStarted = чистый сигнал, НОЛЬ мутаций. I-PHASE-AUTH-1 — формальный инвариант.

### D-5 — Single-phase SDDState несовместим с context switching

SDDState имеет flat fields (`tasks_completed`, `plan_version`, etc.). При
`PhaseInitialized(23)` reducer сбрасывает `tasks_completed = 0`, уничтожая счётчик
фазы 18. `PhaseContextSwitched(18)` не может восстановить контекст — нет источника.

Replay sequence:
```
PhaseInitialized(18)   → tasks_completed=0
TaskImplemented(T-1801) → tasks_completed=1
PhaseInitialized(23)   → tasks_completed=0   ← RESET, фаза 18 потеряна
TaskImplemented(T-2301) → tasks_completed=1  (фаза 23)
PhaseContextSwitched(18) → phase_current=18, tasks_completed=1  ← НЕВЕРНО
```

Фикс: BC-PC-9 — `FrozenPhaseSnapshot` + `phases_snapshots` в SDDState.

### D-6 — phase_status lifecycle immutability нарушена при context switch

`PhaseContextSwitched` с `phase_status = "ACTIVE"` воскрешает COMPLETE фазы.
Lifecycle immutable нарушен. Фикс: restoring snapshot value, не forced ACTIVE.

---

## 2. Scope

### In-Scope

- **BC-PC-0: Reducer hotfix** — `PhaseStarted` в ЛЮБОЙ ветке (< current, == current,
  > current): НОЛЬ мутаций состояния, только `logging.debug(...)`. Добавить code comment
  `# DO NOT ADD LOGIC HERE — I-PHASE-AUTH-1, I-PHASE-STARTED-1`.
  ERROR → DEBUG для regression case.

- **BC-PC-1: PhaseContextSwitched event** — новый event type в `core/events.py`.
  ДОЛЖЕН быть добавлен одновременно в `V1_L1_EVENT_TYPES` И в
  `EventReducer._EVENT_SCHEMA` (C-1 constraint: import-time assert в `reducer.py:131`).

- **BC-PC-2: phases_known + phases_snapshots в SDDState** — два новых поля:
  - `phases_known: frozenset[int]` — строится из `PhaseInitialized.phase_id` при replay
  - `phases_snapshots: tuple[FrozenPhaseSnapshot, ...]` — per-phase снапшоты состояния;
    tuple для hashability (frozen dataclass constraint); lookup: `{s.phase_id: s for s in ...}`
  - `REDUCER_VERSION: ClassVar[int] = 2` — bump; несовпадение версий → rebuild from
    EventLog, игнорировать YAML-кэш
  - `yaml_state.py` (`read_state`/`write_state`) — поддержка новых полей в State_index.yaml

- **BC-PC-3: switch-phase command** — `commands/switch_phase.py` + регистрация в REGISTRY.
  No-op guard: если `phase_id == state.phase_current` → `MissingContext`.

- **BC-PC-4: ActivatePhaseGuard** — `domain/guards/activate_phase_guard.py`;
  `phase_id == current + 1`. Сообщение об ошибке ДОЛЖНО включать:
  `"Use 'sdd switch-phase N' to return to a previously activated phase."`.

- **BC-PC-5: SwitchPhaseGuard** — `domain/guards/switch_phase_guard.py`;
  `phase_id ∈ phases_known` AND `phase_id != phase_current`.

- **BC-PC-6: Invariants in CLAUDE.md §INV** — обновить I-PHASE-SEQ-1; добавить
  I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-CONTEXT-1..4, I-PHASE-LIFECYCLE-1..2,
  I-PHASE-REDUCER-1, I-PHASES-KNOWN-1..2, I-PHASE-SNAPSHOT-1..4.

- **BC-PC-7: Tests** — unit + integration, 100% coverage BC-PC-1..5; тест на projection
  coherence (I-PHASE-SNAPSHOT-2); тест REDUCER_VERSION mismatch.

- **BC-PC-8: Dead code removal** — удалить `check_phase_activation_guard` из `guards/phase.py`.

- **BC-PC-9: Per-phase snapshots** — `FrozenPhaseSnapshot` frozen dataclass;
  reducer snapshot create/update/restore logic; yaml_state serialisation.

### Out of Scope

- Отображение history переключений контекста — Phase N+2
- `--force` флаг для explicit lifecycle rollback — Phase N+3 (если потребуется)
- Soft switch-phase (не пишет в EventLog) — никогда (нарушает I-1)
- Snapshot compression или compaction — вне данной фазы

---

## 3. Архитектурная модель

### Разделение lifecycle / context

```
lifecycle events  (append to EventLog, immutable):
  PhaseStarted(phase_id)        ← чистый сигнал; NOT authoritative; ZERO state mutations
  PhaseInitialized(phase_id)    ← единственная authoritative точка фазы (I-PHASE-AUTH-1)

navigation events (append to EventLog, replay-safe):
  PhaseContextSwitched(phase_id) ← изменение рабочего контекста; не lifecycle
```

Ключевое свойство `PhaseContextSwitched`: это **write event** (пишется в EventLog,
участвует в replay). Это осознанное решение: state = reduce(events) должен быть
воспроизводим без YAML. История переключений контекста — часть system log.

### Команды (финальная модель)

| Команда | Событие | Guard | Правило |
|---|---|---|---|
| `activate-phase N` | `PhaseStarted` + `PhaseInitialized` | `ActivatePhaseGuard` | `N == current + 1` |
| `switch-phase N` | `PhaseContextSwitched` | `SwitchPhaseGuard` | `N ∈ phases_known`, `N != current` |

### PhaseContextSwitchedEvent dataclass (новый, в `core/events.py`)

```python
@dataclass(frozen=True)
class PhaseContextSwitchedEvent(DomainEvent):
    """BC-PC-1: navigation event, not lifecycle.
    I-PHASE-CONTEXT-1: switch-phase MUST emit this and ONLY this event.
    """
    EVENT_TYPE: ClassVar[str] = "PhaseContextSwitched"
    phase_id:   int
    actor:      str       # "human"
    timestamp:  str       # ISO-8601
```

Регистрация (обе строки атомарны — C-1 constraint):

```python
# core/events.py
V1_L1_EVENT_TYPES = frozenset({
    ...
    "PhaseContextSwitched",   # BC-PC-1: navigation event (not lifecycle)
})

# domain/state/reducer.py — EventReducer._EVENT_SCHEMA
"PhaseContextSwitched": frozenset({"phase_id", "actor", "timestamp"}),
```

### FrozenPhaseSnapshot dataclass (новый, в `reducer.py`)

```python
@dataclass(frozen=True)
class FrozenPhaseSnapshot:
    """Immutable per-phase state snapshot.

    Created by PhaseInitialized. Updated (via replace) by task events matching phase_id.
    Restored (not mutated) by PhaseContextSwitched.

    I-PHASE-SNAPSHOT-3: PhaseInitialized ALWAYS overwrites snapshot for phase_id.
    I-PHASE-SNAPSHOT-1: phases_snapshots MUST contain exactly one entry per phase in phases_known.
    """
    phase_id:          int
    phase_status:      str    # "PLANNED" | "ACTIVE" | "COMPLETE"
    plan_status:       str    # "PLANNED" | "ACTIVE" | "COMPLETE"
    tasks_total:       int
    tasks_completed:   int
    tasks_done_ids:    tuple[str, ...]
    plan_version:      int
    tasks_version:     int
    invariants_status: str    # "UNKNOWN" | "PASS" | "FAIL"
    tests_status:      str    # "UNKNOWN" | "PASS" | "FAIL"
```

### SDDState расширение

```python
@dataclass(frozen=True)
class SDDState:
    # --- Derived fields ---
    phase_current:       int
    plan_version:        int
    tasks_version:       int
    tasks_total:         int
    tasks_completed:     int
    tasks_done_ids:      tuple[str, ...]
    invariants_status:   str
    tests_status:        str
    last_updated:        str
    schema_version:      int
    snapshot_event_id:   int | None

    # --- Human-managed fields (NOT in state_hash) ---
    phase_status:        str
    plan_status:         str

    # --- Multi-phase fields (BC-PC-2, BC-PC-9) ---
    phases_known:     frozenset[int] = field(default_factory=frozenset)
    phases_snapshots: tuple[FrozenPhaseSnapshot, ...] = field(default_factory=tuple)

    REDUCER_VERSION: ClassVar[int] = 2  # bump: adds phases_known + phases_snapshots
    _HUMAN_FIELDS: ClassVar[frozenset[str]] = frozenset({"phase_status", "plan_status", "state_hash"})
    # phases_known и phases_snapshots — derived fields; включены в state_hash.
```

**REDUCER_VERSION mismatch**: если загруженный state имеет `REDUCER_VERSION < 2`, то
`get_current_state()` ДОЛЖЕН сбросить `snapshot_event_id = None` и выполнить full replay
с seq=0, игнорируя YAML-кэш.

### Reducer — полный dispatcher (замена §3 в спеке)

```python
# --- Аккумуляторы (добавить в начало _fold) ---
phases_known_set: set[int] = set(base.phases_known)
phases_snapshots_map: dict[int, FrozenPhaseSnapshot] = {
    s.phase_id: s for s in base.phases_snapshots
}

# --- PhaseInitialized ---
# I-PHASE-AUTH-1: ЕДИНСТВЕННАЯ авторитетная точка для phase_current.
# I-PHASE-SNAPSHOT-3: ВСЕГДА перезаписывает snapshot для phase_id.
if event_type == "PhaseInitialized":
    raw_phase_id = event.get("phase_id", phase_current)
    if isinstance(raw_phase_id, int):
        phase_current = raw_phase_id
        phases_known_set.add(raw_phase_id)
    raw_tasks_total = event.get("tasks_total", tasks_total)
    if isinstance(raw_tasks_total, int):
        tasks_total = raw_tasks_total
    raw_plan_version = event.get("plan_version", plan_version)
    if isinstance(raw_plan_version, int):
        plan_version = raw_plan_version
    tasks_version = plan_version
    phase_status = "ACTIVE"
    plan_status = "ACTIVE"
    tasks_completed = 0
    tasks_done_ids_set = set()
    invariants_status = "UNKNOWN"
    tests_status = "UNKNOWN"
    if isinstance(raw_phase_id, int):
        # I-PHASE-SNAPSHOT-3: unconditional overwrite (re-activation resets snapshot)
        phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
            phase_id=raw_phase_id,
            phase_status="ACTIVE",
            plan_status="ACTIVE",
            tasks_total=tasks_total,
            tasks_completed=0,
            tasks_done_ids=(),
            plan_version=plan_version,
            tasks_version=tasks_version,
            invariants_status="UNKNOWN",
            tests_status="UNKNOWN",
        )

# --- PhaseStarted ---
# I-PHASE-AUTH-1 + I-PHASE-STARTED-1: ЧИСТЫЙ СИГНАЛ. НОЛЬ мутаций состояния.
# DO NOT ADD LOGIC HERE — PhaseInitialized is the only authoritative lifecycle event.
elif event_type == "PhaseStarted":
    raw_phase_id = event.get("phase_id")
    if isinstance(raw_phase_id, int):
        if raw_phase_id < phase_current:
            logging.debug(
                "EventReducer: PhaseStarted phase_id=%r < phase_current=%r"
                " — regression replay, PhaseInitialized is authoritative"
                " (I-PHASE-AUTH-1, I-PHASE-STARTED-1)",
                raw_phase_id, phase_current,
            )
        elif raw_phase_id == phase_current:
            logging.debug(
                "EventReducer: PhaseStarted phase_id=%r == phase_current — normal replay, skip",
                raw_phase_id,
            )
        else:
            logging.debug(
                "EventReducer: PhaseStarted phase_id=%r > phase_current=%r"
                " — PhaseInitialized will follow and is authoritative (I-PHASE-AUTH-1)",
                raw_phase_id, phase_current,
            )
    # NO state mutations in any branch.

# --- PhaseContextSwitched (новый — BC-PC-1) ---
# I-PHASE-LIFECYCLE-1: phase_status берётся из snapshot, НЕ forced to "ACTIVE".
# I-PHASE-SNAPSHOT-4: отсутствие snapshot = Inconsistency (guard должен был предотвратить).
elif event_type == "PhaseContextSwitched":
    raw_phase_id = event.get("phase_id")
    if isinstance(raw_phase_id, int):
        if raw_phase_id not in phases_snapshots_map:
            # I-PHASE-SNAPSHOT-4: guard failure or corrupted event — raise, не skip
            raise Inconsistency(
                f"I-PHASE-SNAPSHOT-4: PhaseContextSwitched phase_id={raw_phase_id}"
                f" has no snapshot; phases_known={sorted(phases_known_set)}."
                f" EventLog may be corrupted."
            )
        snap = phases_snapshots_map[raw_phase_id]
        phase_current       = snap.phase_id
        phase_status        = snap.phase_status        # preserves COMPLETE (I-PHASE-LIFECYCLE-1)
        plan_status         = snap.plan_status
        tasks_total         = snap.tasks_total
        tasks_completed     = snap.tasks_completed
        tasks_done_ids_set  = set(snap.tasks_done_ids)
        plan_version        = snap.plan_version
        tasks_version       = snap.tasks_version
        invariants_status   = snap.invariants_status
        tests_status        = snap.tests_status
        # I-PHASES-KNOWN-1: PhaseContextSwitched MUST NOT modify phases_known.

# --- TaskImplemented ---
elif event_type == "TaskImplemented":
    task_id      = event.get("task_id")
    raw_phase_id = event.get("phase_id")
    if isinstance(task_id, str) and task_id not in tasks_done_ids_set:
        tasks_done_ids_set.add(task_id)
        tasks_completed += 1
    # Обновляем snapshot для phase_id из события (ключевой фикс D-5).
    # Событие может относиться к phase != phase_current при replay через context switch.
    if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
        snap = phases_snapshots_map[raw_phase_id]
        if isinstance(task_id, str) and task_id not in snap.tasks_done_ids:
            new_done = tuple(sorted(set(snap.tasks_done_ids) | {task_id}))
            phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                phase_id=raw_phase_id,
                phase_status=snap.phase_status,
                plan_status=snap.plan_status,
                tasks_total=snap.tasks_total,
                tasks_completed=snap.tasks_completed + 1,
                tasks_done_ids=new_done,
                plan_version=snap.plan_version,
                tasks_version=snap.tasks_version,
                invariants_status=snap.invariants_status,
                tests_status=snap.tests_status,
            )

# --- TaskValidated ---
elif event_type == "TaskValidated":
    result       = event.get("result", "")
    raw_phase_id = event.get("phase_id")
    if result in ("PASS", "FAIL"):
        tests_status      = result
        invariants_status = result
    if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
        snap = phases_snapshots_map[raw_phase_id]
        if result in ("PASS", "FAIL"):
            phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
                phase_id=raw_phase_id,
                phase_status=snap.phase_status,
                plan_status=snap.plan_status,
                tasks_total=snap.tasks_total,
                tasks_completed=snap.tasks_completed,
                tasks_done_ids=snap.tasks_done_ids,
                plan_version=snap.plan_version,
                tasks_version=snap.tasks_version,
                invariants_status=result,
                tests_status=result,
            )

# --- PhaseCompleted ---
elif event_type == "PhaseCompleted":
    # I-PHASE-LIFECYCLE-2: terminal transition; COMPLETE не перезаписывается ничем,
    # кроме нового PhaseInitialized для той же фазы.
    raw_phase_id = event.get("phase_id")
    phase_status = "COMPLETE"
    plan_status  = "COMPLETE"
    if isinstance(raw_phase_id, int) and raw_phase_id in phases_snapshots_map:
        snap = phases_snapshots_map[raw_phase_id]
        phases_snapshots_map[raw_phase_id] = FrozenPhaseSnapshot(
            phase_id=raw_phase_id,
            phase_status="COMPLETE",
            plan_status="COMPLETE",
            tasks_total=snap.tasks_total,
            tasks_completed=snap.tasks_completed,
            tasks_done_ids=snap.tasks_done_ids,
            plan_version=snap.plan_version,
            tasks_version=snap.tasks_version,
            invariants_status=snap.invariants_status,
            tests_status=snap.tests_status,
        )

# --- PhaseActivated (legacy — I-REDUCER-LEGACY-1) ---
elif event_type == "PhaseActivated":
    phase_status = "ACTIVE"

# --- TaskSetDefined ---
elif event_type == "TaskSetDefined":
    raw_phase_id    = event.get("phase_id")
    raw_tasks_total = event.get("tasks_total")
    if isinstance(raw_phase_id, int) and raw_phase_id != phase_current:
        logging.warning(
            "EventReducer: TaskSetDefined phase_id=%r != phase_current=%r — skipping",
            raw_phase_id, phase_current,
        )
    elif isinstance(raw_tasks_total, int):
        tasks_total = raw_tasks_total
```

### SDDState construction (конец _fold)

```python
state = SDDState(
    phase_current=phase_current,
    plan_version=plan_version,
    tasks_version=tasks_version,
    tasks_total=tasks_total,
    tasks_completed=tasks_completed,
    tasks_done_ids=tuple(sorted(tasks_done_ids_set)),
    invariants_status=invariants_status,
    tests_status=tests_status,
    last_updated=last_updated,
    schema_version=schema_version,
    snapshot_event_id=snapshot_event_id,
    phase_status=phase_status,
    plan_status=plan_status,
    phases_known=frozenset(phases_known_set),
    phases_snapshots=tuple(phases_snapshots_map.values()),
)
# I-PHASE-SNAPSHOT-2: assert projection coherence at end of full rebuild
# (in debug/test mode only — не в hot path)
assert _check_snapshot_coherence(state), "I-PHASE-SNAPSHOT-2 violated"
```

```python
def _check_snapshot_coherence(state: SDDState) -> bool:
    """I-PHASE-SNAPSHOT-2: flat state MUST equal phases_snapshots[phase_current]."""
    snap_map = {s.phase_id: s for s in state.phases_snapshots}
    snap = snap_map.get(state.phase_current)
    if snap is None:
        return len(state.phases_snapshots) == 0  # empty state is coherent
    return (
        state.phase_status      == snap.phase_status
        and state.plan_status   == snap.plan_status
        and state.tasks_total   == snap.tasks_total
        and state.tasks_completed == snap.tasks_completed
        and set(state.tasks_done_ids) == set(snap.tasks_done_ids)
        and state.plan_version  == snap.plan_version
        and state.tasks_version == snap.tasks_version
        and state.invariants_status == snap.invariants_status
        and state.tests_status  == snap.tests_status
    )
```

**Производительность**: `_check_snapshot_coherence` вызывается только при
`DEBUG` сборке или в тестах. В production path (full rebuild) можно включить через
`SDD_DEBUG_INVARIANTS=1` env var.

### ActivatePhaseGuard

```python
# domain/guards/activate_phase_guard.py
def make_activate_phase_guard(phase_id: int) -> Guard:
    """I-PHASE-SEQ-1: phase_id MUST equal current + 1."""
    def guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        current = ctx.state.phase_current
        if phase_id != current + 1:
            raise Inconsistency(
                f"I-PHASE-SEQ-1: activate-phase requires phase_id == current+1;"
                f" got phase_id={phase_id}, current={current}."
                f" Use 'sdd switch-phase {phase_id}' to return to a previously activated phase."
            )
        return GuardResult(ALLOW, "ActivatePhaseGuard", "I-PHASE-SEQ-1 pass", None, None), []
    return guard
```

### SwitchPhaseGuard

```python
# domain/guards/switch_phase_guard.py
def make_switch_phase_guard(phase_id: int) -> Guard:
    """I-PHASE-CONTEXT-2,3,4."""
    def guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        known   = ctx.state.phases_known
        current = ctx.state.phase_current
        if not known:
            raise MissingContext(
                "I-PHASE-CONTEXT-3: switch-phase requires at least one activated phase;"
                " phases_known is empty"
            )
        if phase_id not in known:
            raise MissingContext(
                f"I-PHASE-CONTEXT-2: phase {phase_id} not in phases_known={sorted(known)}"
            )
        if phase_id == current:
            raise MissingContext(
                f"I-PHASE-CONTEXT-4: phase {phase_id} is already the current context;"
                f" no switch needed"
            )
        return GuardResult(ALLOW, "SwitchPhaseGuard", "I-PHASE-CONTEXT-2,3,4 pass", None, None), []
    return guard
```

---

## 4. Invariants

### Новые и обновлённые инварианты (добавить в CLAUDE.md §INV)

| ID | Statement | Verification |
|----|-----------|-------------|
| I-PHASE-SEQ-1 | `activate-phase` MUST satisfy `phase_id == current + 1`; no skipping, no regression | `ActivatePhaseGuard`; test_activate_phase_guard.py |
| **I-PHASE-AUTH-1** | ONLY `PhaseInitialized` and `PhaseContextSwitched` MAY mutate `phase_current`. `PhaseStarted` MUST NOT mutate any state field. | reducer._fold; test_reducer_phase_auth.py |
| **I-PHASE-STARTED-1** | `PhaseStarted` MUST NOT be used by any reducer logic or guard logic. It is informational only. Code: `# DO NOT ADD LOGIC HERE`. | code review; test_reducer_phase_auth.py |
| I-PHASE-CONTEXT-1 | `switch-phase` MUST emit `PhaseContextSwitched`; MUST NOT emit `PhaseStarted` or `PhaseInitialized` | handler contract; test_switch_phase.py |
| I-PHASE-CONTEXT-2 | `switch-phase` MUST target a phase in `phases_known` | `SwitchPhaseGuard`; test_switch_phase_guard.py |
| I-PHASE-CONTEXT-3 | `switch-phase` MUST fail if `phases_known` is empty | `SwitchPhaseGuard`; test_switch_phase_guard.py |
| **I-PHASE-CONTEXT-4** | `switch-phase N` where `N == phase_current` MUST be rejected (no-op guard) | `SwitchPhaseGuard`; test_switch_phase_guard.py |
| **I-PHASE-LIFECYCLE-1** | `PhaseContextSwitched` MUST NOT override `phase_status`; MUST restore stored snapshot value (preserves COMPLETE) | reducer._fold; test_reducer_phase_context.py |
| **I-PHASE-LIFECYCLE-2** | `PhaseCompleted` is terminal: `phase_status = "COMPLETE"` in snapshot MUST NOT be overwritten by any event except a new `PhaseInitialized` for the same phase | reducer._fold; test_reducer_phase_lifecycle.py |
| I-PHASE-REDUCER-1 | `PhaseStarted` during replay: DEBUG log only; no state change in any branch | test_reducer_phase_auth.py |
| I-PHASES-KNOWN-1 | `SDDState.phases_known` MUST be `frozenset[int]`; updated ONLY on `PhaseInitialized` replay; `PhaseContextSwitched` MUST NOT modify it | test_reducer_phases_known.py |
| **I-PHASES-KNOWN-2** | `phases_known == {s.phase_id for s in phases_snapshots}` at all times | test_reducer_snapshots.py; _check_snapshot_coherence |
| **I-PHASE-SNAPSHOT-1** | `phases_snapshots` MUST contain exactly one entry per `phase_id ∈ phases_known`; updated by all phase-scoped events matching that `phase_id` | test_reducer_snapshots.py |
| **I-PHASE-SNAPSHOT-2** | Flat state MUST be a projection of `phases_snapshots[phase_current]` after any `_fold` | `_check_snapshot_coherence`; test_reducer_snapshots.py |
| **I-PHASE-SNAPSHOT-3** | `PhaseInitialized` MUST overwrite (not append) snapshot for `phase_id`; unconditional | reducer._fold; test_reducer_snapshots.py |
| **I-PHASE-SNAPSHOT-4** | `PhaseContextSwitched` MUST have a corresponding snapshot; absence MUST raise `Inconsistency` (guard failure or corrupted EventLog) | reducer._fold; test_reducer_phase_context.py |

---

## 5. Pre/Post Conditions

### M0 — Reducer hotfix (BC-PC-0)

**Pre:** Phase 18 ACTIVE, `sdd show-state` показывает ERROR в stderr

**Post:**
- `PhaseStarted` (любой `phase_id`) → ноль мутаций; только DEBUG log
- `PhaseStarted` regression → DEBUG, не ERROR
- Код содержит `# DO NOT ADD LOGIC HERE — I-PHASE-AUTH-1, I-PHASE-STARTED-1`
- `sdd complete T-NNN` не печатает ERROR в stderr при нормальной работе

### M1 — PhaseContextSwitched + SDDState multi-phase fields (BC-PC-1,2,9)

**Pre:** M0 COMPLETE

**Post:**
- `PhaseContextSwitched` зарегистрирован в `V1_L1_EVENT_TYPES` И в `EventReducer._EVENT_SCHEMA`
  (C-1 constraint: import-time assert не падает)
- `FrozenPhaseSnapshot` frozen dataclass присутствует в `reducer.py`
- `SDDState` содержит `phases_known: frozenset[int]` и `phases_snapshots: tuple[FrozenPhaseSnapshot, ...]`
- `REDUCER_VERSION = 2`; несовпадение → full rebuild от seq=0
- Reducer корректно строит `phases_snapshots` при полном replay:
  - `PhaseInitialized(N)` → создаёт/перезаписывает `snapshots_map[N]` (I-PHASE-SNAPSHOT-3)
  - `TaskImplemented(task_id, phase_id=N)` → обновляет `snapshots_map[N].tasks_completed`
  - `PhaseCompleted(phase_id=N)` → `snapshots_map[N].phase_status = "COMPLETE"`
  - `PhaseContextSwitched(N)` → восстанавливает все flat fields из `snapshots_map[N]`
- `PhaseContextSwitched` при `phase_id not in snapshots_map` → raises `Inconsistency` (I-PHASE-SNAPSHOT-4)
- `_check_snapshot_coherence` проходит после каждого `_fold` (I-PHASE-SNAPSHOT-2)
- `yaml_state.py` read/write поддерживает `phases_known` и `phases_snapshots`
- Replay determinism: `reduce(events) == reduce(events)` для одного EventLog

### M2 — switch-phase command + guards (BC-PC-3..5)

**Pre:** M1 COMPLETE

**Post:**
- `sdd switch-phase 18` (при `phases_known={18,23}`) → `PhaseContextSwitched(18)` в EventLog;
  `phase_current=18`; `tasks_completed` = phase 18 count из истории; `plan_version=18`;
  `tasks_version=18`
- `sdd switch-phase 18` при `phase_current=18` → `MissingContext` (I-PHASE-CONTEXT-4)
- `sdd switch-phase 999` → `MissingContext` (I-PHASE-CONTEXT-2)
- `sdd switch-phase 18` при пустом EventLog → `MissingContext` (I-PHASE-CONTEXT-3)
- `sdd activate-phase 19` при `phase_current=18` → exit 0
- `sdd activate-phase 20` при `phase_current=18` → `Inconsistency` (I-PHASE-SEQ-1);
  сообщение содержит `"switch-phase 20"`
- `sdd switch-phase 18` при phase 18 COMPLETE → `phase_current=18`, `phase_status="COMPLETE"` (I-PHASE-LIFECYCLE-1)
- `sdd switch-phase 23` после `switch-phase 18` → `tasks_completed` = phase 23's count (D-5 fix)

### M3 — Cleanup + CLAUDE.md §INV (BC-PC-6,8)

**Pre:** M2 COMPLETE

**Post:**
- `check_phase_activation_guard` удалён из `guards/phase.py`
- CLAUDE.md §INV содержит все инварианты из таблицы §4 (16 строк)
- State_index.yaml schema задокументирована с полями `phases_known` и `phases_snapshots`

---

## 6. Test Matrix

| # | File | Test Cases | Covers |
|---|------|------------|--------|
| 1 | `tests/unit/domain/state/test_reducer_phase_auth.py` | PhaseStarted(< current) → ноль мутаций + DEBUG; PhaseStarted(> current) → ноль мутаций + DEBUG; PhaseStarted(== current) → ноль мутаций + DEBUG; I-PHASE-STARTED-1: no logic in any branch | I-PHASE-AUTH-1, I-PHASE-STARTED-1, I-PHASE-REDUCER-1 |
| 2 | `tests/unit/domain/state/test_reducer_phase_context.py` | PhaseContextSwitched restores ALL fields from snapshot; phase_status COMPLETE preserved after switch (not forced ACTIVE); phases_known unchanged; missing phase_id → Inconsistency (I-PHASE-SNAPSHOT-4) | I-PHASE-LIFECYCLE-1, I-PHASES-KNOWN-1, I-PHASE-SNAPSHOT-4 |
| 3 | `tests/unit/domain/state/test_reducer_snapshots.py` | PhaseInitialized creates snapshot; PhaseInitialized twice → overwrite (I-PHASE-SNAPSHOT-3); TaskImplemented updates correct snapshot by phase_id (cross-phase: events for phase 18 while phase_current=23 update snapshots[18]); PhaseCompleted marks snapshot COMPLETE; context switch restores correct counters; I-PHASES-KNOWN-2: phases_known == {s.phase_id for s in snapshots}; I-PHASE-SNAPSHOT-2: coherence assert | I-PHASE-SNAPSHOT-1..3, I-PHASES-KNOWN-2, D-5 fix |
| 4 | `tests/unit/domain/state/test_reducer_phases_known.py` | phases_known grows only on PhaseInitialized; PhaseContextSwitched does NOT add to phases_known | I-PHASES-KNOWN-1 |
| 5 | `tests/unit/guards/test_activate_phase_guard.py` | phase_id == current+1 → ALLOW; phase_id > current+1 → Inconsistency with "switch-phase" in message; phase_id <= current → Inconsistency with "switch-phase" in message | I-PHASE-SEQ-1, BUG-6 fix |
| 6 | `tests/unit/guards/test_switch_phase_guard.py` | phase in known + != current → ALLOW; phase not in known → MissingContext; empty phases_known → MissingContext; phase == current → MissingContext | I-PHASE-CONTEXT-2,3,4 |
| 7 | `tests/unit/commands/test_switch_phase.py` | handler emits PhaseContextSwitched only; NOT PhaseStarted/PhaseInitialized; payload includes phase_id, actor, timestamp | I-PHASE-CONTEXT-1 |
| 8 | `tests/integration/test_switch_phase_flow.py` | Full scenario: activate(18)→implement×3→activate(23)→implement×2→switch(18)→assert(tasks_completed=3, plan_version=18, phase_status=ACTIVE)→switch(23)→assert(tasks_completed=2)→complete(23)→switch(23_COMPLETE)→assert(phase_status=COMPLETE); replay twice → identical state (determinism) | D-5, D-6 fix; end-to-end |
| 9 | `tests/unit/domain/state/test_reducer_c1.py` | C-1 constraint: `V1_L1_EVENT_TYPES == _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys())` после добавления PhaseContextSwitched | C-1 (reducer.py import-time assert) |
| 10 | `tests/unit/domain/state/test_yaml_state_snapshots.py` | write_state + read_state round-trip с phases_known и phases_snapshots; REDUCER_VERSION=2 в output; mismatch версии → rebuild flag | yaml_state.py; REDUCER_VERSION mismatch |
| 11 | `tests/unit/domain/state/test_reducer_phase_lifecycle.py` | PhaseCompleted → snapshot.phase_status=COMPLETE; последующий TaskImplemented не перезаписывает COMPLETE; только новый PhaseInitialized может сбросить | I-PHASE-LIFECYCLE-2 |

---

## 7. Migration Note

Существующий event log содержит `PhaseInitialized(18)` на seq 22638 после фаз 22-23.
Это исторический артефакт: `activate-phase 18` был запущен при `phase_current=23`.

После внедрения спеки:
- Replay корректен: `PhaseInitialized(18)` добавляет 18 в `phases_known` и устанавливает
  `phase_current=18`; snapshot для фазы 18 создаётся/перезаписывается (I-PHASE-SNAPSHOT-3)
- `PhaseStarted(18)` на seq 22637: DEBUG-лог, ноль мутаций (I-PHASE-AUTH-1)
- Никаких компенсирующих событий не нужно; EventLog остаётся immutable (I-GEB-2)
- Будущие возвраты к ранее созданным фазам: `sdd switch-phase N` (не `activate-phase`)

### Snapshot bootstrap для существующего EventLog

При первом replay с `REDUCER_VERSION=2` `phases_snapshots` строится корректно из
всех `PhaseInitialized` и task событий в порядке seq. Миграционный скрипт не нужен.

### REDUCER_VERSION mismatch

Если загруженный `SDDState` имеет `REDUCER_VERSION < 2` (YAML-кэш от старого reducer):
- `get_current_state()` ДОЛЖЕН сбросить `snapshot_event_id = None`
- Выполнить full replay с seq=0 (ignore cache)
- Написать обновлённый YAML с `REDUCER_VERSION=2`

`rebuild_state()` уже использует `RebuildMode.STRICT` (full replay). Mismatch rule —
safety net для future incremental replay paths.

### TaskSet file loading после context switch

`rebuild_taskset()` использует `state.phase_current` → `taskset_file(phase_current)`.
После `PhaseContextSwitched(18)`: `phase_current=18`, `plan_version=18` (из snapshot) →
`taskset_file(18)` = `TaskSet_v18.md`. Изменений в `projections.py` не требуется.

---

## 8. Acceptance Criteria

| AC | Проверяет |
|----|-----------|
| AC-1 | `sdd complete T-NNN` → no ERROR in stderr при нормальной работе (M0) |
| AC-2 | `sdd switch-phase 18` (phases_known={15,17,18,22,23}) → exit 0, `phase_current=18`, `plan_version=18`, `tasks_completed=<phase18 count>` (M2) |
| AC-3 | `sdd switch-phase 999` → exit 1, `error_type=MissingContext` (M2) |
| AC-4 | `sdd activate-phase 19` при `phase_current=18` → exit 0 (M2) |
| AC-5 | `sdd activate-phase 20` при `phase_current=18` → exit 1, `error_type=Inconsistency`; сообщение содержит `"switch-phase 20"` (BUG-6 fix) |
| AC-6 | `sdd switch-phase 18` при `phase_current==18` → exit 1, `error_type=MissingContext` (BUG-4 fix) |
| AC-7 | Full replay: `reduce(events)` идентичен при двух последовательных вызовах (детерминизм, BUG-1 fix) |
| AC-8 | `sdd switch-phase 18` при COMPLETE phase 18 → `phase_current=18`, `phase_status="COMPLETE"` (не ACTIVE) (BUG-2 fix, I-PHASE-LIFECYCLE-1) |
| AC-9 | После `switch-phase 18` и обратно `switch-phase 23` → `tasks_completed` = phase 23 count (BUG-3 fix) |
| AC-10 | После `switch-phase 18` → `plan_version=18`, `tasks_version=18` (BUG-5 fix) |
| AC-11 | `phases_known == {s.phase_id for s in phases_snapshots}` после любого replay (I-PHASES-KNOWN-2) |
| AC-12 | C-1 assert проходит: import `sdd.domain.state.reducer` не падает (BC-PC-1) |
| AC-13 | `check_phase_activation_guard` отсутствует в codebase (M3, BC-PC-8) |
| AC-14 | `REDUCER_VERSION=2`; `phases_snapshots` сериализованы в State_index.yaml (BC-PC-2) |
| AC-15 | `_check_snapshot_coherence(state)` возвращает True после full rebuild (I-PHASE-SNAPSHOT-2) |
| AC-16 | `PhaseContextSwitched` с `phase_id not in snapshots` при replay → raises `Inconsistency` (I-PHASE-SNAPSHOT-4) |

---

## 9. Implementation Sequencing

Порядок обязателен из-за C-1 import-time assert и dependency chain.

**Step 1 (BC-PC-9 data model)**: Определить `FrozenPhaseSnapshot` в `reducer.py`.
Добавить `phases_known` и `phases_snapshots` в `SDDState`. Bump `REDUCER_VERSION = 2`.
Обновить `_make_empty_state()`.

**Step 2 (BC-PC-1 event)**: Добавить `PhaseContextSwitched` в `V1_L1_EVENT_TYPES`
в `events.py`; добавить `PhaseContextSwitchedEvent` dataclass.

**Step 3 (BC-PC-0 + reducer)**: Добавить `PhaseContextSwitched` в `EventReducer._EVENT_SCHEMA`.
Обновить все handler branches в `_fold` согласно §3. Обновить accumulator block и
SDDState construction. Добавить `_check_snapshot_coherence`. C-1 assert теперь проходит.

**Step 4 (BC-PC-2 yaml_state)**: Обновить `write_state` и `read_state` в `yaml_state.py`
для `phases_known` и `phases_snapshots`. YAML schema: два новых top-level ключа.

**Step 5 (BC-PC-4)**: Реализовать `activate_phase_guard.py` с исправленным сообщением.
Подключить в `_build_spec_guards` для `activate-phase` CommandSpec.

**Step 6 (BC-PC-3 + BC-PC-5)**: Реализовать `switch_phase.py` и `SwitchPhaseGuard`
с no-op check. Зарегистрировать в REGISTRY.

**Step 7 (BC-PC-8)**: Удалить `check_phase_activation_guard` из `guards/phase.py`.

**Step 8 (BC-PC-7 tests)**: Реализовать test files по матрице §6 в порядке: 9→1→4→3→11→2→10→5→6→7→8.

**Step 9 (BC-PC-6)**: Обновить CLAUDE.md §INV — 16 инвариантов из таблицы §4.

### Dependency graph

```
Step 1 → Step 2 → Step 3 → Step 4
                         → Step 5 → Step 6
                         → Step 7
                         → Step 8 (все reducer-тесты требуют Step 3)
         Step 6 ------→ Step 8 (switch_phase тесты требуют Step 6)
         Step 9 (независим, после Step 3)
```

### Критические файлы

- `src/sdd/domain/state/reducer.py` — FrozenPhaseSnapshot, SDDState, _fold, _check_snapshot_coherence
- `src/sdd/core/events.py` — V1_L1_EVENT_TYPES, PhaseContextSwitchedEvent
- `src/sdd/domain/state/yaml_state.py` — read_state/write_state
- `src/sdd/commands/registry.py` — регистрация switch-phase
- `src/sdd/guards/phase.py` — удалить check_phase_activation_guard
- `src/sdd/domain/guards/activate_phase_guard.py` — новый файл
- `src/sdd/domain/guards/switch_phase_guard.py` — новый файл
- `src/sdd/commands/switch_phase.py` — новый файл
