---
created: '2026-05-05'
domain: sdd
id: idea/sdd-actor-model
layer: architecture
page_type: idea
sdd_domain: Core
sdd_layer: L1
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
tags:
- enforcement
- pipeline
- automation
- llm
- domain/sdd
- sdd/l1
- sdd/core
updated: '2026-05-06'
version: 2
---
# SDD Actor Model

Два актора SDD-системы и их границы ответственности.

## Summary

SDD различает двух акторов: **Human** (архитектор правил + аудитор) и **LLM** (исполнитель). Harness — это не актор, а контроллер между ними.

## How It Works

```text
Human:
  ✓ activate-phase, approve spec
  ✓ резолвить HUMAN_GATE
  ✓ ревьюить MetaOptimization proposals
  ✓ CLI (все команды доступны)
  ✗ прямая запись в EventLog
  ✗ bypass guards

LLM:
  ✓ tool calls через InputPort
  ✓ resolve / explain / write внутри write_scope
  ✗ прямой CLI
  ✗ event_store.append() вне handler
  ✗ modify .sdd/specs/
  ✗ activate-phase без --executed-by llm
```

**Роли:**

- **Human** = архитектор правил (определяет политики, одобряет спеки) + аудитор (ревьюит AuditEngine output)
- **LLM** = исполнитель (реализует задачи, управляется через [[agent-handle]])
- **Harness** = контроллер: L0 обеспечивает каркас, L1 управляет поведением, L2 обеспечивает интеллект

Граница human/llm — это human gate: переход между сессиями требует явного действия человека или clearance в EventLog.

## When To Use

При любом вопросе "кто может это сделать?" — сверяться с этой моделью.

## Trade-offs

- LLM ограничен tool calls — нет прямого доступа к файловой системе вне [[sandbox-manager]].
- Human gates замедляют цикл, но обеспечивают supervision над критическими решениями.

## Open Questions

- [ ] (P0) Q24 PARTIAL: Может ли human override structural guard (не policy)? Механика не описана.
- [ ] (P2) Q138: Canonical список ролей агентов: Planner, Executor, Reviewer, Auditor. Могут ли переопределяться через PolicyKernel?
- [ ] (P2) Q139: Sequential vs Streaming паттерн оркестрации фазы. Где описывается?
- [ ] (P2) Q140: Reviewer имеет только read+comment, Executor — read+write? Где задаётся tool ACL?
- [ ] (P2) Q143: Как создаётся, передаётся и инвалидируется actor_id агента в сессии?

## See Also

- [[agent-handle]]
- [[input-port]]
- [[session-orchestrator]]
- [[policy-kernel]]
- [[sdd-component-inventory]]
