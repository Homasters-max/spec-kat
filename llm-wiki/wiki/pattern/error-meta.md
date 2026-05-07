---
id: pattern/error-meta
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- validation
- ssot
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/error-model-architecture.md
---
# ErrorMeta

Frozen dataclass — метаданные одного error code из [[error-registry]]. Хранит severity, layer, rule-linkage и default_strategy. `abort_kind` не хранится — вычисляется из `origin` в [[classification-result]].

## Summary

Запись реестра: каждый `error_code` → один `ErrorMeta`. Содержит всё, что нужно для routing решения, кроме runtime-контекста.

## How It Works

```python
@dataclass(frozen=True)
class ErrorMeta:
    severity: Literal["FATAL", "ERROR", "WARNING"]
    layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"]
    invariant_id: str | None   # L0: "GL-7", "I-ERROR-1", "GL-1", "GL-3"
    rule_id: str | None        # L1: "NO_EXPLAIN_BEFORE_WRITE", "MAX_WRITE_CYCLES", etc.
    default_strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"]
```

### Таблица severity

| Severity | Layer | Runtime behaviour |
|----------|-------|-------------------|
| `FATAL` | L0 | PROTOCOL_ABORT, AuditEngine запускается |
| `ERROR` | L1 | PROTOCOL_ABORT или HUMAN_GATE |
| `WARNING` | TRANSIENT | RETRY/RE_EXPLAIN, loop продолжается |

### XOR-правило

Для L0/L1: `bool(invariant_id) XOR bool(rule_id)` — ровно одно заполнено.

```text
L0 example: invariant_id="GL-7",  rule_id=None
L1 example: invariant_id=None,    rule_id="NO_EXPLAIN_BEFORE_WRITE"
TRANSIENT:  invariant_id=None,    rule_id=None   (оба None, инвариант не применяется)
UNKNOWN:    invariant_id=None,    rule_id=None
```

### FATAL ≠ CORE_ABORT

Распространённое заблуждение: FATAL severity → CORE_ABORT. Это неверно.

| Путь | abort_kind | Пример |
|------|-----------|--------|
| `validate()` structural failure | CORE_ABORT | `INVALID_TOOL_CALL_STRUCTURE` |
| `validate()` policy failure | PROTOCOL_ABORT | `PHASE_WRITE_NOT_ALLOWED` |
| Guard через CommandBus | PROTOCOL_ABORT | `DIRECT_EVENTSTORE_ACCESS` (FATAL L0) |

CORE_ABORT = только структурный мусор от LLM (до dispatch). FATAL L0 violation через guard → PROTOCOL_ABORT.

## When To Use

Используется только через [[error-registry]] — никогда не конструируется напрямую вне `sdd/errors.py`.

## Trade-offs

- `abort_kind` вычислен, не хранится: один источник истины о `abort_kind` — [[classification-result]] через `effective_abort_kind` property.
- Frozen dataclass: immutable, безопасен для кеширования и replay.

## See Also

- [[error-registry]]
- [[classification-result]]
- [[error-event]]
