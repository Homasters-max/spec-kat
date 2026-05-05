---
id: pattern/session-orchestrator
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- enforcement
- write-path
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
---
# Session Orchestrator

L1-компонент: chains stateless sessions, проверяет human gates в EventLog перед стартом каждой сессии, делегирует выполнение [[agent-loop]].

## How It Works

Нет постоянно живущего loop (GL-9). Session Orchestrator = оркестратор между сессиями:

```text
[Human starts session]
    ↓
Orchestrator.start():
  1. check EventLog: human gate cleared?
     → если нет → emit HumanGateReached, stop
  2. determine session type (IMPLEMENT / VALIDATE / ...)
  3. load current state via ReadModel
  4. initialize ContextKernel
  5. create SandboxManager.create(task_id)
  6. AgentHandle.start(model, config)
  7. AgentLoop.run(phase_id, agent_handle) → LoopOutcome
     ↓
Orchestrator.complete():
  ветвление по LoopOutcome (см. ниже)
```

**LoopOutcome ветвление:**

| LoopOutcome | Действие |
|-------------|----------|
| `COMPLETE` | `SandboxManager.commit()`; `AuditEngine.calculate()`; `ScenarioGen.build()`; emit `SessionCompleted`; suggest next session |
| `GATE` | `SandboxManager.freeze(ttl=policy.gate_freeze_ttl_hours)`; human уведомляется; новый [[agent-loop]] при возобновлении работает в том же Sandbox (unfreeze); по истечении TTL → discard + ErrorEvent |
| `CORE_ABORT` | `SandboxManager.discard()` немедленно; сессия закрывается без AuditEngine; ErrorEvent уже в EventLog |
| `PROTOCOL_ABORT` | AuditEngine запускается (M1-M8, M9=0 принудительно); результат для MetaOptimization; `SandboxManager.discard()`; сессия закрывается |

**Human gate check:** Orchestrator читает EventLog через ReadModel и ищет `HumanGateCleared` events. Если gate не очищен → `HumanGateReached` event + stop. Никакого active polling нет — human инициирует следующую сессию вручную.

## When To Use

Является точкой входа для каждой новой сессии. Управляет lifecycle всех L1-компонентов в рамках одного TaskRun.

## Trade-offs

- Нет persistent loop → нет overhead от долгоживущего процесса, но нет и автоматического продолжения.
- Human должен явно инициировать каждую сессию — intentional design, не ограничение.
- GATE freeze vs discard: freeze сохраняет контекст для возобновления; TTL предотвращает бесконечно висящие Sandbox.

## See Also

- [[agent-loop]]
- [[loop-outcome]]
- [[agent-handle]]
- [[context-kernel]]
- [[sandbox-manager]]
- [[audit-engine]]
- [[classified-recovery]]
- [[sdd-component-inventory]]
