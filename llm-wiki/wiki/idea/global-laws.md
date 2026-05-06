---
created: '2026-05-05'
domain: sdd
id: idea/global-laws
layer: architecture
page_type: idea
sdd_domain: Core
sdd_layer: L0
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
tags:
- ssot
- enforcement
- write-path
- pipeline
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-06'
version: 4
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
                   (Domain Events); Observability Events — легальное исключение,
                   медиируемое [[eventstore-guard]]
GL-8 Sandbox:      каждый TaskRun исполняется в изолированном окружении
GL-9 Agent Loop:   нет постоянно живущего loop — Session Orchestrator chains stateless sessions
GL-10 L2 Access:   L2 компоненты доступны только через CommandBus + ReadModel
```

GL-1 и GL-2 формируют основу event sourcing. GL-3 определяет порядок исполнения. GL-4 делает проекции детерминированными. GL-5 гарантирует независимость ядра. GL-6..GL-10 описывают поведенческие ограничения на агента и систему.


## Consistency Model

```text
Strong (within WriteKernel transaction):
  L1 reads within same transaction always see own writes.

Snapshot (L1 cross-transaction, cycle-bounded):
  Snapshot built once at AgentLoop.start(). Staleness bound: ≤ 1 AgentLoop iteration.

Eventual (L2 only):
  EmbeddingProjection, SemanticSearch — no staleness bound.
  L2 failure does NOT affect L1, Guards, or EventLog.
```

"Cycle-bounded" ≠ "eventually consistent" (Cassandra/DynamoDB): здесь staleness строго ограничен одним AgentLoop iteration.

- **I-CONSISTENCY-1**: Cross-domain consistency = cycle-bounded; only within-WriteKernel-transaction = strongly consistent

## When To Use

При проектировании нового компонента или фазы: проверить что ни один из GL не нарушается. При code review: нарушение GL = блокирующий комментарий.

## Trade-offs

- GL неизменяемы по определению. Если GL нужно изменить — это новая версия системы, не патч.

## Open Questions

- [ ] (P0) Q35: Запрет datetime.now() в handlers? Как внедрять clock abstraction? Тестирование с mock time?
- [ ] (P0) Q36: Что входит в reproducible environment snapshot? OS version, lib versions, DB version? Где фиксируется?
- [ ] (P0) Q37: Как автоматически проверяется, что reducer pure? Mutation testing? Property-based testing?
- [ ] (P0) Q38: Как ловить недетерминизм в runtime? Двойной запуск с проверкой идентичности output?
- [ ] (P1) Q109: Где хранится единый реестр всех инвариантов? CLAUDE.md таблица достаточна или нужен machine-checkable format?
- [ ] (P1) Q110: Есть ли DSL для invariants позволяющий автоматическую проверку — TLA+, Alloy, или custom YAML?
- [ ] (P1) Q111: Когда проверяются инварианты: pre-command, post-command, при replay? Должны ли быть все три?
- [ ] (P1) Q112: Старый EventLog нарушает новый инвариант. Migration event? Upcaster? Это breaking change?
- [ ] (P1) Q113: Как версионируются инварианты? Какие backward-compatible, какие breaking?
- [ ] (P1) Q114: Есть ли метрика покрытия инвариантов тестами? Enforcement gap analysis?
- [ ] (P1) Q115: Как обнаруживаются конфликты между инвариантами (I-X требует A, I-Y требует ¬A)?

- [ ] (P3) Q228: Есть ли математическая модель системы (state machine, temporal logic)? TLA+, Alloy?
- [ ] (P3) Q229: Можно ли формально доказать: ∀ EventLog, reduce(EventLog) детерминирован?
- [ ] (P3) Q230: Можно ли доказать eventual consistency projections при eventual EventLog delivery?
- [ ] (P3) Q231: Формальное доказательство: replay(EventLog) воспроизводит точно тот же State что и live execution?
- [ ] (P3) Q232: Используется ли model checking (TLA+) для проверки core invariants — deadlock freedom, safety, liveness?
- [ ] (P3) Q233: Где граница "мы верим в корректность" vs "мы доказали корректность"? Какие инварианты критичны для formal proof?

## Decisions

- [x] (P0) Q34: Randomness control — детерминизм по дизайну, GL-1; datetime.now() в handlers запрещён → [[global-laws]]
- [x] (P0) Q121: Randomness control — GL-1 запрещает любые нетерминированные вызовы → [[global-laws]]

## See Also

- [[event-sourcing]]
- [[sdd-bounded-contexts]]
- [[observability-events]]
- [[eventstore-guard]]
- [[sandbox-manager]]
- [[session-orchestrator]]
- [[sdd-component-inventory]]
