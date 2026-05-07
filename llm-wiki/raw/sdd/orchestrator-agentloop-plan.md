# Plan: Orchestrator Architecture — Wiki Evolution (reviewed)

## Context

Внутренний цикл агента (inner loop) сейчас живёт как псевдокод в `pattern/agent-handle` без формализации. У него нет имени, нет FSM-состояний, нет типизированного контракта с SessionOrchestrator. Retry-логика использует хардкоженный `MAX_RETRIES`. Policy не интегрирована в loop. Phase-awareness отсутствует.

Цель: формализовать AgentLoop как самостоятельный L1-компонент с детерминированным FSM, Policy-driven поведением, replay-safe решениями.

---

## Архитектурные решения

**AgentLoop — новый L1-компонент** (не переименование AgentHandle).  
Отношение: `SessionOrchestrator → AgentLoop → AgentHandle`.  
AgentHandle остаётся чистым LLM API wrapper (start/step/terminate).

**LoopState — эфемерный in-memory dataclass** (не персистируется, совместимо с GL-9).  
Все решения loop фиксируются через events (ErrorClassified, LoopStepRecorded) — replay-safe.

**`phase_id` передаётся в конструктор AgentLoop от SessionOrchestrator** — не читается из State самостоятельно. Phase lock явен в сигнатуре; mid-loop phase switch не влияет на текущий AgentLoop (завершается в своём контексте).

**Phase-awareness через PolicyProjection**, не через `if phase == X` в коде.  
`memory.read.policy(scope=phase_id)` возвращает phase-scoped rules.

---

## Инварианты AgentLoop (обязательные)

| ID | Формулировка |
|----|-------------|
| LOOP-1 | Policy читается по `PolicyProjection.last_update_offset` (детерминировано); при первом входе в PLAN и при каждом RE_EXPLAIN, если `policy_projection.last_update_offset > loop_state.last_policy_offset` |
| LOOP-2 | Все decision-точки loop **replayable из EventLog**: `LoopStepRecorded` содержит снапшот счётчиков (`step_count`, `retry_counts`, `re_explain_count`) и `policy_version`; replay из EventLog полностью восстанавливает LoopState |
| LOOP-EXIT | Каждый loop завершается **ровно одним** из: `COMPLETE \| GATE \| CORE_ABORT \| PROTOCOL_ABORT` |

---

## FSM AgentLoop

```
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
| PLAN | Фиксирует `phase_id` (phase lock на первом входе); читает PolicyProjection `at_offset=current_event_log_offset` → PolicySnapshot; при RE_EXPLAIN: если `policy_projection.last_update_offset > last_policy_offset` → перечитывает Policy; инициализирует/обновляет LoopState |
| STEP | `ContextKernel.build_base() + pulls → AgentHandle.step(context) → ToolCall`; затем `AgentLoop.validate(tool_call)` перед dispatch |
| OBSERVE | `CommandBus.dispatch(tool_call)` → CommandResult (строго типизирован) |
| DECIDE | Детерминированное ветвление по CommandResult; инкремент счётчиков в LoopState; запись LoopStepRecorded в EventStore |
| GATE | `EventStore.append(HumanGateReached(...))` → `AgentHandle.terminate("gate")` → `LoopOutcome.GATE` |
| CORE_ABORT | `EventStore.append(ErrorEvent(...))` → `AgentHandle.terminate("abort")` → `LoopOutcome.CORE_ABORT` |
| PROTOCOL_ABORT | `EventStore.append(ErrorEvent(...))` → `AgentHandle.terminate("abort")` → `LoopOutcome.PROTOCOL_ABORT` |
| DONE | `AgentHandle.terminate("complete")` → `LoopOutcome.COMPLETE` |

> **Важно:** AgentLoop эмитит `HumanGateReached`/`ErrorEvent` **напрямую в EventStore** до вызова `AgentHandle.terminate()`. AgentHandle остаётся чистым LLM API wrapper. `LoopStepRecorded` также идёт напрямую в EventStore, не через CommandBus.

### CommandResult (строго типизирован)

```python
@dataclass(frozen=True)
class CommandResult:
    status: Literal["OK", "ERROR"]
    error_type: str | None          # None если status == OK
    task_complete: bool             # True только если агент вызвал sdd_complete
```

Без строгой типизации DECIDE недетерминирован — поэтому это обязательно.

### DECIDE: полная логика

```python
def decide(result: CommandResult, loop_state: LoopState) -> Transition:
    # 1. Успех — проверяется ДО budget (task_complete имеет приоритет)
    if result.status == "OK":
        if result.task_complete:
            return Transition.DONE
        # 2. Бюджет шагов — hard stop (только если задача не завершена)
        if loop_state.step_count >= loop_state.policy.step_budget:
            return Transition.GATE
        return Transition.STEP  # продолжаем

    # 2. Бюджет шагов при ошибке
    if loop_state.step_count >= loop_state.policy.step_budget:
        return Transition.GATE

    # 3. Ошибка — классифицируем
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
    # structural validation: обязательные поля, типы → при провале: CORE_ABORT
    # policy validation: phase_write_allowed, scope checks → при провале: PROTOCOL_ABORT
```

**Два разных исхода:**
- Structural failure (невалидный формат ToolCall — мусор от LLM) → `CORE_ABORT` (L0 нарушение, AuditEngine пропускается)
- Policy violation (структурно корректный ToolCall, нарушает policy, напр. write при `phase_write_allowed=False`) → `PROTOCOL_ABORT` (AuditEngine запускается, MetaOptimization получает поведенческий сигнал)

### ErrorClassifier: полный mapping по категориям

| Категория | Примеры `error_type` | Стратегия |
|---|---|---|
| Graph errors | `TASK_ISOLATED`, `NO_PATH`, `CONTEXT_STALE`, `GRAPH_CHANGED_AFTER_EXPLAIN` | RE_EXPLAIN |
| Transient errors | `TIMEOUT`, `RATE_LIMIT` | RETRY |
| Policy/scope violations | `SCOPE_VIOLATION`, `PERMISSION_DENIED` | HUMAN_GATE |
| Unknown / unclassified | любой `error_type` не в списках | ABORT → PROTOCOL_ABORT |

`ErrorClassifier.classify(result: CommandResult, loop_state: LoopState)` — сигнатура с `loop_state` для доступа к policy. Budget enforcement остаётся в `decide()`.

---

## LoopState

```python
@dataclass
class LoopState:
    phase_id: str                           # передаётся в конструктор от SessionOrchestrator (phase lock)
    step_count: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)  # error_type → count
    re_explain_count: int = 0
    policy: PolicySnapshot = field(...)     # читается at_offset; обновляется при RE_EXPLAIN (LOOP-1)
    last_policy_offset: int = 0            # offset последнего PolicyProjection update event (не глобальный EventLog offset)
```

---

## LoopTrace (минимальный, для audit + MetaOptimization)

```python
@dataclass
class LoopTraceEntry:
    step: int
    tool_call_type: str         # "resolve" | "explain" | "write" | ...
    decision: str               # "RETRY" | "RE_EXPLAIN" | "GATE" | "ABORT" | "DONE" | "CONTINUE"
    error_type: str | None
    outcome: str | None         # заполняется на последнем шаге
```

`LoopStepRecorded` event в EventStore содержит дополнительно (для LOOP-2 replay):

```python
step_count: int
retry_counts: dict[str, int]
re_explain_count: int
policy_version: str             # "0.0.0-bootstrap" при lazy bootstrap (см. LoopPolicy)
```

AgentLoop эмитит `LoopStepRecorded` **напрямую в EventStore** (не через CommandBus). TraceProjection подписана и обновляет SQL-таблицу. AgentLoop не пишет в TraceProjection напрямую (LOOP-2, L1 isolation).

---

## LoopPolicy — ключи в PolicyProjection

```python
step_budget: int                     # макс. шагов за сессию (default: 50); hard stop
retry_budget: dict[str, int]         # error_type → макс. retry; fallback: "DEFAULT"
  # пример: {"NO_EXPLAIN_BEFORE_WRITE": 3, "TASK_ISOLATED": 2, "DEFAULT": 2}
re_explain_budget: int               # макс. RE_EXPLAIN переходов за сессию (default: 2)
phase_write_allowed: bool            # false в VALIDATE-фазе → write tool_calls отклоняются в STEP
gate_freeze_ttl_hours: int           # TTL frozen Sandbox при GATE (default: 24); истёк → discard() + ErrorEvent
```

**Убрано из v1:** `write_cycle_budget` — нет соответствующего счётчика и enforcement-логики.

**Backward compat:** `retry_limit: int` (scalar) → AgentLoop читает как `{"DEFAULT": retry_limit}`.

**Lazy bootstrap:** при отсутствии записи `memory.read.policy(scope=phase_id)` возвращает `PolicySnapshot` с дефолтными значениями и `policy_version = "0.0.0-bootstrap"`. Дефолты документируются как контракт (не примеры). Human переопределяет через `memory.write.policy(...)`.

---

## LoopOutcome — контракт между AgentLoop и SessionOrchestrator

```python
class LoopOutcome(Enum):
    COMPLETE        # task_complete=true обязателен в последнем CommandResult
    GATE            # HumanGateReached event уже в EventLog; SandboxManager.freeze()
    CORE_ABORT      # structural/L0 violation; SandboxManager.discard(); AuditEngine НЕ запускается
    PROTOCOL_ABORT  # невалидный policy или исчерпан budget или UNKNOWN error; AuditEngine запускается (M1-M8, M9=0)
```

### SessionOrchestrator ветвление

| LoopOutcome | SessionOrchestrator |
|---|---|
| `COMPLETE` | commit результата, закрыть сессию |
| `GATE` | `SandboxManager.freeze(ttl=policy.gate_freeze_ttl_hours)`; сессия terminates; human уведомляется; новый AgentLoop при возобновлении работает в том же Sandbox (unfreeze); по истечении TTL → `SandboxManager.discard()` + `ErrorEvent` |
| `CORE_ABORT` | `SandboxManager.discard()` немедленно; сессия закрывается без AuditEngine; `ErrorEvent` уже в EventLog |
| `PROTOCOL_ABORT` | AuditEngine запускается (M1-M8, M9=0 принудительно); результат для MetaOptimization; сессия закрывается |

### Consistency гарантии

- `COMPLETE` → `task_complete == true` в последнем CommandResult (иначе — GATE, не COMPLETE)
- `GATE` → `HumanGateReached` event уже в EventLog до возврата; Sandbox frozen
- `CORE_ABORT` → `ErrorEvent` (L0 violation) уже в EventLog; Sandbox немедленно discard; AuditEngine пропускается
- `PROTOCOL_ABORT` → `ErrorEvent` (validation/budget/unknown) в EventLog; AuditEngine запускается в ограниченном режиме

---

## Изменения в wiki

### СОЗДАТЬ (3 новые страницы)

| Файл | Ключевое содержание |
|------|-------------------|
| `pattern/agent-loop.md` | FSM + инварианты LOOP-1/LOOP-2/LOOP-EXIT, LoopState, CommandResult, DECIDE логика (с fix: task_complete до step_budget), LoopTrace, ToolCall validation (structural vs policy), phase lock через конструктор |
| `pattern/loop-policy.md` | Справочник policy-ключей, per-error retry_budget с DEFAULT fallback, phase_write_allowed, step_budget как hard stop, gate_freeze_ttl_hours, DEFAULT_POLICY_VERSION="0.0.0-bootstrap", lazy bootstrap, дефолты как контракт |
| `pattern/loop-outcome.md` | LoopOutcome enum (COMPLETE/GATE/CORE_ABORT/PROTOCOL_ABORT), consistency guarantees, SessionOrchestrator ветвление, SandboxManager.freeze/discard/TTL |

### ЭВОЛЮИРОВАТЬ (5 страниц)

| Файл | Что меняется |
|------|-------------|
| `pattern/agent-handle.md` | Убрать inner loop псевдокод → ссылка на [[agent-loop]]; terminate принимает `"complete"\|"gate"\|"abort"` |
| `pattern/error-classifier.md` | Сигнатура: `classify(result: CommandResult, loop_state: LoopState)`; убрать MAX_RETRIES хардкод; полный mapping по категориям (Graph/Transient/Policy/Unknown); UNKNOWN → PROTOCOL_ABORT (fail-safe) |
| `pattern/session-orchestrator.md` | Шаг 6: `AgentLoop.run() → LoopOutcome`; полная таблица ветвления COMPLETE/GATE/CORE_ABORT/PROTOCOL_ABORT; SandboxManager.freeze с TTL |
| `pattern/policy-projection.md` | Добавить loop-specific ключи; `retry_budget` как dict; `gate_freeze_ttl_hours`; `scope=phase_id` API; lazy bootstrap контракт |
| `pattern/sdd-meta-harness.md` | L1 = 12 компонентов (добавить AgentLoop, LoopTrace); обновить execution flow |

---

## Порядок выполнения

1. `pattern/loop-policy.md` — vocabulary + bootstrap контракт, нет зависимостей
2. `pattern/loop-outcome.md` — маленькая, нет зависимостей
3. `pattern/agent-loop.md` — центральная страница (ссылается на 1, 2 и существующие)
4. `pattern/error-classifier.md` — полный mapping + сигнатура
5. `pattern/agent-handle.md` — убрать loop псевдокод
6. `pattern/session-orchestrator.md` — делегировать AgentLoop, ветвление + Sandbox
7. `pattern/policy-projection.md` — добавить loop-ключи + gate_freeze_ttl_hours
8. `pattern/sdd-meta-harness.md` — обновить компонентный список

---

## Проверки совместимости

- **GL-9:** LoopState эфемерный, AgentLoop создаётся заново каждую сессию ✓
- **LOOP-1:** Policy читается по `PolicyProjection.last_update_offset` (не глобальный EventLog offset); при RE_EXPLAIN перечитывается только если offset изменился ✓
- **LOOP-2:** Все decision-точки через events (LoopStepRecorded с counters snapshot + policy_version); replay из EventLog полностью восстанавливает LoopState ✓
- **LOOP-EXIT:** Все exit paths → COMPLETE | GATE | CORE_ABORT | PROTOCOL_ABORT ✓
- **L1/L2 изоляция:** AgentLoop читает только L1 API; LoopTrace через EventStore напрямую (не через CommandBus, не напрямую в TraceProjection) ✓
- **GL-5 (L0 изоляция):** все tool calls через `CommandBus.dispatch()` ✓
- **Audit coverage:** PROTOCOL_ABORT сохраняет M1-M8; MetaOptimization получает сигнал о невалидных tool_calls и UNKNOWN errors ✓
- **phase_id contract:** передаётся конструктором от SessionOrchestrator; AgentLoop не резолвит phase самостоятельно ✓
- **Sandbox GATE semantics:** freeze (не discard); TTL через `gate_freeze_ttl_hours`; новый AgentLoop при возобновлении работает в том же Sandbox ✓

---

## Верификация после реализации

1. `wiki apply` / `wiki derive` — `by-domain.md` содержит 3 новые страницы
2. Все новые страницы: корректный frontmatter (id, page_type, domain=sdd, layer=architecture)
3. See Also ссылки ведут на реальные page ids
4. `pattern/sdd-meta-harness.md` перечисляет AgentLoop в L1-блоках (12 компонентов)
5. `pattern/error-classifier.md` не содержит `MAX_RETRIES` хардкода; содержит полный category mapping
6. `pattern/loop-policy.md` документирует дефолты как контракт; содержит `gate_freeze_ttl_hours`
7. `LoopStepRecorded` schema содержит `step_count`, `retry_counts`, `re_explain_count`, `policy_version`
8. DECIDE логика: `task_complete` проверяется до `step_budget`
