---
id: pattern/command-bus
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- write-path
- enforcement
- automation
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/CommandBus — Idempotency, Dedup, Middleware Pipeline.md
---
# CommandBus

L0-компонент: явная шина маршрутизации команд. Делегирует выполнение в [[middleware-pipeline]], собранный фабрикой `create_command_bus()`.

## How It Works

```python
class CommandBus:
    def __init__(self, pipeline: Next):
        self._pipeline = pipeline

    def dispatch(self, cmd: Command) -> CommandResult:
        return self._pipeline(cmd)
```

`dispatch()` не содержит логики — только делегация в pipeline. Порядок guards, idempotency и error handling определяется в `create_command_bus()`.

### create_command_bus (фабрика)

```python
def create_command_bus(db, policy_reader, write_kernel, ...) -> CommandBus:
    pipeline = build_pipeline([
        ErrorClassifierMiddleware(),           # slot 0: перехват GuardError
        LoggingMiddleware(),                   # slot 0: stderr/stdout
        IdempotencyMiddleware(                 # slot 0.5: exact dedup
            IdempotencyProjection(db)
        ),
        L0GuardMiddleware(...),               # slot 1: state invariants
        L1ExecutionGuardMiddleware(policy_reader),  # slot 2: behavior
        L1ScopeGuardMiddleware(),             # slot 2: file scope
    ], terminal=write_kernel.execute_and_project)
    return CommandBus(pipeline)
```

**Guards бросают `GuardError`**, не возвращают Result — `ErrorClassifierMiddleware` (slot 0) перехватывает и классифицирует.

**`idempotency_key: UUID`** — поле на каждой `Command`. InputPort генерирует `uuid5(NAMESPACE_SDD, f"{call.id}:{call.name}")`, CLI использует `uuid4()`.

**Два входа:**

- [[input-port]] (LLM tool calls) → CommandBus
- CLI (human commands) → CommandBus

Оба входа подчиняются одинаковым guards и middleware.

## When To Use

Единственная точка входа для любой мутирующей операции. `WriteKernel.execute_and_project()` вызывается только через CommandBus, не напрямую.

## Trade-offs

- Guards выполняются последовательно (SEM-13) — нельзя параллельно.
- Добавление нового middleware = изменение фабрики `create_command_bus` + новый тест.
- Guards бросают исключения, не возвращают Result — pipeline обязан иметь `ErrorClassifierMiddleware` на внешнем слое.

## See Also

- [[middleware-pipeline]]
- [[idempotency-middleware]]
- [[input-port]]
- [[eventstore-guard]]
- [[execution-guard]]
- [[scope-guard]]
- [[error-classifier]]
- [[projection-registry]]
