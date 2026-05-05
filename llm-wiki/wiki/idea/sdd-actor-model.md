---
id: idea/sdd-actor-model
page_type: idea
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- automation
- llm
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
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

## See Also

- [[agent-handle]]
- [[input-port]]
- [[session-orchestrator]]
- [[policy-kernel]]
- [[sdd-component-inventory]]
