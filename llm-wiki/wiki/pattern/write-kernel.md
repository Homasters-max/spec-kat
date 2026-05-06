---
created: '2026-05-05'
domain: sdd
id: pattern/write-kernel
layer: architecture
page_type: pattern
sdd_domain: Core
sdd_layer: L0
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
tags:
- write-path
- ssot
- pipeline
- enforcement
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-06'
version: 2
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
- [[command-context]] — контекст исполнения (actor, session_id, correlation_id), передаётся handler'у

## Open Questions

- [ ] (P0) Q5: Что происходит при падении процесса между handle() и append()? Как обнаружить и компенсировать незавершённый batch?
- [ ] (P0) Q49: Как гарантируется deterministic key ordering в JSON serialization? sorted_keys? custom encoder? Тест на ordering stability?
- [ ] (P0) Q50: Есть ли schema_version или schema_hash в каждом событии для обнаружения schema drift?
- [ ] (P0) Q51: Как обрабатываются поля отсутствующие в старых событиях при replay новым reducer? Default values? Strict validation?
- [ ] (P0) Q54: Как избежать расхождения если разные версии кода читают одни события? Serializer compatibility matrix? Migration tests?

## Decisions

- [x] (P0) Q4: Atomic append гарантируется через Write Kernel + OCC; expected_version = snapshot.version → [[optimistic-concurrency-control]]
- [x] (P0) Q27: expected_version source — всегда snapshot.version, никогда не задаётся клиентом → [[optimistic-concurrency-control]]
