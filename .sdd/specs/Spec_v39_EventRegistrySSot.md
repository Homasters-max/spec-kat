# Spec_v39 — Phase 39: Event–Reducer Consistency (SSOT Fix)

Status: Draft
Baseline: Spec_v35_TestHarnessElevation.md

---

## 0. Goal

Устранить структурный SSOT-дефект: добавление нового no-handler события в
`V1_L1_EVENT_TYPES` требует синхронного обновления `EventReducer._KNOWN_NO_HANDLER`
в `reducer.py`, но эта зависимость нигде не объявлена явно.

**Корень проблемы:** `_KNOWN_NO_HANDLER` в `EventReducer` — статический frozenset-литерал,
дублирующий классификацию событий из `V1_L1_EVENT_TYPES`. Два независимых списка
об одном множестве — SSOT-нарушение.

**Решение:** `_KNOWN_NO_HANDLER` становится derived expression:

    _KNOWN_NO_HANDLER = V1_L1_EVENT_TYPES - frozenset(_EVENT_SCHEMA.keys())

Никаких новых модулей, никаких новых структур данных. Минимальный diff.

**Принцип:** `events.py` — SSOT для списка типов. `reducer.py` — SSOT для handler-логики
(в `_EVENT_SCHEMA` и `_fold()`). `_KNOWN_NO_HANDLER` — производная величина, не третий список.

---

## 1. Scope

### In-Scope

- **BC-39-2**: рефакторинг `reducer.py` — `_KNOWN_NO_HANDLER` становится derived
  expression вместо статического литерала; промежуточная переменная `_HANDLER_EVENTS`
  для читаемости
- **BC-39-3**: явный pytest-тест на I-ST-10 и I-EREG-1 вместо import-time assert
- **BC-39-4**: правило в TaskSet-шаблоне для event-addition задач

### Out of Scope

- Создание `event_registry.py` — не нужно (инфраструктура уже в `events.py`)
- Создание `handlers.py` — не нужно (handlers остаются inline в `_fold()`)
- Изменение типа `_EVENT_SCHEMA` (остаётся `dict[str, frozenset[str]]`)
- Изменение `_fold()` логики
- Изменение `events.py` структуры
- Добавление новых event types (не Phase 39)
- Замена DuckDB на PostgreSQL (Phase 32)

---

## 2. Architecture / BCs

### BC-39-2: Рефакторинг reducer.py

Файл: `src/sdd/domain/state/reducer.py`

**БЫЛО:**
```python
class EventReducer:
    _KNOWN_NO_HANDLER: frozenset[str] = frozenset({   # статический литерал
        "StateDerivationCompleted",
        "DecisionRecorded", "SpecApproved", ...        # ~15 типов — дубль events.py
    })
    _EVENT_SCHEMA: ClassVar[dict[str, frozenset[str]]] = {
        "PhaseInitialized": frozenset({...}), ...
    }
    assert _KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES, (...)
```

**СТАЛО:**
```python
class EventReducer:
    _EVENT_SCHEMA: ClassVar[dict[str, frozenset[str]]] = {   # объявляется первым
        "PhaseInitialized": frozenset({...}), ...             # без изменений
    }
    # I-EREG-1: derived — не хранится отдельно от V1_L1_EVENT_TYPES.
    # Добавление no-handler события: только events.py. reducer.py не нужен.
    _HANDLER_EVENTS: ClassVar[frozenset[str]] = frozenset(_EVENT_SCHEMA)
    _KNOWN_NO_HANDLER: frozenset[str] = V1_L1_EVENT_TYPES - _HANDLER_EVENTS
    # import-time assert удалён: тавтология по построению; см. test_event_registry_consistency.py
```

**Побочный эффект (осознанный):** любой тип из `V1_L1_EVENT_TYPES`, не добавленный
в `_EVENT_SCHEMA`, автоматически считается no-handler. Поведение корректно по текущей модели.

**Порядок объявления обязателен:** `_EVENT_SCHEMA` → `_HANDLER_EVENTS` → `_KNOWN_NO_HANDLER`.

**Публичный API `reducer.py` не меняется.** `_KNOWN_NO_HANDLER` и `_EVENT_SCHEMA`
доступны потребителям с теми же типами и содержимым.

---

### BC-39-3: Явный pytest-тест на I-ST-10 / I-EREG-1

Новый файл: `tests/unit/core/test_event_registry_consistency.py`

```python
"""I-ST-10 / I-EREG-1: EventReducer._KNOWN_NO_HANDLER is derived, not duplicated.

Spec_v39 BC-39-3.
"""
from sdd.core.events import V1_L1_EVENT_TYPES
from sdd.domain.state.reducer import EventReducer


def test_i_st_10_all_event_types_classified():
    """I-ST-10: V1_L1_EVENT_TYPES == _KNOWN_NO_HANDLER ∪ _EVENT_SCHEMA.keys()."""
    classified = EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys())
    missing = V1_L1_EVENT_TYPES - classified
    extra = classified - V1_L1_EVENT_TYPES
    assert not missing, f"Events in V1_L1_EVENT_TYPES but not classified: {missing}"
    assert not extra, f"Events classified but not in V1_L1_EVENT_TYPES: {extra}"


def test_i_ereg_1_known_no_handler_is_derived():
    """I-EREG-1: _KNOWN_NO_HANDLER MUST equal V1_L1_EVENT_TYPES - _EVENT_SCHEMA.keys().

    Verifies the derived relationship — no independent static literal.
    """
    expected = V1_L1_EVENT_TYPES - frozenset(EventReducer._EVENT_SCHEMA.keys())
    assert EventReducer._KNOWN_NO_HANDLER == expected, (
        f"_KNOWN_NO_HANDLER is not derived from V1_L1_EVENT_TYPES - _EVENT_SCHEMA.keys(). "
        f"Diff: {EventReducer._KNOWN_NO_HANDLER.symmetric_difference(expected)}"
    )
```

**Почему явный тест важнее assert:**
- `assert` → нечитаемый stack trace при импорте, нет диагностики
- `test` → конкретное сообщение: "Events not classified: {'NewEvent'}"

---

### BC-39-4: Правило в TaskSet-шаблоне

Файл: `.sdd/templates/TaskSet_template.md` — добавить секцию:

```markdown
### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий.
Это основной эффект Spec_v39.
```

---

## 3. Domain Events

Phase 39 не добавляет новых domain events. Чисто структурный рефакторинг.

---

## 4. Invariants

### Новые инварианты

| ID | Statement |
|----|-----------|
| I-EREG-1 | `EventReducer._KNOWN_NO_HANDLER` MUST equal `V1_L1_EVENT_TYPES - frozenset(_EVENT_SCHEMA.keys())`. Derived expression, не независимый литерал. |
| I-EREG-SCOPE-1 | Task, добавляющая event type в `V1_L1_EVENT_TYPES`, MUST обновить `events.py`; MUST обновить `_EVENT_SCHEMA` + `_fold()` только если тип имеет handler; `reducer.py` не нужен для no-handler типа. |

### Сохранённые инварианты

| ID | Статус |
|----|--------|
| I-ST-10 | Сохранён. Теперь выполняется конструктивно по построению + явным тестом (BC-39-3). |
| I-HANDLER-PURE-1 | Сохранён. `_fold()` не трогается. |
| I-1 | Сохранён. Reducer не мутирует состояние через классификацию. |

---

## 5. Pre/Post Conditions

### Добавление нового event type (post Phase 39)

**До Phase 39 (дефектный workflow):**
1. Добавить в `V1_L1_EVENT_TYPES` — `events.py`
2. Добавить в `_KNOWN_NO_HANDLER` — `reducer.py` (скрытая зависимость, нигде не объявлена)
3. Надеяться, что import-time assert поймает пропуск

**После Phase 39:**

| Тип события | Файлы |
|-------------|-------|
| no-handler | `events.py` (V1_L1_EVENT_TYPES) — только один файл |
| has-handler | `events.py` + `reducer.py` (_EVENT_SCHEMA + _fold()) |

`test_i_st_10_all_event_types_classified` → PASS гарантирует консистентность.

---

## 6. Integration

| Модуль | Направление зависимости | Изменение |
|--------|------------------------|-----------|
| `events.py` | — | Без изменений |
| `reducer.py` | imports: events (V1_L1_EVENT_TYPES) | Порядок ClassVar + derived _KNOWN_NO_HANDLER |
| `test_event_registry_consistency.py` | imports: events, reducer | Новый файл |
| `TaskSet_template.md` | — | Новая секция Event-Addition Rule |

---

## 7. Trade-offs & Risks

### Порядок инициализации ClassVar

`_EVENT_SCHEMA` должен быть объявлен до `_HANDLER_EVENTS` и `_KNOWN_NO_HANDLER`.
В исходном коде порядок обратный — это единственное структурное изменение в классе.

### Обратная совместимость

`EventReducer._KNOWN_NO_HANDLER` и `_EVENT_SCHEMA` — ClassVar, доступные извне.
Их тип (`frozenset[str]` / `dict[str, frozenset[str]]`) и содержимое не меняются.
Потребители (тесты, guards) продолжают работать без изменений.

### Автоматическая классификация

Новый тип, добавленный только в `V1_L1_EVENT_TYPES` без записи в `_EVENT_SCHEMA`,
автоматически попадает в `_KNOWN_NO_HANDLER`. Это корректно и явно документировано.

---

## 8. Verification

| # | Проверка | BC |
|---|----------|----|
| 1 | `python3 -c "from sdd.domain.state.reducer import EventReducer"` → OK | BC-39-2 |
| 2 | `test_i_st_10_all_event_types_classified` PASS | BC-39-3 |
| 3 | `test_i_ereg_1_known_no_handler_is_derived` PASS | BC-39-2, BC-39-3 |
| 4 | Добавление нового no-handler типа только в `events.py` → тест PASS, `reducer.py` не трогается | BC-39-2 |
| 5 | Все существующие тесты PASS (1012+) | TP-1 |
| 6 | `sdd show-state` работает (replay не нарушен) | TP-1 |

