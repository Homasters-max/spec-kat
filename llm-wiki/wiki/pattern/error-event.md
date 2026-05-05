---
id: pattern/error-event
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- write-path
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/error-model-architecture.md
---
# ErrorEvent

Terminal event — финальный акт loop при CORE_ABORT или PROTOCOL_ABORT. Пишется напрямую в EventStore из [[agent-loop]] (GL-7 exception для L1). `WARNING` severity не доходит до ErrorEvent — loop продолжается.

## Summary

Три события связаны с error flow:
- `ErrorEvent` — terminal, один раз на loop при ABORT
- `LoopStepRecorded` (расширенный) — audit каждого шага, включая ERROR-шаги
- `HumanGateReached` (расширенный) — при входе в GATE с указанием причины

## How It Works

### ErrorEvent (terminal)

```python
@dataclass(frozen=True)
class ErrorEvent:
    event_id: UUID
    timestamp: datetime
    # из ERROR_REGISTRY
    error_code: str
    severity: Literal["FATAL", "ERROR"]    # WARNING → loop продолжается, сюда не доходит
    layer: Literal["L0", "L1", "UNKNOWN"]  # TRANSIENT → WARNING → не terminal
    invariant_id: str | None
    rule_id: str | None
    abort_kind: Literal["CORE_ABORT", "PROTOCOL_ABORT"]
    # контекст
    phase_id: int
    task_id: str
    message: str
    context: str | None   # file path, command name — строка, не dict (replay-safe)
```

`abort_kind` вычисляется из `ClassificationResult.effective_abort_kind` при эмите — в [[error-meta]] не хранится.

`context: str | None` вместо `details: dict[str, Any]`: untyped dict нарушает replay-safety. Структурированные данные per error_code — отдельный event через [[command-bus]], не поле в ErrorEvent.

### LoopStepRecorded (расширенный)

Audit каждого шага: новые поля None для OK-шагов.

```python
@dataclass(frozen=True)
class LoopStepRecorded:
    # существующие поля
    step_count: int
    retry_counts: dict[str, int]
    re_explain_count: int
    policy_version: str
    # новые поля error audit (None если status == OK)
    error_code: str | None
    severity: Literal["FATAL", "ERROR", "WARNING"] | None
    layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"] | None
    invariant_id: str | None
    rule_id: str | None
    strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"] | None
    origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"] | None
```

Заменяет упразднённый `ErrorClassified` event (Решение 7): одно событие на шаг вместо двух. [[trace-projection]] подписана и читает эти поля.

### HumanGateReached (расширенный)

```python
@dataclass(frozen=True)
class HumanGateReached:
    gate_reason: Literal["STEP_BUDGET", "RETRY_BUDGET", "RE_EXPLAIN_BUDGET", "GUARD_VIOLATION"]
    error_code: str | None     # заполняется если reason == GUARD_VIOLATION
    rule_id: str | None        # из ErrorMeta, если применимо
    step: int
    phase_id: int
    task_id: str | None
```

Budget exhaustion — не ошибка классификации → `gate_reason` явно разграничивает причины GATE.

## When To Use

- `ErrorEvent`: [[agent-loop]] эмитит один раз при CORE_ABORT/PROTOCOL_ABORT перед `AgentHandle.terminate()`
- `LoopStepRecorded`: [[agent-loop]] эмитит в конце каждого шага DECIDE (включая ERROR-шаги)
- `HumanGateReached`: [[agent-loop]] эмитит при входе в GATE-состояние

Все три пишутся напрямую в EventStore (не через CommandBus) — GL-7 exception задокументирован.

## Trade-offs

- Один `LoopStepRecorded` вместо двух событий (ErrorClassified + LoopStepRecorded): меньше EventLog bloat, одна подписка в [[trace-projection]]
- `context: str | None` ограничивает выразительность, но гарантирует replay-safety
- `HumanGateReached.gate_reason` делает явным различие budget-exhaustion vs guard-violation

## See Also

- [[error-registry]]
- [[error-meta]]
- [[classification-result]]
- [[agent-loop]]
- [[loop-outcome]]
- [[trace-projection]]
