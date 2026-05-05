---
id: pattern/error-classifier
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- validation
- pipeline
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# ErrorClassifier

L1-компонент: классифицирует guard failures в одну из четырёх recovery-стратегий.

## How It Works

```python
def classify(error: ErrorEvent, retry_count: int) -> RecoveryStrategy:
    if error.error_type in PROTOCOL_VIOLATIONS:
        if retry_count < MAX_RETRIES:
            return RETRY
        return HUMAN_GATE

    if error.error_type == "GRAPH_CHANGED_AFTER_EXPLAIN":
        return RE_EXPLAIN

    if error.error_type in L0_INVARIANT_VIOLATIONS:
        return ABORT

    return HUMAN_GATE  # unknown → safe default
```

**Стратегии:**

- `RETRY` — агент получает rejection reason как structured feedback, повторяет action
- `RE_EXPLAIN` — обязателен новый цикл resolve+explain перед следующим write
- `HUMAN_GATE` — Session Orchestrator emits `HumanGateReached`, session pauses
- `ABORT` — TaskRun завершается, Sandbox discards, `ErrorEvent` записывается в EventLog

**PROTOCOL_VIOLATIONS:**

```python
{"NO_EXPLAIN_BEFORE_WRITE", "NO_GRAPH_BEFORE_EXPLAIN", "THRASHING", "TASK_ISOLATED"}
```

**L0_INVARIANT_VIOLATIONS:**

```python
{"DIRECT_EVENTSTORE_ACCESS", "WRITE_KERNEL_FAILURE", "REDUCER_ERROR"}
```

Каждое решение классификатора записывается как `ErrorClassified` event — полный аудит.

## When To Use

Вызывается автоматически при любом rejected action в CommandBus. Является частью execution pipeline после L1 guards.

## Trade-offs

- MAX_RETRIES должен быть настраиваем через [[policy-kernel]] — жёсткое значение не подходит для всех задач.

## See Also

- [[classified-recovery]]
- [[execution-guard]]
- [[scope-guard]]
- [[session-orchestrator]]
- [[policy-kernel]]
