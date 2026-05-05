---
id: idea/graph-session-state
page_type: idea
domain: sdd
layer: architecture
tags: [enforcement, pipeline, write-path, domain/sdd]
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/sdd-v2-architecture-deepening.md
---
# Graph Session State

Протокольное состояние агента в рамках одного TaskRun: прошёл ли агент обязательный цикл `resolve → explain → write`. В sdd_v2 реализуется как L0 Projection ([[graph-session-projection]]) в [[projection-registry]] — вычисляется из EventLog, не хранится в памяти.

## How It Works

**Структура:**

```yaml
GraphSessionState:
  task_id          : string
  graph_fingerprint: string   # зафиксирован после ExplainExecuted
  has_graph        : bool
  has_explain      : bool
  writes_count     : int
```

**Lifecycle через события (sdd_v2):**

```text
GraphResolved    → has_graph = true,  graph_fingerprint = event.fingerprint
ExplainExecuted  → has_explain = true, fingerprint_locked = event.fingerprint
WriteExecuted    → writes_count += 1,  has_graph = false, has_explain = false
TaskCompleted    → snapshot фиксируется без изменения флагов
```

`graph_fingerprint` фиксируется при `ExplainExecuted` и верифицируется при `WriteExecuted` — если граф изменился после explain, write блокируется [[execution-guard]].

**Reset при WriteExecuted:** сброс `has_graph/has_explain` означает что каждый следующий write требует нового цикла `resolve → explain`. При `TaskCompleted` флаги не сбрасываются — snapshot фиксирует финальное состояние (`has_graph = false, has_explain = false, writes_count = N`). Признак протокольного завершения = `writes_count > 0` + отсутствие GuardViolation в [[trace-projection]].

**Recovery:** [[execution-guard]] читает [[graph-session-projection]] через `ProjectionReader` при каждом вызове. Краш агента → рестарт → читаем проекцию → состояние восстановлено без специального кода.

## When To Use

Используется [[execution-guard]] при каждой команде агента. В sdd_v2 доступ только через [[graph-session-projection]] (SELECT из ProjectionRegistry) — нет прямого in-memory объекта.

## Trade-offs

**In-memory (оригинал):** быстро, но теряется при краше; recovery не специфицирован как интерфейс; нарушает принцип `State = reduce(EventLog)`.

**L0 Projection (sdd_v2):** State вычисляется из EventLog — нет исключений из базового принципа; [[execution-guard]] stateless; crash recovery бесплатен; требует новых типов событий (`GraphResolved`, `ExplainExecuted`, `WriteExecuted`) в Spec.

## See Also

- [[graph-session-projection]] — реализация как L0 Projection в sdd_v2
- [[execution-guard]] — единственный consumer
- [[projection-registry]] — инфраструктура проекций
- [[replay-based-testing]] — тестирование через replay событий
- [[graph-query-engine]]
