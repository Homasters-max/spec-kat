---
id: pattern/agent-loop
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- enforcement
- llm
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/orchestrator-agentloop-plan.md
---
# AgentLoop

L1-компонент: детерминированный FSM внутреннего цикла агента с Policy-driven поведением и replay-safe решениями. Располагается между [[session-orchestrator]] и [[agent-handle]].

## How It Works

**Иерархия:** `SessionOrchestrator → AgentLoop → AgentHandle`.  
[[agent-handle]] остаётся чистым LLM API wrapper (start/step/terminate). Всю control-логику реализует AgentLoop.

### FSM

```text
PLAN → STEP → OBSERVE → DECIDE ──→ DONE         (LoopOutcome.COMPLETE)
                          │
                          ├──RETRY──→ STEP
                          ├──RE_EXPLAIN──→ PLAN   (если re_explain_count >= budget → GATE)
                          ├──step_budget hit──→ GATE
                          ├──HUMAN_GATE──→ GATE   (LoopOutcome.GATE)
                          ├──CORE_ABORT──→ CORE_ABORT    (LoopOutcome.CORE_ABORT)
                          └──PROTOCOL_ABORT──→ PROTOCOL_ABORT  (LoopOutcome.PROTOCOL_ABORT)
```

| Состояние | Семантика |
|-----------|-----------|
| PLAN | Phase lock на первом входе; читает [[policy-projection]] `at_offset=current_event_log_offset` → `PolicySnapshot`; при RE_EXPLAIN перечитывает только если `policy_projection.last_update_offset > last_policy_offset` (LOOP-1) |
| STEP | `ContextKernel.build_base() + pulls → AgentHandle.step(context) → ToolCall`; затем `AgentLoop.validate(tool_call)` перед dispatch |
| OBSERVE | `CommandBus.dispatch(tool_call)` → `CommandResult` |
| DECIDE | Детерминированное ветвление по `CommandResult`; инкремент счётчиков в `LoopState`; запись `LoopStepRecorded` в EventStore |
| GATE | `EventStore.append(HumanGateReached(...))` → `AgentHandle.terminate("gate")` → `LoopOutcome.GATE` |
| CORE_ABORT | `EventStore.append(ErrorEvent(...))` → `AgentHandle.terminate("abort")` → `LoopOutcome.CORE_ABORT` |
| PROTOCOL_ABORT | `EventStore.append(ErrorEvent(...))` → `AgentHandle.terminate("abort")` → `LoopOutcome.PROTOCOL_ABORT` |
| DONE | `AgentHandle.terminate("complete")` → `LoopOutcome.COMPLETE` |

AgentLoop эмитит `HumanGateReached`/`ErrorEvent` **напрямую в EventStore** до вызова `AgentHandle.terminate()`. `LoopStepRecorded` — тоже напрямую в EventStore, не через [[command-bus]].

### LoopState

```python
@dataclass
class LoopState:
    phase_id: str                           # передаётся конструктором от SessionOrchestrator
    step_count: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)  # error_type → count
    re_explain_count: int = 0
    policy: PolicySnapshot = field(...)     # читается at_offset; обновляется при RE_EXPLAIN
    last_policy_offset: int = 0            # offset последнего PolicyProjection update event
```

LoopState — эфемерный in-memory dataclass, не персистируется (GL-9). Все decision-точки фиксируются через events.

### CommandResult

```python
@dataclass(frozen=True)
class CommandResult:
    status: Literal["OK", "ERROR"]
    error_type: str | None          # None если status == OK
    task_complete: bool             # True только если агент вызвал sdd_complete
```

Без строгой типизации DECIDE недетерминирован.

### DECIDE: полная логика

```python
def decide(result: CommandResult, loop_state: LoopState) -> Transition:
    # task_complete проверяется ДО budget (приоритет)
    if result.status == "OK":
        if result.task_complete:
            return Transition.DONE
        if loop_state.step_count >= loop_state.policy.step_budget:
            return Transition.GATE
        return Transition.STEP

    if loop_state.step_count >= loop_state.policy.step_budget:
        return Transition.GATE

    strategy = ErrorClassifier.classify(result, loop_state)

    if strategy == RETRY:
        budget = loop_state.policy.retry_budget.get(
            result.error_type, loop_state.policy.retry_budget["DEFAULT"]
        )
        if loop_state.retry_counts.get(result.error_type, 0) >= budget:
            return Transition.GATE
        loop_state.retry_counts[result.error_type] = (
            loop_state.retry_counts.get(result.error_type, 0) + 1
        )
        return Transition.STEP

    if strategy == RE_EXPLAIN:
        loop_state.re_explain_count += 1
        if loop_state.re_explain_count >= loop_state.policy.re_explain_budget:
            return Transition.GATE
        return Transition.PLAN   # PLAN перечитает Policy at_offset (LOOP-1)

    if strategy == HUMAN_GATE:
        return Transition.GATE

    if strategy == ABORT:
        return Transition.PROTOCOL_ABORT
```

### ToolCall validation (до CommandBus.dispatch)

```python
def validate(self, tool_call: ToolCall) -> ValidationResult:
    # structural: обязательные поля, типы → провал: CORE_ABORT
    # policy: phase_write_allowed, scope checks → провал: PROTOCOL_ABORT
```

Два разных исхода намеренны: structural failure (мусор от LLM) → CORE_ABORT, AuditEngine пропускается; policy violation (корректный ToolCall, нарушает rules) → PROTOCOL_ABORT, AuditEngine запускается.

## Инварианты

| ID | Формулировка |
|----|-------------|
| LOOP-1 | Policy читается по `PolicyProjection.last_update_offset`; при RE_EXPLAIN перечитывается только если offset изменился |
| LOOP-2 | Все decision-точки replayable из EventLog: `LoopStepRecorded` содержит снапшот (`step_count`, `retry_counts`, `re_explain_count`, `policy_version`) |
| LOOP-EXIT | Каждый loop завершается ровно одним из: `COMPLETE \| GATE \| CORE_ABORT \| PROTOCOL_ABORT` |

### LoopTrace (для audit + MetaOptimization)

```python
@dataclass
class LoopTraceEntry:
    step: int
    tool_call_type: str         # "resolve" | "explain" | "write" | ...
    decision: str               # "RETRY" | "RE_EXPLAIN" | "GATE" | "ABORT" | "DONE" | "CONTINUE"
    error_type: str | None
    outcome: str | None         # заполняется на последнем шаге
```

`LoopStepRecorded` в EventStore дополнительно содержит `step_count`, `retry_counts`, `re_explain_count`, `policy_version` для LOOP-2 replay. [[trace-projection]] подписана на эти события; AgentLoop не пишет в неё напрямую.

## When To Use

Создаётся [[session-orchestrator]] на каждый TaskRun. Получает `phase_id` в конструктор — не резолвит его самостоятельно. Возвращает [[loop-outcome]] по завершению.

## Trade-offs

- FSM с explicit states → все переходы наблюдаемы и тестируемы детерминированно.
- Phase lock через конструктор: mid-loop phase switch не влияет на текущий AgentLoop.
- Прямые EventStore-записи (не через CommandBus) для `LoopStepRecorded`/`HumanGateReached`/`ErrorEvent` — нарушение GL-7 намеренно для L1 isolation; документировано в design.

## See Also

- [[session-orchestrator]]
- [[agent-handle]]
- [[loop-policy]]
- [[loop-outcome]]
- [[error-classifier]]
- [[trace-projection]]
- [[policy-projection]]
- [[command-bus]]
