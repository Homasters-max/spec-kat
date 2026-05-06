---
id: pattern/plan-manager
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- validation
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SDD_Bounded_Contexts_Plan.md
---
# PlanManager

**[proposed]** L2-компонент Blueprint-домена: строит и валидирует детерминированный граф исполнения фазы.

## How It Works

**Dependency DAG**: задачи — это DAG, не список. Зависимости между задачами enforced при построении плана. Циклические зависимости → reject.

**Scope Isolation**: вычисляет `write_scope` для каждой задачи → `TaskScopeProjection` (используется [[sandbox-manager]] для изоляции). Scope = множество файлов/ресурсов, которые задача может изменять.

**Conflict Detection**: запрещает параллельные задачи с пересекающимися `write_scope`. Конфликт → plan rejected.

```text
PlanCreationCommand → PlanManager
  ├─ build task DAG (validate no cycles)
  ├─ compute write_scope per task
  ├─ detect write_scope conflicts for parallel tasks
  ├─ emit PlanCreated (только при успехе)
  └─ update TaskScopeProjection
```

`TaskScopeProjection` читается Engine через `memory.blueprint.read.task_scope(task_id)`.

## When To Use

При создании плана для фазы. Единственный путь к `PlanCreated` event и `TaskScopeProjection`.

## Trade-offs

- DAG-структура сложнее simple list, но предотвращает undefined execution order.
- write_scope computation требует явного объявления scope в задаче — дополнительная нагрузка при написании планов.

## See Also

- [[sdd-bounded-contexts]] — Blueprint domain, L2
- [[spec-manager]] — спека, из которой порождается план
- [[phase-orchestrator]] — читает TaskScopeProjection для next-task determination
- [[memory-layer]] — `memory.blueprint.read.task_scope(task_id)`
- [[sandbox-manager]] — потребитель TaskScopeProjection
