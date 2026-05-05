---
id: pattern/meta-optimization
page_type: pattern
domain: sdd
layer: architecture
tags: [automation, pipeline, llm, validation, domain/sdd]
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# MetaOptimization

L2-компонент: feedback loop над поведением агента. Анализирует TraceStore + AuditEngine output → генерирует Policy proposals → human approval → PolicyUpdated event.

## How It Works

```text
TraceStore (накопленные трейсы)
  +
AuditEngine (AgentScore M1–M9 по задачам)
  ↓
MetaOptimization.analyze():
  - находит паттерны ошибок (какие error_type встречаются чаще)
  - коррелирует AgentScore с model_version
  - сравнивает эффективность политик (retry limits, scope rules)
  ↓
Policy proposals → [HUMAN_GATE]
  ↓
Human approves → PolicyKernel.emit(PolicyUpdated)
  ↓
Guards читают новую политику через ReadModel
```

**Пример proposal:**

```yaml
proposal_id: MP-034
analysis: "RETRY стратегия срабатывает 40% задач фазы 28; MAX_RETRIES=3 → HUMAN_GATE слишком рано"
suggestion: "увеличить MAX_RETRIES до 5 для error_type=NO_EXPLAIN_BEFORE_WRITE"
evidence:
  - task_ids: [T-028-01, T-028-03, T-028-07]
  - avg_retries_before_success: 4.2
approved_by: null  # ожидает human review
```

**Доступ только через CommandBus + ReadModel** (GL-10) — MetaOptimization не читает EventLog напрямую.

## When To Use

Запускается после завершения фазы (Phase complete gate). Не запускается внутри TaskRun — только между сессиями.

## Trade-offs

- Proposals требуют human approval — нет автоматического применения политик.
- Качество proposals зависит от накопленной статистики — нужны минимум N задач для значимых выводов.
- Не является real-time системой — это batch analysis между фазами.

## See Also

- [[policy-kernel]]
- [[audit-engine]]
- [[trace-store]]
- [[classified-recovery]]
- [[sdd-actor-model]]
