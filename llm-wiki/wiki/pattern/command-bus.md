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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# CommandBus

L0-компонент: явная шина маршрутизации команд. `InputPort → Bus → Guard(L0) → Guard(L1) → Handler → EventLog`.

## How It Works

```python
class CommandBus:
    def dispatch(self, cmd: Command) -> CommandResult:
        # 1. L0 Guards (state invariants)
        l0_result = l0_guards.check(state, cmd, ctx)
        if not l0_result.ok:
            return ErrorClassifier.classify(l0_result.error)

        # 2. EventStore Guard
        eventstore_guard.check_caller(inspect.currentframe())

        # 3. L1 ExecutionGuard (behavior protocol)
        l1_result = execution_guard.check(trace, gss, cmd)
        if not l1_result.ok:
            return ErrorClassifier.classify(l1_result.error)

        # 4. L1 ScopeGuard (file scope)
        scope_result = scope_guard.check(cmd, sandbox)
        if not scope_result.ok:
            return ErrorClassifier.classify(scope_result.error)

        # 5. WriteKernel (atomic append + projections)
        return write_kernel.execute_and_project(cmd)
```

**Порядок guards строго фиксирован** — нарушение порядка = нарушение GL-3.

**Два входа в CommandBus:**

- [[input-port]] (LLM tool calls) → CommandBus
- CLI (human commands) → CommandBus (те же guards, те же handlers)

Это гарантирует что human и LLM подчиняются одинаковым правилам.

## When To Use

Единственная точка входа для любой мутирующей операции. CommandRegistry.execute_and_project() должен вызываться через CommandBus, не напрямую.

## Trade-offs

- Все guards выполняются последовательно (SEM-13) — нельзя параллельно.
- Добавление нового guard = изменение в CommandBus + новый тест.

## See Also

- [[input-port]]
- [[eventstore-guard]]
- [[execution-guard]]
- [[scope-guard]]
- [[error-classifier]]
- [[projection-registry]]
