# **SDD Meta Harness Core v2**

> **Статус:** ACTIVE — архитектурный референс SDD v2  
> **Принцип:** design = greenfield; code = partial reuse v1  
> **Язык:** решения зафиксированы через grill-me сессию 2026-05-05

---

## **0. Goal**

Построить **стабильное ядро Meta Harness**, которое:

* управляет исполнением (**event sourcing**)
* управляет поведением агента (**enforcement**)
* управляет навигацией (**graph + context**)
* обеспечивает наблюдаемость (**trace**)

**Гарантии:**

* детерминизм
* единый источник истины (EventLog)
* replay
* расширяемость без изменения ядра

---

## **1. Formal Model**

```text
SDD := ⟨L0, L1, L2⟩
```

### **L0 — Execution Core**

```text
⟨EventLog, Reducer, State, Command, CommandContext, Guard⟩
```

### **L1 — Harness Core**

```text
⟨Graph, QueryEngine, TraceStore, ExecutionGuard, ScopeGuard⟩
```

### **L2 — Extensions**

```text
⟨RAG, Policies, MetaOptimization⟩
```

---

## **2. Global Laws (IMMUTABLE)**

**GL-1 Determinism**

```text
Stateₙ = reduce(EventLog₀…ₙ)
```

**GL-2 SSOT**

```text
EventLog — единственный источник истины
```

**GL-3 Pipeline**

```text
Command → Guard(L0) → Guard(L1) → handle → Event → Reducer → State
```

**GL-4 Projection**

```text
Projection := f(EventLog, Code)
```

**GL-5 Isolation**

```text
L0 не зависит от L1/L2
```

**GL-6 Write Gate**

```text
write разрешён только если:
  start-task выполнен
  resolve выполнен
  explain выполнен
  file ∈ write_scope
```

---

## **3. Architecture**

```text
INTERFACE (CLI / LLM)
    ↓
APPLICATION (Commands + Guards L0 + L1)
    ↓
DOMAIN (Reducer, State, Invariants)
    ↓
INFRA (EventLog)

L1 (Graph, QueryEngine, TraceStore) — deterministic projections
L2 (RAG, Policies) — read-only access via CommandBus + ReadModel
```

---

## **4. L0 — Execution Core**

---

### **4.1 Event**

```yaml
Event:
  id: UUID
  type: string
  version: int          # обязательно, начиная с 1
  command_id: UUID
  payload: dict
  metadata:
    ts: timestamp
    actor: string
    session_id: string
    task_id: string
```

---

### **4.2 Command и CommandContext**

```yaml
Command:
  id: UUID
  type: string
  payload: dict
```

```yaml
CommandContext:
  actor: string
  session_id: string
  task_id: string
  timestamp: ts
```

**Правила:**

* `Command` = что сделать (атомарное действие)
* `CommandContext` = в каком контексте исполняется
* `CommandContext` создаётся **один раз при `start-task`**
* передаётся **неявно** через весь execution pipeline
* копируется в `metadata` каждого `Event`
* `handler` сигнатура: `handle(command, state, ctx) → list[Event]`

---

### **4.3 State**

```yaml
State:
  phases: dict
  tasks: dict
  invariants_status: dict
```

---

### **4.4 Reducer**

```python
def reduce(state: State, event: Event) -> State
```

**Properties:**

* pure — нет side effects
* deterministic — одинаковый input → одинаковый output
* idempotent по `event.id`

---

### **4.5 Guards (L0)**

```text
LifecycleGuard   — проверяет статус фазы/задачи
InvariantGuard   — проверяет state invariants
```

**Порядок в pipeline (строгий):**

```text
L0Guard.check(state, cmd, ctx)
L1Guard.check(trace, state, cmd, ctx)
events = handle(cmd, state, ctx)
event_store.append(events)
reduce(state, events)
```

L1 guard всегда после L0, оба — **до** handler.

---

### **4.6 Invariants**

```yaml
invariants:
  - id: EVENT_SCHEMA
    layer: L0
  - id: PHASE_FLOW
    layer: L0
  - id: TASK_FLOW
    layer: L0
```

---

### **4.7 Event Versioning + Upcasting**

Обязателен с первого дня. Каждый `Event` несёт `version: int`.

```python
class UpcasterRegistry:
    def register(event_type: str, from_version: int, to_version: int, fn: Callable): ...

def upcast(event: Event) -> Event:
    while event.version < CURRENT_VERSION[event.type]:
        event = registry.apply(event)
    return event
```

**Правила:**

* upcasters применяются **последовательно**
* запрещены side effects и IO
* при старте v2 все события имеют `version=1`, upcast = identity
* изменение схемы события → пишем апкастер `N → N+1`
* replay ВСЕГДА проходит через `upcast()` перед reducer

---

### **4.8 EventLog**

```python
class EventStore:
    def append(events: list[Event], caller: str) -> None:
        assert caller in ALLOWED_CALLERS  # ["CommandHandler"]
        # atomic batch
        # dedup by command_id (ON CONFLICT DO NOTHING)
        # dedup by event.id

    def load() -> list[Event]: ...
```

**Requirements:**

* append-only
* ordered
* dedup по `event.id` и `command_id`
* partitioning — **defer до v2.1+**

---

### **4.9 Replay**

```python
state = initial()
for e in event_store.load():
    state = reduce(state, upcast(e))
```

---

## **5. L1 — Harness Core**

---

## **5.1 Graph**

---

### **5.1.1 Node и Edge Model**

```yaml
Node:
  id: string
  type: phase | task | file | spec

Edge:
  from: node_id
  to: node_id
  kind: belongs_to | depends_on | writes | code_depends
  weight:
    priority: int
    confidence: float
```

**Edge семантика:**

```text
task  --belongs_to→  phase      # задача принадлежит фазе
task  --depends_on→  task       # межзадачная зависимость
task  --writes→      file       # из write_scope (SpecExtractor)
file  --code_depends→ file      # импорты (CodeExtractor)
spec  --belongs_to→  phase      # спец принадлежит фазе
```

`function` / `class` узлы — **defer до v2.1+**.

---

### **5.1.2 Graph Source**

```text
Graph = f(Code, Specs, EventLog)
```

**Extractors:**

```text
CodeExtractor   → file nodes + code_depends edges
SpecExtractor   → phase/task/spec nodes + belongs_to/depends_on/writes edges
EventExtractor  → актуализирует статус узлов из EventLog
```

`SpecExtractor` читает `TaskSet_vN.md` → для каждого task берёт `write_scope` → создаёт `task --writes→ file` edges.

---

### **5.1.3 Graph Build Pipeline**

```text
Extract → Link → Cache
```

* **Extract**: каждый extractor создаёт nodes + edges
* **Link**: объединяем, устраняем дубли, вычисляем confidence
* **Cache**: сохраняем под fingerprint

---

### **5.1.4 Fingerprint и Cache**

```python
fingerprint = hash(code_hash + spec_hash + event_offset)

GraphVersion:
  code_hash:      hash всех исходников
  spec_hash:      hash TaskSet + Phases_index
  event_offset:   id последнего применённого события
```

```text
if fingerprint != cached_fingerprint:
    invalidate cache
    rebuild graph
```

---

### **5.1.5 Стратегия перестройки (Rebuild Strategy)**

```text
1. При start-task:
   → строим граф, фиксируем fingerprint в GraphSessionState

2. Lazy check при каждом запросе:
   → if fingerprint changed: rebuild

3. Если fingerprint изменился ПОСЛЕ explain, но ДО write:
   → ExecutionGuard: DENY
   → требуем повторный explain на новом графе
   → детерминизм сохраняется: write всегда на том же графе, что и explain
```

---

## **5.2 QueryEngine**

Заменяет `ContextEngine` + строковый DSL. Единственный интерфейс для навигации по графу.

---

### **5.2.1 Typed Query**

```python
@dataclass
class Query:
    source: str          # "graph"
    selector: str        # "node" | "edge"
    filters: dict        # {"type": "task", "phase_id": 3}
    traversal: dict      # {"edge_kinds": ["depends_on"], "direction": "out", "max_hops": 2}
    limit: int
    order_by: str        # обязательно — deterministic ordering
```

Строковый DSL **не используется**. `Query` — единственный вход.

---

### **5.2.2 Supported Operations**

```yaml
Operations:
  - filter(node.type, attr)
  - traverse(edge.kind, direction)
  - depth(limit)
  - sort(order_by)    # обязательное поле — для детерминизма
```

---

### **5.2.3 Strategies**

```yaml
resolve:
  edge_kinds: ["depends_on", "belongs_to"]
  direction: out

explain:
  edge_kinds: ["depends_on", "belongs_to", "writes"]
  direction: out

trace:
  edge_kinds: ["depends_on"]
  direction: in

invariant:
  edge_kinds: ["belongs_to"]
  direction: out
```

---

### **5.2.4 Determinism**

* нет randomness
* `order_by` обязателен — результаты всегда стабильно упорядочены
* одинаковый граф + одинаковый `Query` → одинаковый результат

---

### **5.2.5 ContextSnapshot**

```python
@dataclass
class ContextSnapshot:
    id: str              # hash(nodes + edges + params)
    nodes: list[Node]
    edges: list[Edge]
    params: QueryParams  # start_nodes, budget, graph_version
```

* `ContextSnapshot` = **return type** `QueryEngine.execute(Query)`
* отдельного persistent хранилища нет
* кэширование — внутренняя деталь `QueryEngine` (dict по fingerprint)
* в `TraceStore` пишется только `snapshot.id` (hash) — для аудита

```python
class QueryEngine:
    def execute(self, query: Query) -> ContextSnapshot: ...
```

---

## **5.3 TraceStore**

Два интерфейса, одна реализация. Хранилище: `execution_log.jsonl`.

```python
@dataclass
class TraceEntry:
    ts: timestamp
    kind: str            # "graph_call" | "explain" | "file_write" | "command"
    payload: dict        # snapshot_id, file_path, command_type и т.д.

class TraceWriter(Protocol):
    def append(self, entry: TraceEntry) -> None: ...

class TraceReader(Protocol):
    def query(self, filters: dict) -> list[TraceEntry]: ...

class TraceStore(TraceWriter, TraceReader):
    # единственная реализация обоих протоколов
    ...
```

**Запись file_writes:**

* Claude Code Edit/Write tools → автоматический hook → `TraceStore.append(TraceEntry(kind="file_write", payload={"path": ...}))`
* агент **не декларирует** file writes вручную — hook делает это автоматически

---

## **5.4 ExecutionGuard (L1)**

---

### **5.4.1 GraphSessionState**

```yaml
GraphSessionState:
  task_id: string
  graph_fingerprint: string   # зафиксирован после explain
  has_graph: bool
  has_explain: bool
  writes_count: int
```

**Lifecycle:**

* создаётся при `start-task`
* `has_graph`, `has_explain` = False; `writes_count` = 0
* **сбрасывается (reset) после каждой write-команды**:
  `has_graph = False`, `has_explain = False`, `writes_count = 0`
* `graph_fingerprint` обновляется при каждом `explain`

---

### **5.4.2 Algorithm**

```python
def check(trace: TraceReader, state: GraphSessionState, cmd: Command) -> Result:

    if cmd.type == "resolve":
        state.has_graph = True
        return OK

    if cmd.type == "explain":
        if not state.has_graph:
            return DENY("NO_GRAPH_BEFORE_EXPLAIN")
        # проверяем: task связан с phase OR depends_on OR writes
        snapshot = query_engine.execute(explain_query(cmd.task_id))
        connected = any(
            e.kind in ("belongs_to", "depends_on", "writes")
            for e in snapshot.edges
            if e.from_ == cmd.task_id
        )
        if not connected:
            return DENY("TASK_ISOLATED")
        state.has_explain = True
        state.graph_fingerprint = current_fingerprint()
        trace.append(TraceEntry(kind="explain", payload={"snapshot_id": snapshot.id}))
        return OK

    if cmd.type == "write":
        if not (state.has_graph and state.has_explain):
            return DENY("NO_EXPLAIN_BEFORE_WRITE")
        if current_fingerprint() != state.graph_fingerprint:
            return DENY("GRAPH_CHANGED_AFTER_EXPLAIN — repeat explain")
        if state.writes_count > 0:
            return DENY("THRASHING")
        state.writes_count += 1
        # reset после write — следующий цикл начинается заново
        state.has_graph = False
        state.has_explain = False
        state.writes_count = 0
        return OK

    return OK
```

---

### **5.4.3 Enforcement Rules (formal)**

```text
NO_GRAPH_BEFORE_EXPLAIN
NO_EXPLAIN_BEFORE_WRITE
GRAPH_CHANGED_AFTER_EXPLAIN    → повторный explain обязателен
THRASHING (> 1 write per cycle)
TASK_ISOLATED                  → explain не прошёл
```

---

## **5.5 ScopeGuard**

---

### **5.5.1 Model**

```yaml
Task:
  write_scope:
    - "src/sdd/*.py"
    - "tests/unit/*.py"
```

---

### **5.5.2 Enforcement**

```python
def check(trace: TraceReader, task: Task) -> Result:
    file_writes = [e.payload["path"] for e in trace.query({"kind": "file_write"})]
    violations = [f for f in file_writes if f not in task.write_scope]
    if violations:
        return DENY(f"OUT_OF_SCOPE: {violations}")
    return OK
```

**Источник данных:** `TraceStore.file_writes` — записи от автоматического hook на Edit/Write tools.

**Правила:**

```text
file ∈ write_scope → разрешено
file ∉ write_scope → DENY (даже если есть graph path)
новый файл ∈ write_scope → разрешено без graph path
новый файл ∉ write_scope → DENY
```

`write_scope` = human-approved declaration. Graph path для файлов из scope **не требуется**.

---

## **6. Task Session Lifecycle**

```text
sdd start-task T-NNN
  → TaskSessionStarted event
  → Graph строится (fingerprint зафиксирован)
  → GraphSessionState инициализирован (has_graph=F, has_explain=F, writes=0)
  → CommandContext создан (actor, session_id, task_id, ts)

  ── Цикл (повторяется столько раз, сколько нужно write) ──

  sdd resolve T-NNN
    → L0 guard → L1 guard (has_graph=True) → handle → append

  sdd explain T-NNN
    → L0 guard → L1 guard (проверяет связность, фиксирует fingerprint) → handle → append

  [агент реализует код — Edit/Write tools → hook → TraceStore.file_writes]

  sdd complete T-NNN  (write-команда)
    → L0 guard → L1 guard (has_graph+has_explain+fingerprint) → ScopeGuard (trace.file_writes)
    → handle → append
    → GraphSessionState reset (has_graph=F, has_explain=F, writes=0)

  ── Конец цикла ──

sdd validate T-NNN --result PASS|FAIL
  → финальная валидация задачи
```

**Инвариант:** без `start-task` → любая команда → DENY.

---

## **7. Unified Invariants**

```yaml
L0 invariants (state):
  - EVENT_SCHEMA
  - PHASE_FLOW
  - TASK_FLOW

L1 invariants (behavior):
  - NO_GRAPH_BEFORE_EXPLAIN
  - NO_EXPLAIN_BEFORE_WRITE
  - GRAPH_CHANGED_AFTER_EXPLAIN
  - THRASHING
  - TASK_ISOLATED
  - SCOPE_VIOLATION
```

**Rule vs Guard:**

```text
Rule  = декларация (что запрещено)
Guard = применение (проверяет rules, возвращает DENY/OK)
```

---

## **8. Execution Flow (полный)**

```python
# Предусловие: start-task уже выполнен

# --- Любая команда ---
guards_L0.check(state, cmd, ctx)           # 1. state invariants
execution_guard.check(trace, gss, cmd)     # 2. behavior protocol (L1)
                                           # оба до handle — fail fast

events = handle(cmd, state, ctx)           # 3. pure handler

event_store.append(events)                 # 4. commit (atomic)

for e in events:
    state = reduce(state, upcast(e))       # 5. state update

# --- После write-команды ---
scope_guard.check(trace, task)             # 6. file scope verification
                                           # (вызывается как часть write-команды)
```

---

## **9. L2 — Extensions**

---

### **9.1 Доступ L2**

```python
class CommandBus:
    def submit(self, cmd: Command) -> None: ...

class ReadModel:
    def query(self, q: Query) -> ContextSnapshot: ...
```

L2 получает только эти два интерфейса. Прямой доступ к `EventStore`, `Reducer`, `Guard` — запрещён.

---

### **9.2 Runtime защита**

```python
def append(events: list[Event], caller: str) -> None:
    assert caller in ["CommandHandler"]  # единственный разрешённый caller
```

`EventStore`, `Reducer` — не экспортируются в public API. L2 импортирует только `interfaces/*`.

---

### **9.3 L2 МОЖЕТ**

```text
читать через ReadModel
генерировать Commands через CommandBus
анализировать TraceStore через TraceReader
```

### **9.4 L2 НЕ МОЖЕТ**

```text
писать в EventLog напрямую
изменять Graph
обходить Guards
нарушать детерминизм
```

---

### **9.5 Deferred до v2.1+**

```text
compensating events (rollback)
EventLog partitioning
function/class graph nodes
ML-based rule generation
```

---

## **10. Replay-Based Testing**

---

### **10.1 Принцип**

```text
Tests = replay(events) + assertions(state, trace)
```

---

### **10.2 Test Model**

```yaml
TestCase:
  input_events: list[Event]
  expected_state: State
  expected_trace: list[TraceEntry]
```

---

### **10.3 Execution**

```python
state = initial()
for e in input_events:
    state = reduce(state, upcast(e))
assert state == expected_state
```

---

### **10.4 Гарантии**

* детерминированные тесты
* не нужны моки (EventLog = source of truth)
* полная валидация системы через replay

---

## **11. Directory Structure**

```text
src/sdd_v2/
  core/            → L0: EventLog, Reducer, State, Command, Guards
  harness/         → L1: Graph, QueryEngine, TraceStore, ExecutionGuard, ScopeGuard
  interfaces/      → Protocol definitions (CommandBus, ReadModel, TraceWriter, TraceReader)
  extensions/      → L2: (RAG, Policies — будущее)
  infra/           → EventStore implementation, storage backend
  app/             → CLI commands, session lifecycle
  tests/           → replay-based tests
```

---

## **12. Guarantees**

```text
Determinism        — одинаковый EventLog → одинаковый State
Replayability      — полное восстановление из EventLog
Explainability     — каждый write обоснован графом (explain gate)
Behavior Control   — агент не может писать без resolve+explain
Scope Enforcement  — file writes верифицированы через TraceStore hook
Extensibility      — L2 расширяет через Commands, не нарушает L0
```

---

## **13. Definition of Done**

```text
✔ deterministic reducer
✔ upcast pipeline работает (version field в каждом Event)
✔ graph projection строится из Code + Specs + EventLog
✔ QueryEngine.execute(Query) детерминирован (order_by обязателен)
✔ explain gate проверяет связность задачи (belongs_to | depends_on | writes)
✔ scope guard верифицирует через TraceStore.file_writes
✔ fingerprint guard блокирует write если граф изменился после explain
✔ GraphSessionState сбрасывается после каждой write-команды
✔ start-task обязателен — без него все команды DENY
✔ L2 доступ только через CommandBus + ReadModel
✔ replay восстанавливает полное состояние системы
```

---

## **14. Core Insight**

```text
L0 = что произошло
L1 = почему и как
L2 = что можно улучшить

write = зафиксировать
explain = почему это корректно
resolve = что делать
```
