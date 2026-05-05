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
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
---
# AgentHandle

L1-компонент: чистый LLM API wrapper с явными операциями start/step/terminate и логированием `model_version`. Не содержит control-логики — ею управляет [[agent-loop]].

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

    def terminate(self, reason: Literal["complete", "gate", "abort"]) -> None:
        # emit SessionTerminated event
```

`terminate()` принимает три явных причины: `"complete"` (task done), `"gate"` (human gate reached), `"abort"` (CORE_ABORT или PROTOCOL_ABORT). [[agent-loop]] вызывает terminate до возврата `LoopOutcome`.

**Ключевое свойство:** каждый `step()` записывает `model_version` в TraceEvent. Это позволяет [[audit-engine]] и MetaOptimization коррелировать качество решений с конкретной версией модели.

Весь control flow (retry, re-explain, gate, abort) находится в [[agent-loop]], не здесь.

## When To Use

Создаётся [[session-orchestrator]] на каждый TaskRun. Один TaskRun = один AgentHandle. AgentHandle — stateful в рамках сессии, но не персистируется (GL-9).

## Trade-offs

- Чистый LLM wrapper без control logic → замена модели = config change, не архитектурное изменение.
- При crash: новый AgentHandle с replay из EventLog восстанавливает [[graph-session-state]].

## See Also

- [[agent-loop]]
- [[session-orchestrator]]
- [[input-port]]
- [[trace-store]]
- [[context-kernel]]
- [[graph-session-state]]
