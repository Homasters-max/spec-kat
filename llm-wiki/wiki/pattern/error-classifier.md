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
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
---
# ErrorClassifier

L1-компонент: классифицирует CommandResult в одну из четырёх recovery-стратегий. Budget enforcement остаётся в [[agent-loop]].

## How It Works

```python
def classify(result: CommandResult, loop_state: LoopState) -> RecoveryStrategy:
    ...
```

`loop_state` передаётся для доступа к policy — классификатор читает policy для context-зависимых решений, но **не управляет счётчиками** (это задача DECIDE в [[agent-loop]]).

**Полный category mapping:**

| Категория | `error_type` | Стратегия |
|-----------|-------------|-----------|
| Graph errors | `TASK_ISOLATED`, `NO_PATH`, `CONTEXT_STALE`, `GRAPH_CHANGED_AFTER_EXPLAIN` | `RE_EXPLAIN` |
| Transient errors | `TIMEOUT`, `RATE_LIMIT` | `RETRY` |
| Policy/scope violations | `SCOPE_VIOLATION`, `PERMISSION_DENIED` | `HUMAN_GATE` |
| L0 invariant violations | `DIRECT_EVENTSTORE_ACCESS`, `WRITE_KERNEL_FAILURE`, `REDUCER_ERROR` | `ABORT` |
| Unknown / unclassified | любой `error_type` не в списках выше | `ABORT` → `PROTOCOL_ABORT` |

Unknown → ABORT — fail-safe: неизвестная ошибка не должна продолжать loop.

**Стратегии:**

- `RETRY` — агент получает rejection reason как structured feedback, [[agent-loop]] повторяет STEP
- `RE_EXPLAIN` — обязателен новый цикл resolve+explain; [[agent-loop]] переходит в PLAN
- `HUMAN_GATE` — [[session-orchestrator]] получает `LoopOutcome.GATE`, сессия pauses
- `ABORT` — [[agent-loop]] переходит в PROTOCOL_ABORT или CORE_ABORT в зависимости от природы ошибки

Каждое решение классификатора записывается как `ErrorClassified` event — полный аудит.

## When To Use

Вызывается из DECIDE-состояния [[agent-loop]] при `result.status == "ERROR"`. Budget enforcement (проверка `retry_counts` vs `retry_budget`) остаётся в `decide()` — не здесь.

## Trade-offs

- UNKNOWN → ABORT (fail-safe): предсказуемое завершение лучше бесконечного RETRY в неизвестном состоянии.
- Нет `MAX_RETRIES` хардкода — retry budgets управляются через [[loop-policy]] в [[policy-projection]].
- `loop_state` в сигнатуре: открывает доступ к policy без глобального состояния.

## See Also

- [[agent-loop]]
- [[classified-recovery]]
- [[loop-policy]]
- [[session-orchestrator]]
- [[execution-guard]]
