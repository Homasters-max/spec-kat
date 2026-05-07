# SDD System Architecture — Component Inventory & Boundaries

**Status:** CONSTITUTION — все последующие имплементации должны соответствовать этому документу  
**Date:** 2026-05-05  
**Source:** Архитектурный допрос (grill-me session), спеки v65–83, wiki domain/sdd  
**Supersedes:** частичные описания в `SDD Meta Harness Core.md`

---

## Определение системы

**SDD = детерминированный runtime для недетерминированного LLM.**

- **Human** — архитектор правил и аудитор: одобряет specs/фазы, резолвит HUMAN_GATE, ревьюит MetaOptimization proposals
- **LLM** — исполнитель: только tool calls через InputPort, управляется через AgentHandle
- **Harness** — контроллер: L0 обеспечивает каркас, L1 управляет поведением, L2 обеспечивает интеллект

Spec-Driven Development — жёсткий каркас (L0), внутри которого агент обретает свободу.

---

## Global Laws (неизменяемые)

```
GL-1 Determinism:  StateN = reduce(EventLog₀…N)
GL-2 SSOT:         EventLog — единственный источник истины
GL-3 Pipeline:     Command → Guard(L0) → Guard(L1) → handle → Event → Reducer → State
GL-4 Projection:   Projection := f(EventLog, Code)
GL-5 Isolation:    L0 не зависит от L1/L2
GL-6 Write Gate:   write разрешён только после start-task + resolve + explain + file ∈ write_scope
GL-7 EventStore:   event_store.append() доступен ТОЛЬКО из Command handlers (EventStore Guard)
GL-8 Sandbox:      каждый TaskRun исполняется в изолированном окружении (SandboxManager)
GL-9 Agent Loop:   нет постоянно живущего loop — Session Orchestrator chains stateless sessions
GL-10 L2 Access:   L2 компоненты доступны только через CommandBus + ReadModel
```

---

## Архитектурные решения (зафиксированные)

| Вопрос | Решение |
|--------|---------|
| GraphSessionState persistence | Вариант A: проекция EventLog (новые события) |
| Context building | Гибрид Push+Pull: base context pushed, LLM может Pull через resolve |
| Error recovery | ClassifiedRecovery: RETRY / RE_EXPLAIN / HUMAN_GATE / ABORT |
| Policy rules | Вариант C: PolicyUpdated events в EventLog (governance через EventLog) + Вариант A для L0 ядра |
| Agent loop | Вариант C: Session Orchestrator chains sessions (нет persistent loop) |
| Human gate | Passive: Orchestrator проверяет EventLog при старте сессии |
| CommandBus | Вариант C: ToolCallAdapter (LLM) → CommandBus → Guard → Handler → EventLog; CLI = human only |
| LLM in architecture | Вариант C: AgentHandle — managed resource с lifecycle start/step/terminate |
| ReadModel | Вариант A: materialized PostgreSQL projections, атомарный update с EventLog append |
| Graph layer | L0 (перенесён из L1): Graph/SpatialIndex — это проекция, не behavioral component |
| Sandbox lifecycle | Вариант A: один Sandbox per Task (create/commit/discard) |
| ScenarioSpec | L2: ScenarioGen автоматически генерирует из завершённых задач |

---

## L0 — Execution Core

*Неизменяемое ядро. Правила только code-enforced (никаких declarative overrides).*

| # | Блок | Описание |
|---|------|----------|
| 1 | **EventLog** | SSOT, append-only, PostgreSQL. Единственный источник истины. |
| 2 | **Reducer** | `State × Event → State`, pure function, deterministic, idempotent по `event.id` |
| 3 | **State** | Projections: phases, tasks, sessions, policies, scenarios. Восстанавливается из EventLog. |
| 4 | **Command + CommandContext** | Единица намерения. CommandContext несёт actor, phase_id, task_id, scope. |
| 5 | **L0 Guards** | Hard-coded spec invariants. Проверяются до handler. Никогда не декларативны. |
| 6 | **CommandRegistry** | `REGISTRY[name] → execute_and_project`. Единственная точка входа для команд. |
| 7 | **CommandBus** | Явная шина: `InputPort → Bus → Guard(L0) → Guard(L1) → Handler → EventLog`. |
| 8 | **WriteKernel** | `execute_and_project`: атомарный append EventLog + sync projections. |
| 9 | **EventStore Guard** | Физически запрещает `event_store.append()` вне Command handlers (I-CMD-ONLY-1). |
| 10 | **UpcasterRegistry** | Event schema versioning. Все события проходят `upcast(e)` перед reduce. |
| 11 | **ErrorEvent** | Typed event: `error_type`, `stage`, `recovery_strategy`. Emitted before any raise. |
| 12 | **ProjectionRegistry** | Синхронно обновляет все materialized PostgreSQL projections при каждом EventLog append. |
| 13 | **Graph / SpatialIndex** | Проекция: `f(Code, Specs, EventLog) → nodes + edges`. Structural context SSOT. |

---

## L1 — Harness Core

*Контроль поведения агента. Детерминированные projections и enforcement.*

| # | Блок | Описание |
|---|------|----------|
| 14 | **QueryEngine** | Typed `Query → ContextSnapshot`. Детерминированный (order_by обязателен). Читает Graph (L0). |
| 15 | **ExecutionGuard** | Enforces `resolve→explain→write` cycle. Fingerprint guard блокирует stale explain. |
| 16 | **ScopeGuard** | File write scope enforcement через scope_policy. Блокирует запись вне write_scope. |
| 17 | **TraceStore** | Execution traces + `model_version` в каждом TraceEvent. Аудитабельность поведения. |
| 18 | **ErrorClassifier** | Классифицирует guard failures → `RETRY / RE_EXPLAIN / HUMAN_GATE / ABORT`. Блок в L1. |
| 19 | **Session Orchestrator** | Chains sessions. Проверяет human gate events в EventLog перед стартом. Нет persistent loop. |
| 20 | **ContextKernel** | Hybrid Push+Pull. Base context (граф задачи + scope + статус) pushes к LLM. LLM может Pull via resolve. |
| 21 | **InputPort (ToolCallAdapter)** | Translates tool_use API calls → CommandBus. CLI остаётся исключительно для human. |
| 22 | **AgentHandle** | Managed LLM lifecycle: `start(model, config) / step(context) → action / terminate()`. Логирует `model_version`. |
| 23 | **SandboxManager** | Per-task isolation: `create(task_id) → SandboxHandle / commit / discard`. Isolated FS + deterministic seed + no network. |
| 24 | **AuditEngine** | M1–M9 → `AgentScore`. Детерминированный расчёт. Читает TraceStore + EventLog через ReadModel. |

### Метрики AuditEngine

```
AgentScore =
  0.20 * M1 (protocol compliance)
+ 0.20 * M2 (scope adherence)
+ 0.20 * M3 (tests)
+ 0.10 * M4 (focus)
+ 0.10 * M5 (time)
+ 0.10 * M6 (behavior)
+ 0.05 * M7 (completion)
+ 0.05 * M8 (step_correctness)
+ 0.10 * M9 (execution_correctness)
```

M9 = детерминированная оценка по ScenarioSpec checks. Если любой `critical=true` check failed → M9=0.

---

## L2 — Extensions

*Только через CommandBus + ReadModel. Не нарушают L0.*

| # | Блок | Описание |
|---|------|----------|
| 25 | **RAG** | Retrieval: исторические трейсы похожих задач + extended read context вне write_scope. Интерфейс: `RAGQuery(task_id, query_type) → List[Fragment]`. |
| 26 | **PolicyKernel** | Governance rules через EventLog. `PolicyUpdated` events. `norm_catalog.yaml` → EventLog. Human одобряет изменения. |
| 27 | **MetaOptimization** | TraceStore + AuditEngine analysis → Policy proposals. Feedback loop: агент → трейс → анализ → политика → агент. Human gate перед применением. |
| 28 | **ScenarioGen** | Завершённые задачи (trace + summary + outputs) → `ScenarioSpec`. Ground truth для M9. Детерминированная генерация. |

---

## Новые типы событий

*Необходимы для полноты проекций. Добавляются в EventRegistry.*

| Событие | Проекция |
|---------|----------|
| `TaskSessionStarted` | GraphSessionState |
| `GraphResolved` | GraphSessionState |
| `TaskExplained` | GraphSessionState |
| `WriteExecuted` | GraphSessionState |
| `PolicyUpdated` | PolicyKernel projection |
| `HumanGateReached` | Session Orchestrator state |
| `ErrorClassified` | Error audit log |
| `ScenarioGenerated` | ScenarioSpec store |

---

## Execution Flow (полный)

```
[Human starts session]
    ↓
Session Orchestrator: check EventLog for human gate clearance
    ↓
ContextKernel: Push base context (Graph query + scope + status)
    ↓
AgentHandle.step(context) → LLM generates tool call
    ↓
InputPort: tool_use → CommandBus
    ↓
CommandBus:
  → L0 Guards (state invariants)
  → EventStore Guard (handler-only access check)
  → L1 ExecutionGuard (resolve→explain→write protocol)
  → L1 ScopeGuard (file scope check inside Sandbox)
    ↓
WriteKernel:
  → Handler (pure, returns events)
  → EventStore.append (atomic)
  → ProjectionRegistry.sync (all materialized projections)
  → Reducer updates State
    ↓
ErrorClassifier (on failure): RETRY / RE_EXPLAIN / HUMAN_GATE / ABORT
    ↓
TraceStore.record(action, result, model_version)
    ↓
[Task complete]
SandboxManager.commit() OR discard()
AuditEngine.calculate(M1–M9) → AgentScore
ScenarioGen.build(task_artifacts) → ScenarioSpec
    ↓
[Phase complete]
MetaOptimization.analyze() → Policy proposals → [Human gate]
```

---

## Два актора

| Актор | Разрешено | Запрещено |
|-------|-----------|-----------|
| **Human** | activate-phase, approve spec, резолвить HUMAN_GATE, ревьюить MetaOptimization proposals, CLI | Прямая запись в EventLog, bypass guards |
| **LLM** | tool calls через InputPort, resolve/explain/write в write_scope | Прямой CLI, append вне handler, modify .sdd/specs/, activate-phase без --executed-by llm |

---

## Блоки по статусу реализации

**Определены в коде (src/sdd/):**
EventLog, Reducer, State, Command, CommandContext, L0 Guards, CommandRegistry, WriteKernel, UpcasterRegistry, ErrorEvent, QueryEngine, ExecutionGuard (частично), ScopeGuard, TraceStore (частично), Graph (частично)

**Определены в спеках, не реализованы:**
ProjectionRegistry, EventStore Guard, CommandBus (явный), InputPort, AgentHandle, SandboxManager, AuditEngine (M1–M8 частично, M9 Phase 74), ErrorClassifier, Session Orchestrator, ContextKernel

**Определены в этом документе как архитектурные блоки:**
RAG, PolicyKernel, MetaOptimization, ScenarioGen

---

*Этот документ фиксирует архитектурные границы и инвентарь компонентов SDD. Изменение любого блока требует новой спеки + human approval.*
