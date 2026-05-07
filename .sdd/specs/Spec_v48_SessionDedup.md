# Spec_v48 — Phase 48: Session Dedup (Domain-Level, Safe)

Status: Draft
Baseline: Spec_v47_ELKernelExtraction.md
Revision: r2 — architectural corrections (p_sessions.seq, lightweight sync, sessions_view locality, projector module)

---

## 0. Goal

Устранить дубли `SessionDeclared` **без изменения семантики EventLog и command_id**.

Текущее состояние: `record-session` при повторном вызове с теми же `(session_type, phase_id)`
всегда эмитирует новый `SessionDeclared`. Это засоряет event log дублями.

После Phase 48:

- `command_id` остаётся **opaque, уникальным (uuid4)** — без изменений
- дедупликация происходит **на уровне domain (policy)** через `sessions_view` (snapshot p_sessions)
- `sessions_view` строится после лёгкой синхронизации p_sessions — не полного YAML-rebuild
- guard остаётся **pure** — никакого IO в guard-функциях (I-GUARD-PURE-1)
- `sessions_view` — локальная переменная `execute_command`, **не поле GuardContext**
- replay остаётся **100% детерминированным** — никаких изменений в reducer
- исторические события **не требуют миграции**
- повторный вызов **наблюдаем** через INFO лог + метрику (I-COMMAND-OBSERVABILITY-1)
- дедупликация — **best-effort** при конкурентном доступе (I-DEDUP-NOT-STRONG-1)

Phase 48 — чистый domain refinement: **нет новых domain events, нет изменений в бизнес-логике**.

---

## 1. Non-Goals (жёстко)

❌ НЕ изменяем:

- `command_id` генерацию (uuid4 остаётся)
- `EventLog.append()` idempotency механизм
- существующие события в event_log
- replay алгоритм и reducer
- `GuardOutcome` — остаётся `ALLOW | DENY` (нет NOOP outcome)
- `GuardContext` поля — `sessions_view` НЕ добавляется в GuardContext

❌ НЕ вводим:

- `GuardOutcome.NOOP`
- `sync_projections()` вызов в execute_command (избыточен: пересобирает YAML + TaskSet)
- `sessions_view` в `GuardContext` (guard его не читает — неправильный слой)
- time-based dedup в infra
- hash-based command_id
- implicit поведение в EventLog
- `SessionSkipped` или `SessionDeduplicated` события
- cross-day или cross-phase dedup
- multi-session aggregation
- строгую гарантию уникальности при конкурентном исполнении

---

## 2. Scope

### In-Scope

| BC | Описание | Файлы |
|----|----------|-------|
| BC-48-C | `SessionRecord` + `SessionsView` (O(1)-indexed, frozen) + `build_sessions_view(conn)` | `infra/projector.py` |
| BC-48-C2 | `p_sessions.seq BIGINT NOT NULL` — миграция схемы; заполняется из `event_log.sequence_id` | `infra/projector.py` |
| BC-48-B | `execute_command`: Step 0 conditional p_sessions sync + Step 2.5 dedup; `CommandSpec.dedup_policy` | `commands/registry.py` |
| BC-48-A | `SessionDedupPolicy.should_emit(sessions_view, cmd) → bool` (pure, frozen dataclass) | `domain/session/policy.py` |
| BC-48-D | `record-session` CommandSpec wire-up с `dedup_policy` | `commands/record_session.py` |
| BC-48-E | INFO logging + metric `session_dedup_skipped_total{session_type, phase_id}` | `commands/registry.py` |
| BC-48-F | Unit + integration tests | `tests/unit/domain/`, `tests/unit/commands/`, `tests/unit/infra/` |

### Out of Scope

- `execute_command` монолит рефактор (`commands/registry.py:615–787`) — Phase 49+
- `_sdd_root` глобал инвертирование (`infra/paths.py`) — Phase 49+
- `GuardContext` разбивка — Phase 49+
- DB-level `UNIQUE(session_type, phase_id)` в p_sessions — Future
- `show_path.py` → PG query вместо YAML — Future
- BC-47-D (PG fixtures TRUNCATE) если deferrable из Phase 47 — Phase 48 первым task'ом

---

## 3. Architecture

### Ключевая идея

```
Dedup    = domain decision, не storage trick
Data     = p_sessions (projection), не EventLog
Sync     = лёгкий (только p_sessions), не полный YAML-rebuild
Locality = sessions_view — локальная переменная execute_command, не поле GuardContext
Guard    = pure read от GuardContext; sessions_view до guard pipeline не доходит
```

### Flow до Phase 48

```
record-session
  → execute_command
    → guard ALLOW (всегда)
    → handler.handle() → [SessionDeclaredEvent]
    → EventLog.append([event])          ← дубль при повторе
```

### Flow после Phase 48

```
record-session
  → execute_command
    Step 0 [ЕСЛИ spec.dedup_policy is not None]:
        _sync_p_sessions(conn)          ← NEW: только p_sessions, не YAML (I-PROJECTION-FRESH-1)
        sessions_view = build_sessions_view(conn)   ← NEW: локальная переменная (I-SESSIONS-VIEW-LOCAL-1)
    Step 1: ctx = GuardContext(state, phase, task, norms, event_log, task_graph, now)
                              ← без sessions_view; GuardContext не изменён (I-GUARD-CONTEXT-UNCHANGED-1)
    Step 2: guard ALLOW (без изменений)
    ↓
    [NEW] Step 2.5: dedup policy check (только если spec.dedup_policy is not None)
      if not spec.dedup_policy.should_emit(sessions_view, cmd):
          logger.info("Session deduplicated: type=%s phase=%s", ...)
          record_metric("session_dedup_skipped_total", labels={...})
          return   ← success; zero events (I-COMMAND-OBSERVABILITY-1)
    ↓
    Step 3: handler.handle() → [SessionDeclaredEvent]
    Step 4: EventLog.append([event])
```

### Почему sessions_view — не поле GuardContext

Guard-функции читают только `GuardContext`. Dedup-шаг (2.5) выполняется **после** guard pipeline — guards уже отработали и не имеют доступа к `sessions_view`. Добавление поля в `GuardContext`, которое ни один guard не читает, нарушает контракт интерфейса: каждое поле GuardContext должно использоваться guard-функциями. `sessions_view` — данные для `execute_command`, не для guard.

### Почему не sync_projections

`sync_projections(db_path, taskset_path, state_path)` пересобирает YAML State_index + TaskSet_vN.md. Для dedup нужна только актуальность `p_sessions`. Полный rebuild избыточен и медленнее. Вместо него: `_sync_p_sessions(conn)` — лёгкая функция, которая применяет к `p_sessions` только необработанные события (seq > max(p_sessions.seq)).

### Синхронизация p_sessions (I-PROJECTION-FRESH-1)

```python
def _sync_p_sessions(conn) -> None:
    """Apply to p_sessions any SessionDeclared events not yet projected.

    Queries max seq already in p_sessions, then applies missing events
    from event_log in seq ASC order.
    I-PROJECTION-FRESH-1: p_sessions is current before build_sessions_view().
    """
    ...
```

Без `_sync_p_sessions` возможен сценарий:

```
EventLog: SessionDeclared seq=100
p_sessions: ещё не обновлена
→ build_sessions_view() → empty → dedup пропускает дубль
```

### p_sessions.seq — обязательная колонка (I-PSESSIONS-SEQ-1)

`build_sessions_view` фильтрует транзитивно инвалидированные записи через:

```sql
WHERE seq NOT IN (
    SELECT DISTINCT target_seq FROM invalidated_events
    WHERE transitive_invalidation = TRUE
)
```

Без колонки `seq` этот фильтр нереализуем. `seq` заполняется из `event_log.sequence_id` при `_handle_session_declared`.

### SessionsView — immutable snapshot с O(1) доступом

```python
@dataclass(frozen=True)
class SessionRecord:
    session_type: str
    phase_id:     int | None
    task_id:      str | None
    seq:          int          # из event_log.sequence_id
    timestamp:    str


@dataclass(frozen=True)
class SessionsView:
    """Immutable snapshot of non-invalidated sessions from p_sessions.

    I-SESSIONSVIEW-O1-1: get_last is O(1) via dict index keyed by (session_type, phase_id).
    I-GUARD-PURE-1: built before guard pipeline; guards do not receive it.
    I-PROJECTION-SESSIONS-1: records are pre-filtered (transitively invalidated excluded).
    """
    _index: dict[tuple[str, int | None], SessionRecord]

    def get_last(
        self,
        session_type: str,
        phase_id: int | None,
    ) -> SessionRecord | None:
        """O(1) lookup. Returns None if no non-invalidated session exists for key."""
        return self._index.get((session_type, phase_id))
```

### Ограничение: best-effort dedup (I-DEDUP-NOT-STRONG-1)

```
Thread A: _sync_p_sessions → empty → build_sessions_view → empty
Thread B: _sync_p_sessions → empty → build_sessions_view → empty
A → emit seq=101
B → emit seq=102   ← дубль возможен при concurrent execution
```

Phase 48 не защищает от race condition. Future: `UNIQUE(session_type, phase_id)` в p_sessions.

---

## 4. Domain Events

Phase 48 не вводит новых domain events. Чистый domain refinement.

Запрещено вводить:
- `SessionSkipped` — dedup не является domain-фактом
- `SessionDeduplicated` — то же

---

## 5. Types & Interfaces

### Новые типы (infra/projector.py)

```python
@dataclass(frozen=True)
class SessionRecord:
    session_type: str
    phase_id:     int | None
    task_id:      str | None
    seq:          int
    timestamp:    str


@dataclass(frozen=True)
class SessionsView:
    """Immutable snapshot of non-invalidated sessions from p_sessions.

    I-GUARD-PURE-1: not passed to GuardContext; guards do not read it.
    I-SESSIONS-VIEW-LOCAL-1: lives as local variable in execute_command only.
    I-PROJECTION-SESSIONS-1: records pre-filtered (transitively invalidated excluded).
    I-SESSIONSVIEW-O1-1: get_last is O(1).
    """
    _index: dict[tuple[str, int | None], SessionRecord]

    def get_last(
        self,
        session_type: str,
        phase_id: int | None,
    ) -> SessionRecord | None: ...


def _sync_p_sessions(conn) -> None:
    """Apply missing SessionDeclared events to p_sessions.

    Finds max(seq) in p_sessions, applies SessionDeclared events
    with seq > that value from event_log, ORDER BY seq ASC.
    I-PROJECTION-FRESH-1: must be called before build_sessions_view().
    """
    ...


def build_sessions_view(conn) -> SessionsView:
    """Query p_sessions (post-sync) and return immutable O(1)-indexed snapshot.

    SQL:
      SELECT session_type, phase_id, task_id, seq, timestamp
      FROM p_sessions
      WHERE seq NOT IN (
          SELECT DISTINCT target_seq
          FROM invalidated_events
          WHERE transitive_invalidation = TRUE   -- I-INVALIDATION-FINAL-1
      )
      ORDER BY seq ASC   -- I-PROJECTION-ORDER-1

    Builds _index: last record per (session_type, phase_id) wins.
    I-DEDUP-PROJECTION-CONSISTENCY-1: caller MUST call _sync_p_sessions() before this.
    """
    ...
```

### Схема p_sessions (изменение)

```sql
-- Добавить колонку seq (BC-48-C2):
ALTER TABLE p_sessions ADD COLUMN seq BIGINT NOT NULL;

-- Полная схема после миграции:
CREATE TABLE IF NOT EXISTS p_sessions (
    id           BIGSERIAL PRIMARY KEY,
    session_type TEXT    NOT NULL,
    phase_id     INTEGER,
    task_id      TEXT,
    seq          BIGINT  NOT NULL,    -- NEW: из event_log.sequence_id
    timestamp    TEXT
);
```

`_handle_session_declared` в `projector.py` дополняется записью `seq`:

```python
cur.execute(
    "INSERT INTO p_sessions (session_type, phase_id, task_id, seq, timestamp)"
    " VALUES (%s, %s, %s, %s, %s)",
    (
        getattr(event, "session_type", None),
        getattr(event, "phase_id", None),
        getattr(event, "task_id", None),
        getattr(event, "seq", None),          # NEW
        getattr(event, "timestamp", None),
    ),
)
```

### GuardContext — без изменений

```python
@dataclass(frozen=True)
class GuardContext:
    # Все поля без изменений:
    state:      "SDDState"
    phase:      PhaseState
    task:       Task | None
    norms:      "NormCatalog"
    event_log:  EventLogView
    task_graph: DAG
    now:        str
    # sessions_view НЕ добавляется (I-GUARD-CONTEXT-UNCHANGED-1)
```

### Новые типы (domain/session/policy.py)

```python
@dataclass(frozen=True)
class SessionDedupPolicy:
    """Domain policy: prevents duplicate SessionDeclared within same context.

    I-DEDUP-DOMAIN-1: dedup via sessions_view (p_sessions snapshot), not EventLog.
    I-SESSION-DEDUP-SCOPE-1: scope is strictly (session_type, phase_id).
    I-DEDUP-NOT-STRONG-1: best-effort; no concurrent execution guarantee.
    Pure: no IO, no side effects.
    """

    def should_emit(
        self,
        sessions_view: "SessionsView | None",
        cmd: "RecordSessionCommand",
    ) -> bool:
        """Return True if SessionDeclared should be emitted.

        False if non-invalidated session with same (session_type, phase_id)
        already exists in sessions_view.

        None sessions_view → True (degraded gracefully, I-SESSION-DEDUP-2).
        I-SESSION-INVALIDATION-1: transitively invalidated → get_last returns None → True.
        """
        if sessions_view is None:
            return True
        return sessions_view.get_last(cmd.session_type, cmd.phase_id) is None
```

### Изменения в commands/registry.py

```python
@dataclass
class CommandSpec:
    # Существующие поля (без изменений)
    ...
    # Новое поле:
    dedup_policy: "SessionDedupPolicy | None" = None
```

```python
# execute_command — изменённые шаги:

# Step 0 (NEW, conditional): sync p_sessions + build sessions_view
sessions_view: "SessionsView | None" = None
if spec.dedup_policy is not None:
    _sync_p_sessions(conn)                          # I-PROJECTION-FRESH-1
    sessions_view = build_sessions_view(conn)       # I-SESSIONS-VIEW-LOCAL-1

# Step 1 (без изменений): GuardContext не получает sessions_view
ctx = GuardContext(
    state=state,
    phase=phase,
    task=task,
    norms=norms,
    event_log=event_log_view,
    task_graph=task_graph,
    now=now,
    # sessions_view НЕ передаётся — I-GUARD-CONTEXT-UNCHANGED-1
)

# Step 2 (без изменений): guard pipeline

# Step 2.5 (NEW): dedup policy check
if spec.dedup_policy is not None:
    if not spec.dedup_policy.should_emit(sessions_view, cmd):
        logger.info(
            "Session deduplicated: type=%s phase=%s (I-SESSION-DEDUP-2)",
            getattr(cmd, "session_type", "?"),
            getattr(cmd, "phase_id", "?"),
        )
        record_metric(
            "session_dedup_skipped_total",
            labels={
                "session_type": getattr(cmd, "session_type", "unknown"),
                "phase_id":     str(getattr(cmd, "phase_id", "unknown")),
            },
        )
        return   # I-COMMAND-NOOP-2: NOOP MUST NOT affect projections or state

# Step 3: handler.handle() → events (только если should_emit)
# Step 4: EventLog.append (без изменений)
```

---

## 6. Invariants

### Новые инварианты

| ID | Statement | BC |
|----|-----------|----|
| I-SESSION-DEDUP-2 | `SessionDeclared` MUST NOT emit если НЕинвалидированный `SessionDeclared` с тем же `(session_type, phase_id)` уже есть в p_sessions | BC-48-A/D |
| I-DEDUP-DOMAIN-1 | Dedup MUST происходить через `SessionDedupPolicy` и `sessions_view` (p_sessions snapshot), не через EventLog hash или command_id | BC-48-A/C |
| I-COMMAND-ID-IMMUTABLE-1 | Phase 48 MUST NOT изменять command_id семантику или генерацию (uuid4 остаётся) | BC-48-B |
| I-COMMAND-NOOP-1 | Command MAY produce zero events если dedup policy returns False | BC-48-B |
| I-COMMAND-NOOP-2 | NOOP execution MUST NOT affect projections or state | BC-48-B |
| I-COMMAND-OBSERVABILITY-1 | Every command execution MUST be observable via EventLog OR deterministic logs/metrics; NOOP path MUST emit INFO log + metric | BC-48-B/E |
| I-GUARD-PURE-1 | Guards MUST NOT perform IO; все данные MUST поступать через GuardContext | BC-48-A/C |
| I-GUARD-CONTEXT-UNCHANGED-1 | `GuardContext` MUST NOT receive `sessions_view`; Phase 48 MUST NOT modify GuardContext fields | BC-48-B/C |
| I-SESSIONS-VIEW-LOCAL-1 | `sessions_view` MUST exist only as a local variable in `execute_command`; MUST NOT be stored in any shared context or passed to guards | BC-48-B/C |
| I-PROJECTION-FRESH-1 | `_sync_p_sessions(conn)` MUST be called before `build_sessions_view()`; only when `spec.dedup_policy is not None` | BC-48-B/C |
| I-DEDUP-PROJECTION-CONSISTENCY-1 | `SessionsView` MUST be built after `_sync_p_sessions()` covering all preceding committed events | BC-48-C |
| I-DEDUP-NOT-STRONG-1 | Дедупликация — best-effort; уникальность при конкурентном выполнении НЕ гарантирована | BC-48-B |
| I-PROJECTION-SESSIONS-1 | `build_sessions_view()` MUST фильтровать транзитивно инвалидированные seq | BC-48-C |
| I-SESSION-INVALIDATION-1 | Если `SessionDeclared` транзитивно инвалидирован → `sessions_view.get_last()` → None → dedup разрешает новый `SessionDeclared` | BC-48-A/C |
| I-SESSION-DEDUP-SCOPE-1 | Scope дедупликации = строго `(session_type, phase_id)`; разные ключи — независимы | BC-48-A |
| I-INVALIDATION-FINAL-1 | Если seq транзитивно инвалидирован → MUST NOT появляться в `SessionsView` | BC-48-C |
| I-SESSIONSVIEW-O1-1 | `SessionsView.get_last()` MUST быть O(1); реализация через dict | BC-48-C |
| I-PROJECTION-ORDER-1 | `SessionsView` records MUST обрабатываться в порядке `seq ASC`; последний seq побеждает | BC-48-C |
| I-PSESSIONS-SEQ-1 | `p_sessions` MUST иметь колонку `seq BIGINT NOT NULL`; заполняется из `event_log.sequence_id` в `_handle_session_declared` | BC-48-C2 |

### Сохраняются без изменений

- I-IDEM-SCHEMA-1 (EventLog idempotency)
- I-SESSION-DECLARED-1 (audit-only, no state mutation)
- I-REPLAY-1 (deterministic replay — dedup step не влияет на replay)
- I-GUARD-REASON-1 (DENY format)

### Удалён из спека

- ~~I-GUARD-CONTEXT-MINIMAL-1~~ — не нужен: `sessions_view` не попадает в GuardContext (I-GUARD-CONTEXT-UNCHANGED-1 делает этот инвариант излишним)

---

## 7. Pre/Post Conditions

### BC-48-C + BC-48-C2: SessionRecord, SessionsView, _sync_p_sessions, build_sessions_view, p_sessions.seq

**Pre:**
- P-1: Phase 47 завершена, все тесты зелёные
- p_sessions таблица существует в `infra/projector.py`
- `_handle_session_declared()` существует в `projector.py`

**Post:**
- `p_sessions.seq BIGINT NOT NULL` добавлена; `_handle_session_declared` записывает `seq`
- `SessionRecord`, `SessionsView` (frozen, O(1) indexed) в `infra/projector.py`
- `_sync_p_sessions(conn)` в `infra/projector.py` — применяет пропущенные события
- `build_sessions_view(conn)` — фильтрует инвалидированные seq; ORDER BY seq ASC
- `GuardContext` не изменён (I-GUARD-CONTEXT-UNCHANGED-1)
- `python3 -c "from sdd.infra.projector import SessionsView, build_sessions_view; print('OK')"` → OK
- I-GUARD-PURE-1, I-PROJECTION-SESSIONS-1, I-SESSIONSVIEW-O1-1, I-PROJECTION-ORDER-1,
  I-INVALIDATION-FINAL-1, I-PSESSIONS-SEQ-1 PASS

### BC-48-B: execute_command Step 0 + dedup step + CommandSpec

**Pre:**
- BC-48-C/C2 завершён

**Post:**
- `CommandSpec.dedup_policy: SessionDedupPolicy | None = None`
- Step 0: условный (только если `spec.dedup_policy is not None`):
  - `_sync_p_sessions(conn)` вызван до `build_sessions_view()`
  - `sessions_view` — локальная переменная, не поле GuardContext
- Step 2.5 присутствует; при `should_emit() == False` → INFO log + metric → return
- I-COMMAND-NOOP-1, I-COMMAND-NOOP-2, I-COMMAND-OBSERVABILITY-1,
  I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1,
  I-GUARD-CONTEXT-UNCHANGED-1, I-SESSIONS-VIEW-LOCAL-1 PASS

### BC-48-A: SessionDedupPolicy

**Pre:**
- `SessionsView` существует (BC-48-C)

**Post:**
- `should_emit(None, cmd)` → True
- `should_emit(view_с_записью, cmd)` → False
- `should_emit(view_без_совпадений, cmd)` → True
- Pure: `grep "import psycopg\|open(" src/sdd/domain/session/policy.py` → пусто
- I-SESSION-DEDUP-2, I-DEDUP-DOMAIN-1, I-SESSION-DEDUP-SCOPE-1, I-SESSION-INVALIDATION-1 PASS

### BC-48-D: record-session wire-up

**Pre:**
- BC-48-A, BC-48-B завершены

**Post:**
- `CommandSpec` для `record-session` содержит `dedup_policy=SessionDedupPolicy()`
- Повторный `sdd record-session --type IMPLEMENT --phase 48` → один `SessionDeclared` в EventLog
- I-SESSION-DEDUP-2 PASS (integration)

### BC-48-E: Logging + metric с labels

**Pre:**
- BC-48-B, BC-48-D завершены

**Post:**
- При dedup: `logger.info("Session deduplicated: type=IMPLEMENT phase=48")`
- `record_metric("session_dedup_skipped_total", labels={"session_type": "IMPLEMENT", "phase_id": "48"})`
- I-COMMAND-OBSERVABILITY-1 PASS

### BC-48-F: Tests

**Pre:**
- BC-48-A..E завершены

**Post:**
- `pytest tests/unit/domain/test_session_dedup.py` → PASS
- `pytest tests/unit/infra/test_projector_sessions.py` → PASS
- Integration: двойной вызов → 1 событие PASS
- Integration: после invalidate → разрешает PASS

---

## 8. Use Cases

### UC-48-1: Повторный вызов (dedup)

**Pre:** p_sessions содержит (IMPLEMENT, 48) seq=100; синхронизация актуальна
**Steps:**
1. `sdd record-session --type IMPLEMENT --phase 48`
2. `execute_command` Step 0: `_sync_p_sessions(conn)` → p_sessions актуальна
3. Step 0: `build_sessions_view()` → `sessions_view._index = {(IMPLEMENT, 48): seq=100}`
4. Step 2.5: `get_last(IMPLEMENT, 48)` → found → `should_emit()` → False
5. `logger.info("Session deduplicated: type=IMPLEMENT phase=48")`
6. `record_metric("session_dedup_skipped_total", ...)`
7. `return`

**Post:** EventLog не изменился; INFO в логах; метрика +1; I-COMMAND-OBSERVABILITY-1 соблюдён

---

### UC-48-2: Разные session_type — оба создаются

**Pre:** p_sessions пуст
**Steps:**
1. `sdd record-session --type PLAN --phase 48` → emit seq=101
2. `sdd record-session --type DECOMPOSE --phase 48` → `get_last(DECOMPOSE, 48)` → None → emit seq=102

**Post:** 2 `SessionDeclared`; I-SESSION-DEDUP-SCOPE-1 соблюдён

---

### UC-48-3: После transitive invalidate — разрешает новый

**Pre:** p_sessions содержит (IMPLEMENT, 48) seq=100, но seq=100 транзитивно инвалидирован
**Steps:**
1. `sdd record-session --type IMPLEMENT --phase 48`
2. `_sync_p_sessions()` → p_sessions обновлена
3. `build_sessions_view()` → seq=100 исключён → `get_last(IMPLEMENT, 48)` → None
4. `should_emit()` → True → `handler.handle()` → emit seq=103

**Post:** новый `SessionDeclared` seq=103; I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1 соблюдены

---

### UC-48-4: Concurrency (best-effort, документированное ограничение)

**Pre:** p_sessions пуст; два процесса стартуют одновременно
**Steps:**
1. Thread A: `_sync_p_sessions()` → empty; `build_sessions_view()` → empty
2. Thread B: `_sync_p_sessions()` → empty; `build_sessions_view()` → empty
3. A: `should_emit()` → True → append seq=101
4. B: `should_emit()` → True → append seq=102

**Post:** оба события в EventLog; это ожидаемо (I-DEDUP-NOT-STRONG-1)

---

### UC-48-5: Команды без dedup_policy — без изменений

**Pre:** любая команда с `CommandSpec.dedup_policy = None`
**Steps:**
1. Step 0 пропускается полностью (`spec.dedup_policy is None`)
2. Step 2.5 пропускается

**Post:** команда работает без изменений; нет лишнего DB round-trip

---

## 9. Integration

### Предусловия (блокирующие)

| # | Предусловие | Верификация |
|---|-------------|-------------|
| P-1 | Phase 47 завершена | `sdd show-state` → phase_status=COMPLETE |
| P-2 | p_sessions таблица существует | `psql -c "SELECT count(*) FROM p_sessions"` → success |
| P-3 | `_handle_session_declared()` существует в `infra/projector.py` | `grep "def _handle_session_declared" src/sdd/infra/projector.py` → найдено |
| P-4 | `record_session.py` handler существует | `from sdd.commands.record_session import RecordSessionHandler` → OK |
| P-5 | GuardContext frozen dataclass, 7 полей | `grep "frozen=True" src/sdd/domain/guards/context.py` → найдено |

### Порядок BC (строгий)

```
P-1..P-5 → верифицированы
  ↓
BC-48-C + BC-48-C2: SessionRecord, SessionsView, _sync_p_sessions, build_sessions_view + p_sessions.seq
  Шаг 1: SessionRecord + SessionsView (frozen, _index dict) в infra/projector.py
  Шаг 2: p_sessions схема: ALTER TABLE ADD COLUMN seq BIGINT NOT NULL
  Шаг 3: _handle_session_declared += seq из event.seq
  Шаг 4: _sync_p_sessions(conn) — применяет пропущенные события
  Шаг 5: build_sessions_view(conn) — SQL с фильтром транзитивной инвалидации + ORDER BY seq ASC
  Шаг 6: GuardContext — НЕ изменяется
  Шаг 7: pytest PASS — I-GUARD-PURE-1, I-SESSIONSVIEW-O1-1, I-INVALIDATION-FINAL-1, I-PSESSIONS-SEQ-1
  ↓
BC-48-B: execute_command Step 0 (conditional sync) + Step 2.5; CommandSpec.dedup_policy
  Шаг 1: CommandSpec += dedup_policy field
  Шаг 2: Step 0 — условный: если dedup_policy → _sync_p_sessions + build_sessions_view (local var)
  Шаг 3: Step 2.5 — dedup check + log + metric; sessions_view НЕ в GuardContext
  Шаг 4: pytest PASS — I-PROJECTION-FRESH-1, I-COMMAND-OBSERVABILITY-1,
                        I-GUARD-CONTEXT-UNCHANGED-1, I-SESSIONS-VIEW-LOCAL-1
  ↓
BC-48-A: SessionDedupPolicy.should_emit()
  Шаг 1: domain/session/__init__.py (пакет)
  Шаг 2: domain/session/policy.py — SessionDedupPolicy frozen dataclass
  Шаг 3: pytest unit PASS (без DB) — I-SESSION-DEDUP-2, I-SESSION-DEDUP-SCOPE-1
  ↓
BC-48-D: record-session CommandSpec wire-up
  Шаг 1: REGISTRY record-session += dedup_policy=SessionDedupPolicy()
  Шаг 2: integration test — двойной вызов → 1 событие; invalidate → разрешает
  ↓
BC-48-E: logging + metric с labels
  Шаг 1: logger.info с context
  Шаг 2: record_metric с labels {session_type, phase_id}
  Шаг 3: pytest PASS — I-COMMAND-OBSERVABILITY-1
  ↓
BC-48-F: tests (unit + integration)
  Все тесты PASS; smoke PASS
```

---

## 10. Verification

### Unit Tests

| # | Test | Файл | Invariant(s) |
|---|------|------|--------------|
| 1 | `test_policy_no_view_returns_true` | `tests/unit/domain/test_session_dedup.py` | I-SESSION-DEDUP-2 |
| 2 | `test_policy_no_matching_session_returns_true` | `tests/unit/domain/test_session_dedup.py` | I-SESSION-DEDUP-2 |
| 3 | `test_policy_matching_session_returns_false` | `tests/unit/domain/test_session_dedup.py` | I-SESSION-DEDUP-2 |
| 4 | `test_policy_different_type_returns_true` | `tests/unit/domain/test_session_dedup.py` | I-SESSION-DEDUP-SCOPE-1 |
| 5 | `test_policy_different_phase_returns_true` | `tests/unit/domain/test_session_dedup.py` | I-SESSION-DEDUP-SCOPE-1 |
| 6 | `test_sessions_view_get_last_o1` | `tests/unit/infra/test_projector_sessions.py` | I-SESSIONSVIEW-O1-1 |
| 7 | `test_sessions_view_respects_transitive_invalidation` | `tests/unit/infra/test_projector_sessions.py` | I-INVALIDATION-FINAL-1, I-SESSION-INVALIDATION-1 |
| 8 | `test_sessions_view_last_seq_wins` | `tests/unit/infra/test_projector_sessions.py` | I-PROJECTION-ORDER-1 |
| 9 | `test_sessions_view_is_frozen` | `tests/unit/infra/test_projector_sessions.py` | I-GUARD-PURE-1 |
| 10 | `test_policy_pure_no_io` | `tests/unit/domain/test_session_dedup.py` | I-GUARD-PURE-1, I-DEDUP-DOMAIN-1 |
| 11 | `test_dedup_logs_info_not_warning` | `tests/unit/commands/test_record_session_dedup.py` | I-COMMAND-OBSERVABILITY-1 |
| 12 | `test_dedup_increments_metric_with_labels` | `tests/unit/commands/test_record_session_dedup.py` | I-COMMAND-OBSERVABILITY-1 |
| 13 | `test_noop_does_not_affect_projections` | `tests/unit/commands/test_record_session_dedup.py` | I-COMMAND-NOOP-2 |
| 14 | `test_non_dedup_command_skips_step0` | `tests/unit/commands/test_record_session_dedup.py` | I-SESSIONS-VIEW-LOCAL-1 |
| 15 | `test_guard_context_has_no_sessions_view` | `tests/unit/commands/test_record_session_dedup.py` | I-GUARD-CONTEXT-UNCHANGED-1 |
| 16 | `test_psessions_seq_column_populated` | `tests/unit/infra/test_projector_sessions.py` | I-PSESSIONS-SEQ-1 |

### Integration Tests (PG)

| # | Test | Файл | Invariant(s) |
|---|------|------|--------------|
| 17 | `test_double_record_session_emits_one_event` | `tests/unit/commands/test_record_session_dedup_integration.py` | I-SESSION-DEDUP-2 |
| 18 | `test_after_invalidate_record_session_emits_new` | `tests/unit/commands/test_record_session_dedup_integration.py` | I-SESSION-INVALIDATION-1, I-INVALIDATION-FINAL-1 |
| 19 | `test_different_types_both_emitted` | `tests/unit/commands/test_record_session_dedup_integration.py` | I-SESSION-DEDUP-SCOPE-1 |
| 20 | `test_sync_before_sessions_view` | `tests/unit/commands/test_record_session_dedup_integration.py` | I-PROJECTION-FRESH-1, I-DEDUP-PROJECTION-CONSISTENCY-1 |

### Final Smoke

```bash
# 1. Двойной вызов → одно событие
sdd record-session --type IMPLEMENT --phase 48
sdd record-session --type IMPLEMENT --phase 48
sdd query-events --event SessionDeclared --phase 48 --json | python3 -c \
  "import sys,json; d=json.load(sys.stdin); assert len(d)==1, f'expected 1, got {len(d)}'"

# 2. Второй вызов → INFO в логах
sdd record-session --type IMPLEMENT --phase 48 2>&1 | grep "Session deduplicated"
# ожидаемый результат: "Session deduplicated: type=IMPLEMENT phase=48"

# 3. После transitive invalidate → разрешает новый
sdd invalidate-event <seq_первого_SessionDeclared>
sdd record-session --type IMPLEMENT --phase 48
sdd query-events --event SessionDeclared --phase 48 --json | python3 -c \
  "import sys,json; d=json.load(sys.stdin); assert len(d)==2, f'expected 2, got {len(d)}'"

# 4. Разные типы → оба создаются
sdd record-session --type PLAN --phase 48
sdd record-session --type DECOMPOSE --phase 48

# 5. GuardContext не изменён
python3 -c "
from sdd.domain.guards.context import GuardContext
import dataclasses
fields = {f.name for f in dataclasses.fields(GuardContext)}
assert 'sessions_view' not in fields, f'sessions_view leaked into GuardContext: {fields}'
print('OK: GuardContext has no sessions_view')
"

# 6. policy.py чистота
grep -n "import psycopg\|import subprocess\|open(" src/sdd/domain/session/policy.py
# ожидаемый результат: пусто

# 7. Все тесты
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest tests/unit -k "dedup or session" -v
```

---

## 11. Architectural Debt (Phase 49+)

| Issue | Файл | Суть |
|-------|------|------|
| `execute_command` монолит | `commands/registry.py:615–787` | 5-шаговый pipeline без явных швов |
| `_sdd_root` глобал | `infra/paths.py` | Инвертировать зависимость |
| `GuardContext` разбивка | `domain/guards/context.py` | 7 полей → минимальные протоколы |
| DB-level unique constraint | `p_sessions` | `UNIQUE(session_type, phase_id)` — strong concurrency |
| `sync_projections` инкапсуляция | `infra/projections.py` | `rebuild_state()` и `rebuild_taskset()` слишком связаны |
| State_index.yaml staleness | `infra/projections.py` | Incremental projection или прямые p_* queries |
| `show_path.py` → PG query | `commands/show_path.py` | Live данные из PG вместо YAML snapshot |
