# Spec_v49 — Phase 49: Session Dedup Fixes

Status: Draft
Baseline: Spec_v48_SessionDedup.md (Phase 48)

---

## 0. Goal

Устранить три регрессии, выявленные при smoke-верификации Phase 48 (T-4813):
INFO-лог дедупликации не виден в терминале; `sdd invalidate-event` ошибочно отклоняет
`SessionDeclared` через I-INVALID-4; обработчик `record_session` может переопределить
решение ядра о дедупликации и нарушает I-HANDLER-PURE-1. Phase 49 исправляет каждую из
трёх точечными изменениями с учётом архитектурных требований чистоты интерфейсов.

### Architectural rationale (почему решения именно такие)

Исходная формулировка BC-49-B и BC-49-C в черновике содержала две архитектурные ошибки,
выявленные при глубоком анализе потока `execute_command`:

**Проблема BC-49-B (черновик):** Константа `_AUDIT_ONLY_EVENTS` предлагалась в
`invalidate_event.py`. Это создаёт второй источник истины для классификации audit-only
событий: один — `# audit-only` comment в `reducer.py:175`, второй — модульная константа
в handler. Расхождение молчаливо: при добавлении нового audit-only event обновить нужно
оба места. **Решение:** `_AUDIT_ONLY_EVENTS` и метод `is_invalidatable()` живут в
`EventReducer` — единственном месте, которое знает про state-mutation семантику событий.

**Проблема BC-49-C (черновик):** `_session_declared_today()` в handler предлагалось
исправить SQL-subquery. Но сам метод является нарушением `I-HANDLER-PURE-1`: он открывает
соединение с EventStore из `handle()`. Кроме того, он **переопределяет** решение ядра:
ядро в Step 2.5 уже проверяет dedup через `SessionDedupPolicy.should_emit()` +
`build_sessions_view()` (последний уже фильтрует инвалидированные seq — projector.py:412–416).
Если ядро сказало "emit", handler может сказать "нет" через устаревший SQL-запрос — это
архитектурная инверсия. **Решение:** удалить `_session_declared_today()` целиком; handler
становится чистой функцией; ядро — единственный dedup authority.

---

## 1. Scope

### In-Scope

- BC-49-A: CLI Logging — `src/sdd/cli.py`
- BC-49-B: I-INVALID-4 audit-only exclusion — `src/sdd/infra/reducer.py` + `src/sdd/commands/invalidate_event.py`
- BC-49-C: Remove handler-level dedup; restore I-HANDLER-PURE-1 — `src/sdd/commands/record_session.py`

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-49-A: CLI Logging

```
src/sdd/cli.py
  cli()    # @click.group() callback — добавить logging.basicConfig(level=INFO)
```

Python logging дефолтный уровень — WARNING. INFO-сообщения, эмитированные в
`registry.py` через `_log.info(...)`, не достигают терминала без явной конфигурации.
Решение: вызвать `logging.basicConfig(level=logging.INFO)` в callback CLI-группы до
исполнения любой подкоманды.

### BC-49-B: I-INVALID-4 audit-only exclusion (revised)

```
src/sdd/infra/reducer.py
  EventReducer._AUDIT_ONLY_EVENTS: ClassVar[frozenset[str]]   # новая ClassVar
  EventReducer.is_invalidatable(event_type: str) -> bool      # новый публичный classmethod

src/sdd/commands/invalidate_event.py
  InvalidateEventHandler.handle()   # заменить прямой доступ _EVENT_SCHEMA на is_invalidatable()
```

`SessionDeclared` присутствует в `EventReducer._EVENT_SCHEMA`, но reducer явно помечает
его как audit-only без state mutation (reducer.py:175: `# audit-only`).

Оригинальная реализация I-INVALID-4 проверяет `target_type in EventReducer._EVENT_SCHEMA`
и тем самым применяет правило слишком широко: попадают и state-mutating события, и
audit-only события. При этом handler напрямую читает приватный атрибут `_EVENT_SCHEMA`
другого модуля — нарушение инкапсуляции.

**Решение — два шага:**

1. В `reducer.py`: добавить `_AUDIT_ONLY_EVENTS: ClassVar[frozenset[str]]` (SSOT для
   audit-only классификации) и публичный classmethod `is_invalidatable(event_type)`,
   который инкапсулирует логику: "в схеме И не audit-only → state-mutating → нельзя
   инвалидировать".

2. В `invalidate_event.py`: заменить прямой `_EVENT_SCHEMA` check на вызов
   `EventReducer.is_invalidatable(target_type)`.

Ни один внешний модуль не должен обращаться к `EventReducer._EVENT_SCHEMA` для
проверки инвалидируемости — только через `is_invalidatable()`.

### BC-49-C: Remove handler-level dedup; restore I-HANDLER-PURE-1 (revised)

```
src/sdd/commands/record_session.py
  RecordSessionHandler._session_declared_today()   # DELETED
  RecordSessionHandler.handle()                    # упрощён: всегда возвращает [SessionDeclaredEvent]
```

`_session_declared_today()` нарушает `I-HANDLER-PURE-1` двумя способами:
1. Открывает соединение с EventStore внутри `handle()` (явный запрет в I-HANDLER-PURE-1).
2. Переопределяет решение ядра: `execute_command` Step 2.5 выполняется ДО Step 4
   (handler). Если Step 2.5 решил "emit" (в т.ч. потому что `build_sessions_view()`
   уже отфильтровал инвалидированные seq), handler повторно проверяет через SQL без
   учёта инвалидаций и может вернуть `[]` — молчаливый noop вопреки решению ядра.

Ядро уже содержит полный и корректный dedup path:
- Pre-step: `_sync_p_sessions()` + `build_sessions_view()` строит `SessionsView`,
  которая через `NOT IN (EventInvalidated.target_seq)` фильтрует инвалидированные сессии
  (projector.py:412–416).
- Step 2.5: `SessionDedupPolicy.should_emit(sessions_view, cmd)` — единственный dedup authority.

**Решение:** удалить `_session_declared_today()`. `handle()` становится чистой функцией:
всегда возвращает `[SessionDeclaredEvent(...)]` без IO. Ядро — единственный dedup authority.

### Dependencies

```text
BC-49-A : independent
BC-49-B : independent
BC-49-C : independent of BC-49-B
           (handler просто убирает IO; ядерный dedup уже корректен)

UC-49-3 (re-emit after invalidation) зависит от обоих:
  BC-49-B: sdd invalidate-event SessionDeclared → exit 0 (без BC-49-B: I-INVALID-4 блокирует)
  BC-49-C: handler не ветирует решение ядра (без BC-49-C: handler возвращает [] несмотря на kernel "emit")
```

---

## 3. Domain Events

Phase 49 не добавляет новых event types. Используются существующие события Phase 48:
`SessionDeclared`, `EventInvalidated`.

### Event Catalog

| Event | Emitter | Description |
|-------|---------|-------------|
| `SessionDeclared` | `RecordSessionHandler` | Существующий. audit-only. No state mutation. |
| `EventInvalidated` | `InvalidateEventHandler` | Существующий. Помечает target_seq как недействительный. |

---

## 4. Types & Interfaces

### BC-49-B — EventReducer extensions (reducer.py)

```python
# src/sdd/infra/reducer.py  —  внутри класса EventReducer

_AUDIT_ONLY_EVENTS: ClassVar[frozenset[str]] = frozenset({"SessionDeclared"})
# Audit-only events are present in _EVENT_SCHEMA for schema validation,
# but do NOT mutate state in reduce(). They are invalidatable (I-INVALID-AUDIT-ONLY-1).

@classmethod
def is_invalidatable(cls, event_type: str) -> bool:
    """Return True iff event_type can be invalidated (satisfies I-INVALID-4).

    State-mutating events (in _EVENT_SCHEMA AND NOT in _AUDIT_ONLY_EVENTS)
    cannot be invalidated. Audit-only and unknown types can be invalidated.
    """
    if event_type not in cls._EVENT_SCHEMA:
        return True   # unknown type → not state-mutating → invalidatable
    return event_type in cls._AUDIT_ONLY_EVENTS  # audit-only → invalidatable
```

### BC-49-B — invalidate_event.py (I-INVALID-4 check)

```python
# src/sdd/commands/invalidate_event.py
# Заменить блок lines 87–93 на:

from sdd.infra.reducer import EventReducer   # уже импортирован или добавить

# I-INVALID-4: cannot invalidate state-mutating events
if not EventReducer.is_invalidatable(target_type):
    raise InvariantViolationError(
        f"I-INVALID-4: cannot invalidate state-mutating event "
        f"(type={target_type!r} is state-mutating per EventReducer)"
    )
```

### BC-49-C — record_session.py (handle becomes pure)

```python
# src/sdd/commands/record_session.py
# УДАЛИТЬ: метод _session_declared_today() (lines 53–73) — нарушение I-HANDLER-PURE-1
# УДАЛИТЬ: from sdd.infra.db import open_sdd_connection  (если больше не используется)
# УПРОСТИТЬ handle():

@error_event_boundary(source=__name__)
def handle(self, cmd: Any) -> list[DomainEvent]:
    return [
        SessionDeclaredEvent(
            event_type=SessionDeclaredEvent.EVENT_TYPE,
            event_id=str(uuid.uuid4()),
            appended_at=int(time.time() * 1000),
            level=EventLevel.L1,
            event_source="runtime",
            caused_by_meta_seq=None,
            session_type=cmd.session_type,
            task_id=cmd.task_id,
            phase_id=cmd.phase_id,
            plan_hash=cmd.plan_hash,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    ]
```

Dedup теперь является исключительно ответственностью ядра (Step 2.5).

### BC-49-A — logging.basicConfig

```python
# src/sdd/cli.py, в @cli.group() callback:

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-CLI-LOG-LEVEL-1 | CLI MUST call `logging.basicConfig(level=INFO)` before any subcommand executes; INFO-level log messages MUST appear in terminal stderr | 49 |
| I-INVALID-AUDIT-ONLY-1 | Events in `EventReducer._AUDIT_ONLY_EVENTS` MUST NOT be rejected by I-INVALID-4; they MUST be invalidatable via `sdd invalidate-event` | 49 |
| I-AUDIT-ONLY-SSOT-1 | `EventReducer._AUDIT_ONLY_EVENTS` is the sole declaration of audit-only event types; no module-level copy of this set is permitted outside `reducer.py` | 49 |
| I-INVALIDATABLE-INTERFACE-1 | I-INVALID-4 check MUST be performed exclusively via `EventReducer.is_invalidatable()`; direct access to `EventReducer._EVENT_SCHEMA` from outside `reducer.py` for invalidation logic is forbidden | 49 |
| I-HANDLER-SESSION-PURE-1 | `RecordSessionHandler.handle()` MUST NOT perform IO or dedup checks; it MUST always return `[SessionDeclaredEvent(...)]`; dedup is exclusively the kernel's Step 2.5 responsibility | 49 |
| I-DEDUP-KERNEL-AUTHORITY-1 | `execute_command` Step 2.5 (`SessionDedupPolicy.should_emit()` via `SessionsView`) is the single dedup authority for `record-session`; no handler or guard may independently veto the emission decision made by Step 2.5 | 49 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-HANDLER-PURE-1 | `handle()` methods return events only — no EventStore, no rebuild_state, no sync_projections (BC-49-C restores compliance) |
| I-COMMAND-OBSERVABILITY-1 | INFO-level dedup log must be emitted (Phase 48) — Phase 49 makes it visible in CLI |
| I-SESSION-DEDUP-2 | Dedup policy: одна SessionDeclared per (type, phase_id) per day |
| I-SESSION-INVALIDATION-1 | После инвалидации — новая сессия разрешена |
| I-INVALID-4 | Cannot invalidate state-mutating events (preserved; now correctly scoped via `is_invalidatable()`) |

---

## 6. Pre/Post Conditions

### BC-49-A: logging.basicConfig

**Pre:**
- `src/sdd/cli.py` содержит `@click.group()` callback (cli function)

**Post:**
- `logging.basicConfig(level=logging.INFO)` вызван до dispatch любой подкоманды
- `_log.info(...)` messages в registry.py появляются в stderr

### BC-49-B: EventReducer.is_invalidatable()

**Pre:**
- `InvalidateEventHandler.handle()` содержит прямой доступ `target_type in EventReducer._EVENT_SCHEMA`
- `EventReducer` не имеет `_AUDIT_ONLY_EVENTS` и `is_invalidatable()`

**Post:**
- `EventReducer._AUDIT_ONLY_EVENTS = frozenset({"SessionDeclared"})` объявлена в классе
- `EventReducer.is_invalidatable(event_type)` возвращает `False` для state-mutating (non-audit-only schema events), `True` для остальных
- `InvalidateEventHandler.handle()` вызывает `EventReducer.is_invalidatable(target_type)` вместо прямого `_EVENT_SCHEMA` check
- `sdd invalidate-event --seq <SessionDeclared_seq>` → exit 0
- State-mutating события (напр. `PhaseInitialized`) → exit 1 (I-INVALID-4 preserved)

### BC-49-C: Pure handler

**Pre:**
- `RecordSessionHandler` содержит `_session_declared_today()` с IO в `handle()`
- `handle()` может вернуть `[]` даже если ядро решило "emit"

**Post:**
- `_session_declared_today()` удалён
- `handle()` не открывает DB соединений
- `handle()` всегда возвращает `[SessionDeclaredEvent(...)]`
- Dedup check производится исключительно ядром (Step 2.5)
- После invalidate SessionDeclared → повторный `sdd record-session` → новое событие создаётся
  (kernel Step 2.5 через `build_sessions_view()` не видит инвалидированную сессию)

---

## 7. Use Cases

### UC-49-1: CLI logging visibility

**Actor:** LLM / human
**Trigger:** `sdd record-session --type IMPLEMENT --phase 49` (повторный вызов)
**Pre:** BC-49-A реализован; первая сессия уже записана сегодня
**Steps:**
1. CLI выполняет `logging.basicConfig(level=INFO)` в callback
2. `execute_command` Step 2.5 вызывает `_log.info("Session deduplicated: type=IMPLEMENT phase=49")`
3. Сообщение попадает в stderr

**Post:** `sdd record-session ... 2>&1 | grep "Session deduplicated"` → exit 0

### UC-49-2: Invalidate SessionDeclared

**Actor:** LLM
**Trigger:** `sdd invalidate-event --seq <N> --reason "smoke test" --force`
**Pre:** BC-49-B реализован; seq N — это SessionDeclared событие
**Steps:**
1. `InvalidateEventHandler` вызывает `EventReducer.is_invalidatable("SessionDeclared")`
2. `"SessionDeclared" ∈ _AUDIT_ONLY_EVENTS` → `is_invalidatable()` → True → I-INVALID-4 check пропускает
3. `EventInvalidated` event записан в event_log

**Post:** exit 0; `EventInvalidated` с `target_seq=N` в event_log

### UC-49-3: Re-emit after invalidation

**Actor:** LLM
**Trigger:** `sdd record-session --type IMPLEMENT --phase 49` (после UC-49-2)
**Pre:** BC-49-B + BC-49-C реализованы; SessionDeclared seq N инвалидирован
**Steps:**
1. Pre-step: `_sync_p_sessions()` + `build_sessions_view()` — SQL фильтрует invalidated seqs
   via `WHERE seq NOT IN (SELECT DISTINCT target_seq FROM EventInvalidated)`;
   SessionsView не содержит записи для (IMPLEMENT, 49)
2. Step 2.5: `SessionDedupPolicy.should_emit(sessions_view, cmd)` → `get_last(IMPLEMENT, 49) is None` → True
3. Step 4: handler вызван → `handle()` — pure, без IO — возвращает `[SessionDeclaredEvent(...)]`
4. Step 5: event appended

**Post:** event_log содержит 2 `SessionDeclared` для (IMPLEMENT, 49) за сегодня

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-48 (SessionDedupPolicy) | read-only | Phase 49 не меняет политику dedup |
| BC-48 (execute_command Step 2.5) | read-only | Step 2.5 — единственный dedup authority после BC-49-C |
| projector.py `build_sessions_view()` | read-only | Уже фильтрует EventInvalidated; BC-49-C опирается на это |
| EventReducer._EVENT_SCHEMA | extend | BC-49-B добавляет `_AUDIT_ONLY_EVENTS` + `is_invalidatable()` |

### Reducer Extensions

Phase 49 не изменяет `_EVENT_SCHEMA`. Добавляются:
- `EventReducer._AUDIT_ONLY_EVENTS: ClassVar[frozenset[str]]` — новая классовая переменная
- `EventReducer.is_invalidatable(event_type: str) -> bool` — новый classmethod

`SessionDeclared` остаётся в `_EVENT_SCHEMA` (схемная валидация не меняется).

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_cli_basicconfig_called_before_subcommand` | I-CLI-LOG-LEVEL-1 |
| 2 | `test_cli_info_log_visible_in_stderr` | I-CLI-LOG-LEVEL-1 |
| 3 | `test_audit_only_events_in_reducer_contains_session_declared` | I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1 |
| 4 | `test_is_invalidatable_returns_true_for_session_declared` | I-INVALIDATABLE-INTERFACE-1, I-INVALID-AUDIT-ONLY-1 |
| 5 | `test_is_invalidatable_returns_false_for_state_mutating` | I-INVALID-4 (preserved), I-INVALIDATABLE-INTERFACE-1 |
| 6 | `test_is_invalidatable_returns_true_for_unknown_type` | I-INVALIDATABLE-INTERFACE-1 |
| 7 | `test_invalidate_session_declared_succeeds` | I-INVALID-AUDIT-ONLY-1 |
| 8 | `test_invalidate_state_mutating_still_blocked` | I-INVALID-4 (preserved) |
| 9 | `test_handler_handle_returns_event_without_io` | I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1 |
| 10 | `test_handler_handle_is_pure_no_db_call` | I-HANDLER-SESSION-PURE-1 |
| 11 | `test_reemit_after_invalidation_creates_new_event` | I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1 |
| Smoke | UC-49-1: grep "Session deduplicated" → exit 0 | I-CLI-LOG-LEVEL-1 |
| Smoke | UC-49-2: invalidate SessionDeclared → exit 0 | I-INVALID-AUDIT-ONLY-1 |
| Smoke | UC-49-3: re-emit after invalidate → 2 events | I-DEDUP-KERNEL-AUTHORITY-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Strong consistency для concurrent dedup (I-DEDUP-NOT-STRONG-1) | Future phase |
| Структурное расширение `_EVENT_SCHEMA` с полем `audit_only: bool` на каждую запись вместо отдельной ClassVar | Future phase (Phase 49 решает через `_AUDIT_ONLY_EVENTS` ClassVar + `is_invalidatable()`) |
| Расширение `_AUDIT_ONLY_EVENTS` другими типами | Future phase |
| Изменения в `SessionDedupPolicy`, `build_sessions_view`, `execute_command` Step 0/2.5 | Out of scope (Phase 48 stable) |
| Guard в Pre-step: если `spec.dedup_policy is not None` и `SDD_DATABASE_URL` не задан → raise | Future phase (после Phase 46 PG обязателен, но явного guard нет) |
