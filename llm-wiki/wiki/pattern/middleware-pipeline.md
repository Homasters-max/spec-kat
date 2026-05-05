---
id: pattern/middleware-pipeline
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- write-path
- enforcement
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/CommandBus — Idempotency, Dedup, Middleware Pipeline.md
---
# Middleware Pipeline

Паттерн построения [[command-bus]] через цепочку фиксированных слотов вместо жёстко закодированных шагов в `dispatch()`.

## Summary

`build_pipeline` сворачивает список `Middleware` в единый `Next`-вызов. Порядок слотов зафиксирован в `create_command_bus()` — это конвенция, не свободно-composable цепочка. Паттерн совместим с [[global-laws]] GL-3: L0-ядро (slot 1 + terminal) не имеет L1-зависимостей.

## How It Works

### Middleware интерфейс

```python
Next = Callable[[Command], CommandResult]

class Middleware(Protocol):
    def __call__(self, cmd: Command, next: Next) -> CommandResult: ...

def build_pipeline(middlewares: list[Middleware], terminal: Next) -> Next:
    chain = terminal
    for mw in reversed(middlewares):
        prev = chain
        chain = lambda cmd, m=mw, p=prev: m(cmd, p)
    return chain
```

### Слоты (порядок строго зафиксирован)

```text
slot 0:   ErrorClassifierMiddleware   L0  — перехватывает GuardError из всего ниже
          LoggingMiddleware            L0  — stderr/stdout, timing
slot 0.5: IdempotencyMiddleware        L1  — lookup → short-circuit или pass + store
slot 1:   L0GuardMiddleware            L0  — state invariants, бросает GuardError
slot 2:   L1ExecutionGuardMiddleware   L1  — resolve→explain→write, бросает GuardError
          L1ScopeGuardMiddleware       L1  — file scope, бросает GuardError
terminal: WriteKernel.execute_and_project
```

GL-5 соблюдён: L0-ядро (slot 1 + terminal) не содержит ссылок на L1-компоненты.

### Фабрика `create_command_bus`

```python
def create_command_bus(db, policy_reader, write_kernel, ...) -> CommandBus:
    pipeline = build_pipeline([
        ErrorClassifierMiddleware(),
        LoggingMiddleware(),
        IdempotencyMiddleware(IdempotencyProjection(db)),
        L0GuardMiddleware(...),
        L1ExecutionGuardMiddleware(policy_reader),
        L1ScopeGuardMiddleware(),
    ], terminal=write_kernel.execute_and_project)
    return CommandBus(pipeline)
```

## When To Use

Когда порядок выполнения guards/middleware фиксирован и должен быть явно выражен как структура данных, а не разветвлённый imperative код в `dispatch()`.

## Trade-offs

- Слоты фиксированы в `create_command_bus` — добавление нового middleware требует изменения фабрики.
- Guards бросают `GuardError` (не возвращают Result) — `ErrorClassifierMiddleware` обязателен как внешний слой.
- `build_pipeline` — тупая свёртка без интроспекции; порядок слотов документируется конвенцией, не типами.

## See Also

- [[command-bus]]
- [[idempotency-middleware]]
- [[global-laws]]
- [[error-classifier]]
