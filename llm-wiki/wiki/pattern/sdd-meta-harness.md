---
id: pattern/sdd-meta-harness
page_type: pattern
domain: sdd
layer: architecture
tags:
- event-sourcing
- pipeline
- ssot
- enforcement
- llm
- domain/sdd
version: 4
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
---
# SDD Meta Harness

Трёхуровневая архитектура исполнения агентских задач: детерминированный runtime для недетерминированного LLM.

## How It Works

**SDD = детерминированный runtime для non-deterministic LLM.** L0 — жёсткий каркас, L1 — контроль поведения, L2 — intelligence extensions.

```text
L0 — Execution Core (неизменяемое ядро):
  EventLog, Reducer, State, Command+CommandContext, L0 Guards,
  CommandRegistry, CommandBus, WriteKernel, EventStore Guard,
  UpcasterRegistry, ErrorEvent, ProjectionRegistry,
  Graph/SpatialIndex  ← проекция EventLog+Code, не behavioral

L1 — Harness Core (контроль поведения агента, 12 компонентов):
  QueryEngine, ExecutionGuard, ScopeGuard, TraceProjection,
  ErrorClassifier, Session Orchestrator, ContextKernel,
  InputPort, AgentHandle, AgentLoop, LoopTrace,
  SandboxManager, AuditEngine

L2 — Extensions (только через CommandBus + ReadModel):
  RAG, PolicyKernel, MetaOptimization, ScenarioGen
```

**Global Laws:**

```text
GL-1 Determinism:  StateN = reduce(EventLog₀…N)
GL-2 SSOT:         EventLog — единственный источник истины
GL-3 Pipeline:     Command → Guard(L0) → Guard(L1) → handle → Event → Reducer → State
GL-4 Projection:   Projection := f(EventLog, Code)
GL-5 Isolation:    L0 не зависит от L1/L2
GL-6 Write Gate:   write разрешён только после start-task + resolve + explain + file ∈ write_scope
GL-7 EventStore:   event_store.append() — только из Command handlers
GL-8 Sandbox:      каждый TaskRun в изолированном окружении
GL-9 Agent Loop:   нет persistent loop — Session Orchestrator chains stateless sessions
GL-10 L2 Access:   L2 только через CommandBus + ReadModel
```

**Полный execution flow:**

```python
# Session Orchestrator запускает TaskRun:
sandbox    = SandboxManager.create(task_id)
agent      = AgentHandle.start(model, config)
agent_loop = AgentLoop(phase_id=phase_id, agent_handle=agent)

# AgentLoop управляет внутренним циклом:
outcome = agent_loop.run()   # FSM: PLAN → STEP → OBSERVE → DECIDE → ...

# Session Orchestrator ветвится по LoopOutcome:
# COMPLETE      → commit + AuditEngine + ScenarioGen
# GATE          → SandboxManager.freeze(ttl=policy.gate_freeze_ttl_hours)
# CORE_ABORT    → SandboxManager.discard(); сессия закрывается без AuditEngine
# PROTOCOL_ABORT→ AuditEngine (M1-M8, M9=0); SandboxManager.discard()
```

**AgentLoop внутренний цикл (детали — см. [[agent-loop]]):**

```python
# Каждый шаг:
tool_call = agent.step(context)          # LLM → tool call
AgentLoop.validate(tool_call)            # structural + policy validation
result    = CommandBus.dispatch(tool_call)
strategy  = ErrorClassifier.classify(result, loop_state)
# RETRY / RE_EXPLAIN / HUMAN_GATE / ABORT
LoopStepRecorded → EventStore           # replay-safe decision log (LOOP-2)
```

## When To Use

Читать как архитектурный обзор системы. Для деталей каждого компонента — см. отдельные страницы.

## Trade-offs

- Каждый write требует цикла `resolve → explain → write` — overhead для тривиальных изменений.
- L0 не зависит от L1, но L1 guards всегда вызываются после L0 — нельзя обойти порядок.
- Graph находится в L0 (не L1): это проекция-SSOT, QueryEngine (L1) делает запросы к Graph.
- AgentLoop отделён от AgentHandle: control logic и LLM API wrapper — разные зоны ответственности.

## See Also

- [[sdd-component-inventory]]
- [[global-laws]]
- [[event-sourcing]]
- [[reducer]]
- [[command-bus]]
- [[session-orchestrator]]
- [[agent-loop]]
- [[loop-outcome]]
- [[execution-guard]]
- [[audit-engine]]
- [[trace-store]]
- [[trace-projection]]
- [[commit-discard-gate]]
- [[metric-collector]]
- [[upcaster-registry]]
- [[replay-based-testing]]
