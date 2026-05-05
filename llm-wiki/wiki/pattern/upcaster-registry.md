---
id: pattern/upcaster-registry
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- validation
- automation
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Upcaster Registry

Механизм миграции схемы событий без изменения EventLog: каждое событие несёт `version: int`, апкастеры применяются последовательно перед reducer.

## How It Works

```python
class UpcasterRegistry:
    def register(event_type: str, from_version: int, to_version: int, fn: Callable): ...

def upcast(event: Event) -> Event:
    while event.version < CURRENT_VERSION[event.type]:
        event = registry.apply(event)
    return event
```

**Правила:**

- Replay ВСЕГДА проходит через `upcast()` перед reducer.
- Апкастеры применяются **последовательно** (`N → N+1 → N+2 → ...`).
- Запрещены side effects и IO внутри апкастеров.
- При старте v2 все события имеют `version=1`, upcast = identity.
- Изменение схемы события → пишем апкастер `N → N+1`, НЕ меняем EventLog.

## When To Use

При изменении структуры Event (добавление полей, переименование). Обязателен с первого дня.

## Trade-offs

- Цепочка апкастеров растёт с каждой миграцией схемы.
- Нельзя удалять апкастеры, пока в EventLog есть старые события.

## See Also

- [[reducer]]
- [[event-sourcing]]
- [[sdd-meta-harness]]
