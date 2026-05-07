---
created: '2026-05-05'
domain: sdd
id: idea/event-sourcing
layer: architecture
page_type: idea
sdd_domain: Core
sdd_layer: L0
sources:
- raw/SDD Meta Harness Core.md
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
tags:
- ssot
- write-path
- pipeline
- automation
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-06'
version: 4
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

## Open Questions

- [ ] (P0) Q1 PARTIAL: Как обеспечивается total order EventLog? single-writer vs partition+merge? Где формализован инвариант?
- [ ] (P0) Q2 PARTIAL: Является ли event_index глобальным монотонным счётчиком? Что происходит при concurrent append в PostgreSQL?
- [ ] (P0) Q3 PARTIAL: Что является границей batch? Атомарны ли N events от одного handler? Batch failure path открыт.
- [ ] (P0) Q5: Что происходит при падении процесса между handle() и append()? Как обнаружить незавершённый batch?
- [ ] (P0) Q7: Можно ли replay старого EventLog новой версией reducer без потери инвариантов? Как тестировать совместимость?
- [ ] (P0) Q9: Есть ли несколько EventLog или один глобальный? Как гарантировать causality между ними?
- [ ] (P0) Q10 PARTIAL: Событие ломает reducer на replay. DLQ? Quarantine? Manual upcasting? → [[classified-recovery]] ABORT есть, repair flow нет.
- [ ] (P0) Q11 PARTIAL: Нужен ли snapshotting для prod EventLog? При каком объёме replay неприемлем? SLA? → [[golden-fixture]] только для тестов.
- [ ] (P0) Q55: Явное различие logical time (event_index) vs wall-clock? Что является canonical ordering?
- [ ] (P0) Q56: Нужен ли Lamport clock для causality? При multi-agent — vector clock обязателен?
- [ ] (P0) Q57: Как обрабатываются события с идентичным wall-clock timestamp? Monotonic clock required?
- [ ] (P0) Q58: При distributed setup возможен ли reordering при concurrent append? Как гарантировать total order без distributed lock?
- [ ] (P0) Q59: Как формализовано "happened-before" для команд и событий? EventLog position достаточен?
- [ ] (P0) Q60: Если два события конкурентны, какой deterministic tie-breaker используется?

- [ ] (P2) Q134: Каков исчерпывающий canonical список всех событий системы? (ProjectCreated, PhaseStarted, TaskCompleted…). Где живёт — wiki или enum в коде?
- [ ] (P2) Q135: Должен ли каждый вызов write_file порождать FileWritten event, или это деталь TaskStepRecorded?
- [ ] (P2) Q136: Как записать что агент решил не делать что-то? SkippedTest? DecisionRecorded?
- [ ] (P2) Q137: На каком уровне детализации записываются события? Стратегия для "слишком много vs слишком мало"?

## Decisions

- [x] (P0) Q4: Atomic append гарантируется через Write Kernel + OCC → [[write-kernel]]
- [x] (P0) Q6: Schema evolution через upcasting старых событий → [[upcaster-registry]]
- [x] (P0) Q8: Event immutability технически запрещена через DB constraints → [[eventstore-guard]]
