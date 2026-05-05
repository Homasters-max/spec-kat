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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# SDD Component Inventory

Полный инвентарь блоков SDD-системы — «конституция», от которой пляшут все последующие имплементации.

## Summary

28 блоков, разбитых по трём слоям: L0 (неизменяемое ядро), L1 (контроль поведения агента), L2 (intelligence extensions). Документ получен через архитектурный допрос (grill-me session) по спекам v65–83.

**SDD = детерминированный runtime для недетерминированного LLM.** L0 — жёсткий каркас, внутри которого агент обретает свободу.

## How It Works

```text
L0 — Execution Core (13 блоков):
  EventLog, Reducer, State, Command+CommandContext,
  L0 Guards, CommandRegistry, CommandBus, WriteKernel,
  EventStore Guard, UpcasterRegistry, ErrorEvent,
  ProjectionRegistry, Graph/SpatialIndex

L1 — Harness Core (11 блоков):
  QueryEngine, ExecutionGuard, ScopeGuard, TraceStore,
  ErrorClassifier, Session Orchestrator, ContextKernel,
  InputPort, AgentHandle, SandboxManager, AuditEngine

L2 — Extensions (4 блока):
  RAG, PolicyKernel, MetaOptimization, ScenarioGen
```

Граница между слоями:

- L0 не зависит от L1/L2 (GL-5)
- L2 доступен только через CommandBus + ReadModel (GL-10)
- Правила L0 — только code-enforced, никаких declarative overrides

## When To Use

Читать перед началом любой новой фазы, спеки или имплементации блока SDD. Является точкой истины при конфликте между описаниями в разных документах.

## Trade-offs

- Документ декларативный — реальный статус реализации каждого блока нужно проверять в коде.
- 16 из 28 блоков ещё не реализованы на момент создания (2026-05-05).

## See Also

- [[sdd-meta-harness]]
- [[global-laws]]
- [[sdd-actor-model]]
- [[event-sourcing]]
- [[session-orchestrator]]
- [[audit-engine]]
