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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Graph Session Projection

## Summary

GraphSessionProjection — L0-проекция в [[projection-registry]], заменяющая in-memory `GraphSessionState` в L1. Хранит протокольное состояние агента в рамках TaskRun: `has_graph`, `has_explain`, `graph_fingerprint`, `writes_count`. Вычисляется из EventLog (State = reduce(EventLog)), восстанавливается при краше без специального recovery кода. [[execution-guard]] становится полностью stateless.

## How It Works

**Event → State mapping:**

```text
GraphResolved   → has_graph = true,  graph_fingerprint = event.fingerprint
ExplainExecuted → has_explain = true, fingerprint_locked = event.fingerprint
WriteExecuted   → writes_count += 1,  has_graph = false, has_explain = false
TaskCompleted   → финальный snapshot фиксируется без изменения флагов
```

**Семантика WriteExecuted reset:** сброс `has_graph/has_explain` в `false` означает что для следующей записи агент обязан заново пройти `resolve → explain`. Это намеренный протокольный инвариант — каждый write-цикл независим.

**Семантика TaskCompleted:** финальный snapshot сохраняется как есть. Если последним событием был `WriteExecuted`, snapshot покажет `has_graph = false, has_explain = false, writes_count = N`. Это корректно — флаги отражают состояние после последнего write, не "была ли задача выполнена правильно". Признак протокольного завершения = `writes_count > 0` + отсутствие `GuardViolation` в [[trace-projection]].

**Метод чтения** (stateless read в [[execution-guard]]):

```text
GraphSessionState.current(task_id: TaskId, reader: ProjectionReader) -> GraphSessionState
```

Это SELECT из GraphSessionProjection. Краш → рестарт → читаем ProjectionReader → состояние восстановлено автоматически.

## When To Use

Всегда, когда нужно проверить протокольное состояние агента для конкретного `task_id`: перед `explain` (нужен `has_graph = true`), перед `write` (нужен `has_explain = true`), после `write` (state сброшен, нужен новый цикл).

## Trade-offs

**Плюсы:** State = reduce(EventLog) — нет исключений из этого принципа; [[execution-guard]] stateless — создаётся и уничтожается без потери контекста; replay-based-testing работает автоматически; crash recovery бесплатен.

**Минусы:** каждый вызов ExecutionGuard — SELECT к PostgreSQL (vs in-memory lookup); `GraphResolved`, `ExplainExecuted`, `WriteExecuted` — новые типы событий, требуют формализации в Spec.

**Аудит протокольности:** финальный `has_explain == false` при `TaskCompleted` не означает нарушение. Для проверки протокола нужен `writes_count > 0` + TraceProjection без `GuardViolation` записей.

## See Also

- [[projection-registry]] — инфраструктура проекций
- [[execution-guard]] — единственный consumer, становится stateless
- [[trace-projection]] — смежная проекция для write-истории
- [[graph-session-state]] — заменяемая in-memory структура
- [[replay-based-testing]] — тестирование через replay событий
