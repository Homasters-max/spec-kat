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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# SDD Meta Harness

Трёхуровневая архитектура исполнения агентских задач, обеспечивающая детерминизм, replay и контроль поведения.

## How It Works

Система построена на трёх слоях:

- **L0 — Execution Core**: `⟨EventLog, Reducer, State, Command, CommandContext, Guard⟩` — единственный источник истины, чистые функции, без side-effects.
- **L1 — Harness Core**: `⟨Graph, QueryEngine, TraceStore, ExecutionGuard, ScopeGuard⟩` — детерминированные проекции, контроль поведения агента.
- **L2 — Extensions**: `⟨RAG, Policies, MetaOptimization⟩` — доступ только через `CommandBus + ReadModel`, не нарушает L0.

**Global Laws (неизменяемые):**

```text
GL-1 Determinism:  StateN = reduce(EventLog₀…N)
GL-2 SSOT:         EventLog — единственный источник истины
GL-3 Pipeline:     Command → Guard(L0) → Guard(L1) → handle → Event → Reducer → State
GL-4 Projection:   Projection := f(EventLog, Code)
GL-5 Isolation:    L0 не зависит от L1/L2
GL-6 Write Gate:   write разрешён только после start-task + resolve + explain + file ∈ write_scope
```

**Полный execution flow:**

```python
guards_L0.check(state, cmd, ctx)        # 1. state invariants
execution_guard.check(trace, gss, cmd)  # 2. behavior protocol
events = handle(cmd, state, ctx)        # 3. pure handler
event_store.append(events)              # 4. atomic commit
for e in events:
    state = reduce(state, upcast(e))    # 5. state update
scope_guard.check(trace, task)          # 6. file scope (write-команды)
```

## When To Use

Когда нужно управлять исполнением агентских задач с гарантиями: детерминизм, объяснимость каждого write, контроль области файлов.

## Trade-offs

- Каждый write требует цикла `resolve → explain → write` — overhead для тривиальных изменений.
- L0 не зависит от L1, но L1 guards всегда вызываются после L0 — нельзя обойти порядок.
- function/class узлы графа отложены до v2.1+.

## See Also

- [[event-sourcing]]
- [[reducer]]
- [[graph-query-engine]]
- [[execution-guard]]
- [[scope-guard]]
- [[trace-store]]
- [[upcaster-registry]]
- [[replay-based-testing]]
