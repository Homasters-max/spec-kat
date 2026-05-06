---
created: '2026-05-05'
domain: sdd
id: pattern/agent-loop
layer: architecture
page_type: pattern
sdd_domain: Engine
sdd_layer: L1
sources:
- raw/orchestrator-agentloop-plan.md
- raw/error-model-architecture.md
tags:
- pipeline
- automation
- enforcement
- llm
- domain/sdd
- sdd/l1
- sdd/engine
updated: '2026-05-06'
version: 3
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
    retry_counts: dict[str, int] = field(default_factory=dict)  # error_code → count
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
    error_code: str | None       # None если status == OK (error_type переименован в error_code)
    task_complete: bool          # True только если агент вызвал sdd_complete
```

### DECIDE: полная логика

```python
def decide(result: CommandResult, loop_state: LoopState) -> Transition:
    if result.status == "OK":
        if result.task_complete:
            return Transition.DONE
        if loop_state.step_count >= loop_state.policy.step_budget:
            return Transition.GATE
        return Transition.STEP

    if loop_state.step_count >= loop_state.policy.step_budget:
        return Transition.GATE

    classification: ClassificationResult = ErrorClassifier.classify(result, loop_state)

    if classification.strategy == "RETRY":
        budget = loop_state.policy.retry_budget.get(
            result.error_code, loop_state.policy.retry_budget["DEFAULT"]
        )
        if loop_state.retry_counts.get(result.error_code, 0) >= budget:
            return Transition.GATE
        loop_state.retry_counts[result.error_code] = (
            loop_state.retry_counts.get(result.error_code, 0) + 1
        )
        return Transition.STEP

    if classification.strategy == "RE_EXPLAIN":
        loop_state.re_explain_count += 1
        if loop_state.re_explain_count >= loop_state.policy.re_explain_budget:
            return Transition.GATE
        return Transition.PLAN

    if classification.strategy == "HUMAN_GATE":
        return Transition.GATE

    if classification.strategy == "ABORT":
        abort_kind = classification.effective_abort_kind
        return Transition.CORE_ABORT if abort_kind == "CORE_ABORT" else Transition.PROTOCOL_ABORT
```

### ToolCall validation (до CommandBus.dispatch)

```python
def validate(self, tool_call: ToolCall) -> ClassificationResult:
    # structural: обязательные поля, типы
    #   → провал: ClassificationResult(strategy="ABORT", meta=..., origin="VALIDATE_STRUCTURAL")
    # policy: phase_write_allowed, scope checks
    #   → провал: ClassificationResult(strategy="ABORT", meta=..., origin="VALIDATE_POLICY")
```

Два разных origin намеренны: structural failure (мусор от LLM) → `effective_abort_kind = "CORE_ABORT"`, AuditEngine пропускается; policy violation → `effective_abort_kind = "PROTOCOL_ABORT"`, AuditEngine запускается.

### LoopStepRecorded (расширенный)

В конце каждого DECIDE-шага записывается в EventStore:

```python
@dataclass(frozen=True)
class LoopStepRecorded:
    # существующие поля
    step_count: int
    retry_counts: dict[str, int]
    re_explain_count: int
    policy_version: str
    # новые поля error audit (None если status == OK)
    error_code: str | None
    severity: Literal["FATAL", "ERROR", "WARNING"] | None
    layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"] | None
    invariant_id: str | None
    rule_id: str | None
    strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"] | None
    origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"] | None
```

Заменяет упразднённый `ErrorClassified` event. [[trace-projection]] подписана и читает новые поля.

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
    error_code: str | None
    outcome: str | None         # заполняется на последнем шаге
```

`LoopStepRecorded` в EventStore дополнительно содержит `step_count`, `retry_counts`, `re_explain_count`, `policy_version` для LOOP-2 replay. [[trace-projection]] подписана на эти события; AgentLoop не пишет в неё напрямую.

## When To Use

Создаётся [[session-orchestrator]] на каждый TaskRun. Получает `phase_id` в конструктор — не резолвит его самостоятельно. Возвращает [[loop-outcome]] по завершению.

## Trade-offs

- FSM с explicit states → все переходы наблюдаемы и тестируемы детерминированно.
- Phase lock через конструктор: mid-loop phase switch не влияет на текущий AgentLoop.
- Прямые EventStore-записи (не через CommandBus) для `LoopStepRecorded`/`HumanGateReached`/`ErrorEvent` — нарушение GL-7 намеренно для L1 isolation; документировано в design.
- `ClassificationResult` из `validate()` и `ErrorClassifier.classify()`: единый тип → DECIDE не ветвится по источнику классификации.

## Open Questions

- [ ] (P1) Q129: Записывается ли полный raw output LLM в EventLog (LLMResponseReceived) или только parsed tool_call?
- [ ] (P1) Q130: Записывается ли финальный assembled prompt (после ContextKernel) в EventLog? Как реплеить если промпт изменился?
- [ ] (P1) Q131: При replay — можно ли подменять LLM на stub (записанные ответы)? Как изолировать LLM-вызов от CommandBus?
- [ ] (P1) Q132: Допускает ли система расхождение в текстовых ответах LLM при replay (fuzzy match) или требует bit-identical?
- [ ] (P1) Q133: Что если версия LLM изменилась между записью события и replay? Ошибка или допустимая вариация?
- [ ] (P2) Q138: Canonical список ролей агентов: Planner, Executor, Reviewer, Auditor. Могут ли переопределяться через PolicyKernel?
- [ ] (P2) Q139: Sequential (Planner→Executor→Reviewer) vs Streaming (Generator→Critic loop). Где описывается паттерн оркестрации фазы?
- [ ] (P2) Q140: Reviewer имеет только read+comment, Executor — read+write? Где задаётся tool ACL?
- [ ] (P2) Q141: Может ли Executor породить Sub-executor? Как отслеживаются деревья вызовов в EventLog через causation_event_id?
- [ ] (P2) Q142: Reviewer и Executor бесконечный цикл правок. Какой budget/timeout? Escalation to HUMAN_GATE?
- [ ] (P2) Q143: Как создаётся, передаётся и инвалидируется actor_id агента в сессии?
- [ ] (P3) Q215: Как задаётся максимум токенов на TaskRun? Кто enforces — LoopPolicy или отдельный budget guard?
- [ ] (P3) Q216: Как записываются LLM API costs? В EventLog как metric event или отдельный store?
- [ ] (P3) Q217: При каком % budget usage агент предупреждает? При 100% — HUMAN_GATE или ABORT?
- [ ] (P3) Q218: Как PolicyKernel управляет выбором модели (дорогая/дешёвая) для разных типов задач?
- [ ] (P3) Q219: При нехватке token budget — автоматическое сжатие context? Какой алгоритм? Влияние на детерминизм?
- [ ] (P3) Q220: Суммарный бюджет на фазу? Как распределяется между задачами?
- [ ] (P3) Q221: Как измерить ROI задачи — AgentScore / tokens_spent? Метрика M10?

## See Also

- [[session-orchestrator]]
- [[agent-handle]]
- [[loop-policy]]
- [[loop-outcome]]
- [[error-classifier]]
- [[classification-result]]
- [[error-event]]
- [[trace-projection]]
- [[policy-projection]]
- [[command-bus]]
