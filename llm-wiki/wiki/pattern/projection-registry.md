---
id: pattern/projection-registry
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- write-path
- pipeline
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# ProjectionRegistry

L0-компонент: синхронно обновляет все materialized PostgreSQL projections при каждом EventLog append. Заменяет legacy `State_index.yaml`.

## How It Works

```python
class ProjectionRegistry:
    projections: list[Projection]

    def sync(self, events: list[Event], conn: Connection) -> None:
        for projection in self.projections:
            for event in events:
                projection.apply(event, conn)
        # всё — одна транзакция с EventLog append
```

**Атомарность:** ProjectionRegistry.sync() вызывается внутри той же PostgreSQL транзакции что и `EventStore.append()`. Нет window где EventLog обновлён, а проекции — нет.

**Зарегистрированные проекции:**

```text
PhaseStateProjection      → таблица phase_states
TaskStateProjection       → таблица task_states
GraphSessionProjection    → таблица graph_sessions   (новые события)
PolicyProjection          → таблица policy_rules
AuditProjection           → таблица audit_summaries
SessionProjection         → таблица session_states
```

**ReadModel** = набор SQL queries поверх этих таблиц. Компоненты L1/L2 читают через ReadModel, не через replay EventLog.

## When To Use

Прозрачно для вызывающего кода — активируется автоматически внутри WriteKernel при каждом `execute_and_project()`.

## Trade-offs

- Синхронный sync увеличивает latency каждого append, но гарантирует консистентность.
- Добавление новой проекции = регистрация в ProjectionRegistry + миграция таблицы.
- `State_index.yaml` deprecated — не использовать как источник правды.

## See Also

- [[event-sourcing]]
- [[reducer]]
- [[command-bus]]
- [[sdd-component-inventory]]
