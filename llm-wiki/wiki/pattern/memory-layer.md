---
created: '2026-05-05'
domain: sdd
id: pattern/memory-layer
layer: architecture
page_type: pattern
sdd_domain: Core
sdd_layer: L1
sources:
- raw/Memory Layer and Invariant Management.md
- raw/SDD_Bounded_Contexts_Plan.md
tags:
- ssot
- read-only
- pipeline
- llm
- domain/sdd
- sdd/l1
- sdd/core
updated: '2026-05-06'
version: 2
---
# Memory Layer

Единый детерминированный read-only фасад над всеми [[projection-registry]] проекциями. Не хранит данные — только предоставляет Query API.

```text
всё чтение    → через Memory Layer
все изменения → через CommandBus
```

## How It Works

```text
EventLog (SSOT)
      ↓ Reducer
Projections:
  L1 (deterministic, strict consistency):
    GraphProjection, TraceProjection, StateProjection
    PolicyProjection  ← единственный источник behavioral rules

  L2 (eventual consistency, isolated failure):
    RAGProjection, EmbeddingProjection
    ↑ обновляются через outbox/async worker (вне L1 транзакции)

┌──────────────── Memory Layer ─────────────────┐
│  L1 API                    L2 API             │
│  ReadModel                 QueryEngineSemantic │
│  QueryEngineDeterministic                     │
└───────────────────────────────────────────────┘
         ↓                           ↓
  Guards, ContextKernel        MetaOptimization,
  AuditEngine (L1 only)        ScenarioGen, RAG
```

**L1 API (deterministic, strict consistency):**

```python
read.task(task_id)       -> TaskState
read.phase(phase_id)     -> PhaseState
read.policy(scope=None)  -> list[PolicyRule]   # source of behavioral rules
read.trace(task_id)      -> TraceSummary
query.execute(Query)     -> ContextSnapshot
query.explain(task_id)   -> ContextSnapshot
```

**L2 API (eventual, SemanticSearch):**

```python
query.semantic(q)        -> list[Result]
read.similar(node_id)    -> list[Node]
read.search(query)       -> list[Result]
```

**Физическое разделение ([[l1-l2-isolation]]):** Guards и ContextKernel получают только L1 API. L2 API физически недоступен в L1 namespace — три уровня enforcement: API surface, type-level (`L1MemoryLayer` sealed), runtime `assert isinstance(memory, L1MemoryLayer)`.

**Типы памяти:**

| Тип | Примеры | Характеристики |
|-----------|--------------------------|--------------------------------|
| Persistent | EventLog | append-only, SSOT, неизменяем |
| Derived | Projections (все) | вычислено из EventLog |
| Ephemeral | ContextSnapshot | не персистируется, in-process |
| Execution | CommandContext | живёт в рамках сессии |

**Consistency:**
- L1: strict read-after-write (одна PostgreSQL транзакция с EventLog)
- L2: eventual (outbox → async worker, FIFO по event_offset, single-writer)
- L1 никогда не зависит от L2 readiness; partial_result в L2 не ошибка

**Bootstrap guard:** если `read.policy()` возвращает пустой список вне тест-контекста → `BootstrapRequired`.

## Cross-Domain Access (Domain-Namespaced API)

Все домены читают чужие проекции ТОЛЬКО через MemoryLayer. API организован по domain-namespace — явное ownership без hidden coupling:

```text
memory.blueprint.read.spec(phase_id)          ← Blueprint domain
memory.blueprint.read.task_scope(task_id)     ← Blueprint domain
memory.blueprint.read.constitution()          ← Blueprint domain
memory.blueprint.read.policy(scope)           ← Blueprint domain

memory.engine.read.trace(task_id)             ← Engine domain

memory.intelligence.read.metrics(task_id)     ← Intelligence domain
memory.intelligence.read.audit_score(task_id) ← Intelligence domain
```

**3-step registration protocol** (все шаги обязательны):

1. `<domain>/projections/<name>.py` — логика проекции (владелец — домен)
2. `core/contracts/<name>_dto.py` — DTO типа (доступен всем доменам)
3. `MemoryLayer.<domain>.read.<name>(...)` — явный именованный метод (шаг НЕ опциональный)

Без шага 3 проекция недоступна другим доменам. Growth is intentional — каждый новый метод = явное архитектурное решение.

```text
src/sdd/core/
  contracts/   ← ONLY shared types (Events, Commands, DTOs)
  runtime/     ← EventLog, WriteKernel, ProjectionRegistry, Guards, MemoryLayer
```

## When To Use

Везде, где компонент системы читает состояние. L1-компоненты (Guards, ContextKernel, PolicyKernel) используют исключительно L1 API. L2-компоненты (MetaOptimization, ScenarioGen, RAG, Blueprint proposed components) получают L2 или domain-namespaced API.

## Trade-offs

- L1 query = SELECT к PostgreSQL; slight latency vs in-memory, но гарантированная consistency.
- L2 failure изолирован: не влияет на L1, Guards, EventLog (ML-9).
- SemanticSearch деградирует до `partial_result` при недоступности [[embedding-projection]] — не ошибка.
- MemoryLayer API растёт явно при каждом новом cross-domain projection — intentional design, не bottleneck.

## Invariants

| ID | Формулировка |
|----|--------------|
| ML-1 | Memory Layer не пишет (read-only) |
| ML-2 | deterministic: same projections → same output |
| ML-3 | no side effects |
| ML-4 | source only = projections (не EventLog напрямую) |
| ML-5 | все данные системы доступны через Memory Layer |
| ML-6 | L1/L2 API жёстко изолированы (API surface + type-level + runtime + CI linter) |
| ML-7 | [[embedding-projection]] версионирована; replay FAIL блокирует только L2 |
| ML-8 | L1 = strict consistency; L2 = eventual (FIFO, single-writer, idempotent по event_id) |
| ML-9 | failure в L2 не влияет на L1, Guards, EventLog |
| ML-10 | ContextSnapshot в L1 строится только из deterministic sources |
| I-ML-REG-1 | Every cross-domain projection MUST have an explicit named method in MemoryLayer; wildcard/generic access is forbidden |
| I-ML-NS-1 | MemoryLayer MUST be domain-namespaced: `memory.<domain>.read.<name>()`. Flat `memory.read.*` namespace is forbidden |
| I-ML-REG-2 | Each MemoryLayer namespace corresponds to exactly one domain. Method names match projection class names without abbreviations |

## See Also

- [[l1-l2-isolation]] — модель изоляции L1/L2 API
- [[sdd-bounded-contexts]] — cross-domain seam contracts; I-SEAM-3
- [[policy-projection]] — источник behavioral rules
- [[embedding-projection]] — L2 проекция с версионированием
- [[projection-registry]] — инфраструктура проекций
- [[context-kernel]] — основной L1-потребитель
- [[execution-guard]] — L1-потребитель (guards)
