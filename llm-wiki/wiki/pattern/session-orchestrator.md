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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# Session Orchestrator

L1-компонент: chains stateless sessions, проверяет human gates в EventLog перед стартом каждой сессии.

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
     ↓
[Agent session runs]
     ↓
Orchestrator.complete():
  1. SandboxManager.commit() or discard()
  2. AuditEngine.calculate()
  3. ScenarioGen.build()
  4. emit SessionCompleted event
  5. suggest next session type
```

**Human gate check:** Orchestrator читает EventLog через ReadModel и ищет `HumanGateCleared` events. Если gate не очищен → `HumanGateReached` event + stop. Никакого active polling нет — human инициирует следующую сессию вручную.

## When To Use

Является точкой входа для каждой новой сессии. Управляет lifecycle всех L1-компонентов в рамках одного TaskRun.

## Trade-offs

- Нет persistent loop → нет overhead от долгоживущего процесса, но нет и автоматического продолжения.
- Human должен явно инициировать каждую сессию — intentional design, не ограничение.

## See Also

- [[agent-handle]]
- [[context-kernel]]
- [[sandbox-manager]]
- [[audit-engine]]
- [[classified-recovery]]
- [[sdd-component-inventory]]
