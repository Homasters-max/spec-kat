---
id: pattern/replay-based-testing
page_type: pattern
domain: sdd
layer: architecture
tags:
- automation
- validation
- pipeline
- ssot
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Replay-Based Testing

Подход к тестированию SDD системы: тесты = replay(events) + assertions(state, trace). Не требует моков — EventLog является source of truth.

## How It Works

```yaml
TestCase:
  input_events: list[Event]
  expected_state: State
  expected_trace: list[TraceEntry]
```

```python
state = initial()
for e in input_events:
    state = reduce(state, upcast(e))
assert state == expected_state
```

**Гарантии:**

- Детерминированные тесты — одинаковый EventLog → одинаковый State.
- Не нужны моки (EventLog = source of truth).
- Полная валидация системы через replay.

## When To Use

Для тестирования любой части SDD, которая изменяет или читает State. Особенно эффективно для reducer, guards, projections.

## Trade-offs

- Тесты зависят от правильности input_events — нужно вручную конструировать тестовые последовательности.
- Изменение схемы Event требует обновления тестовых данных + upcasters.

## See Also

- [[reducer]]
- [[upcaster-registry]]
- [[event-sourcing]]
- [[sdd-meta-harness]]
