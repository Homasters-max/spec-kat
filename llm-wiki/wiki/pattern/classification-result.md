---
id: pattern/classification-result
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- validation
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/error-model-architecture.md
---
# ClassificationResult

Unified return type из `validate()` и `ErrorClassifier.classify()`. Объединяет strategy, meta и origin в одном frozen объекте; `effective_abort_kind` вычисляется как property.

## Summary

Вместо возврата голой `RecoveryStrategy` — структурированный результат, из которого можно однозначно получить `abort_kind` без дополнительного контекста.

## How It Works

```python
@dataclass(frozen=True)
class ClassificationResult:
    strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"]
    meta: ErrorMeta
    origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"]

    @property
    def effective_abort_kind(self) -> Literal["CORE_ABORT", "PROTOCOL_ABORT"] | None:
        if self.strategy != "ABORT":
            return None
        return "CORE_ABORT" if self.origin == "VALIDATE_STRUCTURAL" else "PROTOCOL_ABORT"
```

### origin — источник классификации

| origin | Контекст | abort_kind |
|--------|---------|-----------|
| `VALIDATE_STRUCTURAL` | `validate()` нашёл невалидную структуру ToolCall | `CORE_ABORT` |
| `VALIDATE_POLICY` | `validate()` нашёл нарушение policy (фаза, scope) | `PROTOCOL_ABORT` |
| `GUARD` | [[error-classifier]].classify() через CommandBus | `PROTOCOL_ABORT` |

**Важное ограничение:** `ErrorClassifier.classify()` всегда выставляет `origin="GUARD"` — он не знает о validate-пути. Только `validate()` сам выставляет `VALIDATE_STRUCTURAL` или `VALIDATE_POLICY`.

### Вычисление abort_kind

```python
"CORE_ABORT"     if origin == "VALIDATE_STRUCTURAL"
"PROTOCOL_ABORT" if origin in ("VALIDATE_POLICY", "GUARD")
```

`None` если strategy != "ABORT" (RETRY/RE_EXPLAIN/HUMAN_GATE не имеют abort_kind).

## When To Use

Возвращается из двух мест:
- `AgentLoop.validate(tool_call)` — перед `CommandBus.dispatch()`
- `ErrorClassifier.classify(result, loop_state)` — в DECIDE состоянии [[agent-loop]]

[[agent-loop]] читает `result.strategy` для ветвления, `result.effective_abort_kind` для эмита `ErrorEvent`.

## Trade-offs

- Единый return type: `validate()` и `classify()` возвращают одно и то же → DECIDE-логика не ветвится по источнику.
- `effective_abort_kind` как property: не хранится в [[error-meta]], вычисляется lazily — zero-cost для non-ABORT путей.
- `origin` в classify() фиксирован как `"GUARD"`: classifier не знает о validate-пути, coupling минимален.

## See Also

- [[error-meta]]
- [[error-registry]]
- [[error-classifier]]
- [[agent-loop]]
- [[error-event]]
