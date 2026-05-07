# Plan: SDD Bounded Contexts — wiki documentation

## Context

В wiki уже есть `sdd-component-inventory` (30 блоков, L0/L1/L2) и `sdd-meta-harness` (execution flow).
Оба документа режут систему **горизонтально** — по уровню детерминизма.

Цель: добавить **вертикальный** разрез — 4 Bounded Contexts. Ключевой тезис:
> Bounded Contexts — это не про папки, а про правила взаимодействия: инварианты + контракты + enforcement.

Основной сценарий использования страницы: **разработчик хочет понять, почему прямой вызов Engine→Blueprint запрещён** (scenario B). Страница объясняет enforcement rules, а не просто перечисляет компоненты.

Blueprint вводит **5 новых компонентов** `[proposed]`:
- SpecManager (L2, Blueprint)
- PlanManager (L2, Blueprint)
- PhaseOrchestrator (L2, Blueprint)
- ConstitutionParser (**L2**, Blueprint — парсит constitution, публикует ConstitutionProjection)
- MemoryLayer (**L1**, Core — типизированный фасад над ProjectionRegistry)

> **Исправление к первоначальному плану:** ConstitutionParser перенесён из Engine в Blueprint (L2).
> Парсинг формата constitution.md — это domain knowledge Blueprint. Engine читает ConstitutionProjection
> через MemoryLayer, а не парсит файл напрямую.

## Scope

Только `/root/project/obsidian-vault/llm-wiki/wiki/`. В другие папки не ходим.

---

## Страница `idea/sdd-bounded-contexts.md` — полная структура

### Summary

```
Два ортогональных разреза SDD:

Horizontal (execution semantics): L0 Core → L1 Execution → L2 Intelligence
Vertical (domain ownership):      Core / Blueprint / Engine / Intelligence

Каждый компонент = (Layer, Domain)
```

### Lifecycle Boundaries

```text
Domain Foundation:
  - persisted via EventLog
  - replayable, deterministic

Execution Runtime:
  - ephemeral, NOT replayable
  - produces Commands only
```

Инварианты:
- **I-BC-1**: Runtime MUST NOT mutate EventStore directly
- **I-BC-2**: Foundation MUST NOT depend on Runtime state

### Consistency Model

Граница синхронности — критичная деталь, которую легко пропустить:

```text
Strong consistency (within WriteKernel transaction):
  L1 reads within same transaction always see own writes.
  Enforced by single PostgreSQL transaction boundary.

Snapshot consistency (L1 cross-transaction):
  Snapshot built once at AgentLoop.start() (PLAN state).
  Stable for full cycle duration.
  Staleness bound: ≤ 1 AgentLoop iteration.
  Refreshed only on explicit RE_EXPLAIN transition (LOOP-1).

Eventual consistency (L2 only):
  EmbeddingProjection, SemanticSearch — no staleness bound.
  L2 failure does NOT affect L1, Guards, or EventLog (ML-9).
```

Как это работает на практике:
```text
1. Command → WriteKernel
2. Handler emits events
3. Events append to EventLog
4. Projections updated SYNCHRONOUSLY within append()
5. AgentLoop начинает новый цикл → poll всех нужных проекций

⟹ Projection read в начале цикла = консистентный snapshot всех предыдущих команд
⟹ NO synchronous cross-domain calls EVER
```

Почему не "eventually consistent":
> Этот термин подразумевает неограниченную задержку сходимости (Cassandra, DynamoDB).
> Здесь staleness строго ограничен: каждый новый цикл AgentLoop читает проекции,
> синхронно обновлённые в предыдущих командах. Задержка = один цикл, не "когда-нибудь".

Правило:
```text
If Engine needs immediate decision → read Projection via MemoryLayer
If Engine needs to change state   → emit Event
```

Инварианты:
- **I-CONSISTENCY-1**: Cross-domain consistency = cycle-bounded; only within-WriteKernel-transaction = strongly consistent
- **I-SEAM-4**: Projection updates MUST be synchronous within `append()` — иначе модель consistency ломается
- **I-TX-1**: WriteKernel transaction = ONLY atomic boundary in system

### Observability Events — разрешение конфликта GL-7 / AgentLoop / I-BC-1

**Проблема:** три документа давали конфликтующие ответы на вопрос «кто может писать в EventStore?»
- `global-laws.md` GL-7: «только из Command handlers»
- `agent-loop.md`: AgentLoop пишет LoopStepRecorded / HumanGateReached / ErrorEvent напрямую — «намеренное нарушение GL-7 для L1 isolation»
- I-BC-1: «Runtime MUST NOT mutate EventStore directly»

**Решение (принято):** вводятся два типа событий с разными enforcement rules.

```text
Domain Events       — производятся CommandHandler'ами
                    — идут через WriteKernel (OCC, projection sync, full pipeline)
                    — мутируют domain state и проекции

Observability Events — производятся L1 Runtime напрямую
                    — обходят WriteKernel и CommandBus
                    — НЕ мутируют domain projections (Reducer их игнорирует)
                    — проходят через EventStoreGuard (origin check: вызов только из L1 Runtime)
```

**Исчерпывающий список Observability Events (закрытый, без ad-hoc дополнений):**
- `LoopStepRecorded` — фиксация шага AgentLoop
- `HumanGateReached` — AgentLoop достиг human gate
- `ErrorEvent` — L1 Runtime сигнализирует об ошибке

**Уточнение GL-7:** "event_store.append() только из Command handlers" — применяется к Domain Events.
Observability Events — легальное исключение, медиируемое EventStoreGuard.

**Уточнение I-BC-1:** "Runtime MUST NOT mutate EventStore directly" — "напрямую" = в обход EventStoreGuard.
Observability Events идут через EventStoreGuard (который проверяет: вызов из L1 Runtime, событие в whitelist) — I-BC-1 не нарушается.

Инварианты:
- **I-OBS-1**: Observability Events MUST NOT appear in Reducer's event-to-state map; projections MUST ignore them
- **I-OBS-2**: The list of Observability Events is closed (exhaustive); adding new ones requires explicit protocol decision, не inline в код
- **I-OBS-3**: EventStoreGuard MUST validate Observability Event origin (call-stack: L1 Runtime module) AND event type (whitelist)
- **I-OBS-4**: Observability Events are append-only like Domain Events but do NOT trigger ProjectionRegistry.sync()
- **I-OBS-5**: Observability Events MUST preserve ordering relative to Domain Events within the same step: Domain Event THEN Observability Event. Enforced by append order inside WriteKernel.execute_and_project() — Observability Events are appended in the same EventLog but after Domain Events for the same step. Guarantees replay produces identical trace.

### Domains Table (ownership + events)

| Domain | Role | Owns | Produces Events |
|--------|------|------|----------------|
| Core | Physics of system | EventLog, Reducer, WriteKernel, ProjectionRegistry, MemoryLayer | — |
| Blueprint | Project model (human-facing) | SpecProjection, PlanProjection, PhaseStateProjection, PolicyProjection, ConstitutionProjection, TaskScopeProjection, ProposalProjection | SpecDrafted, SpecApproved, PlanCreated, PhaseStarted, PhaseCompleted, PhaseAbandoned, ProposalApplied, ProposalRejected |
| Engine | Execution runtime | AgentLoop, ContextKernel, Sandbox | TaskStarted, StepExecuted, WriteApplied, ErrorOccurred, TaskCompleted |
| Intelligence | Analysis | Metrics, Replay, Audit | MetricComputed, ProposalGenerated |

Ключевые ограничения ownership:
- Только Blueprint эмитит фазовые события (`PhaseStarted`, `PhaseCompleted`). Engine НЕ может инициировать фазы.
- Intelligence НИКОГДА не меняет state напрямую. Только через human gate → Blueprint-команды.
- Orchestration logic (что делать следующим) — в Blueprint (PhaseOrchestrator). Engine только исполняет.

### Компоненты Blueprint [proposed] — детальные обязанности

#### SpecManager (L2)
Управляет жизненным циклом и качеством спецификаций.
- **Traceability**: связывает спеку с исходными требованиями (Requirement ID)
- **Validation Gate**: проверяет спеку против ConstitutionProjection (нарушения конституции → reject)
- **Idempotency**: дедуплицирует спеки по hash/имени; `SpecDrafted` эмитируется только один раз
- **Coverage Tracking**: владеет данными о покрытии секций спеки задачами; нельзя `ApproveSpec` при uncovered секциях

#### PlanManager (L2)
Строит и валидирует детерминированный граф исполнения фазы.
- **Dependency DAG**: задачи — это DAG, не список; зависимости между задачами enforced
- **Scope Isolation**: вычисляет `write_scope` для каждой задачи → TaskScopeProjection (используется SandboxManager)
- **Conflict Detection**: запрещает параллельные задачи с пересекающимися write_scope

#### PhaseOrchestrator (L2)
Мозг Blueprint — управляет макро-состоянием фазы. **Coordinator, не Engine**: принимает решения, но не исполняет их напрямую.
- **Next Task**: читает TaskScopeProjection через MemoryLayer, определяет следующую задачу по DAG
- **Definition of Done**: проверяет критерии завершения фазы (все задачи выполнены, порог AgentScore достигнут)
- **Cross-Phase Dependencies**: проверяет наличие артефактов от предыдущих фаз
- **Force Transition**: обрабатывает команду человека "перейти на следующую фазу" → эмитит `PhaseAbandoned`

**I-ORCH-1**: PhaseOrchestrator MUST be pure decision logic — no execution side-effects. All decisions output Commands or Events via CommandBus. All execution delegated to SandboxManager / AgentHandle / AuditEngine. Внутренних условий вида «если phase == X выполнить Y» быть не должно — это domain business logic, которой в Orchestrator нет.

#### ConstitutionParser (L2, Blueprint)
Парсит `constitution.md`, публикует `ConstitutionProjection`.
- Engine читает ConstitutionProjection через `memory.read.constitution()` — не знает о парсере
- SpecManager использует ConstitutionProjection для validation gate

### Intelligence feedback loop

```text
MetaOptimization → ProposalGenerated → EventLog
Blueprint читает ProposalProjection через MemoryLayer
PhaseOrchestrator видит pending proposal → останавливает цикл → HUMAN_GATE
  ├─ human: ApplyProposal → Blueprint обрабатывает через SpecManager/PlanManager
  └─ human: RejectProposal → ProposalRejected → EventLog → цикл продолжается
```

Intelligence никогда не меняет state напрямую. I-BC-1 не нарушается.

### Domain Contracts (ключевая секция)

Каждый домен открывает только:
1. **Commands** (input)
2. **Events** (output)
3. **Projections** (read-only, через MemoryLayer)

Контракты взаимодействия:
```text
Blueprint → Engine:       Event: SpecApproved → Engine реагирует (via projection poll)
Engine → Blueprint:       Event: TaskCompleted → PhaseOrchestrator обновляет PhaseState
Intelligence → Blueprint: Event: ProposalGenerated → human gate → ApplyProposal / RejectProposal
```

Ownership:
- **I-CMD-OWN-1**: Each Command MUST belong to exactly one domain
- **I-EVENT-OWN-1**: Each Event has exactly one owning domain

**CommandBus как domain-enforcing facade (упрощённая модель):**

Один экземпляр CommandBus + CommandRegistry (command → domain) + domain-ownership guard.
Cross-domain dispatch → `CommandBusBoundaryError` (не молчаливый игнор, а явный сбой).

```text
ONE CommandBus (singleton, I-CMD-SINGLETON-1)
  CommandRegistry: command_type → domain
  
  dispatch(cmd, caller_domain):
    cmd_domain = CommandRegistry.lookup(cmd.type).domain
    if caller_domain != cmd_domain:
        raise CommandBusBoundaryError(cmd.type, caller_domain, cmd_domain)

# ✅ Blueprint команда из Blueprint контекста
command_bus.dispatch(SpecDraftCommand(...), caller_domain="blueprint")

# ❌ CommandBusBoundaryError: TaskStartedCommand принадлежит Engine
command_bus.dispatch(TaskStartedCommand(...), caller_domain="blueprint")
```

Почему не multiple instances: domain-partitioned экземпляры дублируют enforcement, который уже есть
в CommandRegistry + lint-правилах. Три механизма контроля одного нарушения — tech debt.
ONE bus + ONE guard = единая точка ответственности.

- **I-CMD-SINGLETON-1**: Exactly ONE CommandBus instance MUST exist per runtime. L2 extensions MUST NOT create secondary CommandBus instances.
- **I-CMD-BUS-1**: CommandBus MUST validate domain ownership via CommandRegistry; dispatch MUST raise CommandBusBoundaryError if caller_domain != command_domain.
- **I-CMD-BUS-2**: Cross-domain triggering MUST go via Event emission + projection poll, never via cross-domain bus dispatch.
- **I-CORE-BUS-1**: CommandBus MUST NOT import L1/L2 modules directly. L1 middleware injected via factory create_command_bus() (DI pattern).

### Shared Kernel: `core/contracts/`

Проблема: Events/Commands/DTOs должны быть доступны всем доменам, но не должны тянуть бизнес-логику.

```text
src/sdd/core/
  contracts/      ← ONLY shared types (Events, Commands, DTOs, TaskScopeDataclass)
  runtime/        ← EventLog, WriteKernel, ProjectionRegistry, Guards, MemoryLayer[p]
```

Паттерн cross-domain контракта (3 слоя):
```text
1. core/contracts/scopes.py      ← TaskScopeDataclass (тип, доступен всем)
2. blueprint/projections/task_scope.py  ← логика вычисления scope (владелец — Blueprint)
3. memory.read.task_scope(task_id)      ← типизированный доступ для Engine
```

Engine НЕ знает про `blueprint/projections/`. Engine вызывает только `memory.read.*`.

**MemoryLayer registration contract (решение кандидата 4, domain-namespaced):**

Каждая cross-domain проекция ОБЯЗАНА иметь явный именованный метод в MemoryLayer API.
Нет метода в MemoryLayer → нет cross-domain доступа. Wildcards и generic get(projection_name) запрещены.

API организован по domain-namespace для снижения когнитивной нагрузки и явного ownership:

```text
memory.blueprint.read.spec(phase_id)          ← Blueprint domain
memory.blueprint.read.task_scope(task_id)     ← Blueprint domain
memory.blueprint.read.constitution()          ← Blueprint domain
memory.blueprint.read.policy(scope)           ← Blueprint domain

memory.engine.read.trace(task_id)             ← Engine domain (если нужно другим доменам)

memory.intelligence.read.metrics(task_id)     ← Intelligence domain
memory.intelligence.read.audit_score(task_id) ← Intelligence domain
```

Добавление cross-domain проекции = 3 обязательных шага:
  1. <domain>/projections/<name>.py              ← логика проекции (владелец — домен)
  2. core/contracts/<name>_dto.py                ← DTO типа (доступен всем)
  3. MemoryLayer.<domain>.read.<name>(...)       ← явный именованный метод (обязательно)

Шаг 3 НЕ опциональный. Без него проекция недоступна другим доменам.

Это означает: MemoryLayer API растёт явно при каждом новом cross-domain projection.
Growth is intentional — каждый новый метод = явное архитектурное решение.

- **I-ML-REG-1**: Every cross-domain projection MUST have an explicit named method in MemoryLayer; wildcard/generic access is forbidden
- **I-ML-NS-1**: MemoryLayer MUST be domain-namespaced: `memory.<domain>.read.<projection_name>(...)`. Flat `memory.read.*` namespace is forbidden — it hides ownership and enables implicit coupling.
- **I-ML-REG-2**: Each MemoryLayer namespace corresponds to exactly one domain. Method names match projection class names without abbreviations.

Инварианты:
- **I-CONTRACT-1**: All cross-domain types MUST be defined in `core/contracts/`
- **I-CONTRACT-2**: `contracts/` MUST NOT depend on reducers, projections, or handlers
- **I-CONTRACT-3**: Domains MUST NOT import each other directly

### Seams (с инвариантами)

1. **EventLog as API**
   - **I-SEAM-1**: Cross-domain communication ONLY via Events. No direct calls allowed.

2. **CommandBus as Facade**
   - ONE CommandBus + CommandRegistry-based domain-ownership guard (I-CMD-SINGLETON-1).
   - Cross-domain = events, NOT commands. Смешение запрещено (I-CMD-BUS-2).
   - **I-SEAM-2**: CommandBus validates domain ownership via CommandRegistry; single runtime instance.

3. **Memory Layer as Contract**
   - Все домены читают чужие проекции ТОЛЬКО через `MemoryLayer` (L1, Core).
   - **I-SEAM-3**: No direct DB access across domains. No generic/wildcard projection access.
   - MemoryLayer скрывает от читателя, в каком домене физически живёт проекция.
   - API domain-namespaced: `memory.<domain>.read.<name>()` = принятое архитектурное решение (I-ML-NS-1).

4. **Projection Consistency**
   - **I-SEAM-4**: Projection updates MUST be synchronous within `append()`.

#### Anti-Patterns (читать перед PR-ревью)

```python
# ❌ FORBIDDEN: Cross-domain direct import (I-DEP-1 violation)
from sdd.blueprint.projections.task_scope import TaskScopeProjection
scope = TaskScopeProjection.get(task_id)  # Engine лезет в Blueprint напрямую!

# ✅ CORRECT: Read via Memory Layer (I-SEAM-3)
scope = memory.read.task_scope(task_id)  # Engine читает через Core facade

# ❌ FORBIDDEN: Engine инициирует фазу (I-EVENT-OWN-1 violation)
event_store.append(PhaseStarted(phase_id=2))  # Engine не владеет фазовыми событиями!

# ✅ CORRECT: Engine сигнализирует о завершении задачи, Blueprint реагирует
event_store.append(TaskCompleted(task_id="T-001"))  # Engine эмитит то, чем владеет

# ❌ FORBIDDEN: Async cross-domain subscription (I-SUB-1 violation)
event_bus.subscribe("SpecApproved", engine.on_spec_approved)  # нарушает replay!

# ✅ CORRECT: Poll at start of AgentLoop cycle
spec = memory.read.approved_spec(phase_id)  # читаем проекцию в начале цикла

# ❌ FORBIDDEN: Cross-domain CommandBus dispatch (I-CMD-BUS-1 violation)
command_bus.dispatch(TaskStartedCommand(...), caller_domain="blueprint")  # Engine команда из Blueprint!

# ✅ CORRECT: Engine dispatch из Engine context
command_bus.dispatch(TaskStartedCommand(...), caller_domain="engine")  # ✅

# ❌ FORBIDDEN: Generic MemoryLayer access без явного метода (I-ML-REG-1 violation)
memory.read.get("constitution_projection")  # wildcard — запрещено

# ❌ FORBIDDEN: Flat namespace (I-ML-NS-1 violation)
memory.read.constitution()  # нет domain-namespace — hidden ownership

# ✅ CORRECT: Domain-namespaced явный метод
constitution = memory.blueprint.read.constitution()  # namespace = blueprint, явное ownership

# ❌ FORBIDDEN: Прямой append Observability Event без whitelist (I-OBS-2 violation)
event_store.append(MyCustomRuntimeEvent(...))  # не в whitelist!

# ✅ CORRECT: Только события из закрытого списка
event_store.append(LoopStepRecorded(...))  # в whitelist; EventStoreGuard пропустит
```

### Event Subscription: projection-based polling

Выбор механизма зафиксирован явно:

```text
Option A (CHOSEN): polling via projection
Option B (rejected): async subscription bus
Option C (rejected): DomainRouter поверх EventLog
```

**Почему DomainRouter отклонён:** он решает задачу push-delivery, которой в системе нет.
Polling-модель делает Router бессмысленным; его добавление создало бы God Object знающий обо всех доменах.

**Polling mechanism:**
```text
NOT: periodic timer
YES: начало каждого цикла AgentLoop
```
Engine читает проекции в начале каждого цикла — не по таймеру. Это decoupled и детерминировано.

- **I-SUB-1**: Domains MUST NOT rely on async event delivery. All reactions MUST be reproducible via replay.

### Dependency Rules

```text
ALLOWED:
  Core ← Blueprint
  Core ← Engine
  Core ← Intelligence
  Any domain → Core (через MemoryLayer для cross-domain read)

FORBIDDEN:
  Blueprint → Engine (direct)
  Engine → Blueprint (direct)
  Engine → Intelligence (direct)
  Any domain → другой domain (прямой import)
```

- **I-DEP-1**: No imports across domain boundaries except Core
- **I-DEP-2**: All cross-domain interaction via EventLog (write) + MemoryLayer (read)
- **I-DEP-TEST-1**: Dependency rules DO NOT apply to `tests/` — тесты вне domain model. Но тесты MUST use only public interfaces: CommandBus, EventLog, Projections.

### Domain × Layer Matrix (исправленная)

```text
                Core         Blueprint      Engine      Intelligence
L0 Core          ✓
L1 Runtime       ✓ (ML*)       ✓**            ✓
L2 Analysis/Dec               ✓***           ✓****          ✓
```

`*`  MemoryLayer → L1, Core (новый компонент)
`**` PolicyKernel → L1, Blueprint (execution control, применяет policy; НЕ L2 — не генерирует её)
`***` SpecManager, PlanManager, PhaseOrchestrator, ConstitutionParser → L2, Blueprint
`****` AgentLoop — L1 (execution); AuditEngine, ScenarioGen, MetaOptimization — L2 (decision/analysis)

**I-LAYER-1**: L1 = runtime execution ONLY. L2 = decision / planning / analysis.

**Явные обоснования спорных классификаций (решение кандидата 3/5):**

PolicyKernel → **L1, Blueprint** (не L2):
> PolicyKernel *применяет* governance rules в runtime — это execution, не decision.
> MetaOptimization (L2, Intelligence) *генерирует* proposal на изменение policy.
> PolicyKernel и MetaOptimization — два разных компонента с разными интерфейсами.
> Текущая вики-страница `pattern/policy-kernel.md` некорректно помечает его L2 — требует исправления.

AuditEngine → **L2, Intelligence** (не L1):
> AuditEngine вычисляет AgentScore из метрик M1–M9 — это analysis, не execution.
> Тот факт, что его вызывает L1 SessionOrchestrator, не делает его L1-компонентом.
> Being called from L1 ≠ being L1. Вызываемый — по роли, не по местонахождению вызова.
> Текущая вики-страница `pattern/audit-engine.md` некорректно помечает его L1 — требует исправления.

Blueprint компоненты:
- SpecManager → L2, PlanManager → L2, PhaseOrchestrator → L2, ConstitutionParser → **L2**
- PolicyKernel → **L1** (применяет policy в runtime; MetaOptimization L2 Intelligence — генерирует её)

Wiki-страницы требующие исправления Layer:
- `pattern/policy-kernel.md`: L2 → **L1** (Blueprint)
- `pattern/audit-engine.md`: L1 → **L2** (Intelligence)

### Directory Structure

```text
src/sdd/
├── core/
│   ├── contracts/    ← shared types only (Events, Commands, DTOs, TaskScopeDataclass)
│   └── runtime/      ← EventLog, WriteKernel, Reducer, ProjectionRegistry,
│                        Guards, MemoryLayer[p,L1,new]
├── blueprint/        ← SpecManager[p,L2], PlanManager[p,L2], PhaseOrchestrator[p,L2],
│                        ConstitutionParser[p,L2], PolicyKernel[L1]
├── engine/           ← AgentLoop[L1], AgentHandle[L1], SandboxManager[L1],
│                        ContextKernel[L1], InputPort[L1]
└── intelligence/     ← AuditEngine[L2], MetaOptimization[L2],
                         ScenarioGen[L2], ReplayEngine[L1]
```

**I-FS-1**: Directory structure MUST match domain boundaries.

### Enforcement (без этого BC — просто текст)

**Static [реализовано частично]:** lint rule — запрет `import` между доменами (`src/sdd/*` only).
Работает только при наличии физических domain-директорий.

**Runtime [proposed]:** `EventStoreGuard` двухуровневый; `CommandBus` domain-partitioned (I-CMD-BUS-1).

EventStoreGuard enforcement levels (решение кандидата 6):
```text
Level 1 [реализовано]:  call-stack check — вызов идёт из CommandHandler или L1 Runtime
Level 2 [proposed]:     domain-origin check — Domain Events принадлежат домену вызывающей команды

Механика Level 2:
  1. Из executing CommandContext получаем command_type
  2. CommandRegistry.lookup(command_type) → domain
  3. Appended event.domain MUST == lookup result
  4. Нарушение → DomainOriginViolation → ErrorEvent → ABORT

Observability Events (LoopStepRecorded, HumanGateReached, ErrorEvent):
  - Level 1: вызов из L1 Runtime module (call-stack) + event_type в whitelist
  - Level 2: не применяется (Observability Events не domain-scoped)
  - EventStoreGuard.validate_observability(event) проверяет только whitelist + call-stack origin
```

- **I-GUARD-DOMAIN-1**: EventStoreGuard Level 2 MUST use CommandRegistry (not inline domain map) as single source of command→domain mapping
- **I-GUARD-OBS-1**: Observability Events bypass domain-origin check but MUST pass origin whitelist check

**Audit [реализовано]:** `AuditEngine` проверяет отсутствие прямых вызовов.

**I-COMP-1**: Each component MUST belong to exactly one domain.

**Enforcement Responsibility Matrix:**

Каждый инвариант покрыт ровно одним первичным слоем. Дублирование без явной документации = tech debt.

```text
Compile-time (CI linter — tach/import-linter):
  - Import boundaries между доменами (I-DEP-1)
  - L2 access из Guards запрещён (ML-6)
  - Guard pipeline slot order (I-GUARD-PIPELINE-1)
  - CommandBus singleton: нет second instantiation (I-CMD-SINGLETON-1)

Runtime (Guards + EventStoreGuard + CommandBus):
  - EventStore direct access (GL-7, EventStoreGuard Level 1)
  - Domain-origin check (I-GUARD-DOMAIN-1, EventStoreGuard Level 2)
  - CommandBus domain-ownership guard (I-CMD-BUS-1)
  - Structural axioms: NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT

Post-factum (AuditEngine):
  - M1-M9 score (протокольное соблюдение)
  - Adversarial regression M9
  - Protocol violations (M8)
```

- **I-ENF-MATRIX-1**: Each invariant MUST be assigned exactly ONE primary enforcement layer. Secondary layers (defence-in-depth) are allowed but MUST be documented here. Unassigned = tech debt.

### Workflow (как добавлять компоненты)

Перед добавлением нового компонента:
1. Определить domain (Core / Blueprint / Engine / Intelligence)
2. Определить layer (L1 = runtime execution, L2 = decision/analysis)
3. Определить events (output) — разместить в `core/contracts/`
4. Определить projections (output) — разместить в `<domain>/projections/`
5. Зарегистрировать read-access в MemoryLayer если другие домены читают эти проекции
6. Проверить dependency rules

### Event Grain

Граница между "событие" и "промежуточный шаг" должна быть явной, иначе EventLog взрывается.

- **I-EVENT-GRAIN-1**: Domain Events MUST represent state transitions only. Intermediate computation steps MUST NOT produce Domain Events. Тест: «Если replay этого события не меняет domain state → это не Domain Event».
- **I-EVENT-GRAIN-2**: Observability Events (LoopStepRecorded) represent AgentLoop FSM transitions, not computation steps. One per FSM transition, not one per LLM call or tool invocation.

Практическое правило при code review: если Event не имеет соответствующей записи в Reducer — возможно, это промежуточный шаг, оформленный как событие.

### Trade-offs

1. **Over-segmentation**: слишком раннее деление → усложнение
2. **Event explosion**: cross-domain только через events → рост EventLog; контролируется I-EVENT-GRAIN-1/2
3. **Latency**: projection polling медленнее прямых вызовов (но bounded by cycle)
4. **Blueprint immaturity**: SpecManager/PlanManager/PhaseOrchestrator/ConstitutionParser пока `[proposed]`
5. **MemoryLayer as bottleneck**: единая точка cross-domain read → рост API управляем через domain-namespace (I-ML-NS-1)

### Open Questions

- (P2) Нужно ли versioning доменов?
- (P2) Как именно происходит инициализация domain-partitioned CommandBus экземпляров? DI container? Factory? Startup sequence?
- (P2) Кто владеет списком Observability Events whitelist — константа в EventStoreGuard или отдельный реестр?
- (P3) Как тестировать Level 2 domain-origin check без реального CommandContext?

> **Закрытые вопросы (из grill-me session):**
> - ~~Как реализуется projection-based polling?~~ → начало каждого цикла AgentLoop
> - ~~Нужен ли DomainRouter?~~ → rejected; polling eliminates the need
> - ~~Где живёт orchestration logic?~~ → Blueprint (PhaseOrchestrator)
> - ~~Может ли Engine инициировать фазы?~~ → нет; только Blueprint эмитит фазовые события
>
> **Закрытые вопросы (из improve-codebase-architecture session, 2026-05-06):**
> - ~~Конфликт GL-7 / AgentLoop / I-BC-1?~~ → Observability Events category; GL-7 применяется к Domain Events; I-BC-1 уточнён («напрямую» = в обход EventStoreGuard)
> - ~~CommandBus — нет domain enforcement в интерфейсе?~~ → domain-partitioned экземпляры; I-CMD-BUS-1/2
> - ~~MemoryLayer — нет cross-domain seam контракта?~~ → I-ML-REG-1/2; explicit named methods mandatory; 3-step registration protocol
> - ~~EventStoreGuard — одноуровневый enforcement?~~ → Level 1 [реализован] + Level 2 domain-origin [proposed]; I-GUARD-DOMAIN-1
> - ~~AuditEngine L1 vs L2 конфликт?~~ → L2, Intelligence (analysis ≠ execution); wiki-страница требует исправления
> - ~~PolicyKernel L2 vs L1 конфликт?~~ → L1, Blueprint (applies policy ≠ generates policy); wiki-страница требует исправления
>
> **Закрытые вопросы (из risk-analysis session, 2026-05-06):**
> - ~~CommandBus: multiple instances vs ONE instance?~~ → ONE CommandBus + CommandRegistry guard (I-CMD-SINGLETON-1, I-CMD-BUS-1); multiple instances дублируют enforcement на 3 слоях
> - ~~MemoryLayer: flat namespace vs domain-namespace?~~ → domain-namespaced API `memory.<domain>.read.<name>()` (I-ML-NS-1); flat namespace скрывает ownership
> - ~~Observability Events ordering guarantee?~~ → I-OBS-5: Domain Event THEN Observability Event в рамках одного step; порядок enforce в WriteKernel.execute_and_project()
> - ~~Consistency model: нестандартный термин «cycle-bounded»?~~ → формализован: Strong (tx) → Snapshot (cycle) → Eventual (L2); staleness bound ≤ 1 iteration задокументирован
> - ~~PhaseOrchestrator как скрытый Engine?~~ → I-ORCH-1: pure decision logic; coordinator pattern; нет inline domain conditions
> - ~~Event explosion — trade-off или scaling risk?~~ → I-EVENT-GRAIN-1/2: Events = state transitions only; Observability Events = FSM transitions only
> - ~~Enforcement: 4 механизма без явного разграничения?~~ → I-ENF-MATRIX-1: Enforcement Responsibility Matrix (compile/runtime/post-factum); каждый инвариант = один primary layer

### See Also

`[[sdd-component-inventory]]`, `[[sdd-meta-harness]]`, `[[command-bus]]`, `[[event-sourcing]]`, `[[memory-layer]]`, `[[global-laws]]`, `[[execution-guard]]`, `[[eventstore-guard]]`, `[[write-kernel]]`, `[[projection-registry]]`, `[[policy-kernel]]`

---

## Обновление `idea/sdd-component-inventory.md` (.diff)

- Добавить колонку **Domain**: `Component | Layer | Domain | Status`
- Добавить 5 новых блоков `[proposed]`:
  - SpecManager (L2, Blueprint)
  - PlanManager (L2, Blueprint)
  - PhaseOrchestrator (L2, Blueprint)
  - ConstitutionParser (L2, Blueprint) ← был Engine L1 в первоначальном плане
  - MemoryLayer (L1, Core) ← новый, не был в первоначальном плане
- Исправить PolicyKernel: Layer L2 → **L1** (execution control, не decision)
- Обновить счётчик: 30 → **35**
- Добавить инвариант **I-COMP-1**
- Добавить `[[sdd-bounded-contexts]]` в See Also

---

## Финальная модель (резюме)

```text
1. Consistency model:     Strong (WriteKernel tx) → Snapshot (cycle-bounded, ≤1 iteration) → Eventual (L2 only)
2. Cross-domain comms:    Events (write) + MemoryLayer (read, domain-namespaced)
3. Contracts:             core/contracts/ (types) + <domain>/projections/ (logic) + memory.<domain>.read (access)
4. Enforcement scope:     src/sdd/* only (tests/ excluded); matrix: compile/runtime/post-factum (I-ENF-MATRIX-1)
5. Determinism:           no async dependencies; polling at AgentLoop start; no DomainRouter
6. Orchestration:         Blueprint only (PhaseOrchestrator, pure decision I-ORCH-1); Engine cannot initiate phases
7. Intelligence feedback: ProposalGenerated → EventLog → human gate → Blueprint applies/rejects
8. Event categories:      Domain Events (via WriteKernel, reducer) + Observability Events (same EventLog,
                          ordered after Domain Events, whitelist: LoopStepRecorded/HumanGateReached/ErrorEvent,
                          no projection mutation; I-OBS-5 ordering guarantee)
9. Event grain:           Domain Events = state transitions only (I-EVENT-GRAIN-1);
                          Observability Events = FSM transitions only (I-EVENT-GRAIN-2)
10. CommandBus:           ONE instance (I-CMD-SINGLETON-1); domain-ownership via CommandRegistry guard (I-CMD-BUS-1);
                          cross-domain dispatch → CommandBusBoundaryError; DI injection for L1 middleware (I-CORE-BUS-1)
11. MemoryLayer API:      domain-namespaced: memory.<domain>.read.<name>() (I-ML-NS-1);
                          explicit named methods only (I-ML-REG-1); each new method = architectural decision
12. EventStoreGuard:      Level 1 call-stack [реализован] + Level 2 domain-origin via CommandRegistry [proposed]
```

**Wiki-страницы требующие исправления (action items):**
- `pattern/policy-kernel.md`: исправить «L2» → «L1, Blueprint»; разделить PolicyKernel (apply) и MetaOptimization (generate)
- `pattern/audit-engine.md`: исправить «L1» → «L2, Intelligence»; обосновать: analysis ≠ execution
- `pattern/memory-layer.md`: добавить domain-namespace (I-ML-NS-1); 3-step registration protocol; текущий фокус L1/L2 изоляции неполный
- `pattern/command-bus.md`: исправить multiple instances → ONE instance + CommandRegistry guard (I-CMD-SINGLETON-1, I-CMD-BUS-1); I-CORE-BUS-1 DI pattern
- `pattern/eventstore-guard.md`: добавить I-OBS-5 ordering; Level 1 vs Level 2 enforcement; I-GUARD-DOMAIN-1
- `idea/global-laws.md`: уточнить GL-7 — применяется к Domain Events; добавить ссылку на Observability Events исключение; формальная Consistency Model
