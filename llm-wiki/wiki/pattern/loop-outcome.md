---
id: pattern/loop-outcome
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/orchestrator-agentloop-plan.md
---
# LoopOutcome

Enum-контракт между [[agent-loop]] и [[session-orchestrator]]: четыре terminal outcomes с чёткими гарантиями о состоянии EventLog и Sandbox.

## How It Works

```python
class LoopOutcome(Enum):
    COMPLETE        # task_complete=true в последнем CommandResult
    GATE            # HumanGateReached event уже в EventLog; Sandbox frozen
    CORE_ABORT      # structural/L0 violation; Sandbox discard; AuditEngine НЕ запускается
    PROTOCOL_ABORT  # policy violation или budget exceeded или UNKNOWN error;
                    # AuditEngine запускается (M1-M8, M9=0 принудительно)
```

**Consistency гарантии (до возврата из AgentLoop.run()):**

| Outcome | EventLog | Sandbox | AuditEngine |
|---------|----------|---------|-------------|
| `COMPLETE` | `task_complete == true` в последнем CommandResult | открыт | запускается штатно |
| `GATE` | `HumanGateReached` записан | freeze(ttl) | не запускается сразу |
| `CORE_ABORT` | `ErrorEvent` (L0 violation) записан | discard немедленно | пропускается |
| `PROTOCOL_ABORT` | `ErrorEvent` (validation/budget/unknown) записан | discard | запускается (M1-M8, M9=0) |

**SessionOrchestrator ветвление:**

| LoopOutcome | Действие |
|-------------|----------|
| `COMPLETE` | commit результата, закрыть сессию |
| `GATE` | `SandboxManager.freeze(ttl=policy.gate_freeze_ttl_hours)`; human уведомляется; новый [[agent-loop]] при возобновлении работает в том же Sandbox (unfreeze); по истечении TTL → discard + ErrorEvent |
| `CORE_ABORT` | `SandboxManager.discard()` немедленно; сессия закрывается без AuditEngine |
| `PROTOCOL_ABORT` | AuditEngine (M1-M8, M9=0 принудительно); результат для MetaOptimization; сессия закрывается |

**Разница CORE_ABORT vs PROTOCOL_ABORT:**

- `CORE_ABORT` — невалидный формат ToolCall (структурный мусор от LLM) → L0-нарушение; AuditEngine пропускается, MetaOptimization не получает сигнал.
- `PROTOCOL_ABORT` — структурно корректный ToolCall нарушает policy (напр. write при `phase_write_allowed=False`), или budget exceeded, или UNKNOWN error → AuditEngine запускается, MetaOptimization получает поведенческий сигнал.

## When To Use

Возвращается из `AgentLoop.run()`. [[session-orchestrator]] ветвится по outcome-значению. Никогда не конструируется вручную — только как return value AgentLoop.

## Trade-offs

- Явные 4 outcomes вместо bool/exception → SessionOrchestrator не угадывает состояние.
- GATE vs PROTOCOL_ABORT — семантическая граница: GATE = human decision needed, PROTOCOL_ABORT = automated failure path.
- M9=0 в PROTOCOL_ABORT — намеренное ограничение MetaOptimization чтобы не полагаться на невалидные данные.

## See Also

- [[agent-loop]]
- [[session-orchestrator]]
- [[loop-policy]]
- [[audit-engine]]
