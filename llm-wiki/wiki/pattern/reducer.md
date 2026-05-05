---
id: pattern/reducer
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- automation
- pipeline
version: 1
created: '2026-05-05'
updated: '2026-05-05'
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
