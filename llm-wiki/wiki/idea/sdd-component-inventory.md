---
id: idea/sdd-component-inventory
page_type: idea
domain: sdd
layer: architecture
tags:
- ssot
- enforcement
- pipeline
- automation
- domain/sdd
version: 4
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/SDD_Bounded_Contexts_Plan.md
---
# SDD Component Inventory

Полный инвентарь блоков SDD-системы — «конституция», от которой пляшут все последующие имплементации.

## Summary

35 блоков (30 base + 5 proposed), разбитых по трём слоям (L0/L1/L2) и четырём доменам (Core/Blueprint/Engine/Intelligence). Каждый компонент = (Layer, Domain). Документ получен через архитектурный допрос (grill-me session) по спекам v65–83, дополнен bounded contexts анализом.

**SDD = детерминированный runtime для недетерминированного LLM.** L0 — жёсткий каркас, внутри которого агент обретает свободу.

- **I-COMP-1**: Each component MUST belong to exactly one domain.

## How It Works

```text
L0 — Execution Core (13 блоков) | Domain: Core
  EventLog, Reducer, State, Command+CommandContext,
  L0 Guards, CommandRegistry, CommandBus, WriteKernel,
  EventStore Guard, UpcasterRegistry, ErrorEvent,
  ProjectionRegistry, Graph/SpatialIndex

L1 — Harness Core (14 блоков)
  Domain: Core
    QueryEngine, ExecutionGuard, ScopeGuard, TraceStore,
    ErrorClassifier, Session Orchestrator, ContextKernel,
    InputPort, AgentHandle, SandboxManager,
    IdempotencyMiddleware, IdempotencyProjection,
    MemoryLayer [new, proposed]
  Domain: Blueprint
    PolicyKernel  ← L1 (применяет policy в runtime; не генерирует её)

L2 — Extensions (8 блоков)
  Domain: Blueprint [proposed]
    SpecManager, PlanManager, PhaseOrchestrator, ConstitutionParser
  Domain: Intelligence
    AuditEngine, MetaOptimization, ScenarioGen, RAG
```

Граница между слоями:

- L0 не зависит от L1/L2 (GL-5)
- L2 доступен только через CommandBus + ReadModel (GL-10)
- Правила L0 — только code-enforced, никаких declarative overrides
- L1 = runtime execution; L2 = decision / planning / analysis

Domain ownership: каждый блок принадлежит ровно одному домену. Для вертикального разреза (domain boundaries, contracts, seams) см. [[sdd-bounded-contexts]].

## When To Use

Читать перед началом любой новой фазы, спеки или имплементации блока SDD. Является точкой истины при конфликте между описаниями в разных документах.

## Trade-offs

- Документ декларативный — реальный статус реализации каждого блока нужно проверять в коде.
- 21 из 35 блоков ещё не реализованы на момент обновления (5 proposed + 16 base).

## Open Questions

- [ ] (P1) Q61: Какова схема идентификаторов для каждой сущности? (T-034, P-012). Auto-increment или детерминированный hash?
- [ ] (P1) Q62: Если агент дважды создаёт спеку "Auth Module" — дедупликация по имени/hash или два документа?
- [ ] (P1) Q63: Спека изменилась — новый документ или новая версия? История в EventLog или Git-like commits?
- [ ] (P1) Q64: Как выражается Project→Phase→Task→Step в ID? Composite keys? Flat global IDs?
- [ ] (P1) Q65: Как задача ссылается на спеку из которой порождена? Bidirectional traceability?
- [ ] (P2) Q154: Разные DB, разные schemas или изоляция через project_id в таблицах?
- [ ] (P2) Q155: Canonical layout SDD-проекта? `.sdd/eventlog/`, `.sdd/projections/`, `specs/`, `src/`, `tests/`?
- [ ] (P2) Q156: Что в `~/.sdd/config.yaml` vs `project/.sdd/config.yaml`?
- [ ] (P2) Q157: `sdd switch project-B`. Как Memory Layer понимает чьи projections читать?
- [ ] (P2) Q158: Может ли Проект А импортировать спеку или policy из Проекта Б? Механика?
- [ ] (P2) Q176: Canonical процедура запуска нового SDD-проекта с нуля? `sdd init` команда?
- [ ] (P2) Q177: Что минимально необходимо для первого TaskRun? (DB, config, schema, initial phase)
- [ ] (P2) Q178: Как перевести существующий проект на SDD? Импорт истории?
- [ ] (P2) Q179: Есть ли готовые шаблоны спек/планов для типовых фаз (auth, CRUD, API)?
- [ ] (P2) Q180: Где human-читаемый getting started guide? Как поддерживается в актуальности?

## See Also

- [[sdd-meta-harness]]
- [[sdd-bounded-contexts]]
- [[global-laws]]
- [[sdd-actor-model]]
- [[event-sourcing]]
- [[session-orchestrator]]
- [[audit-engine]]
- [[idempotency-middleware]]
- [[idempotency-projection]]
- [[memory-layer]]
- [[spec-manager]]
- [[plan-manager]]
- [[phase-orchestrator]]
- [[constitution-parser]]
