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
version: 3
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
- raw/error-model-architecture.md
---
# ErrorClassifier

L1-компонент: классифицирует `CommandResult` в [[classification-result]] — strategy + meta + origin. Budget enforcement остаётся в [[agent-loop]].

## How It Works

```python
def classify(result: CommandResult, loop_state: LoopState) -> ClassificationResult:
    meta = ERROR_REGISTRY.get(result.error_code)
    if meta is None:
        meta = ErrorMeta("ERROR", "UNKNOWN", None, None, "ABORT")
    return ClassificationResult(
        strategy=meta.default_strategy,
        meta=meta,
        origin="GUARD",   # classify() всегда GUARD; validate() выставляет VALIDATE_*
    )
```

`origin="GUARD"` — фиксированное значение в `classify()`. Только `AgentLoop.validate()` выставляет `VALIDATE_STRUCTURAL` или `VALIDATE_POLICY`. Classifier не знает о validate-пути.

**Полный category mapping (через ERROR_REGISTRY):**

| Категория | error_code | strategy |
|-----------|-----------|---------|
| Graph errors | `TASK_ISOLATED`, `NO_PATH`, `CONTEXT_STALE`, `GRAPH_CHANGED_AFTER_EXPLAIN` | `RE_EXPLAIN` |
| Transient errors | `TIMEOUT`, `RATE_LIMIT` | `RETRY` |
| Policy/scope violations | `SCOPE_VIOLATION`, `PERMISSION_DENIED` | `HUMAN_GATE` |
| Budget violation | `MAX_WRITE_CYCLES_EXCEEDED` | `HUMAN_GATE` |
| L0 invariant violations | `DIRECT_EVENTSTORE_ACCESS`, `WRITE_KERNEL_FAILURE`, `REDUCER_ERROR`, `INVALID_TOOL_CALL_STRUCTURE` | `ABORT` |
| Unknown / unclassified | error_code отсутствует в ERROR_REGISTRY | `ABORT` → PROTOCOL_ABORT |

UNKNOWN → ABORT — fail-safe: неизвестная ошибка не должна продолжать loop (ERR-6).

**Стратегии:**

- `RETRY` — [[agent-loop]] повторяет STEP; budget-check в DECIDE
- `RE_EXPLAIN` — обязателен новый resolve+explain; [[agent-loop]] переходит в PLAN
- `HUMAN_GATE` — [[session-orchestrator]] получает `LoopOutcome.GATE`
- `ABORT` — [[agent-loop]] переходит в PROTOCOL_ABORT (все guard-пути → PROTOCOL_ABORT через ClassificationResult.effective_abort_kind)

Audit шага записывается через расширенный `LoopStepRecorded` (не через `ErrorClassified` — он упразднён).

## When To Use

Вызывается из DECIDE-состояния [[agent-loop]] при `result.status == "ERROR"`. Budget enforcement (проверка `retry_counts` vs `retry_budget`) остаётся в `decide()` — не здесь.

## Trade-offs

- Lookup в ERROR_REGISTRY вместо инлайн-категорий: нет дрейфа между classifier и реестром (ERR-1, ERR-9)
- `strategy_override` в PolicyProjection не добавляется: L1-axioms не управляемы через конфиг; `retry_budget[error_code] = 0` достаточно для escalation
- Единственный фиксированный `origin="GUARD"`: classifier decoupled от validate-пути

## See Also

- [[error-registry]]
- [[classification-result]]
- [[error-meta]]
- [[agent-loop]]
- [[loop-policy]]
- [[session-orchestrator]]
- [[execution-guard]]
