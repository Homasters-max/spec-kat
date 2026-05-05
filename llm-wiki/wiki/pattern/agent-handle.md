---
id: pattern/agent-handle
page_type: pattern
domain: sdd
layer: architecture
tags:
- llm
- pipeline
- automation
- write-path
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# AgentHandle

L1-компонент: управляемый lifecycle LLM-агента с явными операциями start/step/terminate и логированием model_version.

## How It Works

```python
class AgentHandle:
    def start(self, model: str, config: AgentConfig) -> None:
        self.model_version = model
        self.session_id = uuid4()
        # emit TaskSessionStarted event

    def step(self, context: ContextPacket) -> ToolCall:
        # call Claude API with tool_use
        # log TraceEvent(model_version=self.model_version, ...)
        return tool_call

    def terminate(self, reason: str) -> None:
        # emit SessionTerminated event
```

**Ключевое свойство:** каждый `step()` записывает `model_version` в TraceEvent. Это позволяет [[audit-engine]] и [[meta-optimization]] коррелировать качество решений с конкретной версией модели.

**Lifecycle в рамках TaskRun:**

```text
Session Orchestrator → AgentHandle.start()
  loop:
    context = ContextKernel.build_base() + pulls
    tool_call = AgentHandle.step(context)
    result = CommandBus.dispatch(tool_call)
    if result.error: ErrorClassifier.classify() → strategy
    if strategy == ABORT: break
  AgentHandle.terminate()
```

Смена модели = конфиг change, не архитектурное изменение. `model_version` — строка в формате `"claude-sonnet-4-6"`.

## When To Use

Создаётся Session Orchestrator'ом на каждый TaskRun. Один TaskRun = один AgentHandle.

## Trade-offs

- AgentHandle — stateful в рамках сессии, но не персистируется (GL-9).
- При crash сессии: новый AgentHandle с replay из EventLog восстанавливает GraphSessionState.

## See Also

- [[session-orchestrator]]
- [[input-port]]
- [[trace-store]]
- [[context-kernel]]
- [[graph-session-state]]
