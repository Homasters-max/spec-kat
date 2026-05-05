---
id: pattern/graph-session-projection
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- enforcement
- write-path
- pipeline
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
- raw/Memory Layer and Invariant Management.md
---
# Graph Session Projection

## Summary

GraphSessionProjection — L1-проекция в [[projection-registry]], хранящая протокольное состояние агента в рамках TaskRun: `has_graph`, `has_explain`, `graph_fingerprint`, `total_writes`. Вычисляется из EventLog (State = reduce(EventLog)). [[execution-guard]] остаётся stateless — state читается через ProjectionReader при каждом вызове.

## How It Works

**Event → State mapping:**

```text
GraphResolved   → has_graph = true,  graph_fingerprint = event.fingerprint
ExplainExecuted → has_explain = true, fingerprint_locked = event.fingerprint
WriteExecuted   → total_writes += 1,  has_graph = false, has_explain = false
TaskCompleted   → финальный snapshot фиксируется без изменения флагов
```

**`total_writes`** — накопительный счётчик write-циклов для audit метрик. Per-cycle сброс не нужен. THRASHING guard **удалён** — ограничение числа циклов перенесено в [[policy-projection]] как behavioral rule:

```python
cycles = memory.read.trace(task_id).write_cycles
limit  = memory.read.policy().max_write_cycles_per_task
if cycles > limit:
    return DENY("MAX_WRITE_CYCLES_EXCEEDED")  # severity из policy: RETRY / HUMAN_GATE
```

Guard не хранит счётчик сам — читает из [[trace-projection]] и [[policy-projection]].

**Семантика WriteExecuted reset:** сброс `has_graph/has_explain` в `false` — намеренный протокольный инвариант. Каждый write-цикл требует нового `resolve → explain`.

**Семантика TaskCompleted:**

```text
Финальное значение флагов НЕ является признаком протокольной корректности.

Протокольная корректность = audit metric:
  total_writes > 0
  + отсутствие GuardViolation в TraceProjection
```

**Метод чтения** (stateless read в [[execution-guard]]):

```python
GraphSessionState.current(task_id: str, reader: ProjectionReader) -> GraphSessionState
```

SELECT из GraphSessionProjection. Краш → рестарт → читаем ProjectionReader → state восстановлен.

## When To Use

Всегда, когда нужно проверить протокольное состояние агента для `task_id`: перед `explain` (нужен `has_graph = true`), перед `write` (нужен `has_explain = true`). Behavioral limits (write cycles) — через [[policy-projection]].

## Trade-offs

**Плюсы:** нет исключений из State = reduce(EventLog); [[execution-guard]] stateless; crash recovery бесплатен; `total_writes` даёт audit метрику без per-cycle overhead.

**Минусы:** каждый вызов ExecutionGuard — SELECT к PostgreSQL; `GraphResolved`, `ExplainExecuted`, `WriteExecuted` требуют формализации в Spec.

## See Also

- [[projection-registry]] — инфраструктура L1 проекций
- [[execution-guard]] — stateless consumer
- [[policy-projection]] — источник MAX_WRITE_CYCLES limit
- [[trace-projection]] — смежная проекция (write_cycles для behavioral check)
- [[memory-layer]] — фасад доступа к state
