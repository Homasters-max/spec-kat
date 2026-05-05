---
id: idea/event-sourcing
page_type: idea
domain: sdd
layer: architecture
tags:
- ssot
- write-path
- pipeline
- automation
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Event Sourcing

Архитектурный принцип: состояние системы полностью восстанавливается из последовательности событий.

## How It Works

```text
StateN = reduce(EventLog₀…N)
```

EventLog — единственный источник истины (SSOT). Текущее состояние — это проекция: `Projection := f(EventLog, Code)`.

**Replay:**

```python
state = initial()
for e in event_store.load():
    state = reduce(state, upcast(e))
```

**EventStore требования:**

- append-only
- ordered
- dedup по `event.id` и `command_id`
- atomic batch append
- единственный разрешённый caller: `"CommandHandler"`

## When To Use

Когда нужны: полная аудитабельность, replay для восстановления состояния, детерминированные тесты без моков.

## Trade-offs

- EventLog растёт бесконечно (partitioning — defer до v2.1+).
- Replay медленнее прямого чтения состояния из БД.
- Требует upcasting при изменении схемы событий.

## See Also

- [[reducer]]
- [[upcaster-registry]]
- [[replay-based-testing]]
- [[sdd-meta-harness]]
