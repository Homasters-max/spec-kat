# Spec_v35 — Phase 35: Test Harness Elevation

Status: Draft
Baseline: Spec_v34_EventLogDeepModule.md

---

## 0. Goal

Два точечных анти-паттерна в тестах поведения команд снижают устойчивость
тестовой базы при рефакторинге:

1. `patch.object(handler, "_check_idempotent", ...)` — патчит приватный метод
   хэндлера. Хрупок: любое переименование `_check_idempotent` ломает тест молча.
2. `conn.execute("SELECT event_type FROM events")` — читает строки таблицы напрямую
   вместо публичного EventLog-интерфейса. Хрупок: рефакторинг схемы таблицы
   ломает тесты поведения, не связанные с хранилищем.

Phase 35 устраняет оба паттерна в тестах поведения. Никаких изменений в `src/`.

**Источник:** grilling-сессия `/improve-codebase-architecture`, кандидат №5.

---

## 1. Scope

### In-Scope

- **BC-35-1**: Заменить `patch.object(handler, "_check_idempotent")` на
  `execute_sequence` double-call с одним `command_id` во всех тестах поведения
  команд.
- **BC-35-2**: Заменить `conn.execute("SELECT event_type FROM events")` на
  `EventLogQuerier(...).query(...)` или `get_current_state(db_path)` в
  `test_metrics.py` там, где это state assertion (не atomicity test).

### Out of Scope

- `test_db.py` — корректные unit-тесты DB-модуля через его собственный интерфейс;
  не трогать.
- `patch("subprocess.Popen")` — внешняя граница (процесс ОС); не трогать.
  Добавить комментарий `# subprocess boundary — intentional`.
- `_FailingConn` в `test_i_m_1_enforced` — патчит `commit()` для проверки
  атомарности транзакции, не для state inspection; не трогать.
  Добавить комментарий `# atomicity test — intentional internal patch`.
- `test_event_log_class.py`, `test_event_log.py` — тестируют EventLog-модуль
  через его собственный интерфейс; не трогать.
- Изменения в `src/` — запрещены в этой фазе.

---

## 2. Architecture / BCs

### BC-35-1: Idempotency Tests → execute_sequence Double-Call

**Файлы:**
- `tests/unit/commands/test_validate_invariants.py` — ~10 вхождений `patch.object(handler, "_check_idempotent")`
- `tests/unit/commands/test_validate_timeout.py` — 2 вхождения
- `tests/unit/commands/test_check_dod.py` — 6 вхождений

**Текущий паттерн (заменить):**
```python
with patch.object(handler, "_check_idempotent", return_value=False):
    result = handler.handle(cmd, state)
    # проверяем результат
```

**Новый паттерн:**
```python
# Используем один и тот же command_id в обоих вызовах
from tests.harness.api import execute_sequence

cmd_id = uuid4()
spec = REGISTRY["<command_name>"].spec   # из реестра, не конструировать вручную
cmd = SomeCommand(command_id=cmd_id, ...)

events1, _ = execute_sequence([(spec, cmd)], db_path=db_path)
assert len(events1) > 0   # первый вызов — событие создано

cmd2 = SomeCommand(command_id=cmd_id, ...)  # тот же command_id
events2, _ = execute_sequence([(spec, cmd2)], db_path=db_path)
assert events2 == []   # второй вызов — EventStore dedup, нет новых событий
```

**Важно (R-1):** `command_id` ДОЛЖЕН быть одинаковым в обоих вызовах.
Если передать разные `uuid4()` — idempotency-check не сработает (EventStore
дедупликация по `command_id`).

**Важно (R-3):** Если поиск `patch.object(handler, "_check_idempotent")` вернёт
более 5 файлов — остановиться и сообщить человеку перед продолжением.

**Leverage:** `tests/harness/api.py::execute_sequence` уже реализован. Тест
проверяет реальный механизм idempotency (EventStore dedup), а не внутренний
guard-метод хэндлера.

---

### BC-35-2: Direct SQL State Assertions → Public EventLog API

**Файлы:**
- `tests/unit/infra/test_metrics.py`:
  - `test_record_metric_batch_with_task_completed` — `conn.execute("SELECT event_type FROM events").fetchall()`
  - (другие вхождения с `open_sdd_connection + SELECT` для state assertion)

**Текущий паттерн (заменить):**
```python
conn = open_sdd_connection(db_path)
rows = conn.execute("SELECT event_type FROM events").fetchall()
assert ("TaskImplemented",) in rows
```

**Новый паттерн (предпочтительный):**
```python
from sdd.infra.event_log import EventLogQuerier

querier = EventLogQuerier(db_path)
events = querier.query()
assert any(e.event_type == "TaskImplemented" for e in events)
```

**Или (альтернативный):**
```python
from sdd.infra.projections import get_current_state

state = get_current_state(db_path)
# проверить через state-поля
```

**Замечание по R-2 (`test_i_m_1_enforced`):** Вхождение `_FailingConn` в этом
тесте — проверка атомарности транзакции, не state inspection. Оставить как есть.
Добавить комментарий:
```python
# atomicity test — intentional internal patch
```

**Риск (R-2):** Если `get_current_state` не включает нужное поле — использовать
`EventLogQuerier` вместо `get_current_state`. Проверить заранее какие поля
доступны в `SDDState`.

---

## 3. Domain Events

Phase 35 не эмитирует новых domain events.
`SessionDeclared` (I-SESSION-DECLARED-1) эмитируется в начале сессии штатно.

---

## 4. Types & Interfaces

Нет изменений в `src/`. Только тесты.

**Используемые публичные API:**

| API | Модуль | Назначение |
|-----|--------|------------|
| `execute_sequence(cmds, db_path)` | `tests/harness/api.py` | Double-call idempotency test |
| `REGISTRY["<name>"].spec` | `sdd.commands.registry` | Получить CommandSpec без ручного конструирования |
| `EventLogQuerier(db_path).query()` | `sdd.infra.event_log` | Публичный запрос событий |
| `get_current_state(db_path)` | `sdd.infra.projections` | Текущее состояние через проекцию |

---

## 5. Invariants

### New Invariants — Phase 35

| ID | Statement |
|----|-----------|
| I-TEST-IDEM-1 | Idempotency tests MUST use `execute_sequence` double-call with same `command_id`, NOT `patch.object(handler, "_check_idempotent")`. |
| I-TEST-STATE-1 | State assertions in behavior tests MUST use `EventLogQuerier` or `get_current_state`, NOT raw `conn.execute("SELECT ... FROM events")`. |
| I-TEST-BOUNDARY-1 | `patch("subprocess.Popen")` is the only acceptable internal patch for external OS process boundary. Document with `# subprocess boundary — intentional`. |

### Acceptance Criteria для BC-35-1

`grep -rn 'patch.object.*_check_idempotent' tests/unit/commands/` → пусто.
`grep -rn 'execute_sequence' tests/unit/commands/test_validate_invariants.py` → непусто.

### Acceptance Criteria для BC-35-2

`grep -n 'conn.execute.*SELECT.*event_type.*FROM.*events' tests/unit/infra/test_metrics.py` → пусто (в context state assertions).
`grep -n 'EventLogQuerier\|get_current_state' tests/unit/infra/test_metrics.py` → непусто.

---

## 6. Pre/Post Conditions

### Pre

- Phase 34 COMPLETE (EventLog deep module API доступен)
- Phase 33 COMPLETE (CommandSpec guard factory; `_check_idempotent` в финальном состоянии)
- `tests/harness/api.py::execute_sequence` работает корректно
- `REGISTRY` содержит CommandSpec для всех затрагиваемых команд

### Post

- Ни один файл в `src/` не изменён
- `git diff src/` → пусто
- Все `patch.object(handler, "_check_idempotent")` в тестах поведения команд устранены
- Все state assertions в `test_metrics.py` используют публичный API
- Тесты проходят (pytest зелёный)

---

## 7. Use Cases

### UC-35-1: Переименование _check_idempotent не ломает тесты

**Actor:** Developer
**Trigger:** Рефакторинг `_check_idempotent` в src/ (переименование, изменение сигнатуры)
**Pre:** Phase 35 COMPLETE
**Steps:**
1. Разработчик переименовывает `_check_idempotent` → `_is_duplicate`
2. `pytest tests/unit/commands/` — все idempotency-тесты проходят
3. Нет `AttributeError` из `patch.object`
**Post:** Тесты поведения не зависят от приватных имён хэндлеров

### UC-35-2: Рефакторинг схемы events не ломает test_metrics

**Actor:** Developer
**Trigger:** Phase 36 (PostgresMigration) изменяет схему EventLog
**Pre:** Phase 35 COMPLETE
**Steps:**
1. EventLog мигрирует на Postgres (Phase 36)
2. `pytest tests/unit/infra/test_metrics.py` — тесты проходят
3. Нет сломанных `conn.execute("SELECT event_type FROM events")`
**Post:** Тесты метрик изолированы от деталей хранилища

---

## 8. Integration

### Dependencies

| BC | Direction | Purpose |
|----|-----------|---------|
| Spec_v33 BC-33-FACTORY | upstream | CommandSpecGuardFactory — `_check_idempotent` в финальном виде |
| Spec_v34 §4 EventLog Public Interface | upstream | `EventLogQuerier` API доступен |
| `tests/harness/api.py` | uses | `execute_sequence` double-call |
| `sdd.commands.registry.REGISTRY` | uses | CommandSpec из реестра |

### Downstream (что разблокирует Phase 35)

Тесты становятся устойчивы к рефакторингу схемы EventLog (Phase 36, 32).

---

## 9. Verification

| # | Проверка | BC |
|---|----------|----|
| 1 | `grep -rn 'patch.object.*_check_idempotent' tests/unit/commands/` → пусто | BC-35-1 |
| 2 | `grep -rn 'execute_sequence' tests/unit/commands/test_validate_invariants.py` → непусто | BC-35-1 |
| 3 | `grep -rn 'execute_sequence' tests/unit/commands/test_check_dod.py` → непусто | BC-35-1 |
| 4 | `grep -rn 'execute_sequence' tests/unit/commands/test_validate_timeout.py` → непусто | BC-35-1 |
| 5 | `grep -n 'conn.execute.*SELECT.*event_type' tests/unit/infra/test_metrics.py` → пусто | BC-35-2 |
| 6 | `grep -n 'EventLogQuerier\|get_current_state' tests/unit/infra/test_metrics.py` → непусто | BC-35-2 |
| 7 | `grep -rn 'atomicity test.*intentional' tests/` → непусто | BC-35-2 exception |
| 8 | `pytest tests/unit/commands/ tests/unit/infra/test_metrics.py -v` → all green | all BCs |
| 9 | `git diff src/` → пусто | all BCs |

---

## 10. Out of Scope

| Item | Phase |
|------|-------|
| `test_event_log_class.py`, `test_event_log.py` SQL — корректные тесты модуля | не менять |
| `patch("subprocess.Popen")` — внешняя граница | не менять |
| `_FailingConn` atomicity test | не менять |
| Изменения в `src/` | запрещены |
| Новые тестовые утилиты в `tests/harness/` | Phase 36+ |
