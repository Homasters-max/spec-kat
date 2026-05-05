# Memory Layer and Invariant Management

## 0. Главная идея

```text
Memory Layer = deterministic read facade над всеми projections

Memory Layer НЕ хранит данные.
Memory Layer НЕ является слоём хранилищ.
Memory Layer = единый Query API над projections.
```

Финальное правило системы:

```text
всё чтение  → через Memory Layer
все изменения → через CommandBus
```

---

## 1. Архитектура

```text
EventLog (SSOT)
      ↓ Reducer
Projections:
  L1 (deterministic, strict consistency):
    GraphProjection
    TraceProjection
    StateProjection
    PolicyProjection          ← единственный источник behavioral rules

  L2 (eventual consistency, isolated failure):
    RAGProjection
    EmbeddingProjection   ← versioned: model_id + version + config_hash
    ↑ обновляются через outbox/async worker (вне L1 транзакции)
      ↓
┌──────────────────── Memory Layer ──────────────────────┐
│  L1 API                       L2 API                   │
│  ReadModel                    QueryEngineSemantic       │
│  QueryEngineDeterministic                               │
│                                                         │
│  read.task(task_id)           query.semantic(q)         │
│  read.phase(phase_id)         read.similar(node_id)     │
│  read.policy(scope=None)      read.search(query)        │
│  read.trace(task_id)                                    │
│  query.execute(Query)                                   │
└──────────────────────────────────────────────────────────┘
         ↓                              ↓
  Guards, ContextKernel,          MetaOptimization,
  AuditEngine                     ScenarioGen, RAG
  (L1 API only)                   (L2 API via ReadModel.l2)
```

---

## 2. Типы памяти

Вместо "слоёв хранения" — четыре типа:

| Тип | Примеры | Характеристики |
|---|---|---|
| Persistent | EventLog | append-only, SSOT, неизменяем |
| Derived | Projections (все) | вычислено из EventLog, воспроизводимо |
| Ephemeral | ContextSnapshot | не персистируется, in-process |
| Execution | CommandContext | создаётся при start-task, живёт в рамках сессии |

---

## 3. API Memory Layer

### 3.1 ReadModel (L1, deterministic)

```python
read.task(task_id)           -> TaskState
read.phase(phase_id)         -> PhaseState
read.policy(scope=None)      -> list[PolicyRule]   # глобально; scope зарезервирован для v2
read.trace(task_id)          -> TraceSummary
```

### 3.2 QueryEngineDeterministic (L1, deterministic)

```python
query.execute(Query)         -> ContextSnapshot
query.explain(task_id)       -> ContextSnapshot
```

### 3.3 QueryEngineSemantic (L2 only, eventual)

```python
query.semantic(q)            -> list[Result]
read.similar(node_id)        -> list[Node]
read.search(query)           -> list[Result]
```

**Физическое разделение (ML-6):**

```python
# L1 module — Guards и AuditEngine видят только это
class ReadModel: ...
class QueryEngineDeterministic: ...

# L2 module — физически недоступен из L1
class QueryEngineSemantic: ...
```

**Enforcement — 3 уровня:**

```text
1. API surface:
   L1 компоненты получают ТОЛЬКО:
     ReadModel
     QueryEngineDeterministic
   L2 фасады (QueryEngineSemantic) не импортируются в L1 namespace

2. Type-level:
   L1MemoryLayer — final/sealed класс (нельзя подменить на L2-содержащий тип)
   L2 интерфейсы не входят в L1MemoryLayer

3. Runtime assert:
   guard проверяет тип memory при вызове:
     assert isinstance(memory, L1MemoryLayer)
   CI линтер (tach / import-linter): правило guards/* не импортирует memory/l2/*
```

---

## 4. ContextKernel через Memory Layer

```python
class ContextKernel:

    def build(task_id: str, memory: MemoryLayer) -> ContextPacket:
        return ContextPacket(
            graph  = memory.query.explain(task_id),         # L1
            state  = memory.read.task(task_id),             # L1
            scope  = memory.read.task(task_id).write_scope, # L1
            policy = memory.read.policy(),                  # L1, behavioral rules
            trace  = memory.read.trace(task_id).summary(),  # L1
            # semantic = optional L2 layer, не блокирует L1
        )
```

ContextSnapshot в L1 строится **только** из deterministic sources (ML-10). Semantic data — опциональный слой поверх.

**Bootstrap guard:** если `memory.read.policy()` возвращает пустой список в non-test окружении
(`PYTEST_CURRENT_TEST` отсутствует) → поднимается `BootstrapRequired`. В тест-контексте —
hardcoded defaults, bootstrap не требуется.

---

## 5. Guards через Memory Layer

Guards = pure functions над externalized state. Нет instance state, нет side effects.

```python
def check(cmd: Command, ctx: CommandContext,
          projection_reader: ProjectionReader,
          memory: L1MemoryLayer) -> Result:
    state  = GraphSessionState.current(ctx.task_id, projection_reader)  # L1
    policy = memory.read.policy()                                        # L1, behavioral rules
    # guard физически не имеет доступа к L2 API (ML-6)
    # axioms (NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT) — hardcoded
    # behavioral rules (retry_limit, scope permissions) — из policy
```

**Иерархия правил в Guards:**

```text
Axioms (code-enforced, ABORT):
  NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT, NO_GRAPH_BEFORE_EXPLAIN
  → hardcoded, не читаются из ProjectionRegistry

Structural (guard-enforced, RETRY/HUMAN_GATE):
  GL-6 Write Gate → ExecutionGuard + ScopeGuard
  → частично hardcoded, частично config

Behavioral (policy-managed):
  retry_limit, scope permissions
  → PolicyProjection через memory.read.policy()
```

---

## 6. Модель инвариантов — без InvariantProjection

`InvariantProjection` **удалена**. Отдельной проекции для инвариантов нет.

`InvariantDeclared` / `InvariantUpdated` events — **удалены**.
`invariant_catalog.yaml` — **удалён**.

**Финальная модель:**

```text
Axioms:
  hardcoded в Guards
  не персистируются, не читаются из EventLog
  не переопределяются через PolicyKernel

Behavioral rules:
  PolicyProjection (через PolicyUpdated events)
  управляются через PolicyKernel → [HUMAN_GATE] → PolicyUpdated
  bootstrap: norm_catalog.yaml → bootstrap-policy → PolicyUpdated events
```

`PolicyProjection` полностью покрывает функцию `InvariantProjection` для behavioral rules.
Axioms покрываются hardcoded guard логикой.

---

## 7. EmbeddingProjection — версионирование

```yaml
EmbeddingEntry:
  node_id: string
  embedding: vector
  model_id: "e5-small"
  version: "v1"
  config_hash: "abc123..."
```

В Event metadata:

```yaml
embedding:
  model_id: "e5-small"
  version: "v1"
  config_hash: "abc123..."
```

**Replay правило:** replay использует тот же embedding spec. Если модель недоступна →
`EmbeddingProjection replay FAIL`. Нарушение = нарушение GL-1 (Determinism).

**Scope replay FAIL:** блокирует только L2 EmbeddingProjection. L1 projections восстанавливаются
нормально. Система работает; L2 SemanticSearch деградирует до `partial_result` (ML-9).

**Миграция модели:** отдельный `embedding-migration` процесс с human gate. Пересчитывает
embeddings → эмитит `EmbeddingRecomputed` events с новым `model_id`. До завершения миграции
L2 помечается `STALE`.

---

## 8. Consistency модель

```text
L1 projections: strict read-after-write consistency
  → обновляются синхронно с commit в EventLog (одна PostgreSQL транзакция)
  → Guards и ContextKernel всегда видят актуальное состояние

L2 projections: eventual consistency
  → НЕ в транзакции EventLog append
  → обновляются через outbox/async worker:
      EventLog commit → outbox table → async worker → RAGProjection / EmbeddingProjection
  → сбой L2 worker не откатывает L1 commit
  → L2 queries MUST быть tolerant к stale data
  → partial_result допустим (не ошибка)
  → L1 никогда не зависит от L2 readiness
```

**Outbox ordering (ML-8+):** L2 outbox worker MUST обрабатывать события строго по `event_offset` (FIFO).

```text
Правила:
  - один consumer на projection (single-writer, no parallel apply)
  - retries идемпотентны по event_id (не меняют порядок)
  - если event_offset N+1 прибыл раньше N — ждать N (no gap apply)
```

Нарушение порядка = нарушение GL-1 (Determinism) для L2.

Пример:

```python
if embedding_not_ready:
    return partial_result   # не ошибка, L2 eventual
```

---

## 9. Feedback loop (guard violations → обучение)

```text
Guard violation
  → ErrorClassified + guard_rule_id (hardcoded axiom или policy_id из PolicyProjection)
  → TraceProjection: violation count per rule_id per phase
  → AuditEngine: Mi tagged с rule_id
  → MetaOptimization: анализ трендов (читает через ReadModel.l2, не через CommandBus)
    → proposal: "GL-6 нарушается в 40% задач фазы 28"
    → [HUMAN_GATE]
    → PolicyKernel.emit(PolicyUpdated) для behavioral rules
    → EventLog → PolicyProjection обновляется
```

Axioms (GL-1, GL-7, NO_EXPLAIN_BEFORE_WRITE) — вне этого цикла. Не меняются через PolicyKernel.

---

## 10. ProjectionRegistry — маршрутизация по подписке

Проекции регистрируются с явным списком команд, не через runtime-фильтрацию флагов CommandSpec.

```python
class ProjectionRegistry:
    def register(
        projection: Projection,
        subscribed_commands: set[str]  # явный список, не флаги
    ) -> None: ...

# Регистрация:
registry.register(TraceProjection(),        {"resolve", "explain", "write"})
registry.register(GraphSessionProjection(), {"resolve", "explain", "write", "complete-task"})
registry.register(PolicyProjection(),       {"update-policy", "bootstrap-policy"})
```

WriteKernel при получении события делает lookup по типу команды → роутит только в подписанные проекции. O(1) вместо O(projections × events).

**Разделение concerns:**

```text
CommandSpec.affects_trace     → семантическая аннотация для Guards / AuditEngine (не routing)
CommandSpec.graph_structural  → семантика для GraphQueryEngine (не routing)
subscribed_commands           → инфраструктурная маршрутизация WriteKernel (SSOT)
```

**Контракт:**
- ProjectionRegistry не читает флаги из CommandSpec
- Каждая проекция регистрируется с явным `subscribed_commands`
- WriteKernel роутит событие только в подписанные проекции

**Тест:** для каждой проекции → replay только подписанных событий → assert state.

---

## 11. GraphSessionProjection — семантика

**Event → State mapping:**

```text
GraphResolved   → has_graph = true,  graph_fingerprint = event.fingerprint
ExplainExecuted → has_explain = true, fingerprint_locked = event.fingerprint
WriteExecuted   → total_writes += 1,  has_graph = false, has_explain = false
TaskCompleted   → финальный snapshot фиксируется без изменения флагов
```

**writes_count:** только накопительный счётчик `total_writes` для audit метрик.
Per-cycle счётчик не нужен — THRASHING guard **удалён** (см. ниже).

**THRASHING → Policy, не Guard:** протокол (L1) ≠ поведение (L2 policy).

- Протокол (`NO_EXPLAIN_BEFORE_WRITE`, fingerprint) — hardcoded axioms в Guard, enforces порядок.
- Ограничение числа циклов — behavioral rule в `PolicyProjection`:

```python
# PolicyProjection содержит:
max_write_cycles_per_task: int  # например, 3

# Guard check (behavioral, через policy):
cycles = memory.read.trace(task_id).write_cycles
limit  = memory.read.policy().max_write_cycles_per_task
if cycles > limit:
    return DENY("MAX_WRITE_CYCLES_EXCEEDED")  # severity из policy: RETRY / HUMAN_GATE
```

Guard не хранит счётчик сам — читает из `TraceProjection` и `PolicyProjection`.

**Семантика TaskCompleted:**

```text
Финальное значение флагов НЕ является признаком протокольной корректности.

Протокольная корректность = audit metric:
  total_writes > 0
  + отсутствие GuardViolation в TraceProjection
```

---

## 12. Масштабируемость

Добавление нового компонента = добавление проекции + регистрация в ProjectionRegistry:

```text
+ MetricsProjection     → registry.register(MetricsProjection(), {"complete-task", "validate"})
+ RAGProjection         → async worker (L2, eventual)
+ EmbeddingProjection   → async worker (L2, eventual)
+ AuditHistoryProjection → registry.register(...)
```

Ядро не трогается. Memory Layer API не меняется. Новый consumer получает доступ через тот же
`ReadModel` или `QueryEngineSemantic`.

---

## 13. Инварианты Memory Layer

| ID | Формулировка |
|---|---|
| ML-1 | read-only — Memory Layer не пишет |
| ML-2 | deterministic — same projections → same output |
| ML-3 | no side effects |
| ML-4 | source only = projections (не EventLog напрямую) |
| ML-5 | все данные системы доступны через Memory Layer |
| ML-6 | L1/L2 API жёстко изолированы: (1) API surface — L1 получает только `ReadModel`+`QueryEngineDeterministic`; (2) type-level — `L1MemoryLayer` final/sealed; (3) runtime — `assert isinstance(memory, L1MemoryLayer)`; (4) CI import linter |
| ML-7 | EmbeddingProjection версионирована (model_id + version + config_hash); replay FAIL блокирует только L2, не L1 |
| ML-8 | L1 = strict consistency (одна транзакция с EventLog); L2 = eventual (outbox/async worker, FIFO по event_offset, single-writer, идемпотентность по event_id); L1 не зависит от L2 readiness |
| ML-9 | failure в L2 projection не влияет на L1 projections, Guards, EventLog |
| ML-10 | ContextSnapshot в L1 строится только из deterministic sources; semantic data — optional layer |

---

## 14. Требуемые изменения в других файлах

Следующие wiki-страницы расходятся с решениями этого документа и требуют обновления:

| Файл | Что изменить |
|---|---|
| `raw/execution-guard.md` | 1. Guard signature: добавить `projection_reader`, убрать `state: GraphSessionState` как аргумент — state читается внутри через `GraphSessionState.current(task_id, projection_reader)`. 2. Удалить THRASHING check (`writes_count > 0`). 3. Убрать мутации `state.has_graph = True` — guard pure function, не мутирует state. |
| `wiki/pattern/execution-guard.md` | То же что выше + добавить `MAX_WRITE_CYCLES_EXCEEDED` check через `read.trace().write_cycles` + `read.policy().max_write_cycles_per_task`. |
| `wiki/pattern/projection-registry.md` | 1. Заменить O(N×N) loop на `subscribed_commands` routing. 2. Убрать `InvariantProjection` из списка зарегистрированных проекций. 3. Уточнить что L2 проекции (RAG, Embedding) не регистрируются в ProjectionRegistry — они через outbox/async worker. |
| `wiki/pattern/trace-projection.md` | Уточнить: `CommandSpec.affects_trace` — семантическая аннотация, НЕ используется для routing в ProjectionRegistry. Routing = `subscribed_commands`. |
| `wiki/pattern/graph-session-projection.md` | 1. Переименовать `writes_count` → `total_writes` (накопительный, для audit). 2. Убрать упоминания per-cycle reset счётчика. 3. Явно задокументировать удаление THRASHING guard. |
| `wiki/pattern/context-kernel.md` | Обновить ContextPacket: `invariants` → `policy = memory.read.policy()`. |
