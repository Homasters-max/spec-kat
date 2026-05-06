---
id: pattern/reducer
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- automation
- pipeline
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD Meta Harness Core.md
---
# Reducer

Чистая функция перехода состояния: `State × Event → State`.

## How It Works

```python
def reduce(state: State, event: Event) -> State: ...
```

**Обязательные свойства:**

- **pure** — нет side effects
- **deterministic** — одинаковый input → одинаковый output
- **idempotent по `event.id`** — повторное применение того же события не меняет состояние

Reducer применяется только к событиям, прошедшим через [[upcaster-registry]]:

```python
state = reduce(state, upcast(e))
```

**State schema:**

```yaml
State:
  phases: dict
  tasks: dict
  invariants_status: dict
```

## When To Use

Везде, где нужно восстанавливать состояние из EventLog (replay, тесты, проекции).

## Trade-offs

- Reducer должен обрабатывать ВСЕ версии событий через upcast — нельзя добавить логику напрямую в старые события.
- Не должен содержать IO или вызовы EventStore.

## See Also

- [[event-sourcing]]
- [[upcaster-registry]]
- [[replay-based-testing]]
- [[sdd-meta-harness]]

## Open Questions

- [ ] (P0) Q35: Запрет datetime.now() в handlers? Как внедрять clock abstraction? Тестирование с mock time?
- [ ] (P0) Q36: Что входит в reproducible environment? OS version, lib versions, DB version? Где фиксируется?
- [ ] (P0) Q37: Как автоматически проверяется, что reducer pure? Mutation testing? Property-based testing?
- [ ] (P0) Q38: Как ловить недетерминизм в runtime? Двойной запуск с проверкой идентичности output?
- [ ] (P0) Q39 PARTIAL: Как гарантировать replay_context при изменении graph? → [[deterministic-context]] но нет формального proof.
- [ ] (P1) Q80 PARTIAL: phases_snapshots есть в SDDState, но materialized snapshots для ускорения prod replay не реализованы. SLA на полный replay vs snapshot replay?
- [ ] (P1) Q81: Как ограничить рост state? Eviction policy для старых phases_snapshots?
- [ ] (P1) Q82: Можно ли replay с checkpoint вместо начала? Как гарантировать корректность?
- [ ] (P1) Q83: Проверяется ли state после каждого события? Post-condition assertions в reducer?
- [ ] (P1) Q84: Где ловится invariant violation — reducer или guard? Что если reducer нарушил инвариант?
- [ ] (P1) Q85: Canonical format для State_index.yaml? Versioned? Migration path?

## Decisions

- [x] (P0) Q34: Randomness control — детерминизм по дизайну, GL-1 → [[global-laws]]
- [x] (P1) Q79: Reducer composition — один pure reducer → [[reducer]]
