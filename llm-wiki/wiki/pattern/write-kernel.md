---
id: pattern/write-kernel
page_type: pattern
domain: sdd
layer: architecture
tags:
- write-path
- ssot
- pipeline
- enforcement
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Write Kernel

Единственная точка записи в SDD: управляет snapshot lifecycle, вызывает guard pipeline, передаёт события в EventStore атомарно. Все side-effects происходят только здесь.

## How It Works

```python
def execute_and_project(cmd: Command, ctx: CommandContext) -> None:
    # 1. Load snapshot (current state)
    snapshot = reduce(event_store.load())

    # 2. Run guard pipeline (slots 0 → 2c)
    guard_result = pipeline.run(cmd, ctx, snapshot)
    if not guard_result.ok:
        raise GuardError(guard_result)

    # 3. Execute handler (pure function)
    events = handler(cmd, snapshot)

    # 4. Atomic append with OCC
    event_store.append(events, expected_version=snapshot.version)

    # 5. Rebuild projections
    projection_registry.rebuild(events)
```

**Инварианты:**

- Единственный разрешённый caller EventStore.append (I-EVENTLOG-5 / GL-7)
- Snapshot передаётся handler'у, не читается handler'ом самостоятельно (I-CQRS-1)
- All side-effects (EventStore.append, projection rebuilds) — только здесь (§INV I-3)

**Snapshot management:**

```python
snapshot = reduce(event_store.load(up_to=N))
# snapshot.version = N → передаётся в OCC expected_version
```

## When To Use

Вызывается всеми командами в SDD pipeline. [[execution-guard]] и другие middlewares работают как обёртка над `execute_and_project`. Прямой вызов `EventStore.append` из любого другого места — нарушение GL-7.

## Trade-offs

- Единая точка записи упрощает аудит и тестирование
- Все projections rebuild синхронно — latency tradeoff при большом числе projections
- OCC retry orchestrated снаружи (middleware / orchestrator)

## See Also

- [[cqrs-boundary]]
- [[execution-guard]]
- [[optimistic-concurrency-control]]
- [[event-sourcing]]
- [[deterministic-context]]
