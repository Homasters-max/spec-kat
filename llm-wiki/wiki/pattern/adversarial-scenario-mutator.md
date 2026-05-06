---
id: pattern/adversarial-scenario-mutator
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
---
# AdversarialScenarioMutator

Генерирует `AdversarialScenario` из провальных задач через детерминированную мутацию. Статическая `MUTATION_TABLE`: `error_type → MutationStrategy`. Двухуровневая мутация: task_events (Tier 1/2) + ScenarioSpec checks (Tier 3). Детерминированность важнее гибкости — никакой LLM-генерации мутаций.

## How It Works

```python
MUTATION_TABLE: dict[str, MutationStrategy] = {
    "SCOPE_VIOLATION":              MutateScopeInEvents(),
    "GRAPH_CHANGED_AFTER_EXPLAIN":  ReorderEvents(),
    "TIMEOUT":                      InjectDelayEvents(),
    "PERMISSION_DENIED":            EscalatePayload(),
    # default: InvertCriticalChecks() для Tier 3
}

class AdversarialScenarioMutator:
    def mutate(
        self,
        failed_slice: TaskEventSlice,
        failed_spec: ScenarioSpec,
        error_type: str,
    ) -> AdversarialScenario:
        strategy = MUTATION_TABLE.get(error_type, InvertCriticalChecks())
        mutated_events = strategy.mutate_events(failed_slice.task_events)   # Tier 1/2
        mutated_checks = strategy.mutate_checks(failed_spec.checks)         # Tier 3
        return AdversarialScenario(
            source_task_id=failed_slice.task_id,
            mutated_events=mutated_events,
            adversarial_checks=mutated_checks,
        )
```

**Lifecycle (I-REPLAY-10):**

```text
Task FAILED
  → ErrorClassifier → error_type
  → MUTATION_TABLE[error_type] → MutationStrategy
  → AdversarialScenarioMutator.mutate()
      Tier 1/2: мутирует task_events (инвертирует payload, меняет порядок)
      Tier 3:   мутирует ScenarioSpec checks (инвертирует условия)
  → AdversarialScenario → Tier 3 Adversarial Suite
```

Adversarial scenarios — только из провальных задач. Успешные задачи → только [[scenario-gen]] (ScenarioGenerated).

## When To Use

Вызывается [[audit-engine]] при обработке FAILED TaskRun: adversarial failures входят как sub-метрика M9 в Tier 3 Regression Suite.

## Trade-offs

- MUTATION_TABLE статична — новые паттерны ошибок требуют явного добавления стратегии
- Детерминированность: при добавлении нового `error_type` без стратегии — fallback `InvertCriticalChecks()` применяется ко всем unknown типам

## See Also

- [[scenario-gen]]
- [[audit-engine]]
- [[error-classifier]]
- [[replay-based-testing]]
- [[task-event-slice]]
- [[mutation-registry]] — реестр ErrorCode → MutationStrategy, заменяет статический MUTATION_TABLE
