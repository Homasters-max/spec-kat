---
id: idea/sdd-bounded-contexts
page_type: idea
domain: sdd
layer: architecture
tags:
- bounded-contexts
- enforcement
- ssot
- write-path
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SDD_Bounded_Contexts_Plan.md
---
# SDD Bounded Contexts

Два ортогональных разреза SDD-системы: горизонтальный (по детерминизму) и вертикальный (по domain ownership). Каждый компонент = (Layer, Domain).

```text
Horizontal (execution semantics): L0 Core → L1 Execution → L2 Intelligence
Vertical (domain ownership):      Core / Blueprint / Engine / Intelligence
```

Ключевой тезис: Bounded Contexts — это не про папки, а про правила взаимодействия: инварианты + контракты + enforcement.

## Lifecycle Boundaries

```text
Domain Foundation:
  - persisted via EventLog
  - replayable, deterministic

Execution Runtime:
  - ephemeral, NOT replayable
  - produces Commands only
```

- **I-BC-1**: Runtime MUST NOT mutate EventStore directly (см. исключение Observability Events ниже)
- **I-BC-2**: Foundation MUST NOT depend on Runtime state

## Consistency Model

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

Как работает на практике:

```text
1. Command → WriteKernel
2. Handler emits events
3. Events append to EventLog
4. Projections updated SYNCHRONOUSLY within append()
5. AgentLoop начинает новый цикл → poll всех нужных проекций

⟹ Projection read в начале цикла = консистентный snapshot всех предыдущих команд
⟹ NO synchronous cross-domain calls EVER
```

Правило:

```text
If Engine needs immediate decision → read Projection via MemoryLayer
If Engine needs to change state   → emit Event
```

- **I-CONSISTENCY-1**: Cross-domain consistency = cycle-bounded; only within-WriteKernel-transaction = strongly consistent
- **I-SEAM-4**: Projection updates MUST be synchronous within `append()`
- **I-TX-1**: WriteKernel transaction = ONLY atomic boundary in system

## Observability Events

Разрешение конфликта GL-7 / AgentLoop / I-BC-1: в системе два типа событий с разными enforcement rules.

```text
Domain Events       — производятся CommandHandler'ами
                    — идут через WriteKernel (OCC, projection sync, full pipeline)
                    — мутируют domain state и проекции

Observability Events — производятся L1 Runtime напрямую
                    — обходят WriteKernel и CommandBus
                    — НЕ мутируют domain projections (Reducer их игнорирует)
                    — проходят через EventStoreGuard (origin check: вызов только из L1 Runtime)
```

Закрытый список Observability Events (без ad-hoc дополнений):
- `LoopStepRecorded` — фиксация шага AgentLoop
- `HumanGateReached` — AgentLoop достиг human gate
- `ErrorEvent` — L1 Runtime сигнализирует об ошибке

Уточнение GL-7: "event_store.append() только из Command handlers" — применяется к Domain Events. Observability Events — легальное исключение, медиируемое [[eventstore-guard]].

Уточнение I-BC-1: "напрямую" = в обход EventStoreGuard. Observability Events идут через EventStoreGuard → I-BC-1 не нарушается.

- **I-OBS-1**: Observability Events MUST NOT appear in Reducer's event-to-state map; projections MUST ignore them
- **I-OBS-2**: The list of Observability Events is closed (exhaustive); adding new ones requires explicit protocol decision
- **I-OBS-3**: EventStoreGuard MUST validate Observability Event origin (call-stack: L1 Runtime) AND event type (whitelist)
- **I-OBS-4**: Observability Events do NOT trigger ProjectionRegistry.sync()
- **I-OBS-5**: Domain Event THEN Observability Event (ordering within same step); enforced by append order in WriteKernel.execute_and_project()

## Domains Table

| Domain | Role | Owns | Produces Events |
|--------|------|------|-----------------|
| Core | Physics of system | EventLog, Reducer, WriteKernel, ProjectionRegistry, [[memory-layer]] | — |
| Blueprint | Project model (human-facing) | SpecProjection, PlanProjection, PhaseStateProjection, PolicyProjection, ConstitutionProjection, TaskScopeProjection, ProposalProjection | SpecDrafted, SpecApproved, PlanCreated, PhaseStarted, PhaseCompleted, PhaseAbandoned, ProposalApplied, ProposalRejected |
| Engine | Execution runtime | AgentLoop, ContextKernel, Sandbox | TaskStarted, StepExecuted, WriteApplied, ErrorOccurred, TaskCompleted |
| Intelligence | Analysis | Metrics, Replay, Audit | MetricComputed, ProposalGenerated |

Ключевые ограничения:
- Только Blueprint эмитит фазовые события. Engine НЕ может инициировать фазы.
- Intelligence НИКОГДА не меняет state напрямую. Только через human gate → Blueprint-команды.
- Orchestration logic — в Blueprint ([[phase-orchestrator]]). Engine только исполняет.

- **I-CMD-OWN-1**: Each Command MUST belong to exactly one domain
- **I-EVENT-OWN-1**: Each Event has exactly one owning domain

## Domain Contracts

Каждый домен открывает только: Commands (input), Events (output), Projections (read-only через [[memory-layer]]).

Контракты взаимодействия:

```text
Blueprint → Engine:       Event: SpecApproved → Engine реагирует (via projection poll)
Engine → Blueprint:       Event: TaskCompleted → PhaseOrchestrator обновляет PhaseState
Intelligence → Blueprint: Event: ProposalGenerated → human gate → ApplyProposal / RejectProposal
```

## CommandBus Enforcement

ONE CommandBus (singleton) + CommandRegistry (command → domain) + domain-ownership guard.

```text
dispatch(cmd, caller_domain):
  cmd_domain = CommandRegistry.lookup(cmd.type).domain
  if caller_domain != cmd_domain:
      raise CommandBusBoundaryError(cmd.type, caller_domain, cmd_domain)
```

Cross-domain dispatch → `CommandBusBoundaryError` (явный сбой, не молчаливый игнор).

- **I-CMD-SINGLETON-1**: Exactly ONE CommandBus instance MUST exist per runtime
- **I-CMD-BUS-1**: CommandBus MUST validate domain ownership via CommandRegistry
- **I-CMD-BUS-2**: Cross-domain triggering MUST go via Event emission + projection poll, never via cross-domain bus dispatch
- **I-CORE-BUS-1**: CommandBus MUST NOT import L1/L2 modules directly. L1 middleware injected via factory `create_command_bus()` (DI pattern)

## MemoryLayer as Seam

Все домены читают чужие проекции ТОЛЬКО через [[memory-layer]] (L1, Core). API domain-namespaced:

```text
memory.blueprint.read.spec(phase_id)
memory.blueprint.read.task_scope(task_id)
memory.blueprint.read.constitution()
memory.blueprint.read.policy(scope)
memory.engine.read.trace(task_id)
memory.intelligence.read.metrics(task_id)
memory.intelligence.read.audit_score(task_id)
```

Добавление cross-domain проекции = 3 обязательных шага:
1. `<domain>/projections/<name>.py` — логика проекции (владелец — домен)
2. `core/contracts/<name>_dto.py` — DTO типа (доступен всем)
3. `MemoryLayer.<domain>.read.<name>(...)` — явный именованный метод (обязательно, шаг не опциональный)

- **I-ML-REG-1**: Every cross-domain projection MUST have an explicit named method in MemoryLayer; wildcard/generic access is forbidden
- **I-ML-NS-1**: MemoryLayer MUST be domain-namespaced: `memory.<domain>.read.<name>()`. Flat `memory.read.*` namespace is forbidden
- **I-ML-REG-2**: Each MemoryLayer namespace corresponds to exactly one domain

## Shared Kernel

```text
src/sdd/core/
  contracts/   ← ONLY shared types (Events, Commands, DTOs)
  runtime/     ← EventLog, WriteKernel, ProjectionRegistry, Guards, MemoryLayer
```

- **I-CONTRACT-1**: All cross-domain types MUST be defined in `core/contracts/`
- **I-CONTRACT-2**: `contracts/` MUST NOT depend on reducers, projections, or handlers
- **I-CONTRACT-3**: Domains MUST NOT import each other directly

## Seams

1. **EventLog as API** — **I-SEAM-1**: Cross-domain communication ONLY via Events. No direct calls allowed.
2. **CommandBus as Facade** — **I-SEAM-2**: ONE instance, validates domain ownership via CommandRegistry.
3. **Memory Layer as Contract** — **I-SEAM-3**: No direct DB access across domains. No wildcard projection access.
4. **Projection Consistency** — **I-SEAM-4**: Projection updates MUST be synchronous within `append()`.

## Anti-Patterns

```python
# ❌ FORBIDDEN: Cross-domain direct import (I-DEP-1 violation)
from sdd.blueprint.projections.task_scope import TaskScopeProjection
scope = TaskScopeProjection.get(task_id)

# ✅ CORRECT: Read via Memory Layer (I-SEAM-3)
scope = memory.blueprint.read.task_scope(task_id)

# ❌ FORBIDDEN: Engine инициирует фазу (I-EVENT-OWN-1 violation)
event_store.append(PhaseStarted(phase_id=2))

# ✅ CORRECT: Engine сигнализирует о завершении задачи
event_store.append(TaskCompleted(task_id="T-001"))

# ❌ FORBIDDEN: Async cross-domain subscription (I-SUB-1 violation)
event_bus.subscribe("SpecApproved", engine.on_spec_approved)

# ✅ CORRECT: Poll at start of AgentLoop cycle
spec = memory.blueprint.read.spec(phase_id)

# ❌ FORBIDDEN: Flat namespace (I-ML-NS-1 violation)
memory.read.constitution()

# ✅ CORRECT: Domain-namespaced
constitution = memory.blueprint.read.constitution()

# ❌ FORBIDDEN: Observability Event без whitelist (I-OBS-2 violation)
event_store.append(MyCustomRuntimeEvent(...))

# ✅ CORRECT: Только события из закрытого списка
event_store.append(LoopStepRecorded(...))
```

## Dependency Rules

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
- **I-DEP-TEST-1**: Dependency rules DO NOT apply to `tests/` — но тесты MUST use only public interfaces
- **I-SUB-1**: Domains MUST NOT rely on async event delivery. All reactions MUST be reproducible via replay.

## Domain × Layer Matrix

```text
                Core         Blueprint      Engine      Intelligence
L0 Core          ✓
L1 Runtime       ✓ (ML*)       ✓**            ✓
L2 Analysis/Dec               ✓***           ✓****          ✓
```

`*` MemoryLayer → L1, Core
`**` PolicyKernel → L1, Blueprint (применяет policy; НЕ L2 — не генерирует её)
`***` [[spec-manager]], [[plan-manager]], [[phase-orchestrator]], [[constitution-parser]] → L2, Blueprint
`****` AgentLoop — L1; [[audit-engine]], ScenarioGen, MetaOptimization — L2, Intelligence

- **I-LAYER-1**: L1 = runtime execution ONLY. L2 = decision / planning / analysis.
- **I-COMP-1**: Each component MUST belong to exactly one domain.
- **I-FS-1**: Directory structure MUST match domain boundaries.

## Enforcement Matrix

Каждый инвариант покрыт ровно одним первичным слоем:

```text
Compile-time (CI linter — tach/import-linter):
  - Import boundaries между доменами (I-DEP-1)
  - L2 access из Guards запрещён (ML-6)
  - CommandBus singleton (I-CMD-SINGLETON-1)

Runtime (Guards + EventStoreGuard + CommandBus):
  - EventStore direct access (GL-7, EventStoreGuard Level 1)
  - Domain-origin check (I-GUARD-DOMAIN-1, EventStoreGuard Level 2)
  - CommandBus domain-ownership guard (I-CMD-BUS-1)

Post-factum (AuditEngine):
  - M1-M9 score (protocol compliance)
  - Adversarial regression M9
```

- **I-ENF-MATRIX-1**: Each invariant MUST be assigned exactly ONE primary enforcement layer. Unassigned = tech debt.

## Intelligence Feedback Loop

```text
MetaOptimization → ProposalGenerated → EventLog
Blueprint читает ProposalProjection через MemoryLayer
PhaseOrchestrator видит pending proposal → HUMAN_GATE
  ├─ human: ApplyProposal → Blueprint обрабатывает через SpecManager/PlanManager
  └─ human: RejectProposal → ProposalRejected → EventLog → цикл продолжается
```

## Workflow — добавление нового компонента

1. Определить domain (Core / Blueprint / Engine / Intelligence)
2. Определить layer (L1 = runtime execution, L2 = decision/analysis)
3. Определить events (output) — разместить в `core/contracts/`
4. Определить projections (output) — разместить в `<domain>/projections/`
5. Зарегистрировать read-access в MemoryLayer если другие домены читают эти проекции
6. Проверить dependency rules

## Trade-offs

- Over-segmentation: слишком раннее деление → усложнение
- Event explosion: cross-domain только через events → рост EventLog; контролируется I-EVENT-GRAIN-1/2
- Latency: projection polling медленнее прямых вызовов (но bounded by cycle)
- MemoryLayer as bottleneck: единая точка cross-domain read → рост API управляем через domain-namespace

## Open Questions

- [ ] (P2) Нужно ли versioning доменов?
- [ ] (P2) Как инициализируется CommandBus? DI container? Factory? Startup sequence?
- [ ] (P2) Кто владеет списком Observability Events whitelist — константа в EventStoreGuard или отдельный реестр?
- [ ] (P3) Как тестировать Level 2 domain-origin check без реального CommandContext?

## See Also

- [[sdd-component-inventory]]
- [[sdd-meta-harness]]
- [[command-bus]]
- [[event-sourcing]]
- [[memory-layer]]
- [[global-laws]]
- [[execution-guard]]
- [[eventstore-guard]]
- [[write-kernel]]
- [[projection-registry]]
- [[policy-kernel]]
- [[observability-events]]
- [[phase-orchestrator]]
- [[spec-manager]]
- [[plan-manager]]
- [[constitution-parser]]
