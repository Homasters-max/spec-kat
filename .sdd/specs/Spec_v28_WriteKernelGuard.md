# Spec_v28 — Write Kernel Guard & Event Invalidation

Status: DRAFT — подлежит human approval перед включением в план фазы
Baseline: Spec_v27_CommandIdempotency.md (Phase 27 завершена)
Incident: Phase 27 close, 2026-04-25 — 6 TestEvent записей в production EventLog

---

## 0. Goal

Phase 27 обнажила архитектурную дыру: инвариант `I-KERNEL-WRITE-1` задокументирован,
но **не принуждён**. `assert_in_kernel()` существует в `execution_context.py`, но нигде
не вызывается в `EventStore.append()`. Любой код с доступом к `sdd_append()` и явным
`db_path` может писать напрямую в EventLog — обходя registry, guards, CommandSpec,
idempotency и audit semantics.

Инцидент: LLM во время отладочной сессии выполнил через Bash:

```python
from sdd.infra.event_log import sdd_append
sdd_append('TestEvent', {'x': 1}, db_path='/root/project/.sdd/state/sdd_events.duckdb')
# + цикл for i in range(5): sdd_append('TestEvent', {'x': i}, db_path=...)
```

Результат: 6 невалидных событий в production EventLog (seqs 25970, 25973–25977).
Симптом: `WARNING:root:EventReducer: unknown event_type='TestEvent'` при каждом replay.
Причина симптома: reducer корректно варнит о неизвестных типах, но не может отличить
«неизвестный из будущей версии» от «невалидный мусор».

Данная фаза:
1. **Принуждает** `I-KERNEL-WRITE-1` на двух уровнях: `EventStore.append()` (kernel guard)
   и `sdd_append()` (production DB path guard).
2. **Вводит** `EventInvalidated` — event-sourcing корректный способ нейтрализовать
   невалидные события без нарушения replay детерминизма.
3. **Закрывает** инцидент: 6 TestEvent записей нейтрализованы через `invalidate-event`.

---

## 1. Scope

### In-Scope

- **BC-WG-1: `EventInvalidated`** — новый domain event; регистрация в `V1_L1_EVENT_TYPES`
- **BC-WG-2: `EventStore.replay()` pre-filter** — pre-scan с индексом + per-instance кэш;
  фильтрует target_seqs до передачи reducer-у
- **BC-WG-3: `EventStore.append()` kernel guard** — `assert_in_kernel` +
  `allow_outside_kernel: Literal["bootstrap", "test"] | None`; кэш сбрасывается на append
- **BC-WG-4: `sdd_append()` production-path guard** — запрет записи в production DB вне
  kernel context (второй уровень защиты; закрывает обход BC-WG-3)
- **BC-WG-5: `invalidate-event` REGISTRY command** — единственный путь эмиссии
  `EventInvalidated`; реальная идемпотентность через handler pre-check; запрет на
  инвалидацию state-mutating событий
- **BC-WG-6: Incident backfill** — emit `EventInvalidated` для 6 TestEvent seqs через
  `invalidate-event`; финальный тест: `sdd show-state` без единого WARNING

### Out of Scope

| Item | Причина |
|------|---------|
| Ретроспективная компакция EventLog | Отдельная задача; replay корректен без неё |
| UI/reporting для невалидных событий | Phase N+1 |
| Automated detection via audit log scan | I-DB-WRITE-2 + `sdd_append` guard достаточны |

---

## 2. Architecture / BCs

### BC-WG-1: `EventInvalidated` domain event

```
src/sdd/core/events.py
  EventInvalidatedEvent  # новый frozen dataclass
```

```python
@dataclass(frozen=True)
class EventInvalidatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "EventInvalidated"
    target_seq:           int   # seq невалидного события в EventLog
    reason:               str   # ≤200 chars: human-readable причина
    invalidated_by_phase: int   # phase_current в момент эмиссии (аудит)
```

Регистрируется через `register_l1_event_type("EventInvalidated", handler=None)` при
импорте модуля → попадает в `_KNOWN_NO_HANDLER`. C-1 инвариант проверяется автоматически.

**Почему handler=None:**
`EventInvalidated` не мутирует state напрямую. Его обрабатывает `EventStore.replay()`
на уровне инфраструктуры (pre-filter). Reducer остаётся pure function без DB-запросов.
Replay pre-filter логирует на уровне DEBUG при каждой фильтрации (трассируемость сохранена).

### BC-WG-2: `EventStore.replay()` pre-filter с кэшем и индексом

```
src/sdd/infra/event_store.py
  EventStore._invalidated_cache   # frozenset[int] | None, per-instance
  EventStore._get_invalidated_seqs()  # новый private метод
  EventStore.replay()             # добавляется invalidation pre-filter
```

```python
def _get_invalidated_seqs(self) -> frozenset[int]:
    """Pre-scan с per-instance кэшем (I-INVALID-CACHE-1).

    Кэш сбрасывается в append() при добавлении любого нового события.
    Индекс idx_event_type (созданный в ensure_sdd_schema) гарантирует O(log N) scan.
    """
    if self._invalidated_cache is not None:
        return self._invalidated_cache
    rows = conn.execute(
        "SELECT payload->>'target_seq' FROM events "
        "WHERE event_type = 'EventInvalidated'"
    ).fetchall()
    result = frozenset(int(r[0]) for r in rows if r[0] is not None)
    self._invalidated_cache = result
    return result

def replay(self, ...) -> list[dict]:
    invalidated = self._get_invalidated_seqs()
    raw_events = ...  # основной SELECT
    filtered = []
    for e in raw_events:
        if e["seq"] in invalidated:
            _log.debug("EventStore.replay: skipping invalidated seq=%d", e["seq"])
            continue
        filtered.append(e)
    return filtered
```

**Схема (добавить в `ensure_sdd_schema`):**
```sql
CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type);
```

**Почему per-instance кэш, а не module-level:**
`EventStore` инстанцируется per-command. Кэш живёт ровно столько, сколько один вызов
execute_command — нет проблем с stale данными между командами. Сброс при append() страхует
от случая когда один инстанс делает и append, и replay (unlikely, но корректно).

**Сложность:**
- Pre-scan: O(log N) с индексом по `event_type`
- Основной replay: без изменений
- Кэш-hit: O(1)

### BC-WG-3: `EventStore.append()` kernel guard

```
src/sdd/infra/event_store.py
  EventStore.append()   # guard + кэш сброс + typed bypass
```

```python
from typing import Literal

AllowOutsideKernel = Literal["bootstrap", "test"] | None

def append(
    self,
    events: list[DomainEvent],
    source: str = "runtime",
    command_id: str | None = None,
    expected_head: int | None = None,
    allow_outside_kernel: AllowOutsideKernel = None,   # ← NEW: typed, not bool
) -> None:
    if allow_outside_kernel is None:
        from sdd.core.execution_context import assert_in_kernel
        assert_in_kernel("EventStore.append")
    elif allow_outside_kernel not in ("bootstrap", "test"):
        # Статически невозможно из-за Literal, но explicit check для runtime safety
        raise ValueError(
            f"allow_outside_kernel must be 'bootstrap' or 'test', got {allow_outside_kernel!r}"
        )
    # Сбрасываем кэш при любой записи (I-INVALID-CACHE-1)
    self._invalidated_cache = None
    ...  # existing logic unchanged
```

**Typed bypass — зачем Literal вместо bool:**
`bool=True` — LLM или разработчик ставит не задумываясь. `Literal["bootstrap", "test"]`
требует явного выбора контекста → misuse становится заметным в code review.

**Легитимные bypass:**

| Caller | Значение | Файл |
|--------|----------|------|
| `reconcile_bootstrap.py` | `"bootstrap"` | backfill EventLog (I-BOOTSTRAP-1) |
| `bootstrap_complete.py` | `"bootstrap"` | Bootstrap path |
| `tests/harness/fixtures.py` | `"test"` | tmp_db_path — не production DB |

### BC-WG-4: `sdd_append()` production-path guard (второй уровень)

```
src/sdd/infra/event_log.py
  sdd_append()     # добавляется production DB path check
```

```python
def sdd_append(
    event_type: str,
    payload: dict,
    db_path: str | None = None,
    level: str = "L1",
) -> None:
    # I-DB-WRITE-3: sdd_append cannot target production DB outside kernel context
    resolved = str(Path(db_path or event_store_file()).resolve())
    prod_resolved = str(event_store_file().resolve())
    if resolved == prod_resolved:
        from sdd.core.execution_context import current_execution_context
        if current_execution_context() != "execute_command":
            raise KernelContextError(
                f"sdd_append: direct write to production DB forbidden outside "
                f"execute_command (I-DB-WRITE-3). Use sdd CLI instead."
            )
    ...  # existing logic
```

**Почему это важно:**
BC-WG-3 защищает `EventStore.append`. Но инцидент Phase 27 показал: LLM использовал
`sdd_append` напрямую, минуя `EventStore` полностью. Без BC-WG-4 LLM-via-Bash bypass
остаётся открытым. Проверка по resolved path — надёжнее проверки строки (symlinks, `..`).

**Не ломает:**
- Bootstrap и reconcile — вызываются внутри `execute_command` или используют tmp_db
- Тесты — используют `tmp_db_path`, не production DB

### BC-WG-5: `invalidate-event` REGISTRY command

```
src/sdd/commands/invalidate_event.py   # новый handler
src/sdd/commands/registry.py           # REGISTRY entry
```

```python
# REGISTRY["invalidate-event"]:
CommandSpec(
    name="invalidate-event",
    handler_class=InvalidateEventHandler,
    actor="human",                     # только human инвалидирует (аудит требует)
    action="invalidate_event",
    projection=ProjectionType.NONE,    # audit-only; state не меняется
    uses_task_id=False,
    requires_active_phase=False,       # работает при любом phase status
    event_schema=(EventInvalidatedEvent,),
    preconditions=(
        "target_seq exists in EventLog",
        "event_type at target_seq NOT in _EVENT_SCHEMA",  # I-INVALID-4
        "event_type at target_seq != 'EventInvalidated'",  # I-INVALID-3
        "no prior EventInvalidated for target_seq",        # I-INVALID-IDEM-1
    ),
    postconditions=("EventInvalidated in EventLog",),
    description="Neutralize invalid EventLog entry (kernel violation recovery)",
    idempotent=True,                   # idempotency через handler pre-check, не payload-hash
)
```

**Handler — полная логика (I-INVALID-1..4 + I-INVALID-IDEM-1):**

```python
class InvalidateEventHandler(CommandHandlerBase):
    def handle(self, cmd: InvalidateEventCommand) -> list[DomainEvent]:
        # I-INVALID-1: target_seq must exist
        row = db.execute(
            "SELECT event_type FROM events WHERE seq = ?", [cmd.target_seq]
        ).fetchone()
        if row is None:
            raise InvariantViolationError(
                f"I-INVALID-1: seq={cmd.target_seq} not found in EventLog"
            )
        target_type = row[0]

        # I-INVALID-3: cannot invalidate EventInvalidated (no recursion)
        if target_type == "EventInvalidated":
            raise InvariantViolationError(
                f"I-INVALID-3: cannot invalidate EventInvalidated event"
            )

        # I-INVALID-4: cannot invalidate state-mutating events
        # _EVENT_SCHEMA содержит только события с state logic (TaskImplemented и т.д.)
        from sdd.core.events import _EVENT_SCHEMA
        if target_type in _EVENT_SCHEMA:
            raise InvariantViolationError(
                f"I-INVALID-4: cannot invalidate state-mutating event "
                f"(type={target_type!r} is in _EVENT_SCHEMA). "
                f"Only non-state events (unknown types, _KNOWN_NO_HANDLER) may be invalidated."
            )

        # I-INVALID-IDEM-1: real idempotency via pre-check (NOT payload-hash dedup)
        # Причина: payload включает reason + invalidated_by_phase + timestamp → non-deterministic hash
        existing = db.execute(
            "SELECT 1 FROM events "
            "WHERE event_type = 'EventInvalidated' "
            "AND CAST(payload->>'target_seq' AS INTEGER) = ?",
            [cmd.target_seq],
        ).fetchone()
        if existing:
            _log.info(
                "invalidate-event: seq=%d already invalidated, noop", cmd.target_seq
            )
            return []  # idempotent noop

        return [EventInvalidatedEvent(
            event_type="EventInvalidated",
            event_id=str(uuid4()),
            appended_at=int(time.time() * 1000),
            level=EventLevel.L1,
            event_source="runtime",
            caused_by_meta_seq=None,
            target_seq=cmd.target_seq,
            reason=cmd.reason[:200],
            invalidated_by_phase=state.phase_current,
        )]
```

**I-INVALID-4 — почему только не-state события:**
Invalidation отключает событие из replay. Если отключить state-mutating событие (например,
`TaskImplemented`), последующие события, зависящие от него, получат неконсистентный state.
Разрешаем инвалидацию только для событий из `_KNOWN_NO_HANDLER` (ToolUse*, HookError,
ErrorOccurred, PhaseStarted, ...) и неизвестных типов (мусор). Это делает invalidation
безопасным инструментом без анализа dependency graph.

**CLI:**
```bash
sdd invalidate-event --seq 25970 --reason "direct write via bash, I-KERNEL-WRITE-1 violation"
```

### BC-WG-6: Incident backfill

Конкретный инцидент Phase 27 — одновременно acceptance test и backfill данных.

**Невалидные записи:**

| seq | event_type | payload | Причина |
|-----|-----------|---------|---------|
| 25970 | TestEvent | `{"x": 1}` | LLM bash: `sdd_append(..., db_path=PROD)` |
| 25973 | TestEvent | `{"x": 0}` | LLM bash: `for i in range(5): sdd_append(...)` |
| 25974 | TestEvent | `{"x": 1}` | — " — |
| 25975 | TestEvent | `{"x": 2}` | — " — |
| 25976 | TestEvent | `{"x": 3}` | — " — |
| 25977 | TestEvent | `{"x": 4}` | — " — |

`TestEvent` не в `_EVENT_SCHEMA` → I-INVALID-4 проходит, инвалидация разрешена.

**Команды backfill:**
```bash
for seq in 25970 25973 25974 25975 25976 25977; do
  sdd invalidate-event --seq $seq \
    --reason "direct write via bash (I-KERNEL-WRITE-1 violation, Phase 27 close, 2026-04-25)"
done
```

**Acceptance criterion фазы:**
```bash
sdd show-state 2>&1 | grep -c "WARNING.*unknown event_type"
# Ожидаемый результат: 0
```

---

## 3. Domain Events

```python
@dataclass(frozen=True)
class EventInvalidatedEvent(DomainEvent):
    EVENT_TYPE: ClassVar[str] = "EventInvalidated"
    target_seq:           int   # seq нейтрализованного события
    reason:               str   # ≤200 chars
    invalidated_by_phase: int   # phase_current при эмиссии (аудит)
```

### Event Catalog

| Event | Emitter | Описание |
|-------|---------|---------|
| `EventInvalidated` | `InvalidateEventHandler` | Нейтрализует запись в EventLog; replay pre-filter исключает target_seq; аудит-trail сохраняется |

---

## 4. Types & Interfaces

### Типы

```python
# event_store.py
AllowOutsideKernel = Literal["bootstrap", "test"] | None
```

### CLI команда

```
sdd invalidate-event --seq N --reason "..."
```

| Параметр | Тип | Обязателен | Ограничение |
|----------|-----|-----------|------------|
| `--seq` | `int` | да | должен существовать в EventLog |
| `--reason` | `str` | да | ≤200 chars |

### EventStore изменения

```python
class EventStore:
    _invalidated_cache: frozenset[int] | None  # per-instance, сброс на append

    def append(
        self, events, source="runtime", command_id=None,
        expected_head=None,
        allow_outside_kernel: AllowOutsideKernel = None,  # typed bypass
    ) -> None: ...

    def replay(self, ...) -> list[dict]: ...  # pre-filters invalidated seqs

    def _get_invalidated_seqs(self) -> frozenset[int]: ...  # cached
```

---

## 5. Invariants

### Новые инварианты

| ID | Statement | Verification |
|----|-----------|-------------|
| I-DB-WRITE-2 | `EventStore.append()` MUST assert kernel context unless `allow_outside_kernel in ("bootstrap", "test")`. Violation → `KernelContextError` before any DB write. | `test_write_kernel_guard_raise_outside_context` |
| I-DB-WRITE-3 | `sdd_append()` targeting production DB MUST be inside `kernel_context("execute_command")`. Violation → `KernelContextError`. Non-production paths unrestricted. | `test_sdd_append_prod_guard_raise_outside_kernel` |
| I-INVALID-1 | `invalidate-event` MUST verify `target_seq` exists in EventLog. Non-existent → `InvariantViolationError`. | `test_invalidate_nonexistent_seq_raises` |
| I-INVALID-2 | `EventStore.replay()` MUST pre-scan `EventInvalidated` events and filter target_seqs BEFORE passing to reducer. Reducer MUST NEVER receive an invalidated event. | `test_replay_skips_invalidated_seq` |
| I-INVALID-3 | `invalidate-event` MUST reject if target event_type == `'EventInvalidated'`. No recursive invalidation. | `test_invalidate_invalidated_raises` |
| I-INVALID-4 | `invalidate-event` MUST reject if target event_type is in `_EVENT_SCHEMA` (state-mutating). Only `_KNOWN_NO_HANDLER` and unknown types may be invalidated. | `test_invalidate_state_event_raises` |
| I-INVALID-IDEM-1 | Double `invalidate-event` for same `target_seq` → second call returns `[]` (noop via handler pre-check). Single `EventInvalidated` in log. Payload-hash dedup NOT relied upon (non-deterministic payload). | `test_invalidate_idempotent` |
| I-INVALID-CACHE-1 | `EventStore._invalidated_cache` MUST be reset to `None` on every `append()`. Per-instance scope. | `test_cache_invalidated_after_append` |

### Уточнение существующих инвариантов

| ID | Уточнение |
|----|-----------|
| I-KERNEL-WRITE-1 | Теперь принуждается кодом: `EventStore.append` (I-DB-WRITE-2) + `sdd_append` (I-DB-WRITE-3) |
| I-SPEC-EXEC-1 | `EventStore.append()` — enforced kernel-only write path на уровне runtime |

### Сохраняемые инварианты

| ID | Statement |
|----|-----------|
| I-OPTLOCK-1 | `expected_head` проверяется до INSERT — не затронуто |
| I-IDEM-SCHEMA-1 | Dedup по `(command_id, event_index)` — `EventInvalidated` корректно dedup'ится при idempotent=True; handler pre-check — первичный механизм |
| I-EL-6 | `V1_L1_EVENT_TYPES == V2_L1_EVENT_TYPES`; `EventInvalidated` добавляется в обе |
| C-1 | `_KNOWN_NO_HANDLER \| frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES` |

---

## 6. Pre/Post Conditions

### BC-WG-3: EventStore.append kernel guard

**Pre (violation path):**
- `allow_outside_kernel=None`
- Вызов вне `kernel_context("execute_command")`

**Post:** `KernelContextError` raised; EventLog не изменён; `_invalidated_cache` не сброшен

**Pre (bypass path):**
- `allow_outside_kernel in ("bootstrap", "test")`

**Post:** обычный append; `_invalidated_cache` сброшен

### BC-WG-4: sdd_append production guard

**Pre:** `resolved_db_path == production_db_path` AND `current_execution_context() != "execute_command"`

**Post:** `KernelContextError`; запись не происходит

**Pre (safe path):** `db_path != production_db_path` ИЛИ внутри `kernel_context`

**Post:** обычный sdd_append

### BC-WG-5: invalidate-event command

**Pre:**
- `target_seq` существует в EventLog (I-INVALID-1)
- `target_event_type not in _EVENT_SCHEMA` (I-INVALID-4)
- `target_event_type != 'EventInvalidated'` (I-INVALID-3)
- Нет предыдущего `EventInvalidated` для `target_seq` (I-INVALID-IDEM-1)

**Post:**
- `EventInvalidated{target_seq, reason, invalidated_by_phase}` в EventLog
- Следующий `replay()`: target_seq отфильтрован, DEBUG log
- `sdd show-state` без WARNING для target_seq

**Pre (noop / idempotent):** уже есть `EventInvalidated` для `target_seq`

**Post (noop):** `[]` возвращается; EventLog не изменён

---

## 7. Use Cases

### UC-28-1: Нейтрализация мусорного события (incident recovery)

**Actor:** human
**Trigger:** WARNING в `sdd show-state` об unknown event_type
**Pre:** `invalidate-event` реализован; target_seq известен
**Steps:**
1. `sdd query-events --type UnknownType` → получить seq
2. `sdd invalidate-event --seq N --reason "..."` → emit `EventInvalidated`
3. `sdd show-state` → WARNING отсутствует

**Post:** WARNING устранён; EventLog неизменён исторически; replay детерминирован

### UC-28-2: LLM пытается писать в production DB через Bash

**Actor:** LLM (нарушение протокола)
**Trigger:** `sdd_append(..., db_path=PROD_DB)` вне `execute_command`
**Pre:** BC-WG-4 реализован
**Steps:**
1. `sdd_append` проверяет `resolved_path == prod_path`
2. Проверяет `current_execution_context()` → не `"execute_command"`
3. → `KernelContextError` с явным сообщением

**Post:** EventLog не изменён; LLM видит ошибку с I-DB-WRITE-3 ссылкой

### UC-28-3: LLM пытается писать через EventStore.append напрямую

**Actor:** LLM (нарушение протокола)
**Trigger:** `EventStore(prod_db).append(...)` вне `kernel_context`
**Pre:** BC-WG-3 реализован
**Steps:**
1. `allow_outside_kernel=None` (default)
2. `assert_in_kernel("EventStore.append")` → `KernelContextError`

**Post:** EventLog не изменён

### UC-28-4: Bootstrap использует bypass

**Actor:** `reconcile_bootstrap.py`
**Trigger:** backfill EventLog для исторических событий
**Pre:** `allow_outside_kernel="bootstrap"` передан явно
**Steps:** append проходит; `_invalidated_cache` сброшен

**Post:** Bootstrap корректно работает; guard не блокирует

### UC-28-5: Попытка инвалидировать TaskImplemented (защита от ошибки)

**Actor:** human (ошибочный вызов)
**Trigger:** `sdd invalidate-event --seq N` где seq N = TaskImplemented event
**Pre:** BC-WG-5 I-INVALID-4 реализован
**Steps:**
1. Handler проверяет `target_event_type in _EVENT_SCHEMA`
2. `TaskImplemented` ∈ `_EVENT_SCHEMA` → `InvariantViolationError`

**Post:** EventLog не изменён; явная ошибка с объяснением

---

## 8. Integration

### Dependencies on Other BCs

| BC | Направление | Цель |
|----|------------|------|
| `core/execution_context.py` | BC-WG-3, BC-WG-4 → | `assert_in_kernel`, `current_execution_context` |
| `core/events.py` | BC-WG-1 → | `EventInvalidatedEvent` + регистрация |
| `infra/event_store.py` | BC-WG-2, BC-WG-3 → | кэш, индекс, pre-filter, guard |
| `infra/event_log.py` | BC-WG-4 → | `sdd_append` production guard |
| `commands/registry.py` | BC-WG-5 → | `REGISTRY["invalidate-event"]` |
| `infra/db.py` | BC-WG-2 → | `ensure_sdd_schema` добавляет `idx_event_type` |

### Reducer — изменений нет

`EventInvalidated` в `_KNOWN_NO_HANDLER`. Reducer не видит invalidated events (pre-filter
в EventStore). Чистота reducer сохранена полностью.

### Обратная совместимость

- `EventStore.append()` — новый `allow_outside_kernel` keyword с default `None`; все
  существующие callers внутри `execute_command` работают без изменений
- `EventStore.replay()` — поведение изменяется только при наличии `EventInvalidated` в log
- `sdd_append()` — guard активен только для production DB path; тесты с tmp_db_path не затронуты

---

## 9. Verification

| # | Test | Инвариант(ы) | Файл |
|---|------|------------|------|
| 1 | `test_write_kernel_guard_raise_outside_context` | I-DB-WRITE-2 | `tests/unit/infra/test_write_kernel_guard.py` |
| 2 | `test_write_kernel_guard_allow_inside_context` | I-DB-WRITE-2 | `tests/unit/infra/test_write_kernel_guard.py` |
| 3 | `test_write_kernel_guard_bootstrap_bypass` | I-DB-WRITE-2 | `tests/unit/infra/test_write_kernel_guard.py` |
| 4 | `test_write_kernel_guard_invalid_bypass_value` | I-DB-WRITE-2 | `tests/unit/infra/test_write_kernel_guard.py` |
| 5 | `test_sdd_append_prod_guard_raise_outside_kernel` | I-DB-WRITE-3 | `tests/unit/infra/test_write_kernel_guard.py` |
| 6 | `test_sdd_append_nonprod_allowed_outside_kernel` | I-DB-WRITE-3 | `tests/unit/infra/test_write_kernel_guard.py` |
| 7 | `test_replay_skips_invalidated_seq` | I-INVALID-2 | `tests/unit/infra/test_event_invalidation.py` |
| 8 | `test_replay_no_warning_for_invalidated` | I-INVALID-2 | `tests/unit/infra/test_event_invalidation.py` |
| 9 | `test_cache_invalidated_after_append` | I-INVALID-CACHE-1 | `tests/unit/infra/test_event_invalidation.py` |
| 10 | `test_invalidate_nonexistent_seq_raises` | I-INVALID-1 | `tests/unit/commands/test_invalidate_event.py` |
| 11 | `test_invalidate_invalidated_raises` | I-INVALID-3 | `tests/unit/commands/test_invalidate_event.py` |
| 12 | `test_invalidate_state_event_raises` | I-INVALID-4 | `tests/unit/commands/test_invalidate_event.py` |
| 13 | `test_invalidate_idempotent` | I-INVALID-IDEM-1 | `tests/unit/commands/test_invalidate_event.py` |
| 14 | `test_incident_backfill_no_warnings` | BC-WG-6 | `tests/integration/test_incident_backfill.py` |

### Test 14 — Ключевой интеграционный тест (воспроизводит инцидент)

```python
def test_incident_backfill_no_warnings(tmp_db_path: str, caplog: pytest.LogCaptureFixture):
    """
    Воспроизводит инцидент Phase 27 end-to-end:
    1. Записываем 6 TestEvent напрямую через sdd_append (bypass — tmp_db, нет guard)
    2. Проверяем что replay даёт WARNING (baseline — проблема существует)
    3. Выполняем invalidate-event для всех 6 seqs через proper command path
    4. Проверяем что повторный replay НЕ даёт WARNING (fix verified)
    """
    import logging
    from sdd.commands.registry import REGISTRY, execute_and_project
    from sdd.infra.event_log import sdd_append
    from sdd.infra.event_store import EventStore
    from sdd.infra.projections import get_current_state

    # Step 1: воспроизводим инцидент — прямая запись мимо kernel
    for i in range(6):
        sdd_append("TestEvent", {"x": i}, db_path=tmp_db_path, level="L1")

    # Step 2: baseline — WARNING должен быть
    with caplog.at_level(logging.WARNING, logger="root"):
        get_current_state(tmp_db_path)
    assert any("unknown event_type='TestEvent'" in r.message for r in caplog.records), \
        "Baseline failed: expected WARNING about TestEvent"

    # Step 3: backfill через proper command path
    caplog.clear()
    store = EventStore(tmp_db_path)
    test_seqs = [
        row["seq"] for row in store.query_by_type("TestEvent")
    ]
    assert len(test_seqs) == 6, f"Expected 6 TestEvent seqs, got {test_seqs}"

    for seq in test_seqs:
        cmd = InvalidateEventCommand(
            target_seq=seq,
            reason="direct write via sdd_append, I-KERNEL-WRITE-1 violation (test reproduction)",
        )
        execute_and_project(REGISTRY["invalidate-event"], cmd, db_path=tmp_db_path)

    # Step 4: fix verified — WARNING отсутствует
    with caplog.at_level(logging.WARNING, logger="root"):
        get_current_state(tmp_db_path)
    assert not any("unknown event_type='TestEvent'" in r.message for r in caplog.records), \
        "Fix failed: WARNING still present after invalidation"
```

---

## 10. Implementation Order

```
BC-WG-1: EventInvalidatedEvent в core/events.py + register_l1_event_type
BC-WG-2: idx_event_type в ensure_sdd_schema + _get_invalidated_seqs + _invalidated_cache + replay pre-filter
BC-WG-3: EventStore.append() guard + AllowOutsideKernel type + cache reset
BC-WG-4: sdd_append() production path guard (I-DB-WRITE-3)
BC-WG-5: InvalidateEventHandler + REGISTRY["invalidate-event"] + CLI
BC-WG-6: Incident backfill + test_incident_backfill_no_warnings
```

---

## 11. New Invariants (добавить в CLAUDE.md §INV после утверждения)

```
| I-DB-WRITE-2 | EventStore.append() MUST assert kernel context unless
|              | allow_outside_kernel in ("bootstrap", "test").
|              | Violation → KernelContextError before any DB write. |
| I-DB-WRITE-3 | sdd_append() targeting production DB MUST be inside
|              | kernel_context("execute_command"). Checked via resolved path.
|              | Violation → KernelContextError. |
| I-INVALID-4  | invalidate-event MUST reject state-mutating events
|              | (event_type in _EVENT_SCHEMA). Only _KNOWN_NO_HANDLER
|              | and unknown types may be invalidated. |
```

---

## 12. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| EventLog compaction (физическое удаление) | Phase N+2 |
| UI / reporting для invalidated events | Phase N+1 |
| Automated kernel violation detection | Phase N+1 |
| Invalidation of state-mutating events (с dependency analysis) | Phase N+3 — требует full DAG analysis |
