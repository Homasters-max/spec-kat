# SDD Architectural Hardening — CQRS / EventLog / Guard / Idempotency

> Финальный план после grill-me сессии (2026-05-05).  
> Все решения верифицированы по 11 вопросам. Готово к реализации в wiki.

---

## Scope

Работа только в `/root/project/obsidian-vault/llm-wiki/wiki`, файлы `domain: sdd`.  
6 страниц: 3 новых, 3 обновлений.

---

## Финальные архитектурные решения

### R-1: Snapshot = reduce(EventLog[0:N])

Handler — pure function. Snapshot передаётся WriteKernel'ом, не читается handler'ом самостоятельно.

```python
snapshot = reduce(event_store.load(up_to=N))  # детерминировано
events   = handler(cmd, snapshot)              # pure, no side effects
event_store.append(events, expected_version=N) # OCC атомарно внутри EventStore
```

При `current_version != expected_version` → `OptimisticConcurrencyError` → retry в middleware/orchestrator.  
Handler retry-safe: детерминированный вход → детерминированный выход.

---

### R-2: Детерминированный event_id

```python
event_id = uuid5(NAMESPACE_SDD, f"{command_id}:{position}")
# position = индекс события в batch от данной команды (0, 1, 2…)
```

- Уникален в пределах команды даже при нескольких событиях одного типа
- Детерминирован: retry команды → те же event_id → безопасный dedup
- `event_type` исключён из ключа (не нужен, коллизий нет при position)

---

### R-3: Reducer — чистая функция, без dedup-ответственности

```python
def reduce(state: State, event: Event) -> State:
    """
    Pure:          no DB, no network, no datetime.now()
    Total:         unknown event type → return state unchanged (not raise)
    Deterministic: identical (state, event) → identical result
    """
```

Идемпотентность обеспечивается двумя слоями:
- **EventStore** (write-time, mandatory): dedup по `event_id` при append
- **ReplayEngine** (read-time, defensive): фильтрует дубликаты перед подачей в reducer

Reducer не знает про `event_id`. State не содержит `seen_ids`. Domain-логика не зависит от dedup.

---

### R-4: Causal Linkage — три поля

```python
@dataclass(frozen=True)
class Event:
    event_id:          UUID      # uuid5(command_id:position) — детерминирован
    command_id:        UUID      # provenance: какая команда породила событие
    causation_event_id: UUID | None  # event graph: предыдущее событие в цепочке (None если первое)
    correlation_id:    UUID      # flow grouping: неизменен по всей сессии
    sequence_no:       int       # монотонно возрастающий, без пропусков
    occurred_at:       datetime  # UTC, immutable после записи
    payload:           dict
```

Семантика:
- `command_id` → «какая команда меня создала»
- `causation_event_id` → «из какого события выросло следующее» (event DAG)
- `correlation_id` → «какая сессия меня создала» (задаётся SessionOrchestrator)

`correlation_id` жизненный цикл:
```python
# SessionOrchestrator при старте сессии:
correlation_id = uuid4()  # один id на всю сессию

# CommandContext несёт его через весь pipeline:
ctx = CommandContext(actor=..., session_id=..., task_id=..., correlation_id=correlation_id)

# WriteKernel копирует в каждый Event:
event.correlation_id = ctx.correlation_id
```

Реконструкция: `WHERE correlation_id = X ORDER BY sequence_no` → полная история сессии.

---

### R-5: build_context — чистая функция от Snapshot

```python
def build_context(task_id: str, snapshot: State) -> ContextPacket:
    """
    Pure function.
    snapshot = reduce(EventLog[0:N]) — несёт version для OCC.
    MUST NOT call datetime.now(), random.*, network, DB.
    """
```

- Snapshot передаётся снаружи (от WriteKernel или SessionOrchestrator)
- Optional memoization cache с инвалидацией по `snapshot.version`
- `replay_context(task_id, N)` = `build_context(task_id, reduce(EventLog[0:N]))` — отлаживаемо

---

### R-6: Projections — два класса

| Класс | Инвариант | Примеры |
|-------|-----------|---------|
| Deterministic | `P.rebuild(EventLog) == P.current_state()` | State, Trace, Graph, Policy, Idempotency |
| Approximate | `P.rebuild(EventLog) ≈ P.current_state()` (semantic equiv.) | EmbeddingProjection |

Только deterministic projections определяют system correctness.  
Approximate projections имеют отдельный контракт (near-neighbor consistency, не побитовое равенство).

---

### R-7 + R-9: Guard Taxonomy — три типа, пять middlewares

**Taxonomy:**

| Guard Type | Enforcement | Failure | Configurable | Bypass |
|------------|-------------|---------|--------------|--------|
| Structural | hardcoded constants | ABORT | No | Never |
| Runtime | call-stack assertion | RuntimeError → ABORT | No | Never |
| Policy | PolicyProjection (EventLog-sourced) | RETRY / HUMAN_GATE | Yes, via human gate | No |

**Structural Guards:**
- `L1ExecutionGuardMiddleware`: 4 hardcoded axioms — NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT, NO_GRAPH_BEFORE_EXPLAIN, TASK_ISOLATED
- `L1ScopeGuardMiddleware`: write_scope из TraceStore (фиксирован при создании задачи, ABORT)

**Policy Guard:**
- `L1PolicyGuardMiddleware`: читает из PolicyProjection
  - `max_write_cycles_per_task` (переехало из ExecutionGuard)
  - actor permissions
  - retry_limit
  - всё изменяемое через human gate

**Финальный pipeline (фиксированный порядок):**

```
slot 0:   ErrorClassifierMiddleware   ← перехват всех GuardError/RuntimeError
slot 0.5: IdempotencyMiddleware        ← dedup команды по idempotency_key (до guards)
slot 1:   L0GuardMiddleware           ← Runtime Guard: EventStore call-stack (GL-7)
slot 2a:  L1ExecutionGuardMiddleware  ← Structural: 4 axioms, hardcoded
slot 2b:  L1ScopeGuardMiddleware      ← Structural: write_scope, ABORT
slot 2c:  L1PolicyGuardMiddleware     ← Policy: PolicyProjection, RETRY/HUMAN_GATE
terminal: WriteKernel.execute_and_project(snapshot, expected_version)
```

---

### R-8: OCC Contract

```python
# Единственная атомарная точка проверки:
EventStore.append(events: list[Event], expected_version: int) -> None
    # raises OptimisticConcurrencyError if current_version != expected_version

# WriteKernel передаёт версию snapshot:
event_store.append(handler_events, expected_version=snapshot.version)

# Retry при конфликте — в middleware или orchestrator:
# OptimisticConcurrencyError → reload snapshot → retry handler → retry append
```

Нет race condition: проверка и append атомарны внутри EventStore (PostgreSQL transaction).

---

## Инварианты

### CQRS

```
I-CQRS-1: handler(cmd, snapshot) → list[Event]
           snapshot = reduce(EventLog[0:N]); передаётся WriteKernel'ом до вызова
I-CQRS-2: handler MUST NOT call any read API (EventStore, Projection, DB, network) во время выполнения
I-CQRS-3: Events NEVER carry imperative payload; Commands NEVER appear in EventLog
```

### EventLog

```
I-EVENTLOG-1: append-only — delete() и update() MUST NOT exist
I-EVENTLOG-2: ordered — sequence_no монотонен; gap → Inconsistency raised
I-EVENTLOG-3: immutable — событие после append не изменяется (hash-verified)
I-EVENTLOG-4: event_id детерминирован: uuid5(NAMESPACE_SDD, f"{command_id}:{position}")
I-EVENTLOG-5: single-caller — append() MUST fail если call-stack не содержит WriteKernel (GL-7)
I-EVENTLOG-6: atomic-batch — события одной команды appended atomically или не appended вовсе
I-EVENTLOG-7: OCC — append(events, expected_version) проверяет версию атомарно
```

### Context

```
I-CTX-DET-1: identical snapshot → identical ContextPacket
             build_context(task_id, s_a) == build_context(task_id, s_b) если s_a == s_b
I-CTX-DET-2: build_context MUST NOT call datetime.now(), random.*, network, DB
```

### Guard Pipeline

```
I-GUARD-PIPELINE-1: порядок слотов (0, 0.5, 1, 2a, 2b, 2c, terminal) фиксирован;
                    тест на порядок обязателен в CI
I-GUARD-PIPELINE-2: Structural Guards (2a, 2b) MUST run before Policy Guard (2c)
I-GUARD-PIPELINE-3: L1PolicyGuardMiddleware читает ТОЛЬКО из PolicyProjection;
                    прямые DB-reads запрещены
```

### Idempotency

```
I-IDEM-EVENT-1: reduce(events + duplicate_events) == reduce(events)
                (гарантируется EventStore dedup + ReplayEngine filter, не Reducer)
I-IDEM-EVENT-3: event_id детерминирован из (command_id, position) → I-EVENTLOG-4
```

### Reducer

```
I-REDUCER-1: reduce — pure function (no side effects)
I-REDUCER-2: reduce — total function (unknown event type → identity, not raise)
```

### Replay

```
I-REPLAY-14: replay(EventLog) == current_state_from_StateProjection()
             проверяется при каждом sdd check-dod
I-REPLAY-16: для каждой deterministic Projection P:
             P.rebuild(EventLog) == P.current_state()
             (approximate projections — отдельный контракт)
```

---

## Файлы wiki для создания/обновления

| Действие | Файл | Ключевые изменения |
|----------|------|-------------------|
| CREATE | `pattern/cqrs-boundary.md` | R-1, I-CQRS-1..3, snapshot = reduce(), OCC |
| UPDATE v1→v2 | `idea/event-sourcing.md` | R-2, R-4, I-EVENTLOG-1..7, causal linkage |
| CREATE | `pattern/deterministic-context.md` | R-5, I-CTX-DET-1..2, build_context(task_id, snapshot) |
| UPDATE v2→v3 | `pattern/execution-guard.md` | R-7+R-9, guard taxonomy, pipeline table, max_write_cycles → PolicyGuard |
| CREATE | `idea/idempotent-events.md` | R-3, I-IDEM-EVENT-1+3, dedup layers |
| UPDATE v2→v3 | `pattern/replay-based-testing.md` | R-6, I-REPLAY-14+16, Reducer contract, deterministic vs approximate |

---

## Удалённые инварианты (были в черновике, признаны неверными)

| ID | Причина удаления |
|----|-----------------|
| I-REDUCER-3 `reduce(reduce(s,e),e)==reduce(s,e)` | Требует seen_ids в State — нарушает purity; dedup → EventStore/ReplayEngine |
| I-IDEM-EVENT-2 `Reducer MUST skip seen event_id` | Та же причина |
| I-REPLAY-15 `replay_context == build_base` | Redundant: следует из I-REPLAY-14 + I-CTX-DET-1 + OCC |
