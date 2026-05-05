---
id: idea/global-laws
page_type: idea
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
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# Global Laws

10 неизменяемых законов SDD-системы. Нарушение любого → ERROR.

## Summary

Global Laws — это уровень выше инвариантов. Инварианты описывают конкретные правила поведения компонентов; Global Laws описывают фундаментальные свойства всей системы.

## How It Works

```text
GL-1 Determinism:  StateN = reduce(EventLog₀…N)
GL-2 SSOT:         EventLog — единственный источник истины
GL-3 Pipeline:     Command → Guard(L0) → Guard(L1) → handle → Event → Reducer → State
GL-4 Projection:   Projection := f(EventLog, Code)
GL-5 Isolation:    L0 не зависит от L1/L2
GL-6 Write Gate:   write разрешён только после start-task + resolve + explain + file ∈ write_scope
GL-7 EventStore:   event_store.append() доступен ТОЛЬКО из Command handlers
GL-8 Sandbox:      каждый TaskRun исполняется в изолированном окружении
GL-9 Agent Loop:   нет постоянно живущего loop — Session Orchestrator chains stateless sessions
GL-10 L2 Access:   L2 компоненты доступны только через CommandBus + ReadModel
```

GL-1 и GL-2 формируют основу event sourcing. GL-3 определяет порядок исполнения. GL-4 делает проекции детерминированными. GL-5 гарантирует независимость ядра. GL-6..GL-10 описывают поведенческие ограничения на агента и систему.

## When To Use

При проектировании нового компонента или фазы: проверить что ни один из GL не нарушается. При code review: нарушение GL = блокирующий комментарий.

## Trade-offs

- GL неизменяемы по определению. Если GL нужно изменить — это новая версия системы, не патч.

## See Also

- [[event-sourcing]]
- [[eventstore-guard]]
- [[sandbox-manager]]
- [[session-orchestrator]]
- [[sdd-component-inventory]]
