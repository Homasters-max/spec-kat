---
id: pattern/error-registry
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- validation
- ssot
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/error-model-architecture.md
---
# ErrorRegistry

Центральный реестр ошибок SDD: единственный источник severity, layer, invariant_id, rule_id для каждого error_code. Реализован как модуль `sdd.errors`.

## Summary

`ERROR_REGISTRY: dict[str, ErrorMeta]` + `ErrorCode` constants — два связанных элемента, живущих в `sdd/errors.py`. Guards не хардкодят строки, а импортируют `ErrorCode.<NAME>`. Fallback на неизвестный код → `layer="UNKNOWN"`, strategy=ABORT.

## How It Works

### ErrorCode — константы

```python
class ErrorCode:
    DIRECT_EVENTSTORE_ACCESS    = "DIRECT_EVENTSTORE_ACCESS"
    WRITE_KERNEL_FAILURE        = "WRITE_KERNEL_FAILURE"
    REDUCER_ERROR               = "REDUCER_ERROR"
    INVALID_TOOL_CALL_STRUCTURE = "INVALID_TOOL_CALL_STRUCTURE"
    PHASE_WRITE_NOT_ALLOWED     = "PHASE_WRITE_NOT_ALLOWED"
    NO_EXPLAIN_BEFORE_WRITE     = "NO_EXPLAIN_BEFORE_WRITE"
    GRAPH_CHANGED_AFTER_EXPLAIN = "GRAPH_CHANGED_AFTER_EXPLAIN"
    TASK_ISOLATED               = "TASK_ISOLATED"
    NO_PATH                     = "NO_PATH"
    CONTEXT_STALE               = "CONTEXT_STALE"
    SCOPE_VIOLATION             = "SCOPE_VIOLATION"
    PERMISSION_DENIED           = "PERMISSION_DENIED"
    MAX_WRITE_CYCLES_EXCEEDED   = "MAX_WRITE_CYCLES_EXCEEDED"
    TIMEOUT                     = "TIMEOUT"
    RATE_LIMIT                  = "RATE_LIMIT"
```

### ERROR_REGISTRY (полный)

```python
ERROR_REGISTRY: dict[str, ErrorMeta] = {
    # L0 — FATAL, invariant_id заполнен, rule_id=None
    ErrorCode.DIRECT_EVENTSTORE_ACCESS:    ErrorMeta("FATAL", "L0", "GL-7",     None, "ABORT"),
    ErrorCode.WRITE_KERNEL_FAILURE:        ErrorMeta("FATAL", "L0", "I-ERROR-1", None, "ABORT"),
    ErrorCode.REDUCER_ERROR:               ErrorMeta("FATAL", "L0", "GL-1",     None, "ABORT"),
    ErrorCode.INVALID_TOOL_CALL_STRUCTURE: ErrorMeta("FATAL", "L0", "GL-3",     None, "ABORT"),

    # L1 — ERROR, rule_id заполнен, invariant_id=None
    ErrorCode.PHASE_WRITE_NOT_ALLOWED:     ErrorMeta("ERROR", "L1", None, "PHASE_WRITE_NOT_ALLOWED", "ABORT"),
    ErrorCode.NO_EXPLAIN_BEFORE_WRITE:     ErrorMeta("ERROR", "L1", None, "NO_EXPLAIN_BEFORE_WRITE", "RETRY"),
    ErrorCode.GRAPH_CHANGED_AFTER_EXPLAIN: ErrorMeta("ERROR", "L1", None, "GRAPH_FINGERPRINT",       "RE_EXPLAIN"),
    ErrorCode.TASK_ISOLATED:               ErrorMeta("ERROR", "L1", None, "TASK_ISOLATED",           "RE_EXPLAIN"),
    ErrorCode.NO_PATH:                     ErrorMeta("ERROR", "L1", None, "NO_GRAPH_BEFORE_EXPLAIN", "RE_EXPLAIN"),
    ErrorCode.CONTEXT_STALE:               ErrorMeta("ERROR", "L1", None, "CONTEXT_STALE",           "RE_EXPLAIN"),
    ErrorCode.SCOPE_VIOLATION:             ErrorMeta("ERROR", "L1", None, "GL-6",                    "HUMAN_GATE"),
    ErrorCode.PERMISSION_DENIED:           ErrorMeta("ERROR", "L1", None, "PERMISSION_DENIED",       "HUMAN_GATE"),
    ErrorCode.MAX_WRITE_CYCLES_EXCEEDED:   ErrorMeta("ERROR", "L1", None, "MAX_WRITE_CYCLES",        "HUMAN_GATE"),

    # TRANSIENT — WARNING, оба None
    ErrorCode.TIMEOUT:                     ErrorMeta("WARNING", "TRANSIENT", None, None, "RETRY"),
    ErrorCode.RATE_LIMIT:                  ErrorMeta("WARNING", "TRANSIENT", None, None, "RETRY"),
}
```

### XOR-инвариант

Для layer L0/L1: `bool(invariant_id) XOR bool(rule_id)` — ровно одно поле заполнено. Для TRANSIENT и UNKNOWN — оба None (инвариант не применяется).

### Fallback (UNKNOWN layer)

Если error_code не в ERROR_REGISTRY:

```python
ErrorMeta(severity="ERROR", layer="UNKNOWN", invariant_id=None, rule_id=None, default_strategy="ABORT")
```

Результат — `PROTOCOL_ABORT`. Служит сигналом: неизвестный код нужно добавить в реестр.

## When To Use

- [[error-classifier]] вызывает `ERROR_REGISTRY[result.error_code]` в `classify()`
- [[agent-loop]] вызывает `validate()`, которая смотрит в реестр через `error_code`
- Guards импортируют `ErrorCode.<NAME>` — никогда не пишут строки напрямую

## Trade-offs

- Единственный источник: нет дрейфа между guard и реестром (ERR-1, ERR-9)
- Shared-модуль (`sdd.errors`): не L0, не L1 — доступен всем слоям без нарушения слоёвости
- `strategy_override` в PolicyProjection не добавляется (Решение 5): L1-axioms не должны быть управляемыми через конфиг

## See Also

- [[error-meta]]
- [[error-event]]
- [[classification-result]]
- [[error-classifier]]
- [[agent-loop]]
