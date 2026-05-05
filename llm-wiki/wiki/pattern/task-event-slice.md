---
id: pattern/task-event-slice
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- validation
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
---
# TaskEventSlice

Изолированный срез EventLog для одной задачи: `context_prefix` (системные события до `TaskStarted`) + `task_events` (события самой задачи). Граница context_prefix задаётся статическим whitelist `CONTEXT_EVENT_TYPES`.

## How It Works

```python
CONTEXT_EVENT_TYPES: frozenset[str] = frozenset({
    "PhaseInitialized",
    "PhaseContextSwitched",
    "PolicyUpdated",
    "BootstrapCompleted",
    # При добавлении нового Guard'а, зависящего от нового event type —
    # разработчик явно добавляет тип сюда (единственная константа, AD-13)
})

@dataclass
class TaskEventSlice:
    task_id: str
    phase_id: int
    schema_version: int
    context_prefix: list[Event]   # системные события ДО TaskStarted
    task_events: list[Event]      # события с TaskStarted по TaskCompleted

    @property
    def full_sequence(self) -> list[Event]:
        return self.context_prefix + self.task_events

class TaskEventSliceBuilder:
    def from_store(self, task_id: str) -> TaskEventSlice:
        # context_prefix = события из CONTEXT_EVENT_TYPES до TaskStarted(task_id)
        # task_events = события с TaskStarted по TaskCompleted
        # Детерминировано, не зависит от других задач фазы
        ...

    def from_fixture(self, fixture: GoldenFixture) -> TaskEventSlice:
        # context_prefix уже сериализован в YAML при golden-capture
        # EventLog не нужен — fixture полностью самодостаточна
        ...
```

**Два пути сборки:**

| Метод | Источник | Когда |
|-------|---------|-------|
| `from_store(task_id)` | EventLog (live) | `sdd golden-capture T-NNN` |
| `from_fixture(fixture)` | GoldenFixture YAML | запуск тестов |

## When To Use

Передаётся в [[replay-engine]] как входные данные: `ReplayEngine().replay(slice.full_sequence)`.

`CONTEXT_EVENT_TYPES` — единственный whitelist (I-REPLAY-12). При добавлении Guard'а, зависящего от нового event type, разработчик явно добавляет тип в константу — нет конфигов, нет магии.

## Trade-offs

- `CONTEXT_EVENT_TYPES` — ручная синхронизация с Guards: если Guard добавлен без обновления константы, тест будет некорректен
- `from_store` читает EventLog — не pure, но вызывается только при capture, не при тестах

- I-REPLAY-12 риск устраняется safeguard-тестом: introspect Guard event reads vs CONTEXT_EVENT_TYPES — CI
  поймает silent incorrectness:

```python
def test_context_event_types_covers_all_guard_dependencies():
    guard_event_reads = introspect_guard_event_types(ExecutionGuard, ScopeGuard)
    missing = guard_event_reads - TaskEventSlice.CONTEXT_EVENT_TYPES
    assert not missing, (
        f"Guards depend on event types not in CONTEXT_EVENT_TYPES: {missing}. "
        f"Update TaskEventSlice.CONTEXT_EVENT_TYPES (I-REPLAY-12)."
    )
```

## See Also

- [[replay-engine]]
- [[golden-fixture]]
- [[event-sourcing]]
- [[replay-based-testing]]
