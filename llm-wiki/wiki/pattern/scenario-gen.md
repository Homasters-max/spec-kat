---
created: '2026-05-05'
domain: sdd
id: pattern/scenario-gen
layer: architecture
page_type: pattern
sdd_domain: Intelligence
sdd_layer: L2
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
tags:
- automation
- validation
- pipeline
- ssot
- domain/sdd
- sdd/l2
- sdd/intelligence
updated: '2026-05-05'
version: 2
---
# ScenarioGen

L2-компонент: детерминированная генерация ScenarioSpec из завершённых задач. Ground truth для M9 (execution_correctness).

## How It Works

```python
class ScenarioGen:
    def build(self, task_artifacts: TaskArtifacts) -> ScenarioSpec:
        # task_artifacts = trace + summary + outputs
        checks = self._extract_checks(task_artifacts)
        return ScenarioSpec(
            task_id=task_artifacts.task_id,
            checks=checks,
            critical_checks=[c for c in checks if c.critical],
        )
```

**ScenarioSpec:**

```yaml
task_id: T-034
checks:
  - id: check_01
    description: "EventLog содержит ровно 3 события"
    critical: true
    verifier: "event_count == 3"
  - id: check_02
    description: "State.phase_status == COMPLETE"
    critical: false
    verifier: "state.phase_status == 'COMPLETE'"
```

**Детерминизм:** одинаковые `task_artifacts` → идентичный `ScenarioSpec`. Нет рандомности в генерации.

**Использование:** ScenarioSpec хранится как `ScenarioGenerated` event в EventLog. AuditEngine читает через ReadModel при расчёте M9.

**Production → regression:** успешно завершённые задачи автоматически становятся regression suite — следующий раз когда аналогичная задача выполняется, M9 проверяет что она ведёт себя так же.

## When To Use

Вызывается Session Orchestrator'ом после `SandboxManager.commit()`. Если задача failed/discarded → ScenarioGen не вызывается (нет ground truth для неуспешных задач).

**Транзакционность (AD-2):** `complete-task` handler эмитит `ScenarioGenerated` только если `task.status == COMPLETE`. WriteKernel включает `TaskCompleted` + `ScenarioGenerated` в одну PostgreSQL транзакцию — нет окна где задача DONE, но ScenarioSpec ещё нет.

Контраст с [[adversarial-scenario-mutator]]: FAILED задачи → мутации для Tier 3 adversarial suite, не ScenarioSpec.

## Trade-offs

- ScenarioSpec quality = quality of task artifacts. Плохой trace → слабые checks.
- Не обнаруживает регрессии если задача решена по-другому но с тем же результатом.

## See Also

- [[audit-engine]]
- [[trace-store]]
- [[replay-based-testing]]
- [[session-orchestrator]]
- [[adversarial-scenario-mutator]]
