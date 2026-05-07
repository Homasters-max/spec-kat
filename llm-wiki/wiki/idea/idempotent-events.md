---
id: idea/idempotent-events
page_type: idea
domain: sdd
layer: architecture
tags:
- dedup
- write-path
- ssot
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Idempotent Events

Идемпотентность в SDD обеспечивается двумя слоями — EventStore и ReplayEngine. Reducer не несёт ответственности за dedup: State не содержит `seen_ids`, domain-логика не зависит от дедупликации.

## How It Works

**Два слоя dedup:**

| Слой | Когда | Назначение |
|------|-------|-----------|
| EventStore (write-time) | При append | Обязательный: dedup по `event_id` |
| ReplayEngine (read-time) | При replay | Defensive: фильтрует дубликаты перед Reducer |

**Reducer — pure, без dedup:**

```python
def reduce(state: State, event: Event) -> State:
    """
    Pure:          no DB, no network, no datetime.now()
    Total:         unknown event type → return state unchanged (not raise)
    Deterministic: identical (state, event) → identical result
    """
```

Reducer не знает про `event_id`. Следствие:

```text
I-IDEM-EVENT-1: reduce(events + duplicate_events) == reduce(events)
                (гарантируется EventStore dedup + ReplayEngine filter, не Reducer)
```

**Детерминированный event_id:**

```python
event_id = uuid5(NAMESPACE_SDD, f"{command_id}:{position}")
# position = индекс события в batch от данной команды (0, 1, 2…)
```

Свойства:
- Уникален в пределах команды даже при нескольких событиях одного типа
- Детерминирован: retry команды → те же `event_id` → безопасный dedup в EventStore
- `event_type` исключён из ключа (коллизий нет при уникальном `position`)

```text
I-IDEM-EVENT-3: event_id детерминирован из (command_id, position) → I-EVENTLOG-4
```

**Удалённые подходы (признаны неверными):**

| Инвариант | Причина отказа |
|-----------|---------------|
| `reduce(reduce(s,e),e)==reduce(s,e)` | Требует `seen_ids` в State — нарушает чистоту Reducer |
| `Reducer MUST skip seen event_id` | Та же причина: вносит побочный эффект в pure function |

## When To Use

Идемпотентность event_id важна при:
- Retry команды после `OptimisticConcurrencyError`
- Сетевых сбоях (команда отправлена дважды)
- Восстановлении из частичного состояния EventLog

## Trade-offs

- Dedup в EventStore требует уникального индекса по `event_id` в PostgreSQL
- ReplayEngine defensive filter — небольшой overhead при replay
- Reducer остаётся простым: нет `seen_ids` Set в State

## See Also

- [[cqrs-boundary]]
- [[event-sourcing]]
- [[write-kernel]]
- [[replay-based-testing]]
