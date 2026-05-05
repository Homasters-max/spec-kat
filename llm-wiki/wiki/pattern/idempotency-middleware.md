---
id: pattern/idempotency-middleware
page_type: pattern
domain: sdd
layer: architecture
tags:
- dedup
- write-path
- pipeline
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/CommandBus — Idempotency, Dedup, Middleware Pipeline.md
---
# IdempotencyMiddleware

L1-middleware в [[middleware-pipeline]]: exact dedup по `idempotency_key`. Кешируются только успешные результаты; ошибки всегда проходят полный pipeline.

## Summary

Занимает slot 0.5 — после `LoggingMiddleware`, до `L0GuardMiddleware`. При повторном вызове с тем же `idempotency_key` возвращает кешированный `CommandResult` без прохождения guards и WriteKernel. Семантика: **at-least-once** (потеря записи допустима — retry обрабатывается повторно).

## How It Works

```python
class IdempotencyMiddleware:
    def __init__(self, projection: IdempotencyProjection):
        self._proj = projection

    def __call__(self, cmd: Command, next: Next) -> CommandResult:
        cached = self._proj.lookup(cmd.idempotency_key)
        if cached is not None:
            return cached                         # short-circuit

        result = next(cmd)

        if result.ok:                             # кешируем только OK
            self._proj.store(cmd.idempotency_key, result)

        return result
```

**Только exact dedup** — semantic dedup (по содержимому команды) намеренно отсутствует.

### `idempotency_key` на Command

```python
@dataclass
class Command:
    idempotency_key: UUID = field(default_factory=uuid4)
```

- **InputPort** генерирует: `uuid5(NAMESPACE_SDD, f"{call.id}:{call.name}")` — детерминированный ключ для LLM tool calls.
- **CLI** использует `uuid4()` — случайный; повторный запуск = новая команда.

## When To Use

При наличии LLM-агента, который может повторно отправить одну и ту же tool call (retry, reconnect, network jitter). Обеспечивает exactly-once семантику результата при at-least-once доставке команды.

## Trade-offs

- Только OK кешируется: ошибка на первом вызове → retry проходит полный pipeline (безопасно).
- At-least-once: если `store()` упал после `next(cmd)` — команда выполнится повторно при retry.
- Middleware не знает о содержимом команды — ключ должен быть семантически корректным (ответственность InputPort).

## See Also

- [[middleware-pipeline]]
- [[idempotency-projection]]
- [[input-port]]
- [[command-bus]]
