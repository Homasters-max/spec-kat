---
id: pattern/input-port
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- write-path
- llm
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# InputPort (ToolCallAdapter)

L1-компонент: транслирует tool_use API calls от LLM в Commands для CommandBus. CLI остаётся исключительно для human.

## How It Works

```python
class InputPort:
    def dispatch(self, tool_call: ToolUseBlock) -> CommandResult:
        cmd = self._translate(tool_call)   # tool_name → Command type
        return command_bus.dispatch(cmd)

    def _translate(self, call: ToolUseBlock) -> Command:
        spec = TOOL_REGISTRY[call.name]    # typed tool schema
        return spec.command_type(**call.input)
```

**Tool Schema → Command mapping:**

```text
tool: sdd_complete    → CompleteTaskCommand(task_id=...)
tool: sdd_resolve     → ResolveCommand(task_id=...)
tool: sdd_explain     → ExplainCommand(task_id=..., context=...)
tool: sdd_write       → WriteCommand(file=..., content=...)
tool: sdd_show_state  → ShowStateQuery(...)
```

**Ключевой инвариант:** LLM не может вызвать `event_store.append()` напрямую — только через tool calls → InputPort → CommandBus → WriteKernel → EventStore Guard. CLI-команды (activate-phase, approve) не выставляются как tools — human-only.

**Tool schemas** генерируются из CommandRegistry автоматически при старте сессии и подаются в `AgentHandle.start()` как `tools` parameter.

## When To Use

Является единственным входом для LLM-actions. Все actions агента проходят через InputPort.

## Trade-offs

- Tool schema должна быть строго типизирована — иначе LLM может передать невалидные параметры.
- Не поддерживает батчинг tool calls — каждый call обрабатывается атомарно.

## See Also

- [[command-bus]]
- [[agent-handle]]
- [[context-kernel]]
- [[sdd-actor-model]]
