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
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/Memory Layer and Invariant Management.md
---
# ProjectionRegistry

L0-компонент: синхронно обновляет L1 materialized PostgreSQL projections при каждом EventLog append. Маршрутизирует события к проекциям по явному списку `subscribed_commands` — O(1) lookup.

## How It Works

**Регистрация с явным subscribed_commands:**

```python
class ProjectionRegistry:
    def register(
        projection: Projection,
        subscribed_commands: set[str]  # явный список, не флаги CommandSpec
    ) -> None: ...

# Регистрация проекций:
registry.register(TraceProjection(),         {"resolve", "explain", "write"})
registry.register(GraphSessionProjection(),  {"resolve", "explain", "write", "complete-task"})
registry.register(PolicyProjection(),        {"update-policy", "bootstrap-policy"})
registry.register(PhaseStateProjection(),    {"activate-phase", "complete-phase"})
registry.register(TaskStateProjection(),     {"start-task", "complete-task", "fail-task"})
registry.register(AuditProjection(),         {"complete-task", "validate", "guard-violation"})
registry.register(SessionProjection(),       {"record-session"})
```

**Routing:** WriteKernel при получении события делает lookup по типу команды → роутит только в подписанные проекции. O(1) вместо O(projections × events).

**Атомарность:** `ProjectionRegistry.sync()` вызывается внутри той же PostgreSQL транзакции что и `EventStore.append()`. Нет окна где EventLog обновлён, а L1 проекции — нет.

**Разделение concerns:**

```text
CommandSpec.affects_trace    → семантическая аннотация для Guards / AuditEngine (НЕ routing)
CommandSpec.graph_structural → семантика для GraphQueryEngine (НЕ routing)
subscribed_commands          → инфраструктурная маршрутизация WriteKernel (SSOT)
```

ProjectionRegistry не читает флаги из CommandSpec. Маршрутизация определяется только `subscribed_commands` при регистрации.

**L2 проекции (RAGProjection, [[embedding-projection]]) НЕ регистрируются в ProjectionRegistry** — они обновляются через outbox/async worker за пределами L1 транзакции. Это обеспечивает isolation failure (ML-9).

**Тест:** для каждой проекции → replay только событий из `subscribed_commands` → assert state.

## When To Use

Прозрачно для вызывающего кода — активируется автоматически внутри WriteKernel при каждом `execute_and_project()`. Добавление нового L1-компонента = регистрация новой проекции с явным `subscribed_commands` + миграция таблицы.

## Trade-offs

- O(1) routing (vs O(N×N) при фильтрации по флагам) — важно при росте числа проекций.
- Явный `subscribed_commands` — routing SSOT; изменение подписки требует явного кода, нет скрытых side-effects.
- L2 проекции вынесены за периметр — сбой async worker не откатывает L1 commit.

## See Also

- [[memory-layer]] — потребитель L1 projections через ReadModel
- [[policy-projection]] — L1 проекция behavioral rules
- [[trace-projection]] — L1 проекция истории шагов (affects_trace = семантика, не routing)
- [[embedding-projection]] — L2 проекция (НЕ в ProjectionRegistry)
- [[command-bus]]

## Open Questions

- [ ] (P1) Q88 PARTIAL: Нет explicit механизма обнаружения desync проекции и EventLog. Как обнаружить corruption?
- [ ] (P1) Q89 PARTIAL: Все ли projections консистентны между собой в одной точке времени? Нет explicit guarantee.
- [ ] (P1) Q90: Как обновить schema проекции без полного rebuild? Rolling migration?
- [ ] (P1) Q91: Разрешены ли projection dependencies (A зависит от B)? Какой порядок обновления?
- [ ] (P1) Q92: Какие projections держать в памяти, какие только в DB? SLA на cold projection read?
- [ ] (P1) Q93: Как тестировать детерминизм проекций? Property-based tests?

## Decisions

- [x] (P1) Q86: Sync vs async projections — sync inline в L1 → [[projection-registry]]
- [x] (P1) Q87: Rebuild trigger — проекции перестраиваются при rebuild → [[projection-registry]]
