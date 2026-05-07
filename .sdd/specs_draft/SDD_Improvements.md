# SDD Process Improvements

> Proposals only — never auto-applied. Each requires DRAFT_SPEC → human approval cycle.

---

## IMP-001: Event–Reducer Consistency Contract

**Status:** PROPOSED  
**Source:** T-3208 scope deviation (2026-04-27)  
**Priority:** Шаг 1 — быстро; Шаг 2 — архитектурно

### Контекст

`EventReducer` содержит инвариант I-ST-10:

```
(_KNOWN_NO_HANDLER ∪ _EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
```

Этот инвариант гарантирует:
- каждое событие либо обрабатывается (`_EVENT_SCHEMA`), либо явно помечено как игнорируемое (`_KNOWN_NO_HANDLER`)
- отсутствуют "висящие" event types

### Проблема

Добавление нового события в `V1_L1_EVENT_TYPES` (в `events.py`) требует синхронного обновления `reducer.py`, но:

- связь **не декларативная** — нигде не выражена явно
- **не enforced на этапе планирования** — TaskSet не требует `reducer.py` в Outputs
- **не проверяется до import-time** — assert I-ST-10 срабатывает поздно, уже в тестах (TP-1 violation)

Это нарушение SSOT: событие объявляется в одном месте, его жизненный цикл — в другом, а связь между ними неявна.

### Правило (норматив)

Если Task добавляет новый event type в `V1_L1_EVENT_TYPES`:

**ТО Task MUST обновить reducer contract:**
1. Либо добавить handler → `_EVENT_SCHEMA`
2. Либо явно пометить → `_KNOWN_NO_HANDLER`

Добавление `reducer.py` в Outputs — **необходимо, но недостаточно**: LLM может включить файл и не обновить нужную структуру. Корректность гарантирует только проверка инварианта, а не checklist.

### Шаг 1 — Быстрый фикс (текущие фазы)

**1a. Правило в TaskSet-шаблоне:**

```
If Outputs include:
  src/sdd/core/events.py
AND task modifies V1_L1_EVENT_TYPES
THEN Outputs MUST include:
  src/sdd/domain/state/reducer.py
AND DoD MUST include:
  I-ST-10 holds after import
```

**1b. Machine-checkable проверка в DoD/validation:**

```python
def test_event_reducer_i_st_10():
    from sdd.domain.state.reducer import EventReducer
    from sdd.core.events import V1_L1_EVENT_TYPES

    classified = EventReducer._KNOWN_NO_HANDLER | frozenset(EventReducer._EVENT_SCHEMA.keys())
    assert classified == V1_L1_EVENT_TYPES
```

Этот тест уже фактически существует как import-time assert; его нужно вынести в явный `pytest` тест, чтобы ошибка была читаемой, а не stack trace при импорте.

### Шаг 2 — Архитектурный фикс (отдельная фаза, DRAFT_SPEC)

Убрать дублирование вообще: сделать `events.py` единственным SSOT.

```python
# events.py — единый реестр
EVENT_REGISTRY: dict[str, Callable | None] = {
    "TaskDefined":        None,            # no-handler
    "InvariantRegistered": None,           # no-handler
    "PhaseInitialized":   handle_phase_initialized,
    # ...
}

V1_L1_EVENT_TYPES: frozenset[str] = frozenset(EVENT_REGISTRY.keys())
```

Тогда `reducer._KNOWN_NO_HANDLER` и `reducer._EVENT_SCHEMA` становятся **производными** от `EVENT_REGISTRY`, а не независимыми дублями. I-ST-10 выполняется конструктивно, а не через assert.

**Требует:** DRAFT_SPEC → APPROVED_SPEC → отдельная фаза декомпозиции.  
**Риск:** breaking change для всех потребителей `_EVENT_SCHEMA` и `_KNOWN_NO_HANDLER`.
