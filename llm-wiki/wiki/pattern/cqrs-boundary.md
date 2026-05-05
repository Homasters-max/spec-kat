---
id: pattern/cqrs-boundary
page_type: pattern
domain: sdd
layer: architecture
tags:
- cqrs
- write-path
- ssot
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# CQRS Boundary

Граница разделения команд и запросов в SDD: handler — чистая функция, snapshot передаётся [[write-kernel]]'ом, запись атомарна через OCC.

## How It Works

```python
snapshot = reduce(event_store.load(up_to=N))  # детерминировано
events   = handler(cmd, snapshot)              # pure, no side effects
event_store.append(events, expected_version=N) # OCC атомарно внутри EventStore
```

**Ключевые свойства:**

- `handler(cmd, snapshot) → list[Event]` — pure function: без DB, без network, без datetime.now()
- Snapshot передаётся [[write-kernel]]'ом до вызова handler, handler не читает EventStore самостоятельно
- `expected_version=N` — версия snapshot; при конфликте → `OptimisticConcurrencyError` → retry
- Handler retry-safe: детерминированный вход → детерминированный выход

**Инварианты:**

```text
I-CQRS-1: handler(cmd, snapshot) → list[Event]
           snapshot = reduce(EventLog[0:N]); передаётся WriteKernel'ом до вызова
I-CQRS-2: handler MUST NOT call any read API (EventStore, Projection, DB, network)
I-CQRS-3: Events NEVER carry imperative payload; Commands NEVER appear in EventLog
```

**Retry flow:**

```text
OptimisticConcurrencyError
  → reload snapshot (reduce fresh EventLog)
  → retry handler
  → retry append
```

Retry orchestrated в middleware или SessionOrchestrator; handler не знает о retry.

## When To Use

Применяется на каждую команду в SDD pipeline. [[write-kernel]] управляет snapshot lifecycle и вызывает guard pipeline перед handler.

## Trade-offs

- Handler детерминирован → replay и тестирование без моков ([[replay-based-testing]])
- OCC создаёт contention под нагрузкой; снимается idempotency + exponential backoff retry
- Snapshot может быть крупным при больших EventLog — optional memoization с инвалидацией по version

## See Also

- [[write-kernel]]
- [[optimistic-concurrency-control]]
- [[idempotent-events]]
- [[replay-based-testing]]
- [[event-sourcing]]
- [[execution-guard]]
