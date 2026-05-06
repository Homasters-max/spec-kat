---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/l0
- enforcement
- ssot
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Layer L0 — Core Physics

## Summary

L0 определяет физику SDD-системы. Все write-операции проходят через L0. Никакой L1/L2 компонент не имеет прямого доступа к EventStore — только через CommandBus и WriteKernel.

## Ключевые компоненты L0

- [[event-sourcing]] — SSOT-механизм; всё состояние = reduce(events)
- [[write-kernel]] — единственная точка мутации EventLog; все side-effects здесь
- [[command-bus]] — маршрутизация команд → handlers
- [[command-spec]] — схема команды: idempotent-флаг, guards, required fields
- [[command-context]] — контекст выполнения команды (actor, phase_id, task_id)
- [[eventstore-guard]] — пре-условия на запись (idempotency, sequence)
- [[projection-registry]] — каталог всех проекций; rebuild через replay
- [[upcaster-registry]] — migration схемы событий при version bump
- [[reducer]] — pure function: (state, event) → state
- [[error-event]] — L0 обязан эмитить ErrorEvent перед raise (I-ERROR-1)
- [[global-laws]] — инварианты, применяемые ко всем событиям
- [[cqrs-boundary]] — физическая граница read/write путей
- [[optimistic-concurrency-control]] — конкурентный контроль на EventLog
- [[observability-events]] — события-маркеры для трассировки
- [[replay-engine]] — воспроизведение EventLog для восстановления state

## Ключевые инварианты

- I-1: All SDD state = reduce(events)
- I-2: All write commands execute via REGISTRY → execute_and_project
- I-3: All side-effects occur in Write Kernel only
- I-ERROR-1: WriteKernel MUST emit ErrorEvent before raising

## Антипаттерны

- Прямой вызов EventStore.append из L1/L2 компонента.
- Reducer с side-effects (не pure function).
- Guard-логика инлайн в handler вместо вызова через scope_policy.py.

## See Also

- [[sdd-layer-l1]]
- [[sdd-horizontal-slice]]
- [[sdd-domain-core]]
