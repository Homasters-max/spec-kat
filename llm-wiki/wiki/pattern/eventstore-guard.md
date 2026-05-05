---
id: pattern/eventstore-guard
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- write-path
- ssot
- validation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# EventStore Guard

L0-компонент: физически запрещает `event_store.append()` в обход Command handlers (I-CMD-ONLY-1, GL-7).

## How It Works

Проблема: ничто не мешает коду вызвать `event_store.append()` напрямую, минуя CommandBus → Guards → Handler pipeline. EventStore Guard закрывает эту дыру.

```python
class EventStoreGuard:
    _allowed_callers = {"CommandHandler"}

    def check_caller(self, frame: FrameInfo) -> None:
        caller = frame.f_locals.get("__class__", None)
        if caller.__name__ not in self._allowed_callers:
            raise DirectEventStoreAccessError(
                f"event_store.append() called outside handler: {caller}"
            )
```

**Механизм**: `EventStore.append()` содержит call-stack check при каждом вызове. Прямой вызов вне `CommandHandler` → `DirectEventStoreAccessError` → `ErrorEvent` → ABORT.

**Альтернативный механизм**: Python module-level `__all__` + import restrictions — но call-stack check надёжнее т.к. работает в runtime.

**Тест:** `test_direct_eventstore_access` проверяет что вызов вне handler поднимает ошибку.

## When To Use

Всегда активен — прозрачный guard на `EventStore.append()`. Не требует явного вызова.

## Trade-offs

- Call-stack inspection = небольшой overhead на каждый append.
- В тестах нужно использовать CommandHandler wrapper, не вызывать append напрямую.

## See Also

- [[event-sourcing]]
- [[command-bus]]
- [[global-laws]]
- [[sdd-component-inventory]]
