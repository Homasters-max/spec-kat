---
id: pattern/optimistic-concurrency-control
page_type: pattern
domain: sdd
layer: architecture
tags:
- write-path
- ssot
- automation
- validation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Optimistic Concurrency Control

OCC в SDD: атомарная проверка версии при append в EventStore. Единственная точка предотвращения race condition при параллельных командах.

## How It Works

```python
EventStore.append(events: list[Event], expected_version: int) -> None
    # raises OptimisticConcurrencyError if current_version != expected_version
```

[[write-kernel]] передаёт версию из snapshot:

```python
event_store.append(handler_events, expected_version=snapshot.version)
```

Проверка и append атомарны внутри PostgreSQL transaction — нет race condition.

**Retry flow:**

```python
# Orchestrator или middleware:
while True:
    snapshot = reduce(event_store.load())        # reload fresh snapshot
    events   = handler(cmd, snapshot)            # pure, deterministic
    try:
        event_store.append(events, expected_version=snapshot.version)
        break
    except OptimisticConcurrencyError:
        continue  # exponential backoff recommended
```

Handler retry-safe: детерминированный вход → детерминированный выход → те же `event_id` → EventStore dedup безопасен.

## When To Use

Применяется на каждый `EventStore.append` в [[cqrs-boundary]]. `IdempotencyMiddleware` в guard pipeline (slot 0.5) дополнительно дедуплицирует команды по `idempotency_key` до retry loop.

## Trade-offs

- Нет lock'ов — высокая throughput при низком contention
- При высоком contention — много retry; снимается через command batching или actor per aggregate
- Требует детерминированного handler для безопасного retry

## See Also

- [[cqrs-boundary]]
- [[write-kernel]]
- [[idempotent-events]]
- [[event-sourcing]]
