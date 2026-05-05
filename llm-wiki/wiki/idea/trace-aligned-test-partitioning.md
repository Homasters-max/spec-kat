---
id: idea/trace-aligned-test-partitioning
page_type: idea
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
---
# Trace-Aligned Test Partitioning (TATP)

Идея: тесты — данные в Projection, а не статические файлы. Тест каталогизируется по `affected_commands` и `affected_projections`. `git diff` + command mapping → точечный запуск только релевантных тестов.

## Суть идеи

Традиционный pytest запускает все тесты — 40 минут, непонятный fail из другой фазы. TATP строит живой индекс тестов через EventLog: каждый `golden-approve` и каждый `ScenarioGenerated` обновляют [[test-catalog-projection]].

`sdd test --diff HEAD~1` спрашивает: "какие команды изменились?" → "какие тесты покрывают эти команды?" → запускает только их.

## Три домена теста

Тесты делятся по `affected_projections`, что соответствует bounded context:

| Домен | Projections | Изолятор |
|-------|------------|---------|
| L0 Core | StateProjection | in-memory |
| L1 Execution | TraceProjection, GraphSessionProjection | temp PostgreSQL |
| L2 Governance | PolicyProjection | full SandboxManager |

Разработчик не выбирает уровень вручную — [[test-catalog-projection]] выводит его автоматически из `affected_projections` записи.

## Почему это работает

EventLog — SSOT (GL-2). Тест — это `(event_slice, expected_state, trace_assertions)`. Projection хранит маппинг `command → tests`. Когда handler команды меняется, все тесты для этой команды автоматически попадают в прогон.

## See Also

- [[test-catalog-projection]]
- [[replay-based-testing]]
- [[replay-engine]]
- [[golden-fixture]]
