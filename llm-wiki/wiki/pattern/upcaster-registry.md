---
id: pattern/upcaster-registry
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- validation
- automation
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-06'
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

## Open Questions

- [ ] (P2) Q203: Как делается upgrade системы без потери событий и downtime? Blue-green? Rolling с multi-version compatibility?
- [ ] (P2) Q204: При каких изменениях (reducer, projection, guard) обязателен full replay EventLog? Можно ли incremental migration?
- [ ] (P2) Q205: Как откатить версию системы если новый код несовместим со старым EventLog? Downgrade path?
- [ ] (P2) Q206: При rolling upgrade — могут ли разные версии нод одновременно читать/писать один EventLog? Compatibility contract?
- [ ] (P2) Q207: Как тестировать upgrade на production данных? Snapshot EventLog → staging → test upgrade → verify State equality?
- [ ] (P2) Q208: Есть ли механизм feature flags для постепенного включения новой функциональности? Через PolicyKernel?

## Decisions

- [x] (P0) Q6: Schema evolution реализована через upcasting — цепочка апкастеров для всех старых версий → [[event-sourcing]]
- [x] (P0) Q35: Reducer versioning — upcaster позволяет reducer работать только с последней версией событий → [[reducer]]
