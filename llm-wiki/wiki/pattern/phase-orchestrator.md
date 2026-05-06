---
id: pattern/phase-orchestrator
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- write-path
- enforcement
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SDD_Bounded_Contexts_Plan.md
---
# PhaseOrchestrator

**[proposed]** L2-компонент Blueprint-домена: управляет макро-состоянием фазы. Coordinator, не Engine — принимает решения, но не исполняет их напрямую.

- **I-ORCH-1**: PhaseOrchestrator MUST be pure decision logic — no execution side-effects. All decisions output Commands or Events via CommandBus. All execution delegated to SandboxManager / AgentHandle / AuditEngine.

## How It Works

**Next Task**: читает `TaskScopeProjection` через `memory.blueprint.read.task_scope(task_id)`, определяет следующую задачу по DAG. Emits команду для Engine (через CommandBus, caller_domain="blueprint").

**Definition of Done**: проверяет критерии завершения фазы: все задачи выполнены + порог AgentScore достигнут. Если DoD met → emit `PhaseCompleted`.

**Cross-Phase Dependencies**: проверяет наличие артефактов от предыдущих фаз через MemoryLayer.

**Force Transition**: обрабатывает команду человека "перейти на следующую фазу" → emit `PhaseAbandoned`.

**Proposal Handling**: видит pending proposal (из Intelligence через `ProposalProjection`) → останавливает цикл → `HumanGateReached`.

```text
Polling: читает проекции в начале каждого AgentLoop цикла (не по таймеру)
Decision: emit Command via CommandBus (caller_domain="blueprint")
No inline conditions like "if phase == X do Y" — это нарушение I-ORCH-1
```

## When To Use

PhaseOrchestrator — единственный компонент, принимающий решение о следующей задаче фазы, завершении фазы или переходе к следующей. Engine не может инициировать фазовые переходы.

## Trade-offs

- Pure decision logic (I-ORCH-1) делает PhaseOrchestrator тестируемым без side-effects.
- Polling в начале AgentLoop cycle означает: решения принимаются на основе snapshot, не real-time state — staleness ≤ 1 iteration.

## Open Questions

- [ ] (P2) Как PhaseOrchestrator обрабатывает задачу с ошибкой — retry, skip, или abort фазы?

## See Also

- [[sdd-bounded-contexts]] — Blueprint domain, L2; I-ORCH-1
- [[plan-manager]] — поставляет TaskScopeProjection (DAG)
- [[memory-layer]] — `memory.blueprint.read.*`
- [[audit-engine]] — поставляет AgentScore для DoD check
- [[agent-loop]] — инфраструктура polling
- [[observability-events]] — HumanGateReached emit
