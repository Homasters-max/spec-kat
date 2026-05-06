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
version: 2
created: '2026-05-05'
updated: '2026-05-06'
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

## Open Questions

- [ ] (P0) Q12 PARTIAL: Сколько retry допустимо? max_retries есть в [[loop-policy]], но backoff алгоритм (exponential/fixed) не задан.
- [ ] (P0) Q13: Всегда ли OCC-конфликт → retry? Когда конфликт должен приводить к ABORT? Как отличить transient от systemic?
- [ ] (P0) Q14: Handler работает долго, snapshot устаревает. Heartbeat? Timeout? Re-read snapshot?
- [ ] (P0) Q15: Разрешены ли параллельные команды к одному aggregate? Если нет — где serialization point?
- [ ] (P0) Q16 PARTIAL: OCC ловит version mismatch, но logical write skew (два агента читают одно состояние, принимают разные решения) не рассмотрен.
- [ ] (P0) Q17: Может ли OCC с несколькими агентами привести к livelock при высокой contention? Jitter на retry?
- [ ] (P1) Q19: Нужны ли saga/compensation patterns? Если handle() эмитирует событие запускающее следующую команду — это сага? Как rollback?

## Decisions

- [x] (P0) Q18: Command dedup через idempotency key → [[idempotency-projection]] + [[idempotency-mode]]

## See Also

- [[cqrs-boundary]]
- [[write-kernel]]
- [[idempotent-events]]
- [[event-sourcing]]
