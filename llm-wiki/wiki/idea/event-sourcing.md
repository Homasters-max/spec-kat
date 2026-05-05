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
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
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

## Event Structure

Каждое событие несёт полную traceability через три causal поля:

```python
@dataclass(frozen=True)
class Event:
    event_id:           UUID      # uuid5(command_id:position) — детерминирован
    command_id:         UUID      # provenance: какая команда породила событие
    causation_event_id: UUID | None  # event DAG: предыдущее событие в цепочке (None если первое)
    correlation_id:     UUID      # flow grouping: неизменен по всей сессии
    sequence_no:        int       # монотонно возрастающий, без пропусков
    occurred_at:        datetime  # UTC, immutable после записи
    payload:            dict
```

**Causal Linkage семантика:**

- `command_id` → «какая команда меня создала»
- `causation_event_id` → «из какого события выросло следующее» (event DAG)
- `correlation_id` → «какая сессия меня создала» (задаётся SessionOrchestrator)

Реконструкция истории сессии: `WHERE correlation_id = X ORDER BY sequence_no`.

**Детерминированный event_id:**

```python
event_id = uuid5(NAMESPACE_SDD, f"{command_id}:{position}")
# position = индекс события в batch (0, 1, 2…); event_type не нужен
```

Retry команды → те же `event_id` → безопасный dedup в EventStore.

## EventStore Инварианты

```text
I-EVENTLOG-1: append-only — delete() и update() MUST NOT exist
I-EVENTLOG-2: ordered — sequence_no монотонен; gap → Inconsistency raised
I-EVENTLOG-3: immutable — событие после append не изменяется (hash-verified)
I-EVENTLOG-4: event_id детерминирован: uuid5(NAMESPACE_SDD, f"{command_id}:{position}")
I-EVENTLOG-5: single-caller — append() MUST fail если call-stack не содержит WriteKernel (GL-7)
I-EVENTLOG-6: atomic-batch — события одной команды appended atomically или не appended вовсе
I-EVENTLOG-7: OCC — append(events, expected_version) проверяет версию атомарно
```

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
- [[cqrs-boundary]]
- [[idempotent-events]]
- [[causal-linkage]]
